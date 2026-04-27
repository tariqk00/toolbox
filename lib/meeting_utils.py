"""Meeting de-duplication helpers shared by ingestion streams."""
from __future__ import annotations

import logging
import re
from collections.abc import Mapping

logger = logging.getLogger(__name__)

SESSIONS_ROOT = "01 - Second Brain/Work/Sessions"


def normalize_meeting_title(subject: str) -> str:
    """Normalize a meeting-ish email subject into a comparison title."""
    value = subject or ""
    value = re.sub(r"^(re|fwd?):\s*", "", value, flags=re.IGNORECASE)
    value = re.sub(r"\[(?:plaud[^\]]*|cc|meeting summary)\]", " ", value, flags=re.IGNORECASE)
    value = re.sub(r"\b\d{4}-\d{2}-\d{2}\b", " ", value)
    value = re.sub(r"\b\d{1,2}[/-]\d{1,2}(?:[/-]\d{2,4})?\b", " ", value)
    value = re.sub(r"\.(?:md|txt|pdf)$", "", value, flags=re.IGNORECASE)
    value = re.sub(r"[^a-z0-9]+", " ", value.lower())
    return re.sub(r"\s+", " ", value).strip()


def meeting_key(subject: str, date_value: str) -> str | None:
    """Return a stable date/title key for cross-source meeting de-duplication."""
    title = normalize_meeting_title(subject)
    if not title:
        return None
    date_part = (date_value or "")[:10]
    return f"{date_part}:{title}" if date_part else title


def dedupe_meeting_emails(
    emails_by_category: Mapping[str, list[dict]],
    state: dict,
    *,
    categories: tuple[str, ...] = ("plaud", "cc_summaries"),
    keep_keys: int = 500,
) -> dict[str, list[dict]]:
    """Filter duplicate meeting emails across categories and update state.

    Category order determines precedence. The default keeps Plaud before CC
    summaries when both produce the same meeting key.
    """
    seen = set(state.get("seen_keys", []))
    batch_seen: set[str] = set()
    output: dict[str, list[dict]] = {}

    for category, emails in emails_by_category.items():
        if category not in categories:
            output[category] = list(emails)
            continue

        kept = []
        for email in emails:
            key = meeting_key(email.get("subject", ""), email.get("date", ""))
            if key and (key in seen or key in batch_seen):
                continue
            if key:
                batch_seen.add(key)
            kept.append(email)
        output[category] = kept

    merged = list(dict.fromkeys([*state.get("seen_keys", []), *batch_seen]))
    state["seen_keys"] = merged[-keep_keys:]
    return output


def is_duplicate_meeting(subject: str, meeting_date: str, participants: list[str] | None = None) -> bool:
    """Compatibility hook for future Drive-backed session de-duplication."""
    return False


def sync_plaud_session(doc_date: str, subject: str, summary_text: str) -> bool:
    """Return whether a Plaud session should be ingested."""
    if is_duplicate_meeting(subject, doc_date):
        logger.info("Meeting session already exists: %s - %s", doc_date, subject)
        return False
    return True
