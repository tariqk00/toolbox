import os.path
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

import os
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TOKEN_PATH = os.path.join(BASE_DIR, 'token_full_drive.json')
SCOPES = ['https://www.googleapis.com/auth/drive']

def get_service():
    creds = Credentials.from_authorized_user_file(TOKEN_PATH, SCOPES)
    return build('drive', 'v3', credentials=creds)

def list_root_buckets():
    service = get_service()
    results = service.files().list(
        q="mimeType = 'application/vnd.google-apps.folder' and trashed = false and 'root' in parents",
        fields="files(id, name)"
    ).execute()
    folders = results.get('files', [])
    for f in folders:
        if f['name'].startswith('0'):
            print(f"Bucket: {f['name']} | ID: {f['id']}")

if __name__ == '__main__':
    list_root_buckets()
