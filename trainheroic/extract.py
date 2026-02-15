"""
TrainHeroic Screenshot → Structured Data Extraction.
Uses Gemini Vision API to extract workout details from TrainHeroic app screenshots
stored in Google Drive. Generates JSON data and monthly summary docs for NotebookLM.
"""
import argparse
import calendar
import io
import json
import logging
import os
import re
import sys
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

from dotenv import load_dotenv

# Resolve paths relative to toolbox root
TOOLBOX_ROOT = Path(__file__).resolve().parent.parent
CONFIG_DIR = TOOLBOX_ROOT / "config"
SECRETS_ENV_PATH = CONFIG_DIR / "secrets.env"
FOLDER_CONFIG_PATH = CONFIG_DIR / "folder_config.json"

# Drive folder path under Health
DRIVE_SUBFOLDER_PATH = "Fitness/Trainheroic"
TRAINHEROIC_FOLDER_ID = "13NQj-cVU9-tf9wXBTlQbHEDl1ywGT7G5"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("TrainHeroicExtract")

EXTRACTION_PROMPT = """Analyze this TrainHeroic workout screenshot and extract all workout data into JSON.

Return ONLY valid JSON with this exact structure (no markdown fencing):
{
  "session": "Week X Day Y",
  "coach": "Coach name",
  "date_moved": "YYYY-MM-DD or null if not visible",
  "metrics": {
    "blocks_completed": number or null,
    "blocks_total": number or null,
    "duration_minutes": number or null,
    "intensity_rating": number or null,
    "intensity_max": 10,
    "total_volume_lbs": number or null
  },
  "exercises": [
    {
      "block": "A1",
      "name": "Exercise Name",
      "category": "STRENGTH/POWER or CONDITIONING or WARMUP or other visible category",
      "sets": number,
      "reps": number or null,
      "weight_lbs": number or null,
      "duration_seconds": number or null,
      "tempo": "string or null",
      "notes": "any user notes or null"
    }
  ],
  "coach_instructions": "any coach notes/instructions text or null",
  "session_comment": "any session-level user comment or null"
}

Rules:
- Extract ALL exercises visible in the screenshot
- For duration-based exercises (like "3 x 00:20"), convert to seconds in duration_seconds field
- Keep the block labels (A1, A2, B1, etc.) exactly as shown
- If a field is not visible, use null
- For weight, use the number only (no "lb" suffix)
- If this screenshot is a continuation/scroll of a session, still extract all visible exercises
- Return ONLY the JSON, no other text"""


def load_config():
    """Load API keys from secrets.env or environment."""
    if SECRETS_ENV_PATH.exists():
        load_dotenv(SECRETS_ENV_PATH)

    gemini_key = os.getenv("GEMINI_API_KEY")
    if not gemini_key:
        logger.error(
            "GEMINI_API_KEY must be set in %s or environment. "
            "Get one free at https://aistudio.google.com/apikey",
            SECRETS_ENV_PATH,
        )
        sys.exit(1)

    return gemini_key


def get_drive_service():
    """Get an authenticated Google Drive service using existing toolbox credentials."""
    for p in [str(TOOLBOX_ROOT), str(TOOLBOX_ROOT.parent)]:
        if p not in sys.path:
            sys.path.insert(0, p)

    from lib.google_api import GoogleAuth

    auth = GoogleAuth(base_dir=str(TOOLBOX_ROOT))
    creds = auth.get_credentials(
        token_filename="token_full_drive.json",
        credentials_filename="config/credentials.json",
    )
    return auth.get_service("drive", "v3", creds)


def load_health_folder_id():
    """Load the Health folder ID from folder_config.json."""
    with open(FOLDER_CONFIG_PATH) as f:
        config = json.load(f)
    health_id = config.get("mappings", {}).get("Health", {}).get("id")
    if not health_id:
        logger.error("Health folder ID not found in folder_config.json")
        sys.exit(1)
    return health_id


