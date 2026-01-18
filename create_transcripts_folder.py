
import sys
import os
import json

sys.path.append(os.path.join(os.getcwd(), 'google-drive'))
from drive_organizer import get_drive_service

service = get_drive_service()
PLAUD_ID = "1lDD6SUh918U6oXjOBB5I9SjFVDAlqjzR"
folder_name = "Transcripts"

file_metadata = {
    'name': folder_name,
    'parents': [PLAUD_ID],
    'mimeType': 'application/vnd.google-apps.folder'
}

file = service.files().create(body=file_metadata, fields='id').execute()
print(f"Created Transcripts Folder: {file.get('id')}")
