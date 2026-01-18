
import sys
import os

sys.path.append(os.path.join(os.getcwd(), 'google-drive'))
from drive_organizer import get_drive_service

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