def get_or_create_drive_folder(service, subfolder_path, parent_id):
    """Create nested subfolders under an existing parent. Returns folder ID."""
    for folder_name in subfolder_path.split("/"):
        query = (
            f"name='{folder_name}' and mimeType='application/vnd.google-apps.folder' "
            f"and '{parent_id}' in parents and trashed=false"
        )
        results = service.files().list(q=query, fields="files(id, name)").execute()
        files = results.get("files", [])

        if files:
            parent_id = files[0]["id"]
        else:
            metadata = {
                "name": folder_name,
                "mimeType": "application/vnd.google-apps.folder",
                "parents": [parent_id],
            }
            folder = service.files().create(body=metadata, fields="id").execute()
            parent_id = folder["id"]
            logger.info("Created Drive folder: %s", folder_name)

    return parent_id


def sanitize_filename(name):
    """Sanitize a string for safe use in filenames."""
    name = re.sub(r"[^\w\s-]", "", name)
    name = re.sub(r"\s+", "_", name.strip())
    return name


def date_from_screenshot_name(screenshot_name):
    """Extract a date from a screenshot filename like Screenshot_20260214-110843.png."""
    m = re.search(r"Screenshot_(\d{4})(\d{2})(\d{2})", screenshot_name or "")
    if m:
        return f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
    return None


def build_descriptive_name(data, screenshot_name=None):
    """Build a descriptive base name from extracted session data.

    Falls back to screenshot timestamp if date_moved is null.
    Examples: 2026-02-20_Week1_Day5, 2026-02-18_Week2_Day1
    """
    date = data.get("date_moved")
    if not date and screenshot_name:
        date = date_from_screenshot_name(screenshot_name)
    if not date:
        date = "unknown-date"

    session = data.get("session", "Unknown")
    # Compact: "Week 1 Day 5" → "Week1_Day5"
    session_clean = re.sub(r"Week\s*(\d+)", r"Week\1", session)
    session_clean = re.sub(r"Day\s*(\d+)", r"Day\1", session_clean)
    session_clean = sanitize_filename(session_clean)
    return f"{date}_{session_clean}"


def list_screenshots(drive_service, folder_ids):
    """List all PNG image files across multiple folder IDs."""
    results = []
    for fid in folder_ids:
        query = (
            f"'{fid}' in parents and trashed=false "
            f"and mimeType='image/png'"
        )
        page_token = None
        while True:
            response = drive_service.files().list(
                q=query,
                fields="nextPageToken, files(id, name, createdTime, parents)",
                pageSize=100,
                pageToken=page_token,
            ).execute()
            for f in response.get("files", []):
                f["_parent_id"] = fid
            results.extend(response.get("files", []))
            page_token = response.get("nextPageToken")
            if not page_token:
                break

    results.sort(key=lambda f: f["name"])
    return results


def list_existing_jsons(drive_service, folder_ids):
    """List existing extracted JSON files across multiple folder IDs."""
    results = []
    for fid in folder_ids:
        query = (
            f"'{fid}' in parents and trashed=false "
            f"and mimeType='application/json'"
        )
        page_token = None
        while True:
            response = drive_service.files().list(
                q=query,
                fields="nextPageToken, files(id, name, parents)",
                pageSize=100,
                pageToken=page_token,
            ).execute()
            for f in response.get("files", []):
                f["_parent_id"] = fid
            results.extend(response.get("files", []))
            page_token = response.get("nextPageToken")
            if not page_token:
                break

    return results


def list_subfolders(drive_service, parent_id):
    """List all subfolders under a parent folder."""
    query = (
        f"'{parent_id}' in parents and trashed=false "
        f"and mimeType='application/vnd.google-apps.folder'"
    )
    results = []
    page_token = None
    while True:
        response = drive_service.files().list(
            q=query,
            fields="nextPageToken, files(id, name)",
            pageSize=100,
            pageToken=page_token,
        ).execute()
        results.extend(response.get("files", []))
        page_token = response.get("nextPageToken")
        if not page_token:
            break
    return results


