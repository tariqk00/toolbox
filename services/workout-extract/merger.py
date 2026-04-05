"""
Workout Record Merger.
Combines gym session data (from screenshots) with biometric data from Garmin
(and future providers: Whoop, Oura) into a unified per-session JSON record.
Saves unified records to Drive under Health/Fitness/Workouts/YYYY/MM/.
"""
import json
import logging
import os
import re
import tempfile
from datetime import datetime
from pathlib import Path

logger = logging.getLogger("WorkoutExtract.Merger")

TOOLBOX_ROOT = Path(__file__).resolve().parent.parent.parent
CONFIG_DIR = TOOLBOX_ROOT / "config"
FOLDER_CONFIG_PATH = CONFIG_DIR / "folder_config.json"

WORKOUTS_SUBFOLDER = "Fitness/Workouts"


def load_health_folder_id():
    with open(FOLDER_CONFIG_PATH) as f:
        config = json.load(f)
    health_id = config.get("mappings", {}).get("Health", {}).get("id")
    if not health_id:
        raise ValueError("Health folder ID not found in folder_config.json")
    return health_id


def get_or_create_folder(service, path, parent_id):
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
    return parent_id


def create_unified_record(gym_session, health_connect=None):
    """
    Merge gym session data with biometric data into a unified workout record.

    Args:
        gym_session: Dict from gym_extract (contains blocks, exercises, metadata)
        health_connect: Dict from Health Connect export or None

    Returns:
        Unified workout dict
    """
    date = (gym_session.get("date_completed")
            or gym_session.get("_source", {}).get("screenshot", ""))

    # Normalize date from screenshot name if needed
    if not date or len(date) < 10:
        import re as _re
        m = _re.search(r"Screenshot_(\d{4})(\d{2})(\d{2})", date)
        if m:
            date = f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
        else:
            date = "unknown-date"
    else:
        date = date[:10]

    return {
        "date": date,
        "workout_label": gym_session.get("workout_label"),
        "program": gym_session.get("program"),
        "source_app": gym_session.get("source_app"),
        "metrics": gym_session.get("metrics"),
        "blocks": gym_session.get("blocks", []),
        "coach_notes": gym_session.get("coach_notes"),
        "session_comment": gym_session.get("session_comment"),
        "health_connect": health_connect,
        "_sources": {
            "screenshot": gym_session.get("_source", {}).get("screenshot"),
            "screenshot_drive_id": gym_session.get("_source", {}).get("screenshot_drive_id"),
        },
        "_merged_at": datetime.now().isoformat(),
    }


def _build_filename(record):
    date = record.get("date", "unknown-date")
    label = record.get("workout_label", "Workout")
    label_clean = re.sub(r"[^\w\s-]", "", label)
    label_clean = re.sub(r"\s+", "_", label_clean.strip())
    app = record.get("source_app", "")
    app_tag = "Bridge" if "Bridge" in app else "TrainHeroic" if "TrainHeroic" in app else "Gym"
    return f"{date}_{label_clean}_{app_tag}"


def save_unified_record(service, record, dry_run=False):
    """Save unified workout record to Drive under Health/Fitness/Workouts/YYYY/MM/."""
    from googleapiclient.http import MediaFileUpload

    date = record.get("date", "unknown-date")
    base_name = _build_filename(record)
    filename = f"{base_name}.json"

    if dry_run:
        logger.info("[DRY RUN] Would save unified record: %s", filename)
        return None

    health_id = load_health_folder_id()

    if date != "unknown-date":
        try:
            dt = datetime.strptime(date, "%Y-%m-%d")
            folder_path = f"{WORKOUTS_SUBFOLDER}/{dt.strftime('%Y')}/{dt.strftime('%m')}"
        except ValueError:
            folder_path = WORKOUTS_SUBFOLDER
    else:
        folder_path = WORKOUTS_SUBFOLDER

    folder_id = get_or_create_folder(service, folder_path, health_id)

    q = f"name='{filename}' and '{folder_id}' in parents and trashed=false"
    existing = service.files().list(q=q, fields="files(id)").execute().get("files", [])

    with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".json", encoding="utf-8") as tmp:
        json.dump(record, tmp, indent=2, default=str)
        tmp_path = tmp.name

    try:
        media = MediaFileUpload(tmp_path, mimetype="application/json", resumable=True)
        if existing:
            service.files().update(fileId=existing[0]["id"], media_body=media).execute()
            logger.info("Updated unified record: %s", filename)
            return existing[0]["id"]
        else:
            res = service.files().create(
                body={"name": filename, "parents": [folder_id]},
                media_body=media, fields="id"
            ).execute()
            logger.info("Saved unified record: %s", filename)
            return res["id"]
    finally:
        os.unlink(tmp_path)
