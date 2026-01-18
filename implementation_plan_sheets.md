# Implementation Plan: Migrate History to Google Sheets

## Goal

Replace local/synced CSV history logging with direct logging to a Google Sheet. This improves accessibility and eliminates sync conflicts.

## User Review Required

> [!IMPORTANT] > **Re-Authentication Required**: Changing API scopes requires generating a new token. I will provide a URL for you to authorize the new `spreadsheets` scope.

## Proposed Changes

### Configuration

1.  **Scopes**: Update `SCOPES` in `drive_organizer.py` to include `https://www.googleapis.com/auth/spreadsheets`.
2.  **Constants**: Add `HISTORY_SHEET_ID`.

### Migration Logic (One-off)

1.  **Create Sheet**: Script to create a new Google Sheet named `AI_Sorter_History` in the `_Master_Archive_Metadata` folder.
2.  **Import Data**: Read `renaming_history.csv` and `_legacy_backup_jan10.csv` and batch-append them to the new Sheet.
3.  **Formatting**: Freeze header row and bold it.

### Runtime Logic (drive_organizer.py)

1.  **Log Function**: Replace `csv.writer` with `service.spreadsheets().values().append`.
2.  **Error Handling**: Ensure network failures don't crash the sorter, fallback to local log? (For now, strict failure is fine as we are supervised).

## Verification Plan

1.  **Auth**: User successfully generates new `token_full_drive.json`.
2.  **Creation**: Verify Sheet exists in Drive.
3.  **Data Check**: Verify all past CSV rows are present in the Sheet.
4.  **Test Run**: Run `run_test_suite.py` and confirm a new row appears in the Sheet.
