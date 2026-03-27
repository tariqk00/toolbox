import sys
sys.path.append('/home/tariqk/repos/personal')

from toolbox.lib.google_api import GoogleAuth

def get_drive_service():
    auth = GoogleAuth()
    return auth.get_service('drive', 'v3')

def main():
    service = get_drive_service()
    ids = ["1lDD6SUh918U6oXjOBB5I9SjFVDAlqjzR", "1ZZf0FAoIXR6T_PzlibUEp7fQxiUbrZST"]
    
    for folder_id in ids:
        try:
            folder = service.files().get(fileId=folder_id, fields="name").execute()
            print(f"ID: {folder_id} -> NAME: {folder.get('name')}")
        except Exception as e:
            print(f"ID: {folder_id} -> Error: {e}")

if __name__ == '__main__':
    main()
