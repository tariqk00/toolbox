"""
Garmin Connect Activity Sync.
Downloads activities from Garmin Connect and uploads to Google Drive.
Designed for daily automated execution via systemd timer.
"""
import argparse
import calendar
import json
import logging
import os
import sys
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

from dotenv import load_dotenv
from garminconnect import Garmin, GarminConnectAuthenticationError

# Resolve paths relative to toolbox root
TOOLBOX_ROOT = Path(__file__).resolve().parent.parent
CONFIG_DIR = TOOLBOX_ROOT / "config"
GARMIN_TOKEN_DIR = CONFIG_DIR / ".garminconnect"
SECRETS_ENV_PATH = CONFIG_DIR / "secrets.env"

# Subfolders to create under the existing Health folder in Drive
DRIVE_SUBFOLDER_PATH = "Fitness/Garmin"
FOLDER_CONFIG_PATH = CONFIG_DIR / "folder_config.json"

# Activity download formats
DOWNLOAD_FORMATS = {
    "fit": Garmin.ActivityDownloadFormat.ORIGINAL,
    "gpx": Garmin.ActivityDownloadFormat.GPX,
    "tcx": Garmin.ActivityDownloadFormat.TCX,
    "csv": Garmin.ActivityDownloadFormat.CSV,
}

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("GarminSync")


def load_config():
    """Load Garmin credentials from secrets.env or environment variables."""
    if SECRETS_ENV_PATH.exists():
        load_dotenv(SECRETS_ENV_PATH)

    email = os.getenv("GARMIN_EMAIL")
    password = os.getenv("GARMIN_PASSWORD")

    if not email or not password:
        logger.error(
            "GARMIN_EMAIL and GARMIN_PASSWORD must be set in %s or environment",
            SECRETS_ENV_PATH,
        )
        sys.exit(1)

    return email, password


def authenticate(email, password):
    """Authenticate with Garmin Connect, resuming from saved tokens when possible."""
    garmin = Garmin(email, password)
    GARMIN_TOKEN_DIR.mkdir(parents=True, exist_ok=True)

    try:
        garmin.login(str(GARMIN_TOKEN_DIR))
        logger.info("Authenticated with Garmin Connect (resumed session)")
    except (FileNotFoundError, GarminConnectAuthenticationError):
        logger.info("No saved session found, performing fresh login...")
        try:
            garmin.login()
            garmin.garth.dump(str(GARMIN_TOKEN_DIR))
            logger.info("Fresh login successful, tokens saved to %s", GARMIN_TOKEN_DIR)
        except GarminConnectAuthenticationError as e:
            logger.error("Authentication failed: %s", e)
            logger.error(
                "If MFA is enabled, run this script interactively first to complete the MFA prompt."
            )
            sys.exit(1)

    return garmin


def get_drive_service():
    """Get an authenticated Google Drive service using existing toolbox credentials."""
    # Need both: toolbox root (for `from lib.google_api`) and its parent
    # (for `from toolbox.lib.log_manager` used inside GoogleAuth)
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
    if not FOLDER_CONFIG_PATH.exists():
        logger.error("folder_config.json not found at %s", FOLDER_CONFIG_PATH)
        sys.exit(1)

    with open(FOLDER_CONFIG_PATH) as f:
        config = json.load(f)

    health_id = config.get("mappings", {}).get("Health", {}).get("id")
    if not health_id:
        logger.error("Health folder ID not found in folder_config.json")
        sys.exit(1)

    logger.debug("Using Health folder ID: %s", health_id)
    return health_id


def get_or_create_drive_folder(service, subfolder_path, parent_id):
    """Create nested subfolders under an existing parent folder. Returns folder ID."""
    parts = subfolder_path.split("/")

    for folder_name in parts:
        query = (
            f"name='{folder_name}' and mimeType='application/vnd.google-apps.folder' "
            f"and '{parent_id}' in parents and trashed=false"
        )
        results = service.files().list(q=query, fields="files(id, name)").execute()
        files = results.get("files", [])

        if files:
            parent_id = files[0]["id"]
        else:
            file_metadata = {
                "name": folder_name,
                "mimeType": "application/vnd.google-apps.folder",
                "parents": [parent_id],
            }
            folder = service.files().create(body=file_metadata, fields="id").execute()
            parent_id = folder["id"]
            logger.info("Created Drive folder: %s", folder_name)

    return parent_id


    return parent_id


