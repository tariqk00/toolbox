import pytest
from unittest.mock import MagicMock, patch
from toolbox.lib.task_utils import add_task, normalize_task_title, is_duplicate_task

def test_normalize_task_title():
    assert normalize_task_title("( 10 min ) Fix things") == "fix things"
    assert normalize_task_title("  Multiple   Spaces  ") == "multiple spaces"

def test_is_duplicate_task():
    existing = "### Buy milk\n**From:** me\n---\n### (5 min) Call bank"
    assert is_duplicate_task("Buy milk", existing_content=existing) is True
    assert is_duplicate_task("Call bank", existing_content=existing) is True
    assert is_duplicate_task("Walk dog", existing_content=existing) is False

@patch("toolbox.lib.task_utils.get_action_required_content")
@patch("toolbox.lib.drive_utils.append_to_file")
def test_add_task_skips_duplicate(mock_append, mock_get_content):
    mock_get_content.return_value = "### Existing Task"
    
    result = add_task("Existing Task", "sender", "reason")
    
    assert result is False
    mock_append.assert_not_called()

@patch("toolbox.lib.task_utils.get_action_required_content")
@patch("toolbox.lib.drive_utils.append_to_file")
@patch("toolbox.lib.tasks.get_tasks_service")
def test_add_task_creates_new(mock_tasks_svc, mock_append, mock_get_content):
    mock_get_content.return_value = "### Other Task"
    
    result = add_task("New Unique Task", "sender", "reason", priority="medium")
    
    assert result is True
    mock_append.assert_called_once()
    args, _ = mock_append.call_args
    assert "New Unique Task" in args[2]
    mock_tasks_svc.assert_not_called()

@patch("toolbox.lib.task_utils.get_action_required_content")
@patch("toolbox.lib.drive_utils.append_to_file")
@patch("toolbox.lib.tasks.get_tasks_service")
@patch("toolbox.lib.tasks.get_or_create_list")
@patch("toolbox.lib.tasks.create_task")
def test_add_task_high_priority_syncs_to_google(mock_create, mock_get_list, mock_tasks_svc, mock_append, mock_get_content):
    mock_get_content.return_value = ""
    mock_get_list.return_value = "list_id"
    
    result = add_task("High Priority Task", "boss", "ASAP", priority="high")
    
    assert result is True
    mock_append.assert_called_once()
    mock_tasks_svc.assert_called_once()
    mock_create.assert_called_once()
    # Check that it synced to Google Tasks
    _, create_args, _ = mock_create.mock_calls[0]
    assert create_args[2] == "High Priority Task"
