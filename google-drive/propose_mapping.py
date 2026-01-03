import json
import re

def parse_path_context(path):
    parts = path.split('/')
    if len(parts) < 2:
        return "Unsorted", "Misc", "Unknown"
    
    parent_folder = parts[-2]
    
    # Pattern A: "01 Sep New York under Attack" (MM-Month - Event)
    match_a = re.search(r'^(\d{2}) ([A-Z][a-z]{2})\s*(.*)', parent_folder)
    if match_a:
        year_short = match_a.group(1)
        month_name = match_a.group(2)
        event_context = match_a.group(3).strip() or parent_folder
        months = {"Jan":"01","Feb":"02","Mar":"03","Apr":"04","May":"05","Jun":"06","Jul":"07","Aug":"08","Sep":"09","Oct":"10","Nov":"11","Dec":"12"}
        month_num = months.get(month_name, "00")
        year_prefix = "20" if int(year_short) < 30 else "19"
        return f"{year_prefix}{year_short}", f"{month_num}-{month_name}", event_context

    # Pattern B: "2010 Spring" or "2007 Summer" (YYYY Season)
    match_b = re.search(r'^(\d{4})\s+(Spring|Summer|Fall|Winter|Autumn)', parent_folder, re.I)
    if match_b:
        year = match_b.group(1)
        season = match_b.group(2).capitalize()
        # Map seasons to approximate middle months
        season_map = {"Spring":"04-Apr", "Summer":"07-Jul", "Autumn":"10-Oct", "Fall":"10-Oct", "Winter":"01-Jan"}
        return year, season_map.get(season, "00-Unknown"), parent_folder

    # Pattern C: "2009-11-15" (YYYY-MM-DD)
    match_c = re.search(r'^(\d{4})-(\d{2})-(\d{2})', parent_folder)
    if match_c:
        year = match_c.group(1)
        month = match_c.group(2)
        return year, month, parent_folder

    return None, None, parent_folder

def propose_mapping(analysis_file):
    with open(analysis_file, 'r') as f:
        data = json.load(f)
        
    mapping = {} 
    
    for item in data:
        # Handle System Files first
        if item['name'].lower() in ['thumbs.db', 'picasa.ini'] or item['mimeType'] == 'application/octet-stream':
             target_path = "_system/files"
             if target_path not in mapping: mapping[target_path] = []
             mapping[target_path].append({'name': item['name'], 'reason': 'System File'})
             continue

        p_year, p_month, p_context = parse_path_context(item['path'])
        
        # Priority 1: EXIF + Folder Context
        if 'photoTakenTime' in item and item['photoTakenTime']:
            target_year = item['photoTakenTime'][:4]
            month_num = item['photoTakenTime'][5:7]
            
            # If folder pattern exists and matches EXIF year/month, use the event context
            if p_year == target_year and p_month.startswith(month_num):
                target_month = f"{p_month} - {p_context}"
            else:
                target_month = f"{month_num} - {p_context}"
            reason = f"EXIF ({item.get('cameraModel', 'Camera')})"
            
        # Priority 2: Folder Pattern only
        elif p_year:
            target_year = p_year
            target_month = f"{p_month} - {p_context}"
            reason = "Folder Pattern"
            
        # Priority 3: No Signal
        else:
            target_year = "Unsorted"
            target_month = p_context
            reason = "No signal"

        target_path = f"{target_year}/{target_month}"
        if target_path not in mapping:
            mapping[target_path] = []
        mapping[target_path].append({
            'name': item['name'],
            'reason': reason
        })
        
    report = []
    for tp in sorted(mapping.keys()):
        files = mapping[tp]
        report.append(f"### {tp}")
        for f in files[:3]: 
            report.append(f"- {f['name']}  *(Reason: {f['reason']})*")
        if len(files) > 3:
            report.append(f"- ... and {len(files)-3} more files.")
        report.append("")
            
    return "\n".join(report)

if __name__ == '__main__':
    print(propose_mapping('qnap_analysis.json'))
