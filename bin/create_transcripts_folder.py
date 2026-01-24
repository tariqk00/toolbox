"""
Creates a 'Transcripts' subfolder within the main Plaud directory.
Target for text-only transcript exports.
"""

import sys
import os
import json


import sys
import os
# Add repo root to path
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if REPO_ROOT not in sys.path:
    sys.path.append(REPO_ROOT)

from toolbox.lib.drive_utils import get_drive_service

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