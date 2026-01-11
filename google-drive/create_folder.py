from drive_organizer import get_drive_service

def create_work_folder():
    service = get_drive_service()
    parent_id = '1HNKo72TkLeurAi6g7X0C90OzqF2z3YB7' # 01 - Second Brain
    folder_name = 'Work'
    
    file_metadata = {
        'name': folder_name,
        'mimeType': 'application/vnd.google-apps.folder',
        'parents': [parent_id]
    }
    
    file = service.files().create(body=file_metadata, fields='id').execute()
    print(f"Created folder: Work ID: {file.get('id')}")

if __name__ == "__main__":
    create_work_folder()
