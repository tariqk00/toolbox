"""
Standardized entity memory markdown schema and updater.
Enforces consistent structure for entity files in Google Drive.
"""
from __future__ import annotations

import logging
import re
from datetime import datetime
from typing import Dict, List, Optional

from toolbox.lib.entity_ids import render_entity_comment

logger = logging.getLogger("toolbox.entity_memory")

SCHEMA_HEADERS = [
    "Summary",
    "Structured Fields",
    "Timeline",
    "Sources",
    "Conflicts",
    "Links"
]

class EntityMemory:
    def __init__(self, name: str, entity_id: Optional[str] = None):
        self.name = name
        self.entity_id = entity_id
        self.summary: str = ""
        self.fields: Dict[str, str] = {}
        self.timeline: List[str] = []
        self.sources: List[str] = []
        self.conflicts: List[str] = []
        self.links: List[str] = []
        self.raw_content: str = ""

    @classmethod
    def parse(cls, content: str) -> EntityMemory:
        """Parse existing markdown content into an EntityMemory object."""
        # Extract name from first # header
        name_match = re.search(r"^#\s+(.+)$", content, re.MULTILINE)
        name = name_match.group(1).strip() if name_match else "Unknown"
        
        # Extract entity_id from comment
        id_match = re.search(r"<!--\s*entity_id:\s*([a-z0-9_]+)\s*-->", content)
        entity_id = id_match.group(1) if id_match else None
        
        em = cls(name, entity_id)
        em.raw_content = content
        
        # Split into sections by ## headers
        sections = re.split(r"^##\s+", content, flags=re.MULTILINE)
        for section in sections[1:]:
            lines = section.splitlines()
            if not lines:
                continue
            header = lines[0].strip()
            body = "\n".join(lines[1:]).strip()
            
            if header == "Summary":
                em.summary = body
            elif header == "Structured Fields":
                for line in body.splitlines():
                    m = re.match(r"^- \*\*([^:]+):\*\*\s*(.*)$", line)
                    if m:
                        em.fields[m.group(1).strip()] = m.group(2).strip()
            elif header == "Timeline":
                em.timeline = [l.strip() for l in body.splitlines() if l.strip()]
            elif header == "Sources":
                em.sources = [l.strip() for l in body.splitlines() if l.strip()]
            elif header == "Conflicts":
                em.conflicts = [l.strip() for l in body.splitlines() if l.strip()]
            elif header == "Links":
                em.links = [l.strip() for l in body.splitlines() if l.strip()]
                
        return em

    def render(self) -> str:
        """Generate markdown content from current state."""
        lines = [f"# {self.name}"]
        if self.entity_id:
            lines.append(render_entity_comment(self.entity_id))
        lines.append("")
        
        lines.append("## Summary")
        lines.append(self.summary or "*(No summary provided)*")
        lines.append("")
        
        lines.append("## Structured Fields")
        if self.fields:
            for k, v in sorted(self.fields.items()):
                lines.append(f"- **{k}:** {v}")
        else:
            lines.append("*(No structured fields)*")
        lines.append("")
        
        lines.append("## Timeline")
        if self.timeline:
            lines.extend(self.timeline)
        else:
            lines.append("*(No events recorded)*")
        lines.append("")
        
        lines.append("## Sources")
        if self.sources:
            lines.extend(self.sources)
        else:
            lines.append("*(No sources listed)*")
        lines.append("")
        
        lines.append("## Conflicts")
        if self.conflicts:
            lines.extend(self.conflicts)
        else:
            lines.append("*(No conflicts detected)*")
        lines.append("")
        
        lines.append("## Links")
        if self.links:
            lines.extend(self.links)
        else:
            lines.append("*(No links provided)*")
        lines.append("")
        
        return "\n".join(lines)

    def set_summary(self, text: str):
        self.summary = text.strip()

    def set_field(self, key: str, value: str):
        self.fields[key.strip()] = str(value).strip()

    def add_timeline_event(self, event: str, date: Optional[str] = None):
        if not date:
            date = datetime.now().strftime("%Y-%m-%d")
        # Ensure event starts with date prefix for consistency
        if not re.match(r"^- \*\*\d{4}-\d{2}-\d{2}:\*\*", event):
            event = f"- **{date}:** {event.strip('- ')}"
        self.timeline.append(event)

    def add_source(self, source: str):
        line = f"- {source.strip('- ')}"
        if line not in self.sources:
            self.sources.append(line)

    def add_conflict(self, conflict: str):
        line = f"- {conflict.strip('- ')}"
        if line not in self.conflicts:
            self.conflicts.append(line)

    def add_link(self, link: str):
        line = f"- {link.strip('- ')}"
        if line not in self.links:
            self.links.append(line)

    @classmethod
    def load_from_drive(cls, category: Optional[str], filename: str) -> EntityMemory:
        """Fetch and parse an entity memory file from Google Drive."""
        from toolbox.lib.drive_utils import get_drive_service, _resolve_path, _get_file_in_folder, download_file_content
        
        service = get_drive_service()
        root = "01 - Second Brain/Memory"
        path = f"{root}/{category}" if category else root
        
        folder_id = _resolve_path(service, path)
        file_id = _get_file_in_folder(service, folder_id, filename)
        
        if not file_id:
            # Return empty skeleton
            name = filename.replace(".md", "")
            return cls(name)
            
        content_bytes = download_file_content(service, file_id, "text/plain")
        content = content_bytes.decode("utf-8")
        return cls.parse(content)

    def save_to_drive(self, category: Optional[str], filename: str):
        """Render and save current state to Google Drive."""
        from toolbox.lib.drive_utils import get_drive_service, _resolve_path, _get_file_in_folder
        from googleapiclient.http import MediaIoBaseUpload
        import io
        
        service = get_drive_service()
        root = "01 - Second Brain/Memory"
        path = f"{root}/{category}" if category else root
        
        folder_id = _resolve_path(service, path)
        file_id = _get_file_in_folder(service, folder_id, filename)
        
        content = self.render()
        media = MediaIoBaseUpload(io.BytesIO(content.encode()), mimetype='text/markdown')
        
        if file_id:
            service.files().update(fileId=file_id, media_body=media).execute()
            logger.info(f"Updated entity memory: {path}/{filename}")
        else:
            meta = {'name': filename, 'parents': [folder_id]}
            service.files().create(body=meta, media_body=media, fields='id').execute()
            logger.info(f"Created entity memory: {path}/{filename}")
