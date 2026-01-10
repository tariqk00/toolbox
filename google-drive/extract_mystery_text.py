import os
import json
import pypdf
import io
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload

TOKEN_PATH = '/home/takhan/github/tariqk00/toolbox/google-drive/token_full_drive.json'
SCOPES = ['https://www.googleapis.com/auth/drive']
STACK_ID = '1HERen6HP4uDLMXV8Vj_cLOJ3xpT6QV2dLuBVm6z9i__is2Jmw0px2qPhy-72NrlsOhXyLB-Y'

def get_service():
    creds = Credentials.from_authorized_user_file(TOKEN_PATH, SCOPES)
    return build('drive', 'v3', credentials=creds)

def extract_text(file_id, name):
    service = get_service()
    request = service.files().get_media(fileId=file_id)
    fh = io.BytesIO()
    downloader = MediaIoBaseDownload(fh, request)
    done = False
    while done is False:
        status, done = downloader.next_chunk()
    
    fh.seek(0)
    try:
        reader = pypdf.PdfReader(fh)
        text = ""
        # Get first 2 pages for performance and context
        for i in range(min(len(reader.pages), 2)):
            text += reader.pages[i].extract_text() + "\n"
        return text[:2000] # Cap at 2k chars for Gemini ingestion
    except Exception as e:
        return f"[Error extracting text from {name}: {str(e)}]"

def main():
    service = get_service()
    results = service.files().list(
        q=f"'{STACK_ID}' in parents and trashed = false",
        fields="files(id, name, mimeType)"
    ).execute()
    items = results.get('files', [])
    
    audit_data = []
    print(f"Reading {len(items)} files...")
    
    for item in items:
        print(f"Processing: {item['name']}...")
        text = ""
        if item['mimeType'] == 'application/pdf':
            text = extract_text(item['id'], item['name'])
        else:
            text = "[Non-PDF file - Metadata analysis only]"
        
        audit_data.append({
            "name": item['name'],
            "id": item['id'],
            "snippet": text
        })
        
    with open('stack_ai_audit_input.json', 'w') as f:
        json.dump(audit_data, f, indent=2)
        
    print(f"Audit data saved to stack_ai_audit_input.json")

if __name__ == '__main__':
    main()
