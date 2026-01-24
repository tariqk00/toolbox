"""
Creates the 'Plaud' folder within the PKM (Personal Knowledge Management) structure.
Destination for raw Plaud note uploads.
"""

import sys
import os
import json

sys.path.append(os.path.join(os.getcwd(), 'google-drive'))
from drive_organizer import get_drive_service

service = get_drive_service()
PKM_ID = "1HNKo72TkLeurAi6g7X0C90OzqF2z3YB7"
folder_name = "Plaud"

file_metadata = {
    'name': folder_name,
    'parents': [PKM_ID],
    'mimeType': 'application/vnd.google-apps.folder'
}

file = service.files().create(body=file_metadata, fields='id').execute()
print(f"Created Plaud Folder: {file.get('id')}")
