import pytest
from toolbox.lib.drive_utils import escape_query_string, _find_or_create_folder, _get_file_in_folder
from unittest.mock import MagicMock

def test_escape_query_string():
    # Simple strings
    assert escape_query_string("normal") == "normal"
    
    # Single quotes
    assert escape_query_string("Sherry's Presentation") == "Sherry\\'s Presentation"
    
    # Backslashes
    assert escape_query_string("Path\\Folder") == "Path\\\\Folder"
    
    # Both
    assert escape_query_string("O'Reilly\\Folder") == "O\\'Reilly\\\\Folder"
    
    # Multiple occurrences
    assert escape_query_string("'test'\\path'\\") == "\\'test\\'\\\\path\\'\\\\"

def test_drive_query_generation():
    service = MagicMock()
    parent_id = "parent123"
    name = "Sherry's Presentation"
    
    # Mock search to return something so it doesn't try to create
    service.files().list().execute.return_value = {"files": [{"id": "file456"}]}
    
    _find_or_create_folder(service, name, parent_id)
    
    # Verify the query string
    args, kwargs = service.files().list.call_args
    query = kwargs.get('q')
    assert "name = 'Sherry\\'s Presentation'" in query
    assert f"'{parent_id}' in parents" in query

def test_get_file_query_generation():
    service = MagicMock()
    folder_id = "folder123"
    filename = "O'Reilly\\Notes.md"
    
    service.files().list().execute.return_value = {"files": []}
    
    _get_file_in_folder(service, folder_id, filename)
    
    args, kwargs = service.files().list.call_args
    query = kwargs.get('q')
    assert "name = 'O\\'Reilly\\\\Notes.md'" in query
    assert f"'{folder_id}' in parents" in query