def get_all_data_folder_ids(drive_service, root_folder_id):
    """Get the root folder + all year/month subfolders for scanning."""
    folder_ids = [root_folder_id]
    year_folders = list_subfolders(drive_service, root_folder_id)
    for yf in year_folders:
        folder_ids.append(yf["id"])
        month_folders = list_subfolders(drive_service, yf["id"])
        for mf in month_folders:
            folder_ids.append(mf["id"])
    return folder_ids


def download_image(drive_service, file_id):
    """Download an image file from Drive as bytes."""
    request = drive_service.files().get_media(fileId=file_id)
    content = io.BytesIO()
    from googleapiclient.http import MediaIoBaseDownload
    downloader = MediaIoBaseDownload(content, request)
    done = False
    while not done:
        _, done = downloader.next_chunk()
    return content.getvalue()


def extract_with_gemini(image_bytes, api_key, filename="screenshot.png"):
    """Send image to Gemini Vision and extract structured workout data."""
    import google.generativeai as genai

    genai.configure(api_key=api_key)
    model = genai.GenerativeModel("gemini-2.0-flash")

    response = model.generate_content(
        [
            EXTRACTION_PROMPT,
            {"mime_type": "image/png", "data": image_bytes},
        ],
        generation_config=genai.GenerationConfig(
            temperature=0.1,
            response_mime_type="application/json",
        ),
    )

    try:
        # Parse the JSON response
        text = response.text.strip()
        # Strip markdown fencing if present
        if text.startswith("```"):
            text = re.sub(r"^```\w*\n?", "", text)
            text = re.sub(r"\n?```$", "", text)
        data = json.loads(text)
        logger.debug("Successfully extracted data from %s", filename)
        return data
    except (json.JSONDecodeError, ValueError) as e:
        logger.warning("Failed to parse Gemini response for %s: %s", filename, e)
        logger.debug("Raw response: %s", response.text[:500])
        return None


def upload_json(drive_service, folder_id, filename, data):
    """Upload extracted JSON to Drive. Returns file ID."""
    from googleapiclient.http import MediaFileUpload

    # Check if already exists
    query = f"name='{filename}' and '{folder_id}' in parents and trashed=false"
    existing = drive_service.files().list(q=query, fields="files(id)").execute().get("files", [])

    with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".json", encoding="utf-8") as tmp:
        json.dump(data, tmp, indent=2, default=str)
        tmp_path = tmp.name

    try:
        media = MediaFileUpload(tmp_path, mimetype="application/json", resumable=True)

        if existing:
            drive_service.files().update(fileId=existing[0]["id"], media_body=media).execute()
            logger.info("Updated JSON: %s", filename)
            return existing[0]["id"]
        else:
            metadata = {"name": filename, "parents": [folder_id]}
            result = drive_service.files().create(body=metadata, media_body=media, fields="id").execute()
            logger.info("Uploaded JSON: %s", filename)
            return result["id"]
    finally:
        os.unlink(tmp_path)


def get_processed_screenshot_ids(drive_service, root_folder_id):
    """Scan existing JSONs across all subfolders to find which screenshots have been processed."""
    all_folder_ids = get_all_data_folder_ids(drive_service, root_folder_id)
    json_files = list_existing_jsons(drive_service, all_folder_ids)
    processed = {}  # screenshot_name → json file info

    for jf in json_files:
        try:
            content = drive_service.files().get_media(fileId=jf["id"]).execute()
            data = json.loads(content)
            source_ss = data.get("_source", {}).get("screenshot")
            if source_ss:
                processed[source_ss] = {"id": jf["id"], "name": jf["name"], "data": data}
        except (json.JSONDecodeError, Exception):
            continue

    return processed


def rename_drive_file(drive_service, file_id, new_name):
    """Rename a file on Google Drive."""
    drive_service.files().update(fileId=file_id, body={"name": new_name}).execute()
    logger.info("Renamed → %s", new_name)


