
import os
import re

REPLACEMENTS = [
    (r'from drive_organizer import get_drive_service', r'from toolbox.lib.drive_utils import get_drive_service'),
    (r'from drive_organizer import get_sheets_service', r'from toolbox.lib.drive_utils import get_sheets_service'),
    (r'from drive_organizer import INBOX_ID', r'from toolbox.lib.drive_utils import INBOX_ID'),
    (r'from drive_organizer import HISTORY_SHEET_ID', r'from toolbox.lib.drive_utils import HISTORY_SHEET_ID'),
    (r'from drive_organizer import METADATA_FOLDER_ID', r'from toolbox.lib.drive_utils import METADATA_FOLDER_ID'),
    (r'from drive_organizer import load_api_key', r'from toolbox.lib.ai_engine import load_api_key'),
    (r'from drive_organizer import SECRET_PATH', r'from toolbox.lib.ai_engine import SECRET_PATH'),
    (r'from drive_organizer import scan_folder', r'from toolbox.services.drive_organizer.main import scan_folder'),
    # Compound imports
    (r'from drive_organizer import .*scan_folder.*', r'from toolbox.services.drive_organizer.main import scan_folder\nfrom toolbox.lib.drive_utils import get_drive_service, FOLDER_MAP'),
     # Fix potential double imports created by split logic by just being naive first?
     # If a line imports multiple things that are now in different files, I need to split the line.
     # e.g. "from drive_organizer import get_drive_service, INBOX_ID" -> all in drive_utils so fine.
     # "from drive_organizer import get_drive_service, load_api_key" -> mixed!
]

def fix_file(filepath):
    with open(filepath, 'r') as f:
        content = f.read()
    
    new_content = content
    
    # 1. Handle Mixed Imports specifically
    if "from drive_organizer import" in content:
        # Check what is being imported
        pattern = r"from drive_organizer import (.*)"
        def replace(match):
            imports = [x.strip() for x in match.group(1).split(',')]
            
            drive_utils_imports = []
            ai_imports = []
            service_imports = []
            
            for imp in imports:
                if imp in ['get_drive_service', 'get_sheets_service', 'load_folder_config', 'INBOX_ID', 'HISTORY_SHEET_ID', 'METADATA_FOLDER_ID', 'FOLDER_MAP', 'resolve_folder_id', 'move_file', 'download_file_content']:
                    drive_utils_imports.append(imp)
                elif imp in ['load_api_key', 'SECRET_PATH']:
                    ai_imports.append(imp)
                elif imp in ['scan_folder', 'stats', 'RunStats']:
                    service_imports.append(imp)
                else:
                    drive_utils_imports.append(imp) # validation? assume drive utils for others
            
            lines = []
            if drive_utils_imports:
                lines.append(f"from toolbox.lib.drive_utils import {', '.join(drive_utils_imports)}")
            if ai_imports:
                lines.append(f"from toolbox.lib.ai_engine import {', '.join(ai_imports)}")
            if service_imports:
                lines.append(f"from toolbox.services.drive_organizer.main import {', '.join(service_imports)}")
                
            return "\n".join(lines)
            
        new_content = re.sub(pattern, replace, content)

    if new_content != content:
        print(f"Fixed {filepath}")
        with open(filepath, 'w') as f:
            f.write(new_content)

def main():
    dirs = ['toolbox/bin', 'toolbox/google-drive']
    for d in dirs:
        if not os.path.exists(d): continue
        for root, _, files in os.walk(d):
            for file in files:
                if file.endswith('.py'):
                    fix_file(os.path.join(root, file))

if __name__ == "__main__":
    main()
