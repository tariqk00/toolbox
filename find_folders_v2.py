
import sys
import os
import json

# Add module path

sys.path.append(os.path.join(os.getcwd(), 'google-drive'))
from drive_organizer import get_drive_service, INBOX_ID

# Load config
config_path = 'google-drive/folder_config.json'
with open(config_path, 'r') as f:
    config = json.load(f)

service = get_drive_service()

parent_map = {
    'Finance': config['mappings']['Finance']['id'],
    'Personal': config['mappings']['Personal']['id']
}

targets = [
    ('Finance', 'Tracking'),
    ('Finance', 'Paycheck'),
    ('Personal', 'ID'),
    ('House', 'House')
]

found = {}

print("Searching...")
for parent_name, child_name in targets:
    if parent_name not in parent_map:
        print(f"Parent {parent_name} not found in config.")
        continue
    
    parent_id = parent_map[parent_name]
    
    # Search
    query = f"'{parent_id}' in parents and name = '{child_name}' and mimeType = 'application/vnd.google-apps.folder' and trashed = false"
    results = service.files().list(q=query, fields="files(id, name)").execute()
    files = results.get('files', [])
    
    if files:
        print(f"Found {parent_name}/{child_name}: {files[0]['id']}")
        found[child_name] = files[0]['id']
    else:
        print(f"NOT Found {parent_name}/{child_name}")

# Print JSON for easy parsing
print("--- JSON ---")
print(json.dumps(found))