def move_file_to_folder(drive_service, file_id, current_parent_id, target_folder_id):
    """Move a file from one folder to another on Google Drive."""
    drive_service.files().update(
        fileId=file_id,
        addParents=target_folder_id,
        removeParents=current_parent_id,
        fields="id, parents",
    ).execute()


def get_month_folder_id(drive_service, root_folder_id, date_str):
    """Get or create the {YYYY}/{MM} subfolder under root for a given date string.

    Args:
        date_str: Date in YYYY-MM-DD format, or screenshot name to parse.
    Returns:
        folder ID for the month subfolder.
    """
    if not date_str or date_str == "unknown-date":
        return root_folder_id  # Can't determine month, stay in root

    try:
        dt = datetime.strptime(date_str[:10], "%Y-%m-%d")
    except ValueError:
        return root_folder_id

    year = dt.strftime("%Y")
    month = dt.strftime("%m")
    health_folder_id = load_health_folder_id()
    return get_or_create_drive_folder(
        drive_service, f"{DRIVE_SUBFOLDER_PATH}/{year}/{month}", health_folder_id
    )


def extract_screenshots(drive_service, api_key, root_folder_id, dry_run=False, force=False):
    """Process all screenshots, extracting workout data to month subfolders."""
    all_folder_ids = get_all_data_folder_ids(drive_service, root_folder_id)
    screenshots = list_screenshots(drive_service, all_folder_ids)
    logger.info("Found %d screenshots in TrainHeroic folders", len(screenshots))

    if not screenshots:
        return []

    # Check which ones are already processed (by source screenshot name)
    if force:
        processed = {}
    else:
        processed = get_processed_screenshot_ids(drive_service, root_folder_id)

    all_extracted = []

    for ss in screenshots:
        if ss["name"] in processed:
            logger.debug("Skipping already processed: %s", ss["name"])
            continue

        logger.info("Processing: %s", ss["name"])

        if dry_run:
            logger.info("[DRY RUN] Would extract: %s", ss["name"])
            continue

        # Download image
        image_bytes = download_image(drive_service, ss["id"])
        logger.debug("Downloaded %s (%d bytes)", ss["name"], len(image_bytes))

        # Extract with Gemini
        data = extract_with_gemini(image_bytes, api_key, ss["name"])
        if not data:
            logger.warning("Skipping %s — extraction failed", ss["name"])
            continue

        # Add source metadata
        data["_source"] = {
            "screenshot": ss["name"],
            "drive_file_id": ss["id"],
            "extracted_at": datetime.now().isoformat(),
        }

        # Build descriptive filename
        source_ss_name = data.get("_source", {}).get("screenshot", ss["name"])
        base_name = build_descriptive_name(data, source_ss_name)
        json_name = f"{base_name}.json"

        # Determine month folder for output
        date_for_folder = data.get("date_moved") or date_from_screenshot_name(ss["name"])
        month_folder_id = get_month_folder_id(drive_service, root_folder_id, date_for_folder)

        # Upload JSON to month subfolder
        upload_json(drive_service, month_folder_id, json_name, data)

        # Move screenshot to month subfolder and rename
        new_ss_name = f"{base_name}.png"
        current_parent = ss.get("_parent_id", root_folder_id)
        if current_parent != month_folder_id:
            move_file_to_folder(drive_service, ss["id"], current_parent, month_folder_id)
            logger.info("Moved screenshot to month folder")
        if ss["name"] != new_ss_name:
            rename_drive_file(drive_service, ss["id"], new_ss_name)

        all_extracted.append(data)

    logger.info("Extracted %d new sessions", len(all_extracted))
    return all_extracted


