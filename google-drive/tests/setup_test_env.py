import sys
import os
import io
import time
from googleapiclient.http import MediaIoBaseUpload

# Add parent directory to path to import drive_organizer
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from drive_organizer import get_drive_service

TEST_ROOT_NAME = "_TEST_SUITE_ANTIGRAVITY"

SCENARIOS = {
    'Inbox': [
        {
            'name': 'work_log_disa.txt',
            'content': 'Meeting with DISA regarding cloud security requirements and logging strategies. Attendees: John, Jane.',
            'mime': 'text/plain',
            'time': '2024-01-10T14:00:00Z' # Wed 2pm UTC (Work Hours)
        },
        {
            'name': 'receipt_home_depot.txt',
            'content': 'Home Depot Receipt. Items: Paint, Brushes, Drop Cloth. Total: $45.00',
            'mime': 'text/plain',
            'time': '2024-01-13T10:00:00Z' # Sat 10am UTC (Weekend - Personal)
        },
        {
            'name': '2024-01-01 - Already_Organized - Notes.txt',
            'content': 'Journal Entry: 2024-01-01. Reflections on the year ahead. Goals include reading 50 books and learning Python.',
            'mime': 'text/plain',
            'time': '2024-01-01T12:00:00Z'
        }
    ],
    'Archive': [
        {
            'name': 'raw_plaud_dump.txt',
            'content': 'Conversation Summary: Discussing vacation plans to Italy.',
            'mime': 'text/plain',
            'time': '2024-02-01T20:00:00Z'
        },
        {
            'name': '2024-05-05 - Work - Protected_File.txt',
            'content': 'Do not rename this file.',
            'mime': 'text/plain',
            'time': '2024-05-05T09:00:00Z'
        }
    ]
}

def find_or_create_folder(service, parent_id, name):
    query = f"mimeType = 'application/vnd.google-apps.folder' and name = '{name}' and '{parent_id}' in parents and trashed = false"
    results = service.files().list(q=query, fields="files(id, name)").execute()
    files = results.get('files', [])
    
    if files:
        return files[0]['id']
    else:
        file_metadata = {
            'name': name,
            'mimeType': 'application/vnd.google-apps.folder',
            'parents': [parent_id]
        }
        file = service.files().create(body=file_metadata, fields='id').execute()
        return file.get('id')

def delete_children(service, folder_id):
    query = f"'{folder_id}' in parents and trashed = false"
    results = service.files().list(q=query, fields="files(id, name)").execute()
    files = results.get('files', [])
    
    print(f"Deleting {len(files)} files in {folder_id}...")
    for f in files:
        try:
            service.files().delete(fileId=f['id']).execute()
        except:
            pass

def upload_file(service, parent_id, name, content, created_time=None):
    file_metadata = {
        'name': name,
        'parents': [parent_id]
    }
    if created_time:
        file_metadata['createdTime'] = created_time
        
    media = MediaIoBaseUpload(io.BytesIO(content.encode('utf-8')), mimetype='text/plain')
    
    service.files().create(body=file_metadata, media_body=media, fields='id').execute()
    print(f"  + Uploaded: {name}")

def main():
    service = get_drive_service()
    
    # 1. Find/Create Root Test Folder
    root_id = find_or_create_folder(service, 'root', TEST_ROOT_NAME)
    print(f"Test Root ID: {root_id}")
    
    # 2. Reset (Delete all children)
    delete_children(service, root_id)
    
    # 3. Create Structure
    inbox_id = find_or_create_folder(service, root_id, 'Inbox')
    work_id = find_or_create_folder(service, root_id, 'Work')
    archive_id = find_or_create_folder(service, root_id, 'Archive')
    
    # 4. Populate Inbox
    print("Populating Inbox...")
    for item in SCENARIOS['Inbox']:
        upload_file(service, inbox_id, item['name'], item['content'], item['time'])
        
    # 5. Populate Archive
    print("Populating Archive...")
    for item in SCENARIOS['Archive']:
        upload_file(service, archive_id, item['name'], item['content'], item['time'])

    print("\n--- Test Environment Ready ---")
    print(f"Inbox ID: {inbox_id}")
    print(f"Work ID: {work_id}")
    print(f"Archive ID: {archive_id}")
    
    # Write IDs to a json file for the runner to use
    import json
    with open('test_config.json', 'w') as f:
        json.dump({
            'root_id': root_id,
            'inbox_id': inbox_id,
            'work_id': work_id,
            'archive_id': archive_id
        }, f)

if __name__ == "__main__":
    main()
