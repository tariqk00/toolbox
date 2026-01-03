import os.path
import json
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

# Scopes for metadata read
SCOPES = ['https://www.googleapis.com/auth/drive.metadata.readonly']

def get_drive_service():
    cred_path = '/home/takhan/github/tariqk00/plaud/token_drive.json'
    client_secrets = '/home/takhan/github/tariqk00/plaud/credentials.json'
    
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

def walk_drive(service, folder_id, folder_path=""):
    files_info = []
    page_token = None
    
    # Fields to fetch deep metadata
    fields = "nextPageToken, files(id, name, mimeType, createdTime, parents, imageMediaMetadata, videoMediaMetadata)"
    
    while True:
        query = f"'{folder_id}' in parents and trashed = false"
        results = service.files().list(q=query, spaces='drive', fields=fields, pageToken=page_token).execute()
        files = results.get('files', [])
        
        for file in files:
            full_path = f"{folder_path}/{file['name']}"
            if file['mimeType'] == 'application/vnd.google-apps.folder':
                files_info.extend(walk_drive(service, file['id'], full_path))
            else:
                info = {
                    'name': file['name'],
                    'path': full_path,
                    'mimeType': file['mimeType'],
                    'driveCreatedTime': file['createdTime'],
                    'id': file['id']
                }
                
                # Extract Photo Metadata
                if 'imageMediaMetadata' in file:
                    imm = file['imageMediaMetadata']
                    info['photoTakenTime'] = imm.get('time')
                    info['cameraMake'] = imm.get('cameraMake')
                    info['cameraModel'] = imm.get('cameraModel')
                
                # Extract Video Metadata
                if 'videoMediaMetadata' in file:
                    vmm = file['videoMediaMetadata']
                    info['videoTime'] = vmm.get('time')
                
                files_info.append(info)
        
        page_token = results.get('nextPageToken')
        if not page_token:
            break
            
    return files_info

if __name__ == '__main__':
    service = get_drive_service()
    
    # QNAP831X Folder ID from previous run
    ROOT_ID = '1-n34nfXCw6Onz7TLckioIltrTGnZ-cmE'
    
    print(f"Starting deep analysis of QNAP831X (ID: {ROOT_ID})...")
    all_data = walk_drive(service, ROOT_ID, "QNAP831X")
    
    output_file = 'qnap_analysis.json'
    with open(output_file, 'w') as f:
        json.dump(all_data, f, indent=2)
    
    print(f"\nAnalysis complete. Found {len(all_data)} files.")
    print(f"Detailed data saved to {output_file}")
    
    # Print some stats
    mime_counts = {}
    photos_with_metadata = 0
    potential_scans = 0
    
    for item in all_data:
        mime = item['mimeType']
        mime_counts[mime] = mime_counts.get(mime, 0) + 1
        
        if 'photoTakenTime' in item and item['photoTakenTime']:
            photos_with_metadata += 1
        elif item['mimeType'].startswith('image/'):
            potential_scans += 1
            
    print("\nStats Summary:")
    for mime, count in mime_counts.items():
        print(f" - {mime}: {count}")
    
    print(f"\nImages with EXIF/Taken Date: {photos_with_metadata}")
    print(f"Images without Taken Date (potential scans): {potential_scans}")
