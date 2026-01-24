"""
Parsing engine for QNAP backups. Reads `qnap_analysis.json` and sorts files 
into a standard Year/Month structured hierarchy.
"""
import os.path
import json
import re
import argparse
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

# Broader scope required for moving files
SCOPES = ['https://www.googleapis.com/auth/drive']

def get_drive_service():
    # Use distinct token for full drive access
    base_dir = os.path.dirname(os.path.abspath(__file__))
    cred_path = os.path.join(base_dir, 'token_full_drive.json')
    # Assuming credentials.json is also in the same dir or passed in. 
    # The original path pointed to ../plaud/credentials.json which is weird. 
    # Let's assume it's in the local dir for now or use a relative path.
    client_secrets = os.path.join(base_dir, 'credentials.json')
    
    creds = None
    if os.path.exists(cred_path):
        creds = Credentials.from_authorized_user_file(cred_path, SCOPES)
    
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(client_secrets, SCOPES)
            # Use fixed port to make redirect predictable if needed, but port=0 is fine
            # open_browser=False ensures it doesn't try to open a local window
            creds = flow.run_local_server(port=0, open_browser=False, 
                                          prompt='consent',
                                          authorization_prompt_message='Please visit this URL to authorize: {url}')
        with open(cred_path, 'w') as token:
            token.write(creds.to_json())
            
    return build('drive', 'v3', credentials=creds)

def parse_path_context(path):
    parts = path.split('/')
    if len(parts) < 2: return "Unsorted", "Misc", "Unknown"
    parent_folder = parts[-2]
    
    # Pattern A: "01 Sep Event Name" (MM-Month - Event)
    match_a = re.search(r'^(\d{2}) (Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s*(.*)', parent_folder, re.I)
    if match_a:
        y_short, m_name, event = match_a.groups()
        event = event.strip() or parent_folder
        months = {"Jan":"01","Feb":"02","Mar":"03","Apr":"04","May":"05","Jun":"06","Jul":"07","Aug":"08","Sep":"09","Oct":"10","Nov":"11","Dec":"12"}
        m_num = months.get(m_name.capitalize(), "00")
        y_pref = "20" if int(y_short) < 30 else "19"
        return f"{y_pref}{y_short}", f"{m_num}-{m_name.capitalize()}", event

    # Pattern B: "YYYY Season"
    match_b = re.search(r'^(\d{4})\s+(Spring|Summer|Fall|Winter|Autumn)', parent_folder, re.I)
    if match_b:
        year, season = match_b.groups()
        season_map = {"Spring":"04-Apr", "Summer":"07-Jul", "Autumn":"10-Oct", "Fall":"10-Oct", "Winter":"01-Jan"}
        return year, season_map.get(season.capitalize(), "00-Unknown"), parent_folder

    # Pattern C: "YYYY-MM-DD"
    match_c = re.search(r'^(\d{4})-(\d{2})-(\d{2})', parent_folder)
    if match_c:
        y, m, d = match_c.groups()
        return y, m, parent_folder

    return None, None, parent_folder

def get_or_create_folder(service, parent_id, folder_name, dry_run=False):
    if parent_id == "DRY_RUN_ID":
        return "DRY_RUN_ID"
        
    safe_name = folder_name.replace("'", "\\'")
    query = f"name = '{safe_name}' and '{parent_id}' in parents and mimeType = 'application/vnd.google-apps.folder' and trashed = false"
    results = service.files().list(q=query, fields='files(id)').execute()
    files = results.get('files', [])
    if files:
        return files[0]['id']
    
    if dry_run:
        print(f"[DRY RUN] Create folder: {folder_name} in parent {parent_id}")
        return "DRY_RUN_ID"
    
    print(f"Creating folder: {folder_name} in parent {parent_id}")
    file_metadata = {
        'name': folder_name,
        'mimeType': 'application/vnd.google-apps.folder',
        'parents': [parent_id]
    }
    folder = service.files().create(body=file_metadata, fields='id').execute()
    return folder.get('id')

def move_file(service, file_id, target_folder_id, dry_run=False):
    if dry_run:
        return True
    
    # Get current parents
    file = service.files().get(fileId=file_id, fields='parents').execute()
    previous_parents = ",".join(file.get('parents'))
    
    # Move file
    print(f"Moving file {file_id} to folder {target_folder_id}...")
    service.files().update(
        fileId=file_id,
        addParents=target_folder_id,
        removeParents=previous_parents,
        fields='id, parents'
    ).execute()
    return True

def run_organization(analysis_file, dry_run=True):
    service = get_drive_service()
    with open(analysis_file, 'r') as f:
        data = json.load(f)
    
    # Target root folder in QNAP831X
    QNAP_ROOT_ID = '1-n34nfXCw6Onz7TLckioIltrTGnZ-cmE'
    ORG_ROOT_ID = get_or_create_folder(service, QNAP_ROOT_ID, 'Organized', dry_run)
    
    counts = {"moved": 0, "system": 0, "unsorted": 0}
    folder_cache = {} # path -> id

    for item in data:
        file_id = item['id']
        name = item['name']
        path = item['path']
        
        # 1. System Files
        if name.lower() in ['thumbs.db', 'picasa.ini'] or item['mimeType'] == 'application/octet-stream':
            target_path = "_system/files"
            counts["system"] += 1
        else:
            y, m, context = parse_path_context(path)
            
            # EXIF Adjustment
            if 'photoTakenTime' in item and item['photoTakenTime']:
                exif_y = item['photoTakenTime'][:4]
                exif_m = item['photoTakenTime'][5:7]
                if y == exif_y and m.startswith(exif_m):
                    target_year, target_month = exif_y, f"{m} - {context}"
                else:
                    target_year, target_month = exif_y, f"{exif_m} - {context}"
            elif y:
                target_year, target_month = y, f"{m} - {context}"
            else:
                target_year, target_month = "Unsorted", context
                counts["unsorted"] += 1
                
            target_path = f"{target_year}/{target_month}"

        # Ensure folder path exists
        parent_id = ORG_ROOT_ID
        current_rel_path = ""
        for folder in target_path.split('/'):
            current_rel_path = f"{current_rel_path}/{folder}".strip('/')
            if current_rel_path not in folder_cache:
                folder_cache[current_rel_path] = get_or_create_folder(service, parent_id, folder, dry_run)
            parent_id = folder_cache[current_rel_path]
            
        # Move the file
        if move_file(service, file_id, parent_id, dry_run):
            if target_path != "_system/files" and not target_path.startswith("Unsorted"):
                counts["moved"] += 1
            if dry_run:
                print(f"[DRY RUN] Move '{name}' -> '{target_path}/'")

    print("\n--- Final Stats ---")
    print(f"Total Files: {len(data)}")
    print(f"To be Organized: {counts['moved']}")
    print(f"To System Archive: {counts['system']}")
    print(f"To Unsorted (Remaining): {counts['unsorted']}")

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--execute', action='store_true', help='Execute the moves (not a dry run)')
    args = parser.parse_args()
    
    run_organization('qnap_analysis.json', dry_run=not args.execute)
