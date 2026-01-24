
import sys
import os
# Add repo root to path
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if REPO_ROOT not in sys.path:
    sys.path.append(REPO_ROOT)

"""
Diagnostic script to verify if high-priority folders (Finance, Personal) 
are correctly resolvable via the `folder_config.json` mapping.
"""

import os
import json
from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request

# Load existing config to get parent IDs
config_path = 'google-drive/folder_config.json'
with open(config_path, 'r') as f:
    config = json.load(f)

SCOPES = ['https://www.googleapis.com/auth/drive']
creds = None
if os.path.exists('google-drive/token.json'):
    creds = Credentials.from_authorized_user_file('google-drive/token.json', SCOPES)

if not creds or not creds.valid:
    if creds and creds.expired and creds.refresh_token:
        creds.refresh(Request())

service = build('drive', 'v3', credentials=creds)

parent_map = {
    'Finance': config['mappings']['Finance']['id'],
    'Personal': config['mappings']['Personal']['id']
}

targets = [
    ('Finance', 'Tracking'),
    ('Finance', 'Paycheck'),
    ('Personal', 'ID'),
    ('House', 'House') # House mapping is seemingly direct or undefined subcat? Config says House -> id.
]

found = {}

for parent_name, child_name in targets:
    if parent_name not in parent_map:
        print(f"Parent {parent_name} not found in config.")
        continue
    
    parent_id = parent_map[parent_name]
    
    # Search for child folder inside parent
    query = f"'{parent_id}' in parents and name = '{child_name}' and mimeType = 'application/vnd.google-apps.folder' and trashed = false"
    results = service.files().list(q=query, fields="files(id, name)").execute()
    files = results.get('files', [])
    
    if files:
        print(f"Found {parent_name}/{child_name}: {files[0]['id']}")
        found[f"{parent_name}/{child_name}"] = files[0]['id']
    else:
        print(f"NOT Found {parent_name}/{child_name}")

print("--- RESULTS ---")
print(json.dumps(found))