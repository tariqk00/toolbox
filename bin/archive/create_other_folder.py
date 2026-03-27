"""
Ensures the '99 - Other' folder exists at the root (or specified location).
Acts as a catch-all for uncategorized items.
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

# Create '99 - Other' at root (or My Drive) if not exists
folder_name = '99 - Other'
parent_id = None # Root

print(f"Checking for '{folder_name}'...")

query = f"name = '{folder_name}' and mimeType = 'application/vnd.google-apps.folder' and trashed = false"
# If we want it in specific parent, add parent check. Assuming Root for now as "Separate folder".

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

print(json.dumps({"Other": folder_id}))