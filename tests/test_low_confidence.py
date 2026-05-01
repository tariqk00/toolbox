from unittest.mock import MagicMock, patch


def test_record_drive_low_confidence_sets_entity_fields():
    from toolbox.lib.low_confidence import record_drive_low_confidence

    fake_memory = MagicMock()
    fake_memory.fields = {}

    with patch("toolbox.lib.low_confidence.EntityMemory.load_from_drive", return_value=fake_memory):
        filename = record_drive_low_confidence(
            file_id="file_123",
            current_name="mystery.pdf",
            source_folder_path="Inbox",
            created_time="2026-01-15T10:00:00Z",
            analysis={
                "entity": "Unknown",
                "summary": "Ambiguous",
                "folder_path": "07 - Finance",
                "confidence": "Low",
                "reasoning": "No clear match",
            },
            proposed_name="2026-01-15 - Unknown - Ambiguous.pdf",
        )

    assert filename == "file_123.md"
    assert fake_memory.name == "Drive File: mystery.pdf"
    assert fake_memory.entity_id.startswith("low_confidence_")
    fake_memory.set_field.assert_any_call("File ID", "file_123")
    fake_memory.set_field.assert_any_call("Confidence", "Low")
    fake_memory.set_field.assert_any_call("Status", "Pending Reprocess")
    fake_memory.save_to_drive.assert_called_once_with("Low Confidence", "file_123.md")


def test_reprocess_low_confidence_promotes_high_confidence_result():
    from toolbox.lib.low_confidence import reprocess_low_confidence_drive_files

    fake_memory = MagicMock()
    fake_memory.fields = {
        "Source Type": "Drive File",
        "File ID": "file_123",
        "Status": "Pending Reprocess",
        "Current Name": "mystery.pdf",
        "Source Folder Path": "01 - Second Brain/Low Confidence",
        "Attempts": "1",
    }

    service = MagicMock()
    service.files().get.return_value.execute.return_value = {
        "id": "file_123",
        "name": "mystery.pdf",
        "mimeType": "application/pdf",
        "createdTime": "2026-01-15T10:00:00Z",
        "parents": ["low_conf_bucket"],
    }
    service.files().update.return_value.execute.return_value = {}

    with patch("toolbox.lib.low_confidence.list_memory_files", return_value={"file_123.md": "memory_id"}), \
         patch("toolbox.lib.low_confidence.EntityMemory.load_from_drive", return_value=fake_memory), \
         patch("toolbox.lib.low_confidence.download_file_content", return_value=b"pdf bytes"), \
         patch("toolbox.lib.low_confidence.get_category_prompt_str", return_value="folders"), \
         patch("toolbox.lib.low_confidence.analyze_with_gemini", return_value=({
             "entity": "Toyota",
             "summary": "Car payment",
             "folder_path": "07 - Finance/Auto",
             "confidence": "High",
             "reasoning": "Clear match",
             "doc_date": "2026-01-15",
         }, 10)), \
         patch("toolbox.lib.low_confidence.resolve_folder_id", return_value="target_folder"), \
         patch("toolbox.lib.low_confidence.move_file", return_value=True) as mock_move:
        results = reprocess_low_confidence_drive_files(limit=1, execute=True, service=service)

    assert len(results) == 1
    assert results[0]["promoted"] is True
    service.files().update.assert_called_once()
    mock_move.assert_called_once_with(service, "file_123", "target_folder", "2026-01-15 - Toyota - Car_payment.pdf")
    fake_memory.set_field.assert_any_call("Status", "Promoted")
    fake_memory.save_to_drive.assert_called_once_with("Low Confidence", "file_123.md")
