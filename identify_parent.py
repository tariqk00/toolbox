"""
Resolves a Google Drive Folder ID to its human-readable Name.
Useful for identifying "Mystery" parent folders found in logs.
"""

import sys
import os

sys.path.append(os.path.join(os.getcwd(), 'google-drive'))
from drive_organizer import get_drive_service

service = get_drive_service()
MYSTERY_PARENT_ID = "1NiTBFVY_u9MmSv1LJJOIZERiwlJgOPB9"

try:
    f = service.files().get(fileId=MYSTERY_PARENT_ID, fields="id, name, parents").execute()
    print(f"Folder {MYSTERY_PARENT_ID} is: '{f['name']}' (Parent: {f.get('parents')})")
except Exception as e:
    print(f"Error: {e}")
