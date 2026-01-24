"""
Lists files in the 'Incoming & Inbox' folder with metadata (Size, Created Time).
Useful for identifying large files or stale items.
"""
from drive_organizer import get_drive_service, INBOX_ID

def check_sizes():
    try:
        service = get_drive_service()
        results = service.files().list(
            q=f"'{INBOX_ID}' in parents and trashed = false",
            fields="files(id, name, mimeType, size, createdTime, modifiedTime)"
        ).execute()
        
        files = results.get('files', [])
        
        print(f"Contents of '00 - Incoming & Inbox' ({len(files)} items):")
        print(f"{'Name':<60} | {'Size (Bytes)':<12} | {'Created':<20} | {'Type'}")
        print("-" * 110)
        
        for f in files:
            name = f.get('name', 'Unknown')[:58]
            size = f.get('size', 'N/A') # Google Docs don't have 'size' usually
            created = f.get('createdTime', 'N/A')
            mime = f.get('mimeType', 'Unknown')
            
            print(f"{name:<60} | {size:<12} | {created:<20} | {mime}")
                
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    check_sizes()
