
import sys
import os

sys.path.append(os.path.join(os.getcwd(), 'google-drive'))
from drive_organizer import get_drive_service

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
