"""
Locates the 'Plaud' folder within the PKM structure and prints its ID.
Used to verify the destination for Voice Note uploads.
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
PKM_ID = "1HNKo72TkLeurAi6g7X0C90OzqF2z3YB7"

query = f"'{PKM_ID}' in parents and name = 'Plaud' and trashed = false"
results = service.files().list(q=query, fields="files(id, name)").execute()
files = results.get('files', [])

if files:
    print(f"Plaud ID: {files[0]['id']}")
else:
    print("Plaud folder not found.")