def move_file_to_folder(service, file_id, current_parent_id, target_folder_id):
    """Move a file from one folder to another on Google Drive."""
    service.files().update(
        fileId=file_id,
        addParents=target_folder_id,
        removeParents=current_parent_id,
        fields="id, parents",
    ).execute()


def upload_to_drive(service, folder_id, filename, data, mime_type="application/octet-stream"):
    """Upload a file to Google Drive. Skips if a file with the same name already exists."""
    from googleapiclient.http import MediaFileUpload

    # Check for existing file
    query = f"name='{filename}' and '{folder_id}' in parents and trashed=false"
    existing = service.files().list(q=query, fields="files(id)").execute().get("files", [])
    if existing:
        logger.debug("Skipping upload, already exists: %s", filename)
        return existing[0]["id"]


def move_file_to_folder(service, file_id, current_parent_id, target_folder_id):
    """Move a file from one folder to another on Google Drive."""
    service.files().update(
        fileId=file_id,
        addParents=target_folder_id,
        removeParents=current_parent_id,
        fields="id, parents",
    ).execute()





def fetch_activities(garmin, start_date, end_date):
    """Fetch activity list from Garmin Connect for the given date range."""
    logger.info("Fetching activities from %s to %s", start_date, end_date)
    activities = garmin.get_activities_by_date(
        start_date.strftime("%Y-%m-%d"),
        end_date.strftime("%Y-%m-%d"),
    )
    logger.info("Found %d activities", len(activities))
    return activities


def download_activity_file(garmin, activity_id, fmt="fit"):
    """Download an activity file in the specified format."""
    dl_format = DOWNLOAD_FORMATS.get(fmt, DOWNLOAD_FORMATS["fit"])
    data = garmin.download_activity(activity_id, dl_fmt=dl_format)
    return data


import re


def sanitize_filename(name):
    """Sanitize a string for use in filenames — replace non-alphanumeric chars with underscores."""
    sanitized = re.sub(r'[^\w\-]', '_', name)
    sanitized = re.sub(r'_+', '_', sanitized).strip('_')
    return sanitized or "Unnamed"


def sync_activities(garmin, drive_service, target_date, dry_run=False, formats=None):
    """Sync activities for a given date to Google Drive."""
    if formats is None:
        formats = ["fit"]

    start_date = target_date
    end_date = target_date + timedelta(days=1)

    activities = fetch_activities(garmin, start_date, end_date)
    if not activities:
        logger.info("No activities found for %s", target_date.strftime("%Y-%m-%d"))
        return 0

    # Structure: Fitness/Garmin/YYYY/MM for daily files
    year = target_date.strftime("%Y")
    month = target_date.strftime("%m")
    date_str = target_date.strftime("%Y-%m-%d")
    subfolder_path = f"{DRIVE_SUBFOLDER_PATH}/{year}/{month}"

    if dry_run:
        logger.info("[DRY RUN] Would create folder: Health > %s", subfolder_path)
        for activity in activities:
            activity_id = activity["activityId"]
            activity_name = activity.get("activityName", "Unnamed")
            activity_type = activity.get("activityType", {}).get("typeKey", "unknown")
            safe_name = sanitize_filename(activity_name)
            logger.info(
                "[DRY RUN] Would download: %s_%s_%s in formats: %s",
                date_str, safe_name, activity_id, formats,
            )
        return len(activities)

    health_folder_id = load_health_folder_id()
    folder_id = get_or_create_drive_folder(drive_service, subfolder_path, health_folder_id)
    synced_count = 0

    for activity in activities:
        activity_id = activity["activityId"]
        activity_name = activity.get("activityName", "Unnamed")
        activity_type = activity.get("activityType", {}).get("typeKey", "unknown")
        safe_name = sanitize_filename(activity_name)

        # Filename prefix: 2026-02-13_Strength_21867483378
        file_prefix = f"{date_str}_{safe_name}_{activity_id}"

        logger.info(
            "Processing activity %s: %s (%s)", activity_id, activity_name, activity_type
        )

        # Upload activity metadata as JSON
        meta_filename = f"{file_prefix}_metadata.json"
        upload_to_drive(drive_service, folder_id, meta_filename, activity, "application/json")

        # Download and upload activity files in requested formats
        for fmt in formats:
            try:
                data = download_activity_file(garmin, activity_id, fmt)
                ext = "zip" if fmt == "fit" else fmt
                filename = f"{file_prefix}.{ext}"
                mime = "application/zip" if fmt == "fit" else "application/octet-stream"
                upload_to_drive(drive_service, folder_id, filename, data, mime)
            except Exception as e:
                logger.warning("Failed to download %s format for activity %s: %s", fmt, activity_id, e)

        synced_count += 1

    return synced_count


