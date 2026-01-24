"""
Searches for the 'Plaud' folder specifically within the PKM hierarchy 
to confirm the correct folder ID for uploads.
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
PKM_ID = "1HNKo72TkLeurAi6g7X0C90OzqF2z3YB7"

results = service.files().list(
    q="name = 'Plaud' and mimeType = 'application/vnd.google-apps.folder' and trashed = false",
    fields="files(id, name, parents)"
).execute()

for f in results.get('files', []):
    print(f"Found: {f['name']} ({f['id']}) Parent: {f.get('parents')}")