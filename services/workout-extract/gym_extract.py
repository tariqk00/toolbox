"""
Gym Workout Screenshot Extractor.
Extracts structured workout data from Bridge Athletics and TrainHeroic screenshots
stored in Google Drive using Gemini Vision.
"""
import io
import json
import logging
import os
import re
import tempfile
from datetime import datetime
from pathlib import Path

logger = logging.getLogger("WorkoutExtract.Gym")

TOOLBOX_ROOT = Path(__file__).resolve().parent.parent.parent
CONFIG_DIR = TOOLBOX_ROOT / "config"
FOLDER_CONFIG_PATH = CONFIG_DIR / "folder_config.json"

# Source configs: where to find screenshots and where to put raw extracted JSONs
# folder_id: Drive folder to scan for screenshots
# output_path: path under Health/Fitness/ for extracted files
TRAINHEROIC_FOLDER_ID = "13NQj-cVU9-tf9wXBTlQbHEDl1ywGT7G5"
BRIDGE_FOLDER_ID = "1h6h_ecsdMVZ87lBJaxJcbh7mgcSgxEm5"

SOURCE_CONFIGS = [
    {
        "name": "Bridge Athletics",
        "folder_id": BRIDGE_FOLDER_ID,
        "output_subfolder": "Fitness/Bridge",
    },
    {
        "name": "TrainHeroic (legacy)",
        "folder_id": TRAINHEROIC_FOLDER_ID,
        "output_subfolder": "Fitness/TrainHeroic",
    },
]

EXTRACTION_PROMPT = """Analyze this gym workout screenshot and extract all workout data into JSON.
The screenshot may be from Bridge Athletics, TrainHeroic, or another workout app.

Return ONLY valid JSON with this exact structure (no markdown fencing):
{
  "workout_label": "Workout 8 or Week 3 Day 2 or similar identifier",
  "program": "Program or coach name visible in the screenshot",
  "source_app": "Bridge Athletics or TrainHeroic or Unknown",
  "date_completed": "YYYY-MM-DD or null if not visible",
  "metrics": {
    "sets_total": null,
    "duration_minutes": null,
    "intensity_rating": null,
    "intensity_max": 10,
    "total_volume_lbs": null
  },
  "blocks": [
    {
      "label": "A",
      "name": "Block name e.g. Deadlift / Row [Stoked Athletics]",
      "exercises": [
        {
          "order": 1,
          "name": "Exercise name",
          "sets": null,
          "reps": null,
          "weight_lbs": null,
          "duration_seconds": null,
          "rpe": null,
          "tempo": null,
          "notes": null
        }
      ]
    }
  ],
  "coach_notes": null,
  "session_comment": null
}

Rules:
- Extract ALL blocks and exercises visible in the screenshot
- For duration-based sets like \":30\", convert to seconds (30)
- Keep block labels exactly as shown (A, B, C or A1, B2 etc)
- If a field is not visible or not applicable, use null
- For weight, use the number only (no \"lb\" suffix)
- source_app: Bridge Athletics uses \"Workout X\" numbering; TrainHeroic uses \"Week X Day Y\"
- Return ONLY the JSON, no other text"""


def load_health_folder_id():
    with open(FOLDER_CONFIG_PATH) as f:
        config = json.load(f)
    health_id = config.get("mappings", {}).get("Health", {}).get("id")
    if not health_id:
        raise ValueError("Health folder ID not found in folder_config.json")
    return health_id


def get_or_create_folder(service, path, parent_id):
    """Create nested folders under parent_id. Returns final folder ID."""
    for name in path.split("/"):
        q = (f"name='{name}' and mimeType='application/vnd.google-apps.folder' "
             f"and '{parent_id}' in parents and trashed=false")
        res = service.files().list(q=q, fields="files(id)").execute()
        if res["files"]:
            parent_id = res["files"][0]["id"]
        else:
            f = service.files().create(
                body={"name": name, "mimeType": "application/vnd.google-apps.folder", "parents": [parent_id]},
                fields="id"
            ).execute()
            parent_id = f["id"]
            logger.info("Created folder: %s", name)
    return parent_id


