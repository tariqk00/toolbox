import sys
sys.path.append('/home/tariqk/github/tariqk00')
from toolbox.lib.drive_utils import get_sheets_service

def main():
    service = get_sheets_service()
    sheet_id = '1N8xlrcCnj97uGPssXnGg_-1t2SvGZlnocc_7BNO28dY'
    try:
        # Get the last few rows to see the newly appended one
        result = service.spreadsheets().values().get(
            spreadsheetId=sheet_id, range='Log!A:F'
        ).execute()
        rows = result.get('values', [])
        print("LAST 3 ROWS IN HISTORY SHEET:")
        for row in rows[-3:]:
            print(row)
    except Exception as e:
        print(f"Error: {e}")

if __name__ == '__main__':
    main()
