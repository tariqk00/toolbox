"""
Lists and groups files in the authoritative 'Plaud' folder.
Groups related files (audio + transcripts) by base name.
"""

import sys
import os

sys.path.append(os.path.join(os.getcwd(), 'google-drive'))
from drive_organizer import get_drive_service

service = get_drive_service()
REAL_PLAUD_ID = "1NiTBFVY_u9MmSv1LJJOIZERiwlJgOPB9"

results = service.files().list(
    q=f"'{REAL_PLAUD_ID}' in parents and trashed = false",
    fields="files(id, name, mimeType)",
    pageSize=300
).execute()

files = results.get('files', [])
print(f"Contents of 'Real' Plaud ({REAL_PLAUD_ID}): {len(files)} files.")

# Group by potential base name (stripping timestamps/suffixes)
groups = {}
for f in files:
    name = f['name']
    # Removing YYYY-MM-DD prefix if present
    # Removing common suffixes like " - summary", " - transcript", ".txt", ".md"
    base = name
    if len(name) > 10 and name[4] == '-' and name[7] == '-':
         # Assume YYYY-MM-DD prefix, strip it
         base = name[13:] # "YYYY-MM-DD - " len is 13
    
    # Normalize
    base = base.replace( " - summary", "").replace(" - transcript", "").replace("summary.txt", "").replace("transcript.txt", "")
    base = os.path.splitext(base.strip())[0]
    
    if base not in groups:
        groups[base] = []
    groups[base].append(name)

print("\n--- Grouped Files ---")
for base, items in groups.items():
    if len(items) > 1:
        print(f"\nGroup: {base}")
        for i in items:
            print(f"  - {i}")
