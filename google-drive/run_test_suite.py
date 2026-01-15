from drive_organizer import scan_folder

TEST_FOLDER_ID = '1yFgFzqduuqa68RsxLe5-ndX3fvlrvFEO'
scan_folder(TEST_FOLDER_ID, dry_run=True, csv_path='test_suite_results.csv', mode='scan')
print("\n[Test Complete] Check test_suite_results.csv for output.")
