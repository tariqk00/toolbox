
import sys
import os
import json

sys.path.append(os.path.join(os.getcwd(), 'google-drive'))
from drive_organizer import get_drive_service

service = get_drive_service()
PKM_ID = "1HNKo72TkLeurAi6g7X0C90OzqF2z3YB7"

query = f"'{PKM_ID}' in parents and name = 'Plaud' and trashed = false"
results = service.files().list(q=query, fields="files(id, name)").execute()
files = results.get('files', [])

if files:
    print(f"Plaud ID: {files[0]['id']}")
else:
    print("Plaud folder not found.")
