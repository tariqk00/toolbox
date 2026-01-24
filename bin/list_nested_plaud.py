"""
Diagnostic tool to list contents of a specific nested 'Plaud' folder.
Used to debug duplicate folder structures.
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
NESTED_PLAUD_ID = "16N14A_m847eSortz8hxbfhrk0YyvtouD"

results = service.files().list(
    q=f"'{NESTED_PLAUD_ID}' in parents and trashed = false",
    fields="files(id, name, mimeType)",
    pageSize=100
).execute()

print(f"Contents of Nested Plaud ({NESTED_PLAUD_ID}):")
files = results.get('files', [])
if not files:
    print("  (Empty)")
for f in files:
    print(f" - {f['name']}")