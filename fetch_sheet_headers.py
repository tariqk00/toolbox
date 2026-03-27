import sys
sys.path.append('/home/tariqk/github/tariqk00')
from toolbox.lib.drive_utils import get_sheets_service

def main():
    service = get_sheets_service()
    sheet_id = '1N8xlrcCnj97uGPssXnGg_-1t2SvGZlnocc_7BNO28dY'
    try:
        result = service.spreadsheets().values().get(
            spreadsheetId=sheet_id, range='Log!A1:G1'
        ).execute()
        headers = result.get('values', [])
        print("HEADERS:", headers)
    except Exception as e:
        print(f"Error: {e}")

if __name__ == '__main__':
    main()