def reorganize_files(drive_service, root_folder_id, dry_run=False):
    """Move existing files from the flat root folder into year/month subfolders."""
    all_folder_ids = get_all_data_folder_ids(drive_service, root_folder_id)
    json_files = list_existing_jsons(drive_service, all_folder_ids)
    logger.info("Found %d JSON files to check for reorganization", len(json_files))

    moved_count = 0
    for jf in json_files:
        try:
            content = drive_service.files().get_media(fileId=jf["id"]).execute()
            data = json.loads(content)
        except (json.JSONDecodeError, Exception):
            logger.warning("Could not parse %s, skipping", jf["name"])
            continue

        # Determine target month folder
        source_ss_name = data.get("_source", {}).get("screenshot", "")
        date_str = data.get("date_moved") or date_from_screenshot_name(source_ss_name)
        if not date_str or date_str == "unknown-date":
            logger.debug("Skipping %s — no date to determine month", jf["name"])
            continue

        month_folder_id = get_month_folder_id(drive_service, root_folder_id, date_str)
        current_parent = jf.get("_parent_id", root_folder_id)

        if current_parent == month_folder_id:
            continue  # Already in correct folder

        if dry_run:
            try:
                dt = datetime.strptime(date_str[:10], "%Y-%m-%d")
                target_path = f"{dt.strftime('%Y')}/{dt.strftime('%m')}"
            except ValueError:
                target_path = "unknown"
            logger.info("[DRY RUN] %s → %s/", jf["name"], target_path)
        else:
            move_file_to_folder(drive_service, jf["id"], current_parent, month_folder_id)
            logger.info("Moved %s to month folder", jf["name"])

            # Also move the source screenshot if it exists
            source_ss_id = data.get("_source", {}).get("drive_file_id")
            if source_ss_id:
                try:
                    # Get current parent of screenshot
                    ss_info = drive_service.files().get(
                        fileId=source_ss_id, fields="parents"
                    ).execute()
                    ss_parent = ss_info.get("parents", [root_folder_id])[0]
                    if ss_parent != month_folder_id:
                        move_file_to_folder(
                            drive_service, source_ss_id, ss_parent, month_folder_id
                        )
                        logger.info("Moved screenshot to month folder")
                except Exception as e:
                    logger.warning("Could not move screenshot: %s", e)

        moved_count += 1

    logger.info("Reorganized %d files", moved_count)


def rename_existing_files(drive_service, root_folder_id, dry_run=False):
    """Rename existing extracted JSONs and their source screenshots to descriptive names."""
    all_folder_ids = get_all_data_folder_ids(drive_service, root_folder_id)
    json_files = list_existing_jsons(drive_service, all_folder_ids)
    logger.info("Found %d JSON files to check for renaming", len(json_files))

    # Track used names to add _pN suffix for multi-screenshot sessions
    used_names = {}  # base_name → count
    renamed_count = 0

    # Sort by screenshot name so pages come in order
    def sort_key(jf):
        try:
            content = drive_service.files().get_media(fileId=jf["id"]).execute()
            data = json.loads(content)
            jf["_data"] = data
            return data.get("_source", {}).get("screenshot", jf["name"])
        except Exception:
            jf["_data"] = None
            return jf["name"]

    json_files.sort(key=sort_key)

    for jf in json_files:
        data = jf.get("_data")
        if not data:
            logger.warning("Could not parse %s, skipping", jf["name"])
            continue

        source_ss_name = data.get("_source", {}).get("screenshot", "")
        base_name = build_descriptive_name(data, source_ss_name)

        # Add page suffix for duplicates (multi-screenshot sessions)
        if base_name in used_names:
            used_names[base_name] += 1
            base_name = f"{base_name}_p{used_names[base_name]}"
        else:
            used_names[base_name] = 1

        target_json_name = f"{base_name}.json"
        current_parent = jf.get("_parent_id", root_folder_id)

        # Rename JSON if needed
        if jf["name"] != target_json_name:
            if dry_run:
                logger.info("[DRY RUN] %s → %s", jf["name"], target_json_name)
            else:
                rename_drive_file(drive_service, jf["id"], target_json_name)
            renamed_count += 1

        # Rename source screenshot if it still has old name
        source_ss_id = data.get("_source", {}).get("drive_file_id")
        target_ss_name = f"{base_name}.png"

        if source_ss_id and source_ss_name != target_ss_name:
            if dry_run:
                logger.info("[DRY RUN] %s → %s", source_ss_name, target_ss_name)
            else:
                try:
                    rename_drive_file(drive_service, source_ss_id, target_ss_name)
                    # Update the _source in the JSON to reflect new screenshot name
                    data["_source"]["screenshot"] = target_ss_name
                    upload_json(drive_service, current_parent, target_json_name, data)
                except Exception as e:
                    logger.warning("Could not rename screenshot %s: %s", source_ss_name, e)

    logger.info("Renamed %d files", renamed_count)


