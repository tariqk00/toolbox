import os.path
import json
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

# If modifying these scopes, delete the file token.json.
# Using broad scopes to match what 'drive_organizer.py' likely uses
SCOPES = [
    'https://www.googleapis.com/auth/drive',
    'https://www.googleapis.com/auth/drive.metadata',
    'https://www.googleapis.com/auth/drive.readonly' 
]

TOKEN_FILE = 'token_full_drive.json' # Using the one found in ls listing
# Fallback to token.json if full drive one fails
if not os.path.exists(TOKEN_FILE):
    TOKEN_FILE = 'token.json'

FOLDER_ID = '16N14A_m847eSortz8hxbfhrk0YyvtouD'

def verify_drive_folder():
    # Dynamically load scopes from the token file itself to avoid mismatch
    if os.path.exists(TOKEN_FILE):
        try:
            with open(TOKEN_FILE, 'r') as f:
                token_data = json.load(f)
                loaded_scopes = token_data.get('scopes', [])
                if loaded_scopes:
                    print(f"ℹ️  Using scopes from token file: {loaded_scopes}")
                    creds = Credentials.from_authorized_user_file(TOKEN_FILE, loaded_scopes)
                else:
                    # Fallback if no scopes in json
                    creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)
        except Exception as e:
            print(f"Error loading token {TOKEN_FILE}: {e}")

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            print("No valid credentials found. Cannot verify drive.")
            return

    try:
        service = build('drive', 'v3', credentials=creds)

        # Search for the dump file globally
        file_name = "n8n_v12_dump.json"
        print(f"🔍 Searching for file: {file_name}")
        
        results = service.files().list(
            q=f"name = '{file_name}' and trashed = false",
            pageSize=10,
            fields="files(id, name, parents, size, createdTime)"
        ).execute()
        
        items = results.get('files', [])

        if not items:
            print("❌ No files found in this folder.")
        else:
            print(f"✅ Found {len(items)} recent files:")
            for item in items:
                print(f" - [{item['createdTime']}] {item['name']} ({item.get('size', '0')} bytes)")

    except Exception as e:
        print(f"An error occurred: {e}")

if __name__ == '__main__':
    verify_drive_folder()
