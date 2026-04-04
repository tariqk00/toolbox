import os
import zipfile
import datetime
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

def backup_workspace():
    # Paths
    workspace_path = "/home/tariqk/.openclaw/workspace"
    backup_filename = f"/tmp/workspace_backup_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.zip"
    
    # Create ZIP
    with zipfile.ZipFile(backup_filename, 'w', zipfile.ZIP_DEFLATED) as zipf:
        for root, dirs, files in os.walk(workspace_path):
            for file in files:
                if ".git" not in root and "memory/2026-04-03.md" not in file:
                    zipf.write(os.path.join(root, file), os.path.relpath(os.path.join(root, file), "/home/tariqk/"))
    
    # Upload would go here using the same approach as before
    # For now, I'm verifying the script runs cleanly
    print(f"Backup created at: {backup_filename}")
    return backup_filename

if __name__ == "__main__":
    backup_workspace()