def format_duration(seconds):
    """Format seconds into human-readable duration."""
    if not seconds:
        return "N/A"
    h, remainder = divmod(int(seconds), 3600)
    m, s = divmod(remainder, 60)
    if h > 0:
        return f"{h}h {m:02d}m"
    return f"{m}m {s:02d}s"


def format_activity_markdown(activity):
    """Format a single activity as readable markdown."""
    name = activity.get("activityName", "Unnamed")
    activity_type = activity.get("activityType", {}).get("typeKey", "unknown")
    start_time = activity.get("startTimeLocal", "")
    duration = format_duration(activity.get("duration"))
    cals = activity.get("calories", 0)
    distance_m = activity.get("distance", 0) or 0
    distance_km = distance_m / 1000 if distance_m > 0 else 0
    avg_hr = activity.get("averageHR")
    max_hr = activity.get("maxHR")
    steps = activity.get("steps")
    total_sets = activity.get("totalSets")
    total_reps = activity.get("totalReps")
    aerobic_te = activity.get("aerobicTrainingEffect")
    anaerobic_te = activity.get("anaerobicTrainingEffect")
    moderate_min = activity.get("moderateIntensityMinutes", 0)
    vigorous_min = activity.get("vigorousIntensityMinutes", 0)
    body_battery = activity.get("differenceBodyBattery")
    water_ml = activity.get("waterEstimated")

    # Extract time from startTimeLocal (e.g. "2026-02-14 10:35:36")
    time_str = start_time.split(" ")[-1][:5] if " " in str(start_time) else ""

    lines = [f"### {name} ({activity_type}) — {time_str}"]
    lines.append(f"- **Duration:** {duration}")

    if distance_km > 0:
        lines.append(f"- **Distance:** {distance_km:.2f} km")
    if cals:
        lines.append(f"- **Calories:** {int(cals)} kcal")
    if avg_hr and max_hr:
        lines.append(f"- **Heart Rate:** avg {int(avg_hr)} / max {int(max_hr)} bpm")
    elif avg_hr:
        lines.append(f"- **Heart Rate:** avg {int(avg_hr)} bpm")

    # HR zone breakdown
    zones = []
    for z in range(1, 6):
        zone_time = activity.get(f"hrTimeInZone_{z}", 0)
        if zone_time and zone_time > 60:
            zones.append(f"Z{z}: {format_duration(zone_time)}")
    if zones:
        lines.append(f"- **HR Zones:** {' | '.join(zones)}")

    if total_sets:
        parts = [f"{total_sets} sets"]
        if total_reps:
            parts.append(f"{total_reps} reps")
        lines.append(f"- **Volume:** {', '.join(parts)}")
    if steps and steps > 100:
        lines.append(f"- **Steps:** {steps:,}")
    if moderate_min or vigorous_min:
        lines.append(f"- **Intensity Minutes:** {moderate_min} moderate, {vigorous_min} vigorous")
    if aerobic_te and aerobic_te > 0:
        te_parts = [f"aerobic {aerobic_te:.1f}"]
        if anaerobic_te and anaerobic_te > 0:
            te_parts.append(f"anaerobic {anaerobic_te:.1f}")
        lines.append(f"- **Training Effect:** {', '.join(te_parts)}")
    if body_battery:
        lines.append(f"- **Body Battery Impact:** {body_battery:+d}")
    if water_ml:
        lines.append(f"- **Estimated Hydration:** {int(water_ml)} mL")

    return "\n".join(lines)


