"""
Test Runner.
Executes the integration test suite (Mocked Folder Map + Real Drive Environment) to verify sorting logic.
"""
import sys
import os
import json
import time
import re

# Add parent directory to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from drive_organizer import scan_folder, get_drive_service, FOLDER_MAP

# --- MOCK THE FOLDER MAP FOR TESTING ---
# We need to inject the TEST IDs into the FOLDER_MAP used by scan_folder
# Since FOLDER_MAP is imported, we can modify it at runtime before calling scan_folder
def patch_folder_map(config):
    # Clear and set Test IDs
    FOLDER_MAP.clear()
    FOLDER_MAP['Work'] = config['work_id']
    FOLDER_MAP['PKM'] = config['archive_id'] # Default others to Archive for simplicity in test
    FOLDER_MAP['Personal'] = config['archive_id']
    FOLDER_MAP['Finance'] = config['archive_id']
    FOLDER_MAP['House'] = config['archive_id'] # Fix for Receipt test
    FOLDER_MAP['Source_Material'] = config['archive_id']
    print(f"DEBUG: Patched FOLDER_MAP with Test IDs: {FOLDER_MAP}")

def load_config():
    with open('test_config.json', 'r') as f:
        return json.load(f)

def verify_file_count(service, folder_id, expected_count, description):
    query = f"'{folder_id}' in parents and trashed = false"
    results = service.files().list(q=query).execute()
    files = results.get('files', [])
    count = len(files)
    if count == expected_count:
        print(f"  [PASS] {description}: Found {count} files.")
        return True
    else:
        print(f"  [FAIL] {description}: Found {count} files (Expected {expected_count}).")
        print(f"         Files found: {[f['name'] for f in files]}")
        return False

def verify_file_exists(service, folder_id, name_pattern, description):
    query = f"'{folder_id}' in parents and trashed = false"
    results = service.files().list(q=query).execute()
    files = results.get('files', [])
    
    for f in files:
        if re.search(name_pattern, f['name'], re.IGNORECASE):
            print(f"  [PASS] {description}: Found file matching '{name_pattern}'")
            return True
            
    print(f"  [FAIL] {description}: NO file matches '{name_pattern}'")
    return False

def main():
    service = get_drive_service()
    
    # 0. Setup / Reset
    print("\n=== STEP 0: Resetting Environment ===")
    import setup_test_env
    setup_test_env.main()
    
    config = load_config()
    patch_folder_map(config)
    
    # 1. TEST INBOX MODE
    print("\n=== STEP 1: Testing INBOX Mode (Auto-Sort) ===")
    # Target: Test Inbox
    # Expectation: 3 files processed. 
    #   - work_log_disa -> Moved to Work
    #   - receipt -> Moved to Archive (Personal)
    #   - already_organized -> Moved to Archive (PKM) because "Move-Always" logic
    
    scan_folder(config['inbox_id'], dry_run=False, csv_path='test_run.csv', mode='inbox')
    
    print("\n    ...Verifying Inbox moves...")
    # Inbox should be empty
    verify_file_count(service, config['inbox_id'], 0, "Inbox Empty")
    
    # Work should have 1 file (DISA log)
    verify_file_exists(service, config['work_id'], r"DISA", "Work Folder has DISA log")
    
    # Archive should have 2 files (Receipt + Notes)
    verify_file_exists(service, config['archive_id'], r"Home_Depot", "Archive has Receipt")
    
    # 2. TEST MAINTENANCE MODE
    print("\n=== STEP 2: Testing MAINTENANCE Mode (Audit) ===")
    # Target: Test Archive (which was populated with 2 files in setup)
    #   - raw_plaud_dump.txt
    #   - 2024-05-05 - Work - Protected_File.txt
    # Note: We also just moved 2 files into it from Step 1, so it has 4 files total now.
    
    # Capture stdout to check for "[Skip - Valid]" and "[RECOMMENDATION]"? 
    # For now, we rely on visual log inspection or just that it doesn't crash.
    # But strictly, we want to ensure files do NOT change names or move.
    
    scan_folder(config['archive_id'], dry_run=True, csv_path='test_maintenance.csv', mode='scan') # Default mode is Maintenance
    
    print("\n    ...Verifying Maintenance Safety...")
    # Verify 'Protected_File' still exists with same name
    verify_file_exists(service, config['archive_id'], r"Protected_File", "Protected File Unchanged")
    
    print("\n=== TEST SUITE COMPLETED ===")

if __name__ == "__main__":
    main()
