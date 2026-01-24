"""
One-time migration script to move local CSV logs (`renaming_history.csv`) 
into a Google Sheet (`AI_Sorter_History`) for better tracking.
"""
from drive_organizer import get_drive_service, METADATA_FOLDER_ID
from googleapiclient.discovery import build
import csv
import os

SHEET_NAME = "AI_Sorter_History"

def get_sheets_service(creds):
    return build('sheets', 'v4', credentials=creds)

def migrate():
    # 1. Setup Services
    drive_service = get_drive_service()
    creds = drive_service._http.credentials
    sheets_service = get_sheets_service(creds)

    # 2. Check if Sheet Exists
    print(f"Checking for existing sheet '{SHEET_NAME}'...")
    query = f"'{METADATA_FOLDER_ID}' in parents and name = '{SHEET_NAME}' and mimeType = 'application/vnd.google-apps.spreadsheet' and trashed = false"
    results = drive_service.files().list(q=query, fields="files(id)").execute()
    files = results.get('files', [])

    spreadsheet_id = None
    if files:
        spreadsheet_id = files[0]['id']
        print(f"Found existing sheet: {spreadsheet_id}")
    else:
        print("Creating new sheet...")
        spreadsheet_body = {
            'properties': {'title': SHEET_NAME},
            'sheets': [{'properties': {'title': 'Log'}}]
        }
        spreadsheet = sheets_service.spreadsheets().create(body=spreadsheet_body, fields='spreadsheetId').execute()
        spreadsheet_id = spreadsheet.get('spreadsheetId')
        
        # Move to Metadata Folder
        # Create puts it in root, need to add parent
        # Actually 'create' doesn't support parents directly easily in v4 sheets.
        # We use Drive API to move it.
        file = drive_service.files().get(fileId=spreadsheet_id, fields='parents').execute()
        previous_parents = ",".join(file.get('parents'))
        drive_service.files().update(fileId=spreadsheet_id, addParents=METADATA_FOLDER_ID, removeParents=previous_parents).execute()
        print(f"Created and moved sheet: {spreadsheet_id}")

        # Add Header
        header = [['Timestamp', 'ID', 'Original', 'New', 'Target_Folder', 'Run_Type']]
        sheets_service.spreadsheets().values().append(
            spreadsheetId=spreadsheet_id, range="Log!A1",
            valueInputOption="RAW", body={'values': header}
        ).execute()

        # Get SheetId (it might not be 0)
        sheet_metadata = sheets_service.spreadsheets().get(spreadsheetId=spreadsheet_id).execute()
        sheet_id = sheet_metadata['sheets'][0]['properties']['sheetId']

        # Format Header (Bold, Freeze)
        requests = [
            {"repeatCell": {"range": {"sheetId": sheet_id, "startRowIndex": 0, "endRowIndex": 1}, "cell": {"userEnteredFormat": {"textFormat": {"bold": True}}}, "fields": "userEnteredFormat.textFormat.bold"}},
            {"updateSheetProperties": {"properties": {"sheetId": sheet_id, "gridProperties": {"frozenRowCount": 1}}, "fields": "gridProperties.frozenRowCount"}}
        ]
        sheets_service.spreadsheets().batchUpdate(spreadsheetId=spreadsheet_id, body={'requests': requests}).execute()

    # 3. Read CSV Data
    all_rows = []
    
    # Legacy
    # Actually, legacy file is on server or Drive?
    # I verified user has _legacy_backup_jan10.csv on Drive.
    # But locally I might have renaming_history.csv.
    # Let's read LOCAL CSVs first.
    
    files_to_read = ['renaming_history.csv']
    # If legacy backup exists locally, read it too.
    # (In previous steps I renamed the remote file, I didn't verify local presence of backup name).
    # I'll just migrate 'renaming_history.csv' which I confirmed has EVERYTHING (merged).
    
    for fname in files_to_read:
        if os.path.exists(fname):
            print(f"Reading {fname}...")
            with open(fname, 'r') as f:
                reader = csv.reader(f)
                rows = list(reader)
                if rows and rows[0][0] == 'Timestamp':
                    rows = rows[1:] # Skip header
                all_rows.extend(rows)

    if not all_rows:
        print("No data found to migrate.")
        return

    print(f"Migrating {len(all_rows)} rows...")
    
    # 4. Append Data
    # Batch in chunks of 500?
    batch_size = 500
    for i in range(0, len(all_rows), batch_size):
        chunk = all_rows[i:i+batch_size]
        body = {'values': chunk}
        sheets_service.spreadsheets().values().append(
            spreadsheetId=spreadsheet_id, range="Log!A1",
            valueInputOption="USER_ENTERED", body=body
        ).execute()
        print(f"  Appended rows {i} to {i+len(chunk)}")

    print(f"\nSUCCESS. Sheet ID: {spreadsheet_id}")
    print("Please update drive_organizer.py with this ID.")

if __name__ == "__main__":
    migrate()
