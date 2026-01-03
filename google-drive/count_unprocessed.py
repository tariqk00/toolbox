import json
import re

def parse_path_date(path):
    parts = path.split('/')
    if len(parts) < 2: return False
    parent = parts[-2]
    # Pattern A: 01 Sep...
    if re.search(r'^(\d{2}) ([A-Z][a-z]{2})', parent): return True
    # Pattern B: 2010 Spring...
    if re.search(r'^(\d{4})\s+(Spring|Summer|Fall|Winter|Autumn)', parent, re.I): return True
    # Pattern C: 2009-11-15...
    if re.search(r'^(\d{4})-(\d{2})-(\d{2})', parent): return True
    return False

def count_unprocessed(analysis_file):
    with open(analysis_file, 'r') as f:
        data = json.load(f)
    
    total = len(data)
    exif = 0
    folder_hint = 0
    system = 0
    unprocessed = 0
    
    breakdown = {}

    for item in data:
        # 1. System Files
        if item['name'].lower() in ['thumbs.db', 'picasa.ini'] or item['mimeType'] == 'application/octet-stream':
            system += 1
            continue
            
        # 2. EXIF
        if item.get('photoTakenTime'):
            exif += 1
            continue
            
        # 3. Folder Hint
        if parse_path_date(item['path']):
            folder_hint += 1
            continue
            
        # 4. Unprocessed
        unprocessed += 1
        parent = item['path'].split('/')[-2] if '/' in item['path'] else "Root"
        breakdown[parent] = breakdown.get(parent, 0) + 1
            
    print(f"Total Files Analyzed: {total}")
    print(f"  - Organized by EXIF: {exif}")
    print(f"  - Organized by Folder Name: {folder_hint}")
    print(f"  - System Files (Cleaned): {system}")
    print(f"  - UNPROCESSED: {unprocessed}")
    print("\nBreakdown of Unprocessed by Parent Folder:")
    for folder, count in sorted(breakdown.items(), key=lambda x: x[1], reverse=True):
        print(f"    - {folder}: {count}")

if __name__ == '__main__':
    count_unprocessed('qnap_analysis.json')
