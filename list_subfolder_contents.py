
import sys
import os

sys.path.append(os.path.join(os.getcwd(), 'google-drive'))
from drive_organizer import get_drive_service

service = get_drive_service()
# Recurse into the subfolders found: 
# Gemini, Plaud, Exports. 
# I need to get their IDs first.
PARENT_ID = "1c-7Wv9J-FPpc3tph7Ax1xx5bMI-5jcaG"

def list_deep_contents():
    # 1. Get Subfolders
    results = service.files().list(
        q=f"'{PARENT_ID}' in parents and trashed = false",
        fields="files(id, name, mimeType)"
    ).execute()
    
    subfolders = results.get('files', [])
    
    for folder in subfolders:
        print(f"\nScanning Subfolder: {folder['name']} ({folder['id']})")
        # 2. List Files in each
        f_res = service.files().list(
            q=f"'{folder['id']}' in parents and trashed = false",
            fields="files(id, name, mimeType)",
            pageSize=50
        ).execute()
        files = f_res.get('files', [])
        for f in files:
            print(f"  - {f['name']}")

list_deep_contents()
