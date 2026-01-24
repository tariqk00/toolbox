"""
Analyzes files in the Plaud cabinet to identify related groups (e.g., Audio + Transcript).
Uses regex normalization to match filenames despite suffixes like 'Summary' or 'Transcript'.
"""

import sys
import os
import re


import sys
import os
# Add repo root to path
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if REPO_ROOT not in sys.path:
    sys.path.append(REPO_ROOT)

from toolbox.lib.drive_utils import get_drive_service

service = get_drive_service()
PLAUD_CABINET_ID = "1c-7Wv9J-FPpc3tph7Ax1xx5bMI-5jcaG" # ID found in earlier log for 'Plaud' parent

def list_and_group_files():
    # 1. Get all files
    results = service.files().list(
        q=f"'{PLAUD_CABINET_ID}' in parents and trashed = false",
        fields="files(id, name, createdTime)",
        pageSize=500
    ).execute()
    
    files = results.get('files', [])
    print(f"Found {len(files)} files in Filing Cabinet / Plaud.")
    
    # 2. Group by "Base Name" 
    # Logic: Strip extension, strip common suffixes (summary, transcript), strip date prefix if needed.
    groups = {}
    
    for f in files:
        name = f['name']
        
        # Simplified normalization:
        # 1. Remove Extension
        base = os.path.splitext(name)[0]
        # 2. Remove common suffixes
        base = re.sub(r'[_ -]?(summary|transcript|PlauIAI)', '', base, flags=re.IGNORECASE).strip()
        # 3. Remove date prefix? strict timestamp matching is hard, but let's try just grouping by the remainder
        
        if base not in groups:
            groups[base] = []
        groups[base].append(name)
        
    # 3. Print Groups with > 1 item
    print("\n--- Potential Relationships (Grouped by Name) ---")
    count = 0
    for base, items in groups.items():
        if len(items) > 1:
            count += 1
            print(f"\nGroup: '{base}'")
            for i in items:
                print(f"  - {i}")
                
    if count == 0:
        print("No obvious groups found by name matching.")
        print("\n--- All Files Sample ---")
        for f in files[:20]:
            print(f"  {f['name']}")

list_and_group_files()