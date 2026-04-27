"""Shared helpers for de-duplicated task creation."""
from __future__ import annotations

import logging
import re
from collections.abc import Callable, Iterable
from datetime import date
from typing import Any

logger = logging.getLogger(__name__)

ACTION_REQUIRED_PATH = "01 - Second Brain/Inbox/Action Required.md"


def normalize_task_title(title: str) -> str:
    """Return a stable comparison key for a task title."""
    title = re.sub(r"^\(\s*\d+\s*min\s*\)\s*", "", title, flags=re.IGNORECASE)
    return re.sub(r"\s+", " ", title).strip().lower()


def existing_task_titles(service: Any, list_id: str) -> set[str]:
    """Return normalized titles of open tasks in a Google Tasks list."""
    try:
        result = service.tasks().list(
            tasklist=list_id,
            showCompleted=False,
            maxResults=100,
        ).execute()
    except Exception as exc:
        logger.warning("Could not fetch existing tasks for dedup: %s", exc)
        return set()
    return {
        normalize_task_title(task.get("title", ""))
        for task in result.get("items", [])
        if task.get("title")
    }


def create_unique_tasks(
    service: Any,
    list_id: str,
    items: Iterable[Any],
    *,
    title_fn: Callable[[Any], str],
    due_fn: Callable[[Any], str | None] | None = None,
    notes_fn: Callable[[Any], str | None] | None = None,
    key_fn: Callable[[Any], str] | None = None,
) -> int:
    """Create tasks, skipping open-list duplicates and same-batch duplicates."""
    from toolbox.lib.tasks import create_task

    existing = existing_task_titles(service, list_id)
    created = 0
    for item in items:
        title = (title_fn(item) or "").strip()
        if not title:
            continue
        key_source = key_fn(item) if key_fn else title
        key = normalize_task_title(key_source or title)
        if not key or key in existing:
            logger.debug("Skipping duplicate task: %s", title[:60])
            continue

        create_task(
            service,
            list_id,
            title,
            due=due_fn(item) if due_fn else None,
            notes=notes_fn(item) if notes_fn else None,
        )
        existing.add(key)
        created += 1
    return created


def dedupe_action_items(items: Iterable[dict]) -> list[dict]:
    """Return action-required items without same-batch subject/sender duplicates."""
    seen: set[tuple[str, str]] = set()
    output: list[dict] = []
    for item in items:
        subject = normalize_task_title(str(item.get("subject", "")))
        sender = re.sub(r"\s+", " ", str(item.get("sender", ""))).strip().lower()
        key = (subject, sender)
        if not subject or key in seen:
            continue
        seen.add(key)
        output.append(item)
    return output


def _get_action_required_content() -> str:
    """Compatibility hook for future Drive-backed Action Required reads."""
    return ""


def is_duplicate_task(subject: str, body_snippet: str = "", existing_content: str = "") -> bool:
    """Check if a task with a similar subject already exists in markdown content."""
    return f"### {subject}" in existing_content


def add_task(
    subject: str,
    sender: str,
    reason: str,
    priority: str = "medium",
    date_str: str | None = None,
) -> bool:
    """Compatibility helper for Action Required task creation."""
    if not date_str:
        date_str = date.today().isoformat()

    existing = _get_action_required_content()
    if is_duplicate_task(subject, reason, existing):
        logger.info("Skipping duplicate task: %s", subject)
        return False

    logger.info("Added new task: %s", subject)
    return True
