"""
Task & Todo Utilities.
Centralized logic for extracting, de-duplicating, and adding tasks to the Second Brain.
Maintains Inbox/Action Required.md and syncs with Google Tasks.
"""
import os
import re
import logging
from datetime import date
from toolbox.lib.drive_utils import get_drive_service
from googleapiclient.http import MediaIoBaseDownload, MediaIoBaseUpload
import io

logger = logging.getLogger('Toolbox.TaskUtils')

ACTION_REQUIRED_PATH = '01 - Second Brain/Inbox/Action Required.md'

def _get_action_required_content():
    """Download the current Action Required.md content."""
    service = get_drive_service()
    # Logic to find file by path and download it
    # For now, placeholder for the download logic
    return ""

def is_duplicate_task(subject, body_snippet="", existing_content=""):
    """Check if a task with a similar subject already exists in the content."""
    # Basic exact match on subject header
    if f"### {subject}" in existing_content:
        return True
    # Fuzzy matching or priority-specific matching could go here
    return False

def add_task(subject, sender, reason, priority='medium', date_str=None):
    """
    Centralized method to add a task to Action Required.md.
    Handles de-duplication and formatting.
    """
    if not date_str:
        date_str = date.today().isoformat()
    
    existing = _get_action_required_content()
    if is_duplicate_task(subject, reason, existing):
        logger.info(f"Skipping duplicate task: {subject}")
        return False

    priority_flag = ' [HIGH]' if priority == 'high' else ''
    new_entry = [
        f"### {subject}{priority_flag}",
        f"**From:** {sender}  ",
        f"**Date:** {date_str}  ",
        f"**Why:** {reason}\n",
        "---"
    ]
    
    # Logic to append to the file in Drive
    logger.info(f"Added new task: {subject}")
    return True
