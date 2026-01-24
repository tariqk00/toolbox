import os.path
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

# Scopes from plaud/drive_mcp.py 
SCOPES = ['https://www.googleapis.com/auth/drive.file', 'https://www.googleapis.com/auth/drive.metadata.readonly']

def get_drive_service():
    base_dir = os.path.dirname(os.path.abspath(__file__))
    cred_path = os.path.join(base_dir, 'token_drive.json')
    client_secrets = os.path.join(base_dir, 'credentials.json')
    
    creds = None
    if os.path.exists(cred_path):
        creds = Credentials.from_authorized_user_file(cred_path, SCOPES)
    
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(client_secrets, SCOPES)
            creds = flow.run_local_server(port=0)
        with open(cred_path, 'w') as token:
            token.write(creds.to_json())
            
    return build('drive', 'v3', credentials=creds)

def find_folder(service, folder_name):
    query = f"name = '{folder_name}' and mimeType = 'application/vnd.google-apps.folder' and trashed = false"
    results = service.files().list(q=query, spaces='drive', fields='files(id, name)').execute()
    return results.get('files', [])

def list_contents(service, folder_id, limit=50):
    query = f"'{folder_id}' in parents and trashed = false"
    # Added 'id' to fields to capture children IDs
    results = service.files().list(q=query, pageSize=limit, fields='files(id, name, mimeType, createdTime)').execute()
    return results.get('files', [])

if __name__ == '__main__':
    service = get_drive_service()
    print("Searching for QNAP831X folder...")
    folders = find_folder(service, 'QNAP831X')
    
    if not folders:
        print("Folder not found.")
    else:
        qnap_id = folders[0]['id']
        print(f"Found QNAP831X (ID: {qnap_id})")
        
        items = list_contents(service, qnap_id)
        print("\nSubfolders in QNAP831X:")
        unprocessed_id = None
        for item in items:
            if item['mimeType'] == 'application/vnd.google-apps.folder':
                print(f" - {item['name']} (ID: {item['id']})")
                if item['name'].lower() == 'unprocessed':
                    unprocessed_id = item['id']
            else:
                print(f" - [FILE] {item['name']} ({item['mimeType']})")
        
        if unprocessed_id:
            print(f"\nListing contents of 'Unprocessed' (ID: {unprocessed_id}):")
            u_items = list_contents(service, unprocessed_id)
            for item in u_items:
                print(f" - {item['name']} ({item['mimeType']}) - Created: {item['createdTime']}")
        else:
            print("\n'Unprocessed' folder not found.")
