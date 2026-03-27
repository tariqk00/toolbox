import sys
sys.path.append('/home/tariqk/github/tariqk00')
from toolbox.lib.google_api import GoogleAuth
from datetime import datetime, timedelta

def get_drive_service():
    auth = GoogleAuth()
    return auth.get_service('drive', 'v3')

def main():
    service = get_drive_service()
    ids = {"Plaud": "1lDD6SUh918U6oXjOBB5I9SjFVDAlqjzR", "Transcripts": "1ZZf0FAoIXR6T_PzlibUEp7fQxiUbrZST"}
    
    time_limit = (datetime.utcnow() - timedelta(hours=2)).isoformat() + "Z"
    
    for name, folder_id in ids.items():
        print(f"--- Checking {name} ({folder_id}) ---")
        try:
            query = f"'{folder_id}' in parents and createdTime > '{time_limit}'"
            results = service.files().list(q=query, fields="files(id, name, createdTime, mimeType)").execute()
            files = results.get('files', [])
            if not files:
                print("  No recent files found.")
            else:
                for f in files:
                    print(f"  FOUND: {f['name']} (created: {f['createdTime']}, type: {f['mimeType']})")
        except Exception as e:
            print(f"  Error: {e}")

if __name__ == '__main__':
    main()
