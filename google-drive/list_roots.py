from drive_organizer import get_drive_service

def list_root_folders():
    service = get_drive_service()
    
    print("Scanning Root Folders...")
    results = service.files().list(
        q="'root' in parents and mimeType = 'application/vnd.google-apps.folder' and trashed = false",
        fields="files(id, name)",
        orderBy="name"
    ).execute()
    
    files = results.get('files', [])
    print(f"Found {len(files)} root folders:")
    for f in files:
        print(f"  {f['name']} ({f['id']})")

if __name__ == "__main__":
    list_root_folders()
