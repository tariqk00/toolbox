"""
Google Drive API Wrapper.
Provides helper functions for File Downloads, Moves, Folder Resolution, and Config Loading.
"""
import os
import io
import json
import logging
from googleapiclient.http import MediaIoBaseDownload
from toolbox.lib.google_api import GoogleAuth

logger = logging.getLogger("DriveSorter.Drive")

# --- CONFIG ---
# This file is in toolbox/lib/drive_utils.py
# Root is toolbox/
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_PATH = os.path.join(BASE_DIR, 'config', 'folder_config.json')
TREE_PATH = os.path.join(BASE_DIR, 'config', 'drive_tree.json')

def load_folder_config():
    try:
        if os.path.exists(CONFIG_PATH):
            with open(CONFIG_PATH, 'r') as f:
                return json.load(f)
    except Exception as e:
        logger.error(f"Error loading folder_config.json: {e}")
    return {"system": {}}

def load_drive_tree():
    try:
        if os.path.exists(TREE_PATH):
            with open(TREE_PATH, 'r') as f:
                return json.load(f)
        else:
            logger.warning("drive_tree.json not found. Run bin/refresh_drive_tree.py to generate it.")
    except Exception as e:
        logger.error(f"Error loading drive_tree.json: {e}")
    return {}

FOLDER_CONFIG = load_folder_config()
DRIVE_TREE = load_drive_tree()
ID_TO_PATH = {v: k for k, v in DRIVE_TREE.get('path_to_id', {}).items()}

_system = FOLDER_CONFIG.get('system', {})
INBOX_ID = _system.get('inbox_id', '')
METADATA_FOLDER_ID = _system.get('metadata_folder_id', '')
HISTORY_SHEET_ID = _system.get('history_sheet_id', '')

def get_drive_service():
    auth = GoogleAuth(base_dir=BASE_DIR)
    # Creds in config/
    creds = auth.get_credentials(token_filename='token_full_drive.json', credentials_filename='config/credentials.json')
    return auth.get_service('drive', 'v3', creds)

def get_sheets_service():
    auth = GoogleAuth(base_dir=BASE_DIR)
    creds = auth.get_credentials(token_filename='token_full_drive.json', credentials_filename='config/credentials.json')
    return auth.get_service('sheets', 'v4', creds)

def get_category_prompt_str():
    """Returns a sorted newline-separated list of all folder paths from drive_tree.json."""
    path_to_id = DRIVE_TREE.get('path_to_id', {})
    if not path_to_id:
        logger.warning("drive_tree.json is empty or missing. Folder list will be empty.")
        return ""
    return "\n".join(sorted(path_to_id.keys()))

def resolve_folder_id(path_str, save_recommendation_callback=None):
    """Resolves a folder path string to a Drive folder ID via direct lookup in drive_tree.json."""
    if not path_str:
        return None

    path_to_id = DRIVE_TREE.get('path_to_id', {})
    folder_id = path_to_id.get(path_str)

    if not folder_id:
        logger.warning(f"  [Resolve] Path not found in drive tree: '{path_str}'")
        if save_recommendation_callback:
            save_recommendation_callback(path_str)
        return None

    return folder_id

def get_folder_path(service, folder_id):
    if not folder_id or folder_id in ["None", "Unknown", "Inbox/Unknown"]:
        return "Unknown"

    path_parts = []
    current_id = folder_id
    
    for _ in range(5): 
        if not current_id: break
        try:
             res = service.files().get(fileId=current_id, fields="name, parents").execute()
             name = res.get('name', 'Unknown')
             path_parts.insert(0, name)
             parents = res.get('parents')
             current_id = parents[0] if parents else None
        except Exception as e:
             break
             
    if not path_parts:
        return "Unknown Folder"
        
    return " / ".join(path_parts)

def download_file_content(service, file_id, mime_type):
    """Downloads content to memory."""
    # logger.info(f"Downloading content for {file_id} ({mime_type})...")
    
    if mime_type.startswith('application/vnd.google-apps.'):
        if 'document' in mime_type:
            request = service.files().export_media(fileId=file_id, mimeType='text/plain')
        elif 'spreadsheet' in mime_type:
            request = service.files().export_media(fileId=file_id, mimeType='text/csv')
        else:
            request = service.files().export_media(fileId=file_id, mimeType='application/pdf')
    elif mime_type in ['application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', 'application/vnd.openxmlformats-officedocument.wordprocessingml.document']:
        request = service.files().get_media(fileId=file_id)
    else:
        request = service.files().get_media(fileId=file_id)
        
    fh = io.BytesIO()
    downloader = MediaIoBaseDownload(fh, request)
    done = False
    while done is False:
        status, done = downloader.next_chunk()
    return fh.getvalue()

def move_file(service, file_id, target_folder_id, processed_name):
    try:
        file = service.files().get(fileId=file_id, fields='parents').execute()
        parents = file.get('parents', [])
        previous_parents = ",".join(parents) if parents else ""
        
        service.files().update(
            fileId=file_id,
            addParents=target_folder_id,
            removeParents=previous_parents,
            fields='id, parents'
        ).execute()
        return True
    except Exception as e:
        logger.error(f"Move Error: {e}")
        return False
