"""
Lists all direct child files/folders of a hardcoded Parent ID.
Simple diagnostic tool for inspecting folder contents.
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
PARENT_ID = "1c-7Wv9J-FPpc3tph7Ax1xx5bMI-5jcaG"

# Simple flat list of EVERYTHING in this folder
results = service.files().list(
    q=f"'{PARENT_ID}' in parents and trashed = false",
    fields="files(id, name, mimeType)",
    pageSize=100
).execute()

print(f"Direct children of {PARENT_ID}:")
for f in results.get('files', []):
    print(f" - {f['name']} [{f['mimeType']}]")