"""
Backs up /home/tariqk/.openclaw/workspace to Google Drive.

Creates a ZIP, uploads to _Master_Archive_Metadata/workspace-backups/,
then prunes old ZIPs keeping only the last KEEP_BACKUPS files.
"""
import os
import sys
import zipfile
import datetime
import logging

# Allow running as a script or module
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
repo_root = os.path.dirname(BASE_DIR)
if repo_root not in sys.path:
    sys.path.insert(0, repo_root)

from googleapiclient.http import MediaFileUpload
from toolbox.lib.drive_utils import get_drive_service, METADATA_FOLDER_ID

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(message)s')
logger = logging.getLogger("workspace-backup")

WORKSPACE_PATH = os.path.expanduser("~/.openclaw/workspace")
BACKUP_FOLDER_NAME = "workspace-backups"
KEEP_BACKUPS = 7

# Files/dirs to skip inside the workspace ZIP
EXCLUDE_PATHS = [".git"]


def _create_zip(workspace_path: str) -> str:
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    zip_path = f"/tmp/workspace_backup_{timestamp}.zip"
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for root, dirs, files in os.walk(workspace_path):
            # Skip excluded dirs in-place
            dirs[:] = [d for d in dirs if d not in EXCLUDE_PATHS]
            for fname in files:
                full = os.path.join(root, fname)
                arcname = os.path.relpath(full, os.path.expanduser("~"))
                zf.write(full, arcname)
    size_mb = os.path.getsize(zip_path) / (1024 * 1024)
    logger.info(f"ZIP created: {zip_path} ({size_mb:.1f} MB)")
    return zip_path


def _find_or_create_backup_folder(service, parent_id: str) -> str:
    """Returns the ID of workspace-backups under parent_id, creating it if absent."""
    query = (
        f"'{parent_id}' in parents "
        f"and name = '{BACKUP_FOLDER_NAME}' "
        f"and mimeType = 'application/vnd.google-apps.folder' "
        f"and trashed = false"
    )
    results = service.files().list(q=query, fields="files(id, name)").execute()
    files = results.get("files", [])
    if files:
        folder_id = files[0]["id"]
        logger.info(f"Found existing backup folder: {folder_id}")
        return folder_id

    logger.info(f"Creating backup folder '{BACKUP_FOLDER_NAME}' under {parent_id}")
    meta = {
        "name": BACKUP_FOLDER_NAME,
        "mimeType": "application/vnd.google-apps.folder",
        "parents": [parent_id],
    }
    folder = service.files().create(body=meta, fields="id").execute()
    return folder["id"]


def _upload_zip(service, zip_path: str, folder_id: str) -> str:
    filename = os.path.basename(zip_path)
    media = MediaFileUpload(zip_path, mimetype="application/zip", resumable=True)
    file_meta = {"name": filename, "parents": [folder_id]}
    result = service.files().create(
        body=file_meta, media_body=media, fields="id, name"
    ).execute()
    logger.info(f"Uploaded: {result['name']} ({result['id']})")
    return result["id"]


def _prune_old_backups(service, folder_id: str, keep: int) -> None:
    """Delete oldest ZIPs in folder_id, keeping the last `keep` files."""
    query = (
        f"'{folder_id}' in parents "
        f"and mimeType = 'application/zip' "
        f"and trashed = false"
    )
    results = service.files().list(
        q=query,
        fields="files(id, name, createdTime)",
        orderBy="createdTime asc",
    ).execute()
    files = results.get("files", [])
    to_delete = files[:-keep] if len(files) > keep else []
    for f in to_delete:
        service.files().delete(fileId=f["id"]).execute()
        logger.info(f"Pruned: {f['name']} ({f['id']})")
    logger.info(f"Backup count after prune: {len(files) - len(to_delete)}/{keep}")


def backup_workspace():
    if not os.path.isdir(WORKSPACE_PATH):
        logger.error(f"Workspace not found: {WORKSPACE_PATH}")
        sys.exit(1)

    if not METADATA_FOLDER_ID:
        logger.error("metadata_folder_id not set in folder_config.json")
        sys.exit(1)

    zip_path = _create_zip(WORKSPACE_PATH)

    try:
        service = get_drive_service()
        folder_id = _find_or_create_backup_folder(service, METADATA_FOLDER_ID)
        _upload_zip(service, zip_path, folder_id)
        _prune_old_backups(service, folder_id, KEEP_BACKUPS)
        logger.info("Backup complete.")
    finally:
        if os.path.exists(zip_path):
            os.remove(zip_path)
            logger.info(f"Cleaned up local ZIP: {zip_path}")


if __name__ == "__main__":
    backup_workspace()
