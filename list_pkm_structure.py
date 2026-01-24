"""
Recursively lists the folder structure of the Second Brain (PKM).
"""

import sys
import os

sys.path.append(os.path.join(os.getcwd(), 'google-drive'))
from drive_organizer import get_drive_service

service = get_drive_service()
PKM_ID = "1HNKo72TkLeurAi6g7X0C90OzqF2z3YB7" # From folder_config.json

def list_folder_tree(folder_id, indent=0):
    query = f"'{folder_id}' in parents and trashed = false"
    # Get all files and folders
    results = service.files().list(
        q=query, 
        fields="files(id, name, mimeType)",
        orderBy="folder,name"
    ).execute()
    
    items = results.get('files', [])
    if not items:
        if indent == 0:
            print("  (Empty)")
        return

    for item in items:
        name = item['name']
        mime = item['mimeType']
        is_folder = (mime == 'application/vnd.google-apps.folder')
        
        prefix = "  " * indent
        icon = "📁" if is_folder else "📄"
        print(f"{prefix}{icon} {name}")
        
        if is_folder:
            list_folder_tree(item['id'], indent + 1)

print(f"Structure of PKM (Second Brain) [{PKM_ID}]:")
list_folder_tree(PKM_ID)
