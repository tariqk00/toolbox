"""
Executed migration of legacy export files (Kindle, Plaud, Pocket, Evernote)
from the 'Exports' folder to their new homes in the Second Brain.
"""
import os.path
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

import os
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TOKEN_PATH = os.path.join(BASE_DIR, 'token_full_drive.json')
SCOPES = ['https://www.googleapis.com/auth/drive']

# Hardcoded IDs or names to look for
INBOX_NAME = "00 - Incoming & Inbox"
EXPORTS_FOLDER_NAME = "Exports"
SECOND_BRAIN_NAME = "01 - Second Brain"
ARCHIVE_NAME = "07 - Archive"

# Mapping structure
# Source Filename -> Target Path List (bucket, sub1, sub2...)
MOVES = {
    # Second Brain
    "Kindle_Highlights_Export.csv": [SECOND_BRAIN_NAME, "Archive (Sources)", "Kindle"],
    "Plaud_transcripts_2024.zip": [SECOND_BRAIN_NAME, "Archive (Sources)", "Plaud"],
    "Pocket_bookmarks.html": [SECOND_BRAIN_NAME, "Archive (Sources)", "Pocket"],
    "Logseq-backup.zip": [SECOND_BRAIN_NAME, "Notes (Manual)", "Logseq"],
    
    # Archive
    "Google Takeout": [ARCHIVE_NAME, "Legacy Exports", "Google Takeout"], # This might be a folder on Drive?
    "WhatsApp Archive.zip": [ARCHIVE_NAME, "Legacy Exports", "WhatsApp"],
    "Evernote_Backup.enex": [ARCHIVE_NAME, "Legacy Exports", "Evernote"],
}

def get_service():
    creds = Credentials.from_authorized_user_file(TOKEN_PATH, SCOPES)
    return build('drive', 'v3', credentials=creds)

def find_folder_id(service, parent_id, folder_name):
    query = f"name = '{folder_name}' and '{parent_id}' in parents and trashed = false"
    # if folder_name implies mimeType check (it's a folder), strict check. 
    # But files also have names. We assume buckets are folders.
    res = service.files().list(q=query, fields="files(id, mimeType)").execute()
    files = res.get('files', [])
    if not files:
        return None
    # Prefer folder mimeType if possible, but for buckets checking ID is enough usually
    for f in files:
        if f['mimeType'] == 'application/vnd.google-apps.folder':
            return f['id']
    return files[0]['id'] # Fallback

def ensure_path(service, root_id, path_segments):
    """
    Traverses or creates folder path from root_id.
    returns final folder id.
    """
    current_id = root_id
    for segment in path_segments:
        found_id = find_folder_id(service, current_id, segment)
        if found_id:
            current_id = found_id
        else:
            print(f"Creating folder '{segment}' inside parent {current_id}...")
            file_metadata = {
                'name': segment,
                'mimeType': 'application/vnd.google-apps.folder',
                'parents': [current_id]
            }
            file = service.files().create(body=file_metadata, fields='id').execute()
            current_id = file.get('id')
    return current_id

def move_file(service, file_id, target_folder_id):
    file = service.files().get(fileId=file_id, fields='parents').execute()
    previous_parents = ",".join(file.get('parents', []))
    service.files().update(
        fileId=file_id,
        addParents=target_folder_id,
        removeParents=previous_parents,
        fields='id, parents'
    ).execute()

def main():
    service = get_service()
    
    # 1. Locate Roots
    root_res = service.files().list(q="'root' in parents and trashed = false", fields="files(id, name)").execute()
    roots = {item['name']: item['id'] for item in root_res.get('files', [])}
    
    if INBOX_NAME not in roots:
        print(f"Error: {INBOX_NAME} not found in root.")
        return

    # 2. Locate Exports folder
    exports_id = find_folder_id(service, roots[INBOX_NAME], EXPORTS_FOLDER_NAME)
    if not exports_id:
        print("Error: Exports folder not found.")
        return
        
    # 3. List Export Items
    items_res = service.files().list(q=f"'{exports_id}' in parents and trashed = false", fields="files(id, name)").execute()
    export_items = {item['name']: item['id'] for item in items_res.get('files', [])}
    
    print(f"Found {len(export_items)} items in Exports.")
    
    for filename, target_path_list in MOVES.items():
        # Handle 'Google Takeout' potentially being a partial match or folder
        # The script assumes exact name match in MOVES keys, but let's be flexible if needed.
        # Actually Google Takeout was seen as 'Google Takeout' (folder? zip?) in previous turns.
        # Assuming exact match.
        
        # Check if we have the item
        # If the key in MOVES is exactly in export_items
        file_id = None
        if filename in export_items:
            file_id = export_items[filename]
        else:
            # Try partial matching for zip/folders if exact match fails
            matches = [k for k in export_items.keys() if filename in k]
            if matches:
                print(f"Exact match not found for '{filename}', using '{matches[0]}'")
                file_id = export_items[matches[0]]
            else:
                print(f"Skipping '{filename}' - not found in current Exports folder.")
                continue

        # Resolve Target
        bucket_name = target_path_list[0]
        sub_path = target_path_list[1:]
        
        if bucket_name not in roots:
            print(f"Error: Target bucket '{bucket_name}' not found.")
            continue
            
        print(f"Processing '{filename}' -> {bucket_name}/{'/'.join(sub_path)}")
        
        target_folder_id = ensure_path(service, roots[bucket_name], sub_path)
        move_file(service, file_id, target_folder_id)
        print("Moved.")

if __name__ == '__main__':
    main()
