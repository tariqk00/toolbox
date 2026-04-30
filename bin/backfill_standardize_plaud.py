#!/usr/bin/env python3
"""
Backfill script to reorganize existing Plaud recordings into the new standardized structure:
Plaud/[Category]/[Year]/[YYYY-MM-DD - Subject].md
"""
import sys
import os
import re
import argparse
from pathlib import Path

# Setup paths
BIN_DIR = Path(__file__).resolve().parent
REPO_ROOT = BIN_DIR.parent
if str(REPO_ROOT.parent) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT.parent))

from toolbox.lib.drive_utils import get_drive_service, move_file
from toolbox.services.email_extractor.writers import _resolve_path, MEMORY_ROOT
from toolbox.bin.standardize_plaud import get_category, get_standard_path

def backfill(dry_run=True):
    service = get_drive_service()
    legacy_folder_path = f"{MEMORY_ROOT}/Plaud"
    
    print(f"--- Standardizing Plaud Folder Structure (dry_run={dry_run}) ---")
    
    # 1. Resolve Legacy Folder ID
    try:
        legacy_folder_id = _resolve_path(service, legacy_folder_path)
    except Exception as e:
        print(f"Error: Could not resolve legacy folder {legacy_folder_path}: {e}")
        return

    # 2. List all files in the legacy folder
    query = f"'{legacy_folder_id}' in parents and mimeType = 'text/markdown' and trashed = false"
    results = service.files().list(q=query, fields="files(id, name)").execute()
    files = results.get('files', [])
    
    if not files:
        print("No files found to reorganize.")
        return

    print(f"Found {len(files)} files. Starting reorganization...")

    stats = {"moved": 0, "errors": 0, "skipped": 0}

    for f in files:
        file_id = f['id']
        name = f['name']
        
        # Extract date from filename (YYYY-MM-DD)
        date_match = re.search(r'^(\d{4}-\d{2}-\d{2})', name)
        if not date_match:
            print(f"  [Skip] Could not parse date from filename: {name}")
            stats["skipped"] += 1
            continue
        doc_date = date_match.group(1)

        # 3. Read content for categorization
        try:
            content_bytes = service.files().get_media(fileId=file_id).execute()
            content = content_bytes.decode('utf-8') if isinstance(content_bytes, bytes) else content_bytes
        except Exception as e:
            print(f"  [Error] Failed to read {name}: {e}")
            stats["errors"] += 1
            continue

        # 4. Determine New Path
        category = get_category(name, content)
        new_rel_path = get_standard_path(category, doc_date)
        new_full_path = f"{MEMORY_ROOT}/{new_rel_path}"
        
        print(f"  [Target] {name} -> {new_rel_path}")

        if dry_run:
            stats["moved"] += 1
            continue

        # 5. Execute Move
        try:
            target_folder_id = _resolve_path(service, new_full_path)
            if move_file(service, file_id, target_folder_id, name):
                print(f"    ✓ Moved.")
                stats["moved"] += 1
            else:
                print(f"    ✗ Move failed.")
                stats["errors"] += 1
        except Exception as e:
            print(f"    ✗ Error moving file: {e}")
            stats["errors"] += 1

    print("\n--- Summary ---")
    print(f"Processed: {len(files)}")
    print(f"Moved:     {stats['moved']}")
    print(f"Skipped:   {stats['skipped']}")
    print(f"Errors:    {stats['errors']}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Backfill Plaud folder standardization.")
    parser.add_argument("--run", action="store_true", help="Actually move the files (default is dry-run)")
    args = parser.parse_args()
    
    backfill(dry_run=not args.run)
