import json
from collections import Counter

def analyze_json(file_path):
    with open(file_path, 'r') as f:
        data = json.load(f)
    
    cameras = Counter()
    dates = Counter()
    folders = Counter()
    potential_scans = []
    native_digital = []
    
    for item in data:
        # Track camera models
        if 'cameraModel' in item and item['cameraModel']:
            cameras[item['cameraModel']] += 1
            native_digital.append(item)
        elif item['mimeType'].startswith('image/'):
            potential_scans.append(item)
            
        # Track folder patterns
        path_parts = item['path'].split('/')
        if len(path_parts) > 2:
            folders[path_parts[-2]] += 1
            
        # Track Taken Dates (just the year-month)
        if 'photoTakenTime' in item and item['photoTakenTime']:
            dates[item['photoTakenTime'][:7]] += 1
            
    print("--- Top Camera Models ---")
    for cam, count in cameras.most_common(10):
        print(f"{cam}: {count}")
        
    print("\n--- Top Folders with Many Files ---")
    for folder, count in folders.most_common(10):
        print(f"{folder}: {count}")
        
    print("\n--- Top Taken Date Clusters (Year-Month) ---")
    for date, count in dates.most_common(10):
        print(f"{date}: {count}")

    print(f"\nTotal potential scans (No EXIF): {len(potential_scans)}")
    print("Sample filenames for potential scans:")
    for item in potential_scans[:10]:
        print(f" - {item['path']}")

if __name__ == '__main__':
    analyze_json('qnap_analysis.json')