def sanitize(name):
    name = re.sub(r"[^\w\s-]", "", name)
    return re.sub(r"\s+", "_", name.strip())


def date_from_screenshot_name(name):
    m = re.search(r"Screenshot_(\d{4})(\d{2})(\d{2})", name or "")
    if m:
        return f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
    return None


def build_filename(data, screenshot_name):
    date = data.get("date_completed") or date_from_screenshot_name(screenshot_name) or "unknown-date"
    label = sanitize(data.get("workout_label", "Unknown"))
    return f"{date}_{label}"


def list_screenshots(service, folder_id):
    """List all PNG files in a folder and its year/month subfolders."""
    all_ids = [folder_id]
    # Recurse one level of year/month subfolders
    for subfolder in _list_subfolders(service, folder_id):
        all_ids.append(subfolder["id"])
        for month_folder in _list_subfolders(service, subfolder["id"]):
            all_ids.append(month_folder["id"])

    results = []
    for fid in all_ids:
        q = f"'{fid}' in parents and trashed=false and mimeType='image/png'"
        page_token = None
        while True:
            res = service.files().list(
                q=q, fields="nextPageToken, files(id, name, createdTime, parents)",
                pageSize=100, pageToken=page_token
            ).execute()
            for f in res.get("files", []):
                f["_parent_id"] = fid
            results.extend(res.get("files", []))
            page_token = res.get("nextPageToken")
            if not page_token:
                break
    return sorted(results, key=lambda f: f["name"])


def _list_subfolders(service, parent_id):
    q = f"'{parent_id}' in parents and trashed=false and mimeType='application/vnd.google-apps.folder'"
    res = service.files().list(q=q, fields="files(id, name)", pageSize=100).execute()
    return res.get("files", [])


def get_processed_screenshots(service, root_folder_id):
    """Scan existing JSONs in the output tree to find already-processed screenshot names."""
    all_ids = [root_folder_id]
    for yf in _list_subfolders(service, root_folder_id):
        all_ids.append(yf["id"])
        for mf in _list_subfolders(service, yf["id"]):
            all_ids.append(mf["id"])

    processed = set()
    for fid in all_ids:
        q = f"'{fid}' in parents and trashed=false and mimeType='application/json'"
        res = service.files().list(q=q, fields="files(id, name)", pageSize=100).execute()
        for jf in res.get("files", []):
            try:
                content = service.files().get_media(fileId=jf["id"]).execute()
                data = json.loads(content)
                ss_name = data.get("_source", {}).get("screenshot")
                if ss_name:
                    processed.add(ss_name)
            except Exception:
                continue
    return processed


def download_image(service, file_id):
    from googleapiclient.http import MediaIoBaseDownload
    request = service.files().get_media(fileId=file_id)
    buf = io.BytesIO()
    dl = MediaIoBaseDownload(buf, request)
    done = False
    while not done:
        _, done = dl.next_chunk()
    return buf.getvalue()


def extract_with_gemini(image_bytes, api_key, filename="screenshot.png"):
    from google import genai
    from google.genai import types

    client = genai.Client(api_key=api_key)
    response = client.models.generate_content(
        model="gemini-2.0-flash",
        contents=[
            EXTRACTION_PROMPT,
            types.Part.from_bytes(data=image_bytes, mime_type="image/png"),
        ],
        config=types.GenerateContentConfig(
            temperature=0.1,
            response_mime_type="application/json",
        ),
    )
    try:
        text = response.text.strip()
        if text.startswith("```"):
            text = re.sub(r"^```\w*\n?", "", text)
            text = re.sub(r"\n?```$", "", text)
        return json.loads(text)
    except (json.JSONDecodeError, ValueError) as e:
        logger.warning("Failed to parse Gemini response for %s: %s", filename, e)
        return None


