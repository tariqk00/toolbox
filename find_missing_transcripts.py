
import sys
import os

sys.path.append(os.path.join(os.getcwd(), 'google-drive'))
from drive_organizer import get_drive_service

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
