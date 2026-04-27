from toolbox.lib.meeting_utils import (
    dedupe_meeting_emails,
    meeting_key,
    normalize_meeting_title,
)


def test_normalize_meeting_title_removes_source_noise():
    assert normalize_meeting_title("[PLAUD-AutoFlow] 04/26 Team Sync.txt") == "team sync"


def test_meeting_key_uses_date_and_normalized_title():
    assert meeting_key("Re: 2026-04-26 Team Sync", "2026-04-26 14:30") == "2026-04-26:team sync"


def test_dedupe_meeting_emails_keeps_first_category_and_updates_state():
    state = {}
    output = dedupe_meeting_emails(
        {
            "plaud": [{"subject": "[PLAUD-AutoFlow] 04/26 Team Sync", "date": "2026-04-26 10:00"}],
            "cc_summaries": [{"subject": "Team Sync", "date": "2026-04-26 11:00"}],
            "travel": [{"subject": "Flight", "date": "2026-04-26"}],
        },
        state,
    )

    assert len(output["plaud"]) == 1
    assert output["cc_summaries"] == []
    assert len(output["travel"]) == 1
    assert state["seen_keys"] == ["2026-04-26:team sync"]
