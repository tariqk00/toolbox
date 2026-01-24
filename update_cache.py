"""
Manually updates the `gemini_cache.json` database based on user overrides 
provided in a local CSV file.
"""

import json
import csv
import sys
import os

# Map numeric ID from user table to csv rows
# My table was 1-indexed based on tail -n 35.
# Let's read the last 35 lines of csv to reconstruct the map.

CACHE_PATH = 'google-drive/gemini_cache.json'
CSV_PATH = 'sorter_dry_run.csv'

def load_cache():
    if os.path.exists(CACHE_PATH):
        with open(CACHE_PATH, 'r') as f:
            return json.load(f)
    return {}

def save_cache(cache):
    with open(CACHE_PATH, 'w') as f:
        json.dump(cache, f, indent=2)

# User Instructions
# Finance/Tracking -> 1, 3, 4, 6, 7, 8, 13, 14, 16, 17, 18, 19, 22, 23
# Personal/ID -> 35
# Finance/Paycheck -> 9, 10
# House -> 34, 21, 20

MAPPING = {
    'House': [2],
    'Other': [3],
    'Finance/Tracking': [5, 6, 7, 8, 9, 10, 11],
    'Personal': [12]
}

# 1. Read CSV to get File IDs
fieldnames = ['id', 'original', 'proposed', 'category', 'confidence']
rows = []
with open(CSV_PATH, 'r') as f:
    # Read all lines first
    lines = f.readlines()
    # Get last 19
    tail_lines = lines[-19:]
    
    # Parse with DictReader using explicit headers
    from io import StringIO
    reader = csv.DictReader(tail_lines, fieldnames=fieldnames)
    rows = list(reader)

print(f"Loaded {len(rows)} rows from CSV tail.")

# 2. Update Cache
cache = load_cache()
updated_count = 0

for category, indices in MAPPING.items():
    for idx in indices:
        # User index is 1-based, list is 0-based
        list_idx = idx - 1
        if list_idx < 0 or list_idx >= len(rows):
            print(f"Skipping invalid index {idx}")
            continue
            
        row = rows[list_idx]
        try:
            fid = row['id']
            name = row['original']
        except KeyError as e:
            print(f"KeyError: {e}. Available keys: {list(row.keys())}")
            # Try parsing unkeyed if header is missing? Or just skip.
            # Maybe the header is malformed?
            continue
        
        if fid not in cache:
            # Create default entry for unsupported/new files
            print(f"Creating New Cache Entry: [{idx}] {name} -> {category}")
            cache[fid] = {
                "doc_date": "0000-00-00", 
                "entity": "User_Manual", 
                "category": category, 
                "summary": "Manual_Override",
                "confidence": "High"
            }
            updated_count += 1
        else:
            print(f"Updating Cache: [{idx}] {name} -> {category}")
            cache[fid]['category'] = category
            cache[fid]['confidence'] = 'High'
            updated_count += 1

# 3. Save
save_cache(cache)
print(f"Done. Updated {updated_count} entries.")