def load_all_extracted_jsons(drive_service, root_folder_id):
    """Download and parse all extracted JSON files from Drive (all subfolders)."""
    all_folder_ids = get_all_data_folder_ids(drive_service, root_folder_id)
    json_files = list_existing_jsons(drive_service, all_folder_ids)

    all_data = []
    for f in json_files:
        content = drive_service.files().get_media(fileId=f["id"]).execute()
        try:
            data = json.loads(content)
            all_data.append(data)
        except json.JSONDecodeError:
            logger.warning("Could not parse %s", f["name"])

    return all_data


def format_exercise_markdown(ex):
    """Format a single exercise for the summary."""
    parts = [f"  - **{ex.get('block', '?')}. {ex.get('name', 'Unknown')}**"]

    details = []
    sets = ex.get("sets")
    reps = ex.get("reps")
    weight = ex.get("weight_lbs")
    duration = ex.get("duration_seconds")

    if sets and reps:
        details.append(f"{sets} × {reps}")
    elif sets and duration:
        m, s = divmod(int(duration), 60)
        details.append(f"{sets} × {m}:{s:02d}")
    elif sets:
        details.append(f"{sets} sets")

    if weight:
        details.append(f"@ {weight} lbs")

    if details:
        parts[0] += f" — {' '.join(details)}"

    tempo = ex.get("tempo")
    if tempo:
        parts.append(f"    - Tempo: {tempo}")

    notes = ex.get("notes")
    if notes:
        parts.append(f"    - Note: {notes}")

    return "\n".join(parts)


