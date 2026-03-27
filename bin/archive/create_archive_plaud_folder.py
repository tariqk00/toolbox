"""
Creates the 'Plaud_Transcripts' folder within the designated Archive directory.
Used for storing processed or old transcripts.
"""

import sys
import os


import sys
import os
# Add repo root to path
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if REPO_ROOT not in sys.path:
    sys.path.append(REPO_ROOT)

from toolbox.lib.drive_utils import get_drive_service

service = get_drive_service()
ARCHIVE_ID = "1BNwYqECrR9oPDC5os5uZcxKbaL7lRCoe" 
folder_name = "Plaud_Transcripts"

file_metadata = {
    'name': folder_name,
    'parents': [ARCHIVE_ID],
    'mimeType': 'application/vnd.google-apps.folder'
}

file = service.files().create(body=file_metadata, fields='id').execute()
print(f"Created Archive Folder: {file.get('id')}")