def upload_json(service, folder_id, filename, data):
    from googleapiclient.http import MediaFileUpload
    q = f"name='{filename}' and '{folder_id}' in parents and trashed=false"
    existing = service.files().list(q=q, fields="files(id)").execute().get("files", [])

    with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".json", encoding="utf-8") as tmp:
        json.dump(data, tmp, indent=2, default=str)
        tmp_path = tmp.name

    try:
        media = MediaFileUpload(tmp_path, mimetype="application/json", resumable=True)
        if existing:
            service.files().update(fileId=existing[0]["id"], media_body=media).execute()
            return existing[0]["id"]
        else:
            res = service.files().create(
                body={"name": filename, "parents": [folder_id]},
                media_body=media, fields="id"
            ).execute()
            logger.info("Uploaded: %s", filename)
            return res["id"]
    finally:
        os.unlink(tmp_path)


def move_and_rename(service, file_id, current_parent_id, target_folder_id, new_name):
    body = {"name": new_name}
    kwargs = {"fileId": file_id, "body": body, "fields": "id"}
    if current_parent_id != target_folder_id:
        kwargs["addParents"] = target_folder_id
        kwargs["removeParents"] = current_parent_id
    service.files().update(**kwargs).execute()


def extract_from_source(service, api_key, source_config, dry_run=False, force=False):
    """
    Extract gym sessions from a single source folder.
    Returns list of session dicts ready for merging.
    """
    source_name = source_config["name"]
    folder_id = source_config["folder_id"]
    output_subfolder = source_config["output_subfolder"]

    health_id = load_health_folder_id()
    output_root_id = get_or_create_folder(service, output_subfolder, health_id)

    screenshots = list_screenshots(service, folder_id)
    logger.info("[%s] Found %d screenshots", source_name, len(screenshots))

    if not screenshots:
        return []

    processed = set() if force else get_processed_screenshots(service, output_root_id)
    sessions = []

    for ss in screenshots:
        if ss["name"] in processed:
            logger.debug("[%s] Skipping already processed: %s", source_name, ss["name"])
            continue

        logger.info("[%s] Processing: %s", source_name, ss["name"])

        if dry_run:
            logger.info("[DRY RUN] Would extract: %s", ss["name"])
            continue

        image_bytes = download_image(service, ss["id"])
        data = extract_with_gemini(image_bytes, api_key, ss["name"])
        if not data:
            logger.warning("[%s] Extraction failed, skipping: %s", source_name, ss["name"])
            continue

        date_str = (data.get("date_completed")
                    or date_from_screenshot_name(ss["name"])
                    or "unknown-date")

        data["_source"] = {
            "screenshot": ss["name"],
            "screenshot_drive_id": ss["id"],
            "source_app_folder": source_name,
            "extracted_at": datetime.now().isoformat(),
        }

        base_name = build_filename(data, ss["name"])
        json_name = f"{base_name}.json"

        # Get or create YYYY/MM subfolder in output
        if date_str != "unknown-date":
            try:
                dt = datetime.strptime(date_str[:10], "%Y-%m-%d")
                month_path = f"{output_subfolder}/{dt.strftime('%Y')}/{dt.strftime('%m')}"
                month_folder_id = get_or_create_folder(service, month_path, health_id)
            except ValueError:
                month_folder_id = output_root_id
        else:
            month_folder_id = output_root_id

        upload_json(service, month_folder_id, json_name, data)

        # Move screenshot to output month folder and rename
        new_ss_name = f"{base_name}.png"
        move_and_rename(service, ss["id"], ss["_parent_id"], month_folder_id, new_ss_name)

        sessions.append(data)

    logger.info("[%s] Extracted %d new sessions", source_name, len(sessions))
    return sessions


def extract_all(service, api_key, dry_run=False, force=False):
    """Extract from all configured sources. Returns combined list of sessions."""
    all_sessions = []
    for source in SOURCE_CONFIGS:
        sessions = extract_from_source(service, api_key, source, dry_run=dry_run, force=force)
        all_sessions.extend(sessions)
    return all_sessions