def generate_summary(drive_service, all_data, folder_id, year_month=None, dry_run=False):
    """Generate a monthly summary Google Doc from extracted data."""
    if not all_data:
        logger.info("No extracted data to summarize")
        return

    # Group by session/date and deduplicate (multiple screenshots per session)
    sessions = {}
    for d in all_data:
        session_key = d.get("session", "Unknown")
        date = d.get("date_moved")

        # Use session + date as unique key
        key = f"{date}_{session_key}" if date else session_key

        if key not in sessions:
            sessions[key] = {
                "session": session_key,
                "coach": d.get("coach"),
                "date": date,
                "metrics": d.get("metrics", {}),
                "exercises": [],
                "coach_instructions": d.get("coach_instructions"),
                "session_comment": d.get("session_comment"),
            }

        # Merge exercises, avoiding duplicates by block label
        existing_blocks = {e["block"] for e in sessions[key]["exercises"] if "block" in e}
        for ex in d.get("exercises", []):
            if ex.get("block") not in existing_blocks:
                sessions[key]["exercises"].append(ex)
                existing_blocks.add(ex.get("block"))

        # Update metrics if we get better data
        for metric_key, val in d.get("metrics", {}).items():
            if val is not None and sessions[key]["metrics"].get(metric_key) is None:
                sessions[key]["metrics"][metric_key] = val

    # Sort sessions by date then session name
    sorted_sessions = sorted(
        sessions.values(),
        key=lambda s: (s.get("date") or "9999-99-99", s.get("session", "")),
    )

    # Determine month for summary
    if year_month:
        month_name = datetime.strptime(year_month, "%Y-%m").strftime("%B %Y")
    else:
        dates = [s["date"] for s in sorted_sessions if s.get("date")]
        if dates:
            month_name = datetime.strptime(dates[0], "%Y-%m-%d").strftime("%B %Y")
        else:
            month_name = "Unknown Period"

    # Build summary document
    lines = [
        f"# TrainHeroic Workout Summary — {month_name}",
        "",
        f"*Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}*",
        f"*Total sessions: {len(sorted_sessions)}*",
        "",
    ]

    # Aggregate stats
    total_volume = sum(
        s.get("metrics", {}).get("total_volume_lbs") or 0 for s in sorted_sessions
    )
    total_exercises = sum(len(s.get("exercises", [])) for s in sorted_sessions)

    # Session type breakdown
    week_counts = {}
    for s in sorted_sessions:
        session = s.get("session", "Unknown")
        week = session.split(" Day")[0] if " Day" in session else session
        week_counts[week] = week_counts.get(week, 0) + 1

    lines.append("## Monthly Overview")
    lines.append(f"- **Total Sessions:** {len(sorted_sessions)}")
    lines.append(f"- **Total Exercises:** {total_exercises}")
    if total_volume > 0:
        lines.append(f"- **Total Volume:** {total_volume:,.0f} lbs")
    if week_counts:
        week_str = ", ".join(f"{v}d {k}" for k, v in sorted(week_counts.items()))
        lines.append(f"- **Program:** {week_str}")

    coach = sorted_sessions[0].get("coach") if sorted_sessions else None
    if coach:
        lines.append(f"- **Coach:** {coach}")
    lines.append("")

    # Individual sessions
    for session_data in sorted_sessions:
        date_str = session_data.get("date")
        session_name = session_data.get("session", "Unknown")
        metrics = session_data.get("metrics", {})

        if date_str:
            try:
                display_date = datetime.strptime(date_str, "%Y-%m-%d").strftime("%A, %B %d")
            except ValueError:
                display_date = date_str
            lines.append(f"## {display_date} — {session_name}")
        else:
            lines.append(f"## {session_name}")

        # Session metrics
        metric_parts = []
        duration = metrics.get("duration_minutes")
        intensity = metrics.get("intensity_rating")
        volume = metrics.get("total_volume_lbs")
        blocks_done = metrics.get("blocks_completed")
        blocks_total = metrics.get("blocks_total")

        if duration:
            metric_parts.append(f"{duration} min")
        if intensity:
            metric_parts.append(f"Intensity: {intensity}/10")
        if volume:
            metric_parts.append(f"Volume: {volume:,.0f} lbs")
        if blocks_done and blocks_total:
            metric_parts.append(f"Blocks: {blocks_done}/{blocks_total}")

        if metric_parts:
            lines.append(f"*{' | '.join(metric_parts)}*")
            lines.append("")

        # Coach instructions
        instructions = session_data.get("coach_instructions")
        if instructions:
            lines.append(f"> Coach: {instructions}")
            lines.append("")

        # Group exercises by category
        exercises = session_data.get("exercises", [])
        current_category = None
        for ex in exercises:
            cat = ex.get("category")
            if cat and cat != current_category:
                lines.append(f"**{cat}**")
                current_category = cat
            lines.append(format_exercise_markdown(ex))

        # Session comment
        comment = session_data.get("session_comment")
        if comment:
            lines.append(f"\n> Session note: {comment}")

        lines.append("")

    summary_text = "\n".join(lines)

    if dry_run:
        logger.info("[DRY RUN] Would upload summary (%d chars)", len(summary_text))
        print(summary_text)
        return

    # Upload as Google Doc
    health_folder_id = load_health_folder_id()
    if year_month:
        year = year_month.split("-")[0]
    else:
        year = datetime.now().strftime("%Y")
    output_folder_id = get_or_create_drive_folder(
        drive_service, f"{DRIVE_SUBFOLDER_PATH}/{year}", health_folder_id
    )

    if year_month:
        doc_filename = f"{year_month}_TrainHeroic_Workout_Summary"
    else:
        doc_filename = f"{datetime.now().strftime('%Y-%m')}_TrainHeroic_Workout_Summary"

    # Check for existing and update or create
    query = f"name='{doc_filename}' and '{output_folder_id}' in parents and trashed=false"
    existing = drive_service.files().list(q=query, fields="files(id)").execute().get("files", [])

    with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".md", encoding="utf-8") as tmp:
        tmp.write(summary_text)
        tmp_path = tmp.name

    try:
        from googleapiclient.http import MediaFileUpload
        media = MediaFileUpload(tmp_path, mimetype="text/plain", resumable=True)

        if existing:
            drive_service.files().update(fileId=existing[0]["id"], media_body=media).execute()
            logger.info("Updated summary doc: %s", doc_filename)
        else:
            metadata = {
                "name": doc_filename,
                "parents": [output_folder_id],
                "mimeType": "application/vnd.google-apps.document",
            }
            drive_service.files().create(body=metadata, media_body=media, fields="id").execute()
            logger.info("Created summary doc: %s", doc_filename)
    finally:
        os.unlink(tmp_path)


