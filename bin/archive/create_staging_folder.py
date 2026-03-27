"""
Creates the '00 - Staging' folder if it does not exist.
This folder is used as an intermediate holding area before final sorting.
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

folder_name = '00 - Staging'

print(f"Checking for '{folder_name}'...")

query = f"name = '{folder_name}' and mimeType = 'application/vnd.google-apps.folder' and trashed = false"
results = service.files().list(q=query, fields="files(id, name)").execute()
files = results.get('files', [])

folder_id = None
if files:
    print(f"  [Exists] {folder_name}: {files[0]['id']}")
    folder_id = files[0]['id']
else:
    file_metadata = {
        'name': folder_name,
        'mimeType': 'application/vnd.google-apps.folder'
    }
    file = service.files().create(body=file_metadata, fields='id').execute()
    print(f"  [Created] {folder_name}: {file.get('id')}")
    folder_id = file.get('id')

print(json.dumps({"Staging": folder_id}))