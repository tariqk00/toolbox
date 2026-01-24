"""
Queries the Google Sheet Activity Log for operations performed "Today".
Useful for verifying daily automation runs.
"""
from drive_organizer import get_sheets_service, HISTORY_SHEET_ID
import datetime

def check_today():
    today_str = datetime.datetime.now().strftime("%Y-%m-%d")
    print(f"Checking for logs from: {today_str}")

    service = get_sheets_service()
    
    # Read entire log (or reasonable last chunk)
    result = service.spreadsheets().values().get(
        spreadsheetId=HISTORY_SHEET_ID, range="Log!A:F"
    ).execute()
    
    rows = result.get('values', [])
    if not rows:
        print("No logs found.")
        return

    headers = rows[0]
    count = 0
    print(f"\n{'Time':<20} | {'Original':<40} | {'New Name':<40}")
    print("-" * 110)

    for row in rows[1:]:
        # Row: [Timestamp, ID, Original, New, Target, Run_Type]
        if len(row) > 0 and row[0].startswith(today_str):
            # Extract plain text from Hyperlink formula if present
            # Formula: =HYPERLINK("url", "label")
            new_name = row[3]
            if new_name.startswith("=HYPERLINK"):
                try:
                    # Extract label: second quoted string
                    parts = new_name.split('"')
                    if len(parts) >= 4:
                        new_name = parts[3]
                except:
                    pass
            
            print(f"{row[0][11:]:<20} | {row[2][:38]:<40} | {new_name[:38]:<40}")
            count += 1
            
    print(f"\nTotal items processed today: {count}")

if __name__ == "__main__":
    check_today()
