from toolbox.bin import usage_report


def test_summarize_cost_records_groups_by_source_and_falls_back_to_run_type():
    records = [
        {
            "timestamp": "2026-05-09T13:00:00+00:00",
            "source": "openclaw",
            "task_type": "heartbeat",
            "tokens_used": 1000,
            "cost_usd_est": 0.02,
        },
        {
            "date": "2026-05-09",
            "run_type": "sorter",
            "tokens_used": 500,
            "cost_usd_est": 0.01,
        },
    ]

    totals = usage_report.summarize_cost_records(records, days=7)

    assert totals["openclaw"]["records"] == 1
    assert totals["openclaw"]["tokens"] == 1000
    assert totals["openclaw"]["cost"] == 0.02
    assert totals["sorter"]["records"] == 1
    assert totals["sorter"]["tokens"] == 500
    assert totals["sorter"]["cost"] == 0.01


def test_format_summary_mentions_source_totals():
    totals = {
        "openclaw": {"records": 2, "tokens": 3000, "cost": 0.06},
    }

    report = usage_report.format_summary(totals, days=7)

    assert "openclaw" in report
    assert "3,000 tokens" in report
    assert "~$0.0600" in report
