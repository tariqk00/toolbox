from unittest.mock import MagicMock, patch


def test_daily_reporter_logs_lifecycle_events():
    from toolbox.bin import daily_reporter

    with patch.object(daily_reporter, "get_drive_service", return_value=MagicMock()), \
         patch.object(daily_reporter, "get_memory_blocks", return_value=[]), \
         patch.object(daily_reporter, "rebuild_site", return_value=False), \
         patch.object(daily_reporter, "update_home_index"), \
         patch.object(daily_reporter, "log") as mock_log:
        daily_reporter.main()

    events = [call.args[0] for call in mock_log.call_args_list]
    assert "RUN_START" in events
    assert "RUN_COMPLETE" in events
    assert events.count("REPORT_SECTION") >= 4


def test_work_reporter_logs_lifecycle_events():
    from toolbox.bin import work_reporter

    with patch.object(work_reporter, "build_backlog"), \
         patch.object(work_reporter, "build_changelog"), \
         patch.object(work_reporter, "build_sessions"), \
         patch.object(work_reporter, "build_health"), \
         patch.object(work_reporter, "rebuild_site", return_value=False), \
         patch.object(work_reporter, "log") as mock_log:
        work_reporter.main()

    events = [call.args[0] for call in mock_log.call_args_list]
    assert "RUN_START" in events
    assert "RUN_COMPLETE" in events


def test_rebuild_site_logs_skip_when_mkdocs_missing():
    from toolbox.lib import reporter_utils

    with patch.object(reporter_utils, "MKDOCS_BIN", reporter_utils.Path("/tmp/does-not-exist")), \
         patch.object(reporter_utils, "log") as mock_log:
        assert reporter_utils.rebuild_site() is False

    assert mock_log.call_args_list[0].args[0] == "SITE_BUILD"
