import os
import io
import json
import logging
from googleapiclient.http import MediaIoBaseDownload
from toolbox.core.google import GoogleAuth

logger = logging.getLogger("DriveSorter.Drive")

# --- CONFIG ---
# This file is in toolbox/core/drive.py
# Root is toolbox/
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_PATH = os.path.join(BASE_DIR, 'google-drive', 'folder_config.json')

def load_folder_config():
    try:
        if os.path.exists(CONFIG_PATH):
            with open(CONFIG_PATH, 'r') as f:
                return json.load(f)
    except Exception as e:
        logger.error(f"Error loading folder_config.json: {e}")
    return {"mappings": {}}

FOLDER_CONFIG = load_folder_config()

def get_drive_service():
    auth = GoogleAuth(base_dir=os.path.join(BASE_DIR, 'google-drive'))
    # Assuming standard token names in that dir
    creds = auth.get_credentials(token_filename='token_full_drive.json', credentials_filename='credentials.json')
    return auth.get_service('drive', 'v3', creds)

def get_sheets_service():
    auth = GoogleAuth(base_dir=os.path.join(BASE_DIR, 'google-drive'))
    creds = auth.get_credentials(token_filename='token_full_drive.json', credentials_filename='credentials.json')
    return auth.get_service('sheets', 'v4', creds)

def get_category_list():
    """Builds a flat list of categories and sub-categories."""
    categories = []
    mappings = FOLDER_CONFIG.get('mappings', {})
    for parent, data in mappings.items():
        categories.append(parent)
        subcats = data.get('subcategories', {})
        for sub in subcats.keys():
            categories.append(f"{parent}/{sub}")
    return sorted(list(set(categories + ["Other"])))

def get_category_prompt_str():
    return ", ".join(get_category_list())

def resolve_folder_id(category_str, save_recommendation_callback=None):
    """Resolves a category string to a folder ID."""
    if not category_str or category_str == 'Other' or category_str == 'Uncategorized':
        return None
        
    mappings = FOLDER_CONFIG.get('mappings', {})
    parts = [p.strip() for p in category_str.split('/')]
    parent_name = parts[0]
    sub_name = parts[1] if len(parts) > 1 else None
    
    parent_data = mappings.get(parent_name)
    if not parent_data:
        if save_recommendation_callback:
            save_recommendation_callback(category_str)
        return None
    
    parent_id = parent_data.get('id')
    
    if sub_name:
        sub_id = parent_data.get('subcategories', {}).get(sub_name)
        if sub_id:
            return sub_id
        else:
            if save_recommendation_callback:
                save_recommendation_callback(f"{parent_name}/{sub_name}")
            return parent_id
            
    return parent_id

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
            request = service.files().export_media(fileId=file_id, mimeType='application/pdf')
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
