
import sys
import os

sys.path.append(os.path.join(os.getcwd(), 'google-drive'))
from drive_organizer import get_drive_service

service = get_drive_service()
ARCHIVE_ID = "1BNwYqECrR9oPDC5os5uZcxKbaL7lRCoe" 
folder_name = "Plaud_Transcripts"

file_metadata = {
    'name': folder_name,
    'parents': [ARCHIVE_ID],
    'mimeType': 'application/vnd.google-apps.folder'
}

file = service.files().create(body=file_metadata, fields='id').execute()
print(f"Created Archive Folder: {file.get('id')}")