def parse_args():
    parser = argparse.ArgumentParser(
        description="Extract workout data from TrainHeroic screenshots in Google Drive"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be processed without uploading",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Re-process all screenshots even if JSON already exists",
    )
    parser.add_argument(
        "--summary-only",
        action="store_true",
        help="Skip extraction, only generate summary from existing JSONs",
    )
    parser.add_argument(
        "--rename",
        action="store_true",
        help="Rename existing extracted files to descriptive names",
    )
    parser.add_argument(
        "--reorganize",
        action="store_true",
        help="Move existing files into year/month subfolders",
    )
    parser.add_argument(
        "--month",
        type=str,
        default=None,
        metavar="YYYY-MM",
        help="Target month for summary (default: auto-detect from data)",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable debug logging",
    )
    return parser.parse_args()


def main():
    args = parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    # Load config
    gemini_key = load_config()

    # Authenticate with Google Drive
    drive_service = get_drive_service() if not args.dry_run else None

    folder_id = TRAINHEROIC_FOLDER_ID

    # Rename mode: rename existing files to descriptive names
    if args.rename:
        logger.info("=== TrainHeroic File Rename ===")
        if not drive_service:
            drive_service = get_drive_service()
        rename_existing_files(drive_service, folder_id, args.dry_run)
        return

    # Reorganize mode: move files into year/month subfolders
    if args.reorganize:
        logger.info("=== TrainHeroic File Reorganize ===")
        if not drive_service:
            drive_service = get_drive_service()
        reorganize_files(drive_service, folder_id, args.dry_run)
        return

    if args.summary_only:
        logger.info("=== TrainHeroic Summary Generation ===")
        if drive_service:
            all_data = load_all_extracted_jsons(drive_service, folder_id)
            logger.info("Loaded %d extracted sessions", len(all_data))
            generate_summary(drive_service, all_data, folder_id, args.month, args.dry_run)
        else:
            logger.error("Cannot generate summary in dry-run mode without Drive access")
        return

    logger.info("=== TrainHeroic Screenshot Extraction ===")

    if args.dry_run:
        # Still need drive service for listing
        drive_service = get_drive_service()

    # Extract data from screenshots
    extracted = extract_screenshots(
        drive_service, gemini_key, folder_id, args.dry_run, args.force
    )

    # Generate summary
    if not args.dry_run:
        all_data = load_all_extracted_jsons(drive_service, folder_id)
        generate_summary(drive_service, all_data, folder_id, args.month)
    elif extracted:
        logger.info("[DRY RUN] Would generate summary from %d sessions", len(extracted))

    logger.info("=== Extraction complete ===")


if __name__ == "__main__":
    main()
