"""
Resolves a Google Drive Folder ID to its human-readable Name.
Useful for identifying "Mystery" parent folders found in logs.
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
MYSTERY_PARENT_ID = "1NiTBFVY_u9MmSv1LJJOIZERiwlJgOPB9"

try:
    f = service.files().get(fileId=MYSTERY_PARENT_ID, fields="id, name, parents").execute()
    print(f"Folder {MYSTERY_PARENT_ID} is: '{f['name']}' (Parent: {f.get('parents')})")
except Exception as e:
    print(f"Error: {e}")