def generate_monthly_summary(garmin, drive_service, year, month, dry_run=False):
    """Generate a monthly activity summary and upload as a Google Doc for NotebookLM."""
    last_day = calendar.monthrange(year, month)[1]
    start_date = datetime(year, month, 1)
    end_date = datetime(year, month, last_day) + timedelta(days=1)
    month_name = start_date.strftime("%B %Y")

    logger.info("Generating summary for %s", month_name)

    activities = garmin.get_activities_by_date(
        start_date.strftime("%Y-%m-%d"),
        end_date.strftime("%Y-%m-%d"),
    )
    logger.info("Found %d activities for %s", len(activities), month_name)

    if not activities:
        logger.info("No activities found for %s", month_name)
        return

    # Sort by start time
    activities.sort(key=lambda a: a.get("startTimeLocal", ""))

    # Build summary document
    lines = [
        f"# Garmin Activity Summary — {month_name}",
        "",
        f"*Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}*",
        f"*Total activities: {len(activities)}*",
        "",
    ]

    # Monthly aggregate stats
    total_cals = sum(a.get("calories", 0) or 0 for a in activities)
    total_duration = sum(a.get("duration", 0) or 0 for a in activities)
    total_distance = sum((a.get("distance", 0) or 0) for a in activities) / 1000
    total_moderate = sum(a.get("moderateIntensityMinutes", 0) or 0 for a in activities)
    total_vigorous = sum(a.get("vigorousIntensityMinutes", 0) or 0 for a in activities)

    # Activity type breakdown
    type_counts = {}
    for a in activities:
        t = a.get("activityType", {}).get("typeKey", "unknown")
        type_counts[t] = type_counts.get(t, 0) + 1
    type_breakdown = ", ".join(f"{v}x {k}" for k, v in sorted(type_counts.items(), key=lambda x: -x[1]))

    lines.append("## Monthly Overview")
    lines.append(f"- **Total Duration:** {format_duration(total_duration)}")
    lines.append(f"- **Total Calories:** {int(total_cals):,} kcal")
    if total_distance > 0:
        lines.append(f"- **Total Distance:** {total_distance:.1f} km")
    lines.append(f"- **Intensity Minutes:** {total_moderate} moderate, {total_vigorous} vigorous")
    lines.append(f"- **Activity Types:** {type_breakdown}")
    lines.append("")

    # Group activities by date
    daily = {}
    for a in activities:
        date_str = str(a.get("startTimeLocal", "")).split(" ")[0]
        daily.setdefault(date_str, []).append(a)

    for date_str in sorted(daily.keys()):
        day_activities = daily[date_str]
        # Parse into readable date
        try:
            display_date = datetime.strptime(date_str, "%Y-%m-%d").strftime("%A, %B %d")
        except ValueError:
            display_date = date_str

        lines.append(f"## {display_date}")
        for activity in day_activities:
            lines.append(format_activity_markdown(activity))
            lines.append("")

    summary_text = "\n".join(lines)

    if dry_run:
        logger.info("[DRY RUN] Would upload summary for %s (%d chars)", month_name, len(summary_text))
        print(summary_text)
        return

    # Upload as a plain text file (Google Drive auto-converts to Doc if requested)
    health_folder_id = load_health_folder_id()
    year_str = start_date.strftime("%Y")
    folder_id = get_or_create_drive_folder(drive_service, f"{DRIVE_SUBFOLDER_PATH}/{year_str}", health_folder_id)

    doc_filename = f"{start_date.strftime('%Y-%m')}_Garmin_Activity_Summary"

    # Check for existing doc and replace
    query = f"name='{doc_filename}' and '{folder_id}' in parents and trashed=false"
    existing = drive_service.files().list(q=query, fields="files(id)").execute().get("files", [])

    # Upload as Google Doc (convert from text/plain)
    with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".md", encoding="utf-8") as tmp:
        tmp.write(summary_text)
        tmp_path = tmp.name

    try:
        from googleapiclient.http import MediaFileUpload
        media = MediaFileUpload(tmp_path, mimetype="text/plain", resumable=True)

        if existing:
            # Update existing doc
            drive_service.files().update(
                fileId=existing[0]["id"],
                media_body=media,
            ).execute()
            logger.info("Updated summary doc: %s", doc_filename)
        else:
            # Create new Google Doc
            file_metadata = {
                "name": doc_filename,
                "parents": [folder_id],
                "mimeType": "application/vnd.google-apps.document",
            }
            drive_service.files().create(
                body=file_metadata,
                media_body=media,
                fields="id",
            ).execute()
            logger.info("Created summary doc: %s", doc_filename)
    finally:
        os.unlink(tmp_path)


