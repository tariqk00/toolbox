import os
import sys
import time
import json
import logging
from datetime import datetime

# Ensure toolbox package is in path
current_dir = os.path.dirname(os.path.abspath(__file__))
repo_root = os.path.dirname(os.path.dirname(os.path.dirname(current_dir)))
if repo_root not in sys.path:
    sys.path.append(repo_root)

from toolbox.lib.drive_utils import (
    get_drive_service, get_sheets_service,
    FOLDER_CONFIG, HISTORY_SHEET_ID
)

# --- CONFIG ---
_toolbox_root = os.path.join(repo_root, 'toolbox')
REPORT_DIR_ID = FOLDER_CONFIG.get('system', {}).get('reports_folder_id', '')
RECOMMENDATIONS_PATH = os.path.join(_toolbox_root, 'config', 'category_recommendations.json')

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("MonthlyReview")

def get_recent_activity():
    """Fetches last 30 days of activity from Google Sheets."""
    if not HISTORY_SHEET_ID:
        return []

    try:
        service = get_sheets_service()
        result = service.spreadsheets().values().get(
            spreadsheetId=HISTORY_SHEET_ID, range="Log!A:F"
        ).execute()
        rows = result.get('values', [])
        if len(rows) <= 1: return []
        
        # Simple filtering for "recent" (last month)
        # Assuming first col is timestamp YYYY-MM-DD
        return rows[1:] 
    except Exception as e:
        logger.error(f"Error fetching activity: {e}")
        return []

def get_folder_stats(service):
    """Counts files in mapped folders."""
    stats = {}
    mappings = FOLDER_CONFIG.get('mappings', {})
    
    for category, data in mappings.items():
        fid = data.get('id')
        if not fid: continue
        
        results = service.files().list(
            q=f"'{fid}' in parents and trashed = false",
            fields="files(id)"
        ).execute()
        stats[category] = len(results.get('files', []))
        
        subcats = data.get('subcategories', {})
        for sub, sub_id in subcats.items():
            res = service.files().list(
                q=f"'{sub_id}' in parents and trashed = false",
                fields="files(id)"
            ).execute()
            stats[f"{category}/{sub}"] = len(res.get('files', []))
            
    return stats

def get_recommendations():
    if os.path.exists(RECOMMENDATIONS_PATH):
        with open(RECOMMENDATIONS_PATH, 'r') as f:
            return json.load(f)
    return {}

def generate_report():
    service = get_drive_service()
    activity = get_recent_activity()
    stats = get_folder_stats(service)
    recs = get_recommendations()
    
    report_date = datetime.now().strftime("%Y-%m")
    report_name = f"Monthly AI Sorter Review - {report_date}"
    
    md_content = f"# AI Sorter Health Report: {report_date}\n\n"
    
    # 1. Activity Summary
    total_actions = len(activity)
    renames = len([r for r in activity if 'Rename' in r[5]])
    moves = len([r for r in activity if 'Move' in r[5]])
    
    md_content += "## Activity Overview\n"
    md_content += f"- **Total Actions Logged**: {total_actions}\n"
    md_content += f"- **Auto-Renames**: {renames}\n"
    md_content += f"- **Auto-Moves**: {moves}\n\n"
    
    # 2. Folder Stats
    md_content += "## Folder Distribution\n"
    md_content += "| Category | File Count |\n| :--- | :--- |\n"
    # Sort by count descending
    sorted_stats = sorted(stats.items(), key=lambda x: x[1], reverse=True)
    for cat, count in sorted_stats[:10]: # Top 10
        md_content += f"| {cat} | {count} |\n"
    md_content += "\n"
    
    # 3. Recommendations
    if recs:
        md_content += "## AI Recommendations (Sub-folder suggestions)\n"
        md_content += "| Proposed Category | Request Count |\n| :--- | :--- |\n"
        for cat, count in sorted(recs.items(), key=lambda x: x[1], reverse=True):
            md_content += f"| {cat} | {count} |\n"
        md_content += "\n"
    
    # Upload to Drive
    file_metadata = {
        'name': report_name,
        'parents': [REPORT_DIR_ID],
        'mimeType': 'text/markdown'
    }
    
    # Using simple media upload for text
    from googleapiclient.http import MediaIoBaseUpload
    import io
    
    fh = io.BytesIO(md_content.encode('utf-8'))
    media = MediaIoBaseUpload(fh, mimetype='text/markdown', resumable=True)
    
    try:
        service.files().create(body=file_metadata, media_body=media, fields='id').execute()
        logger.info(f"Report uploaded successfully: {report_name}")
    except Exception as e:
        logger.error(f"Error uploading report: {e}")

if __name__ == "__main__":
    generate_report()
