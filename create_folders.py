"""
Batch creates standard subfolder structures (Tracking, Paycheck, ID) 
based on the `folder_config.json` definitions for Finance and Personal categories.
"""

import sys
import os
import json

sys.path.append(os.path.join(os.getcwd(), 'google-drive'))
from drive_organizer import get_drive_service

service = get_drive_service()

# Load config to get parents
config_path = 'google-drive/folder_config.json'
with open(config_path, 'r') as f:
    config = json.load(f)

finance_id = config['mappings']['Finance']['id']
personal_id = config['mappings']['Personal']['id']

folders_to_create = [
    {'name': 'Tracking', 'parent': finance_id},
    {'name': 'Paycheck', 'parent': finance_id},
    {'name': 'ID', 'parent': personal_id}
]

created_ids = {}

print("Creating Folders...")
for item in folders_to_create:
    folder_metadata = {
        'name': item['name'],
        'mimeType': 'application/vnd.google-apps.folder',
        'parents': [item['parent']]
    }
    
    # Check if exists first (safety)
    query = f"'{item['parent']}' in parents and name = '{item['name']}' and mimeType = 'application/vnd.google-apps.folder' and trashed = false"
    results = service.files().list(q=query, fields="files(id, name)").execute()
    files = results.get('files', [])
    
    if files:
        print(f"  [Exists] {item['name']}: {files[0]['id']}")
        created_ids[item['name']] = files[0]['id']
    else:
        file = service.files().create(body=folder_metadata, fields='id').execute()
        print(f"  [Created] {item['name']}: {file.get('id')}")
        created_ids[item['name']] = file.get('id')

print("--- JSON ---")
print(json.dumps(created_ids))
