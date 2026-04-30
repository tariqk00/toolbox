
"""
Shared utilities for life-docs reporters (Daily, Work, etc).
Handles paths, markdown generation, site rebuilding, and Drive memory fetching.
"""
import os
import subprocess
import logging
from datetime import datetime, date
from pathlib import Path
from typing import List, Dict, Any, Optional
from toolbox.lib.log_manager import LogManager, log

# Initialize centralized logger
log_manager = LogManager.get_instance('reporting')
logger = log_manager.logger

# --- Paths ---
REPO_ROOT = Path(__file__).resolve().parent.parent
LIFE_DOCS_REPO = Path.home() / 'github' / 'tariqk00' / 'life-docs'
MKDOCS_BIN = REPO_ROOT / 'google-drive' / 'venv' / 'bin' / 'mkdocs'

# --- Drive Integration ---
def get_memory_blocks(service, path: str, date_str: str) -> List[str]:
    """
    Fetch a memory file from Drive and extract blocks for a specific date.
    path: relative to '01 - Second Brain/Memory/'
    date_str: YYYY-MM-DD
    """
    from toolbox.lib.drive_utils import get_drive_service
    from toolbox.services.email_extractor.writers import get_memory_content, MEMORY_ROOT
    
    # get_memory_content handles the Drive interaction
    # category is the first part of the path, filename is the rest
    parts = path.strip('/').split('/')
    if len(parts) > 1:
        category = parts[0]
        filename = '/'.join(parts[1:])
    else:
        category = None
        filename = parts[0]
        
    if not filename.endswith('.md'):
        filename += '.md'
        
    content = get_memory_content(category, filename)
    if not content:
        return []
        
    # Extract blocks starting with '## {date_str}'
    blocks = content.split('\n---')
    return [b.strip() for b in blocks if b.strip().startswith(f'## {date_str}')]

# --- Markdown Helpers ---
def build_stat_card(num: Any, label: str, icon: Optional[str] = None) -> str:
    """Build a life-docs HTML stat card."""
    icon_str = f" {icon}" if icon else ""
    return (
        f'  <div class="lifedoc-stat">\n'
        f'    <span class="num">{num}</span>\n'
        f'    <span class="sub">{label}{icon_str}</span>\n'
    )

def build_row(label: str, time: str = "—", url: Optional[str] = None, detail: Optional[str] = None) -> str:
    """Build a life-docs HTML row."""
    label_html = f'<a href="{url}" target="_blank">{label}</a>' if url else label
    detail_html = f' <span class="chip dim">{detail.lower()}</span>' if detail else ''
    return (
        f'<div class="lifedoc-row">\n'
        f'  <span class="time">{time}</span>\n'
        f'  <span class="label">{label_html}{detail_html}</span>\n'
        f'</div>'
    )

# --- Site Building ---
def rebuild_site():
    """Run mkdocs build in the life-docs repo."""
    if not MKDOCS_BIN.exists():
        logger.warning(f"MkDocs binary not found at {MKDOCS_BIN}, skipping rebuild.")
        log("SITE_BUILD", "SKIPPED", "MkDocs binary not found, skipping site rebuild", data={
            "mkdocs_bin": str(MKDOCS_BIN),
        }, level="WARNING", app_name="reporting")
        return False
        
    try:
        logger.info("Rebuilding life-docs site...")
        subprocess.run(
            [str(MKDOCS_BIN), 'build'],
            cwd=str(LIFE_DOCS_REPO),
            check=True,
            capture_output=True
        )
        log("SITE_BUILD", "SUCCESS", "Rebuilt life-docs site", data={
            "repo": str(LIFE_DOCS_REPO),
        }, app_name="reporting")
        return True
    except subprocess.CalledProcessError as e:
        logger.error(f"MkDocs build failed: {e.stderr.decode()}")
        log("SITE_BUILD", "FAILURE", "MkDocs build failed", data={
            "repo": str(LIFE_DOCS_REPO),
            "error_type": type(e).__name__,
        }, level="ERROR", app_name="reporting")
        return False
    except Exception as e:
        logger.error(f"Error during site rebuild: {e}")
        log("SITE_BUILD", "FAILURE", "Unexpected error during site rebuild", data={
            "repo": str(LIFE_DOCS_REPO),
            "error_type": type(e).__name__,
        }, level="ERROR", app_name="reporting")
        return False

class ReportSection:
    """A section within a markdown report."""
    def __init__(self, title: str, level: int = 2):
        self.title = title
        self.level = level
        self.items: List[str] = []
        
    def add_item(self, item: str):
        self.items.append(item)
        
    def render(self) -> str:
        if not self.items:
            return ""
        prefix = "#" * self.level
        return f"{prefix} {self.title}\n\n" + "\n".join(self.items) + "\n"
