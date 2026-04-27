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


def get_action_required_content() -> str:
    """Read the current Action Required.md content from Drive."""
    from toolbox.lib.drive_utils import get_drive_service, _resolve_path, _get_file_in_folder, download_file_content
    try:
        service = get_drive_service()
        folder_id = _resolve_path(service, "01 - Second Brain/Inbox")
        file_id = _get_file_in_folder(service, folder_id, "Action Required.md")
        if not file_id:
            return ""
        content_bytes = download_file_content(service, file_id, "text/plain")
        return content_bytes.decode("utf-8")
    except Exception as e:
        logger.warning("Could not read Action Required.md for dedup: %s", e)
        return ""


def is_duplicate_task(subject: str, reason: str = "", existing_content: str = "") -> bool:
    """Check if a task with a similar subject already exists in markdown content."""
    # Check for exact heading match
    if f"### {subject}" in existing_content:
        return True
    # Check for normalized subject match in the text
    norm_subject = normalize_task_title(subject)
    if norm_subject in normalize_task_title(existing_content):
        return True
    return False


def add_task(
    subject: str,
    sender: str,
    reason: str,
    priority: str = "medium",
    date_str: str | None = None,
    sync_to_google_tasks: bool = False,
) -> bool:
    """
    Centralized task adder.
    Writes to Drive (Action Required.md) and optionally Google Tasks.
    """
    from toolbox.lib.drive_utils import append_to_file

    if not date_str:
        date_str = date.today().isoformat()

    existing = get_action_required_content()
    if is_duplicate_task(subject, reason, existing):
        logger.info("Skipping duplicate task: %s", subject)
        return False

    # 1. Write to Drive
    priority_flag = " [HIGH]" if priority == "high" else ""
    lines = [
        f"### {subject}{priority_flag}",
        f"**From:** {sender}  ",
        f"**Date:** {date_str}  ",
        f"**Why:** {reason}",
        "",
        "---",
    ]
    append_to_file("01 - Second Brain/Inbox", "Action Required.md", "\n".join(lines))

    # 2. Optional Google Tasks Sync (only for high priority by default if requested)
    if sync_to_google_tasks or priority == "high":
        try:
            from toolbox.lib.tasks import get_tasks_service, get_or_create_list, create_task
            service = get_tasks_service()
            list_id = get_or_create_list(service, "Inbox")
            create_task(service, list_id, subject, due=date_str, notes=f"From: {sender}\nWhy: {reason}")
        except Exception as e:
            logger.error("Failed to sync task to Google Tasks: %s", e)

    logger.info("Added new task: %s", subject)
    return True