def reorganize_files(drive_service, dry_run=False):
    """Move existing files from year folders into month subfolders."""
    health_folder_id = load_health_folder_id()
    # Get Fitness/Garmin folder ID
    garmin_folder_id = get_or_create_drive_folder(drive_service, DRIVE_SUBFOLDER_PATH, health_folder_id)
    
    # List year folders
    query = (
        f"'{garmin_folder_id}' in parents and trashed=false "
        f"and mimeType='application/vnd.google-apps.folder'"
    )
    res = drive_service.files().list(q=query, fields="files(id, name)").execute()
    year_folders = res.get("files", [])
    
    moved_count = 0
    for yf in year_folders:
        year = yf["name"]
        if not re.match(r"^\d{4}$", year):
            continue
            
        logger.info("Checking year folder: %s", year)
        
        # List files in year folder (exclude folders)
        q_files = (
            f"'{yf['id']}' in parents and trashed=false "
            f"and mimeType!='application/vnd.google-apps.folder'"
        )
        page_token = None
        while True:
            f_res = drive_service.files().list(
                q=q_files, 
                fields="nextPageToken, files(id, name)",
                pageSize=100, 
                pageToken=page_token
            ).execute()
            files = f_res.get("files", [])
            
            for f in files:
                # Expect naming: YYYY-MM-DD_...
                # Skip summary docs (YYYY-MM_Garmin_Activity_Summary)
                if "Activity_Summary" in f["name"]:
                    continue
                    
                match = re.match(r"^(\d{4})-(\d{2})-\d{2}_", f["name"])
                if not match:
                    logger.debug("Skipping non-matching file: %s", f["name"])
                    continue
                
                file_year, file_month = match.groups()
                
                # Should be in month subfolder
                target_folder_path = f"{DRIVE_SUBFOLDER_PATH}/{file_year}/{file_month}"
                
                if dry_run:
                    logger.info("[DRY RUN] %s → %s/", f["name"], target_folder_path)
                    moved_count += 1
                    continue
                    
                target_folder_id = get_or_create_drive_folder(drive_service, target_folder_path, health_folder_id)
                
                # Move
                if target_folder_id != yf["id"]:
                    move_file_to_folder(drive_service, f["id"], yf["id"], target_folder_id)
                    logger.info("Moved %s to %s/%s", f["name"], file_year, file_month)
                    moved_count += 1
            
            page_token = f_res.get("nextPageToken")
            if not page_token:
                break
                
    logger.info("Reorganized %d files", moved_count)





def parse_args():
    parser = argparse.ArgumentParser(description="Sync Garmin Connect activities to Google Drive")
    parser.add_argument(
        "--date",
        type=str,
        default=None,
        help="Target date in YYYY-MM-DD format (default: yesterday)",
    )
    parser.add_argument(
        "--days",
        type=int,
        default=1,
        help="Number of days to sync backwards from target date (default: 1)",
    )
    parser.add_argument(
        "--formats",
        type=str,
        nargs="+",
        choices=["fit", "gpx", "tcx", "csv"],
        default=["fit"],
        help="Download formats (default: fit)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be downloaded without actually downloading",
    )
    parser.add_argument(
        "--summary",
        type=str,
        default=None,
        metavar="YYYY-MM",
        help="Generate monthly summary doc for NotebookLM (e.g. 2026-02)",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable debug logging",
    )
    parser.add_argument(
        "--reorganize",
        action="store_true",
        help="Move existing files into month subfolders",
    )
    return parser.parse_args()


def main():
    args = parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    # Authenticate with Garmin
    email, password = load_config()
    garmin = authenticate(email, password)

    # Authenticate with Google Drive
    if not args.dry_run or args.reorganize:
        drive_service = get_drive_service()
    else:
        drive_service = None

    # Reorganize mode
    if args.reorganize:
        logger.info("=== Reorganizing Garmin Files ===")
        reorganize_files(drive_service, args.dry_run)
        return

    # Summary-only mode
    if args.summary:
        try:
            summary_date = datetime.strptime(args.summary, "%Y-%m")
        except ValueError:
            logger.error("Invalid --summary format, expected YYYY-MM")
            sys.exit(1)
        logger.info("=== Garmin Monthly Summary ===")
        generate_monthly_summary(
            garmin, drive_service, summary_date.year, summary_date.month, args.dry_run
        )
        return

    # Determine target date
    if args.date:
        target_date = datetime.strptime(args.date, "%Y-%m-%d")
    else:
        target_date = datetime.now() - timedelta(days=1)

    logger.info("=== Garmin Activity Sync ===")
    logger.info("Target date: %s (syncing %d day(s))", target_date.strftime("%Y-%m-%d"), args.days)
    logger.info("Formats: %s", args.formats)
    logger.info("Dry run: %s", args.dry_run)

    # Sync each day
    total_synced = 0
    for day_offset in range(args.days):
        current_date = target_date - timedelta(days=day_offset)
        synced = sync_activities(garmin, drive_service, current_date, args.dry_run, args.formats)
        total_synced += synced

    logger.info("=== Sync complete: %d activities processed ===", total_synced)

    # Auto-generate summary for the month of the target date
    generate_monthly_summary(
        garmin, drive_service, target_date.year, target_date.month, args.dry_run
    )


if __name__ == "__main__":
    main()
