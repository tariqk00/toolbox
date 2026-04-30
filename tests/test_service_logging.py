from unittest.mock import MagicMock, patch


def test_email_extractor_run_logs_start_and_complete():
    from toolbox.services.email_extractor import main

    config = {"digests": {"known_senders": {}, "raw_senders": {}}}
    state = {}

    with patch.object(main, "load_config", return_value=config), \
         patch.object(main, "load_state", return_value=state), \
         patch.object(main, "save_state"), \
         patch.object(main, "get_gmail_service", return_value=MagicMock()), \
         patch.object(main, "fetch_category_emails", return_value=[]), \
         patch.object(main.orders, "process"), \
         patch.object(main.receipts, "process"), \
         patch.object(main.trips, "process"), \
         patch.object(main.digests, "process"), \
         patch.object(main.google_brief, "process"), \
         patch.object(main.plaud, "process"), \
         patch.object(main.sweep, "run", return_value=None), \
         patch.object(main, "send_message"), \
         patch.object(main, "log") as mock_log:
        main.run()

    events = [call.args[0] for call in mock_log.call_args_list]
    assert "RUN_START" in events
    assert "RUN_COMPLETE" in events
    assert events.count("CATEGORY_FETCH") >= 6


def test_email_extractor_logs_category_errors():
    from toolbox.services.email_extractor import main

    config = {"digests": {"known_senders": {}, "raw_senders": {}}}
    state = {"last_run": "2026-04-29"}
    broken_email = {"id": "abc", "subject": "Broken order"}

    def fake_fetch(_service, category, *_args, **_kwargs):
        return [broken_email] if category == "orders" else []

    with patch.object(main, "load_config", return_value=config), \
         patch.object(main, "load_state", return_value=state), \
         patch.object(main, "save_state"), \
         patch.object(main, "get_gmail_service", return_value=MagicMock()), \
         patch.object(main, "fetch_category_emails", side_effect=fake_fetch), \
         patch.object(main.orders, "process", side_effect=RuntimeError("boom")), \
         patch.object(main.receipts, "process"), \
         patch.object(main.trips, "process"), \
         patch.object(main.digests, "process"), \
         patch.object(main.google_brief, "process"), \
         patch.object(main.plaud, "process"), \
         patch.object(main.sweep, "run", return_value=None), \
         patch.object(main, "send_message"), \
         patch.object(main, "log") as mock_log:
        main.run()

    events = [call.args[0] for call in mock_log.call_args_list]
    assert "CATEGORY_ERROR" in events


def test_sorter_scan_logs_structured_file_events():
    from toolbox.services.drive_organizer import main

    main.stats = main.RunStats()
    service = MagicMock()
    service.files().list.return_value.execute.return_value = {
        "files": [{
            "id": "file-1",
            "name": "invoice.pdf",
            "mimeType": "application/pdf",
            "createdTime": "2026-01-15T10:00:00Z",
        }]
    }
    service.files().update.return_value.execute.return_value = {}

    analysis = {
        "doc_date": "2026-01-15",
        "entity": "Toyota",
        "folder_path": "07 - Finance/Auto",
        "summary": "Car payment",
        "confidence": "medium",
        "reasoning": "Partial match",
    }

    with patch.object(main, "download_file_content", return_value=b"content"), \
         patch.object(main, "analyze_with_gemini", return_value=(analysis, 5)), \
         patch.object(main, "generate_new_name", return_value="2026-01-15 - Toyota - Car payment.pdf"), \
         patch.object(main, "resolve_folder_id", return_value="id_target"), \
         patch.object(main, "get_category_prompt_str", return_value="folders"), \
         patch.object(main.quota_manager, "record_tokens"), \
         patch.object(main, "move_file", return_value=True), \
         patch.object(main, "log") as mock_log, \
         patch.object(main, "log_to_sheet"), \
         patch.object(main, "send_message"):
        main.scan_folder("id_inbox", dry_run=False, service=service, recursive=False, folder_name="Inbox")

    events = [call.args[0] for call in mock_log.call_args_list]
    assert "FILE_ANALYZED" in events
    assert "FILE_SKIPPED" in events
