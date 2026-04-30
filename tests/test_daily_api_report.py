import json
from pathlib import Path
from unittest.mock import patch


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.write_text("".join(json.dumps(row) + "\n" for row in rows))


def test_build_usage_summary_aggregates_cost_log(tmp_path):
    from toolbox.bin import daily_api_report

    cost_log = tmp_path / "cost_log.jsonl"
    _write_jsonl(cost_log, [
        {
            "date": "2026-04-29",
            "run_type": "ai-sorter",
            "files_processed": 10,
            "tokens_used": 1000,
            "cost_usd_est": 0.1000,
        },
        {
            "date": "2026-04-29",
            "run_type": "ai-sorter",
            "files_processed": 5,
            "tokens_used": 400,
            "cost_usd_est": 0.0400,
        },
        {
            "date": "2026-04-29",
            "run_type": "backfill",
            "files_processed": 2,
            "tokens_used": 600,
            "cost_usd_est": 0.0600,
        },
        {
            "date": "2026-04-28",
            "run_type": "ai-sorter",
            "files_processed": 99,
            "tokens_used": 9999,
            "cost_usd_est": 0.9999,
        },
    ])

    summary = daily_api_report.build_usage_summary("2026-04-29", cost_log)

    assert summary["total_tokens"] == 2000
    assert summary["total_files"] == 17
    assert summary["tokens_per_file"] == 117.6
    assert summary["runs"]["ai-sorter"]["runs"] == 2
    assert summary["runs"]["ai-sorter"]["tokens"] == 1400
    assert summary["heaviest_run"] == ("backfill", 300.0, 1)


def test_build_service_summary_tracks_runs_and_auth_failures(tmp_path):
    from toolbox.bin import daily_api_report

    activity = tmp_path / "activity.jsonl"
    _write_jsonl(activity, [
        {
            "timestamp": "2026-04-29T10:00:00Z",
            "app": "ai-sorter",
            "event": "RUN_COMPLETE",
            "status": "SUCCESS",
            "message": "done",
        },
        {
            "timestamp": "2026-04-29T11:00:00Z",
            "app": "email-extractor",
            "event": "RUN_COMPLETE",
            "status": "FAILURE",
            "message": "broke",
        },
        {
            "timestamp": "2026-04-29T12:00:00Z",
            "app": "token-monitor",
            "event": "TOKEN_MONITOR",
            "status": "ALERT",
            "message": "token expired",
        },
        {
            "timestamp": "2026-04-29T12:05:00Z",
            "app": "gmail-auth",
            "event": "AUTH_REFRESH",
            "status": "RETRY",
            "message": "retrying",
        },
        {
            "timestamp": "2026-04-28T12:05:00Z",
            "app": "email-extractor",
            "event": "RUN_COMPLETE",
            "status": "SUCCESS",
            "message": "old",
        },
    ])

    summary = daily_api_report.build_service_summary("2026-04-29", activity)

    assert summary["services"]["ai-sorter"]["success"] == 1
    assert summary["services"]["email-extractor"]["failure"] == 1
    assert summary["services"]["token-monitor"]["failure"] == 1
    assert summary["auth_failures"] == 1
    assert sorted(summary["failing_services"]) == ["email-extractor", "token-monitor"]


def test_main_sends_telegram_report_and_logs_sections():
    from toolbox.bin import daily_api_report

    usage = {
        "report_date": "2026-04-29",
        "runs": {"ai-sorter": {"runs": 1, "tokens": 250, "cost": 0.025, "files": 5}},
        "total_tokens": 250,
        "total_cost": 0.025,
        "total_files": 5,
        "tokens_per_file": 50.0,
        "heaviest_run": ("ai-sorter", 50.0, 1),
    }
    services = {
        "report_date": "2026-04-29",
        "services": {
            app: {"runs": 0, "success": 0, "failure": 0, "latest_status": None, "latest_event": None}
            for app in daily_api_report.CORE_APPS
        },
        "auth_failures": 0,
        "failing_services": [],
        "healthy_services": ["ai-sorter"],
    }
    services["services"]["ai-sorter"] = {
        "runs": 1,
        "success": 1,
        "failure": 0,
        "latest_status": "SUCCESS",
        "latest_event": "RUN_COMPLETE",
    }

    with patch.object(daily_api_report, "build_usage_summary", return_value=usage), \
         patch.object(daily_api_report, "build_service_summary", return_value=services), \
         patch.object(daily_api_report, "send_message", return_value=True) as mock_send, \
         patch.object(daily_api_report, "log") as mock_log:
        assert daily_api_report.main("2026-04-29") is True

    sent_text = mock_send.call_args.args[0]
    assert "Daily API &amp; Optimization Report" in sent_text
    assert "ai-sorter" in sent_text
    events = [call.args[0] for call in mock_log.call_args_list]
    assert events.count("REPORT_SECTION") == 3
    assert events[0] == "RUN_START"
    assert events[-1] == "RUN_COMPLETE"
