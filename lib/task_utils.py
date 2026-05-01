
"""
Shared helpers for centralized task management and de-duplicated task creation.
Supports multiple targets: Google Tasks (via Tasks API) and Drive (Action Required.md).
"""
from __future__ import annotations

import logging
import re
from datetime import date, datetime
from enum import Enum
from typing import Any, Optional, List, Dict, Iterable, Callable
from toolbox.lib.entity_ids import render_entity_comment, task_entity_id

logger = logging.getLogger('TaskUtils')

ACTION_REQUIRED_PATH = "01 - Second Brain/Inbox"
ACTION_REQUIRED_FILE = "Action Required.md"

class TaskPriority(Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"

class TaskClient:
    """Cached client for Google Tasks API."""
    _instance: Optional[TaskClient] = None
    _service: Any = None
    _list_cache: Dict[str, str] = {}

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(TaskClient, cls).__new__(cls)
        return cls._instance

    def get_service(self):
        if self._service is None:
            from toolbox.lib.tasks import get_tasks_service
            self._service = get_tasks_service()
        return self._service

    def get_list_id(self, name: str = "Inbox") -> str:
        if name in self._list_cache:
            return self._list_cache[name]
        
        from toolbox.lib.tasks import get_or_create_list
        lid = get_or_create_list(self.get_service(), name)
        self._list_cache[name] = lid
        return lid

def normalize_task_title(title: str) -> str:
    """Return a stable comparison key for a task title."""
    # Strip common prefixes like "(10 min)" or "[HIGH]"
    title = re.sub(r"^\(\s*\d+\s*min\s*\)\s*", "", title, flags=re.IGNORECASE)
    title = re.sub(r"^\[.*?\]\s*", "", title)
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
    """Read current Action Required.md content from Drive for deduplication."""
    from toolbox.lib.drive_utils import get_drive_service, _resolve_path, _get_file_in_folder
    try:
        service = get_drive_service()
        folder_id = _resolve_path(service, ACTION_REQUIRED_PATH)
        file_id = _get_file_in_folder(service, folder_id, ACTION_REQUIRED_FILE)
        if not file_id:
            return ""
        # Using service.files().get_media() as seen in writers.py
        content_bytes = service.files().get_media(fileId=file_id).execute()
        return content_bytes.decode("utf-8") if isinstance(content_bytes, bytes) else content_bytes
    except Exception as e:
        logger.warning("Could not read Action Required.md for dedup: %s", e)
        return ""

def is_duplicate_task(subject: str, existing_content: str = "") -> bool:
    """Check if a task with similar subject already exists in markdown content."""
    if not existing_content:
        return False
    norm_subject = normalize_task_title(subject)
    # Check for exact heading match (robust) or normalization match
    if f"### {subject}" in existing_content:
        return True
    return norm_subject in normalize_task_title(existing_content)

def add_task(
    subject: str,
    sender: str,
    reason: str,
    priority: str | TaskPriority = TaskPriority.MEDIUM,
    date_str: str | None = None,
    sync_to_google_tasks: bool = False,
    task_list: str = "Inbox",
    entity_source: str = "",
) -> bool:
    """
    Unified task creation interface.
    1. Dedupes against Action Required.md content.
    2. Appends to Action Required.md in Drive.
    3. Optionally syncs to Google Tasks (forced if priority is HIGH/CRITICAL).
    """
    from toolbox.lib.drive_utils import append_to_file
    
    # Standardize priority
    if isinstance(priority, str):
        try:
            priority = TaskPriority(priority.lower())
        except ValueError:
            priority = TaskPriority.MEDIUM

    if not date_str:
        date_str = date.today().isoformat()

    entity_id = task_entity_id(entity_source or sender, subject, date_str)

    # 1. Deduplication
    existing_content = get_action_required_content()
    if is_duplicate_task(subject, existing_content):
        logger.debug("Skipping duplicate task: %s", subject)
        return False

    # 2. Drive Update
    priority_label = f" [{priority.value.upper()}]" if priority in (TaskPriority.HIGH, TaskPriority.CRITICAL) else ""
    lines = [
        render_entity_comment(entity_id),
        f"### {subject}{priority_label}",
        f"**From:** {sender}  ",
        f"**Date:** {date_str}  ",
        f"**Why:** {reason}",
        "",
        "---",
    ]
    append_to_file(ACTION_REQUIRED_PATH, ACTION_REQUIRED_FILE, "\n".join(lines))
    logger.info("Added task to Drive: %s", subject)

    # 3. Google Tasks Sync
    # Force sync for high/critical priority unless explicitly disabled
    force_sync = priority in (TaskPriority.HIGH, TaskPriority.CRITICAL)
    if sync_to_google_tasks or force_sync:
        try:
            client = TaskClient()
            service = client.get_service()
            list_id = client.get_list_id(task_list)
            
            from toolbox.lib.tasks import create_task
            create_task(
                service, 
                list_id, 
                subject, 
                due=date_str, 
                notes=f"From: {sender}\nWhy: {reason}\nPriority: {priority.value}\nEntity ID: {entity_id}"
            )
            logger.info("Synced task to Google Tasks [%s]: %s", task_list, subject)
        except Exception as e:
            logger.error("Failed to sync task to Google Tasks: %s", e)

    return True

def list_google_tasks(task_list: str = "Inbox") -> List[Dict[str, Any]]:
    """Return all active tasks in a Google Tasks list."""
    try:
        client = TaskClient()
        service = client.get_service()
        list_id = client.get_list_id(task_list)
        
        result = service.tasks().list(
            tasklist=list_id,
            showCompleted=False,
            maxResults=100
        ).execute()
        return result.get('items', [])
    except Exception as e:
        logger.error("Failed to list Google Tasks: %s", e)
        return []

def complete_google_task(task_id: str, task_list: str = "Inbox") -> bool:
    """Mark a Google Task as completed."""
    try:
        client = TaskClient()
        service = client.get_service()
        list_id = client.get_list_id(task_list)
        
        service.tasks().patch(
            tasklist=list_id,
            task=task_id,
            body={'status': 'completed', 'completed': datetime.now().isoformat() + 'Z'}
        ).execute()
        logger.info("Marked task %s as completed", task_id)
        return True
    except Exception as e:
        logger.error("Failed to complete task %s: %s", task_id, e)
        return False
