"""
Performs a global Drive search for files with 'transcript' in the name.
Useful for locating misplaced Plaud exports.
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

# Broad search for Plaud-like files to find their location
results = service.files().list(
    q="name contains 'transcript' and trashed = false",
    fields="files(id, name, parents)",
    pageSize=10
).execute()

print("Searching for 'transcript' globally:")
for f in results.get('files', []):
    print(f" - {f['name']} (Parent: {f.get('parents')})")