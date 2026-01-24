"""
Simple utility to look up a Google Drive Folder ID by its name.
"""
from drive_organizer import get_drive_service

def find_folder(name):
    service = get_drive_service()
    query = f"mimeType = 'application/vnd.google-apps.folder' and name = '{name}' and trashed = false"
    results = service.files().list(q=query, fields="files(id, name)").execute()
    files = results.get('files', [])

    if not files:
        print(f"No folder found with name: {name}")
    else:
        for f in files:
            print(f"Found: {f['name']} - ID: {f['id']}")

if __name__ == "__main__":
    find_folder("01 - Second Brain")
