"""
Checks if a specific Google Drive folder exists by ID.
Useful for debugging folder accessibility.
"""
import sys
import os
import json

sys.path.append(os.path.join(os.getcwd(), 'google-drive'))
from drive_organizer import get_drive_service

service = get_drive_service()
folder_id = "1BsNuuDngxR1gdUlb8T0tKmMCz1ZAjJvO"

try:
    f = service.files().get(fileId=folder_id, fields="id, name").execute()
    print(f"Folder {folder_id} is: {f['name']}")
except Exception as e:
    print(f"Error: {e}")
