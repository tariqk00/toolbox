from __future__ import annotations

import logging
import os
import re
from datetime import datetime, timezone

from toolbox.lib.ai_engine import analyze_with_gemini
from toolbox.lib.drive_utils import (
    _resolve_path,
    download_file_content,
    get_category_prompt_str,
    get_drive_service,
    move_file,
    resolve_folder_id,
)
from toolbox.lib.entity_ids import low_confidence_entity_id
from toolbox.lib.entity_memory import EntityMemory
from toolbox.services.email_extractor.writers import list_memory_files

logger = logging.getLogger("toolbox.low_confidence")

LOW_CONFIDENCE_DRIVE_PATH = "01 - Second Brain/Low Confidence"
LOW_CONFIDENCE_MEMORY_CATEGORY = "Low Confidence"

_CONFIDENCE_MAP = {
    "high": "High",
    "medium": "Medium",
    "med": "Medium",
    "low": "Low",
}


def normalize_confidence(value: str) -> str:
    raw = str(value or "").strip().lower()
    return _CONFIDENCE_MAP.get(raw, "Low")


def generate_new_name(analysis: dict, original_name: str, created_time_str: str) -> str:
    ext = os.path.splitext(original_name)[1]
    date = analysis.get("doc_date", "0000-00-00")
    if date == "0000-00-00":
        match = re.search(r"(\d{4}-\d{2}-\d{2})", original_name)
        if match:
            date = match.group(1)
        elif created_time_str:
            date = created_time_str[:10]

    entity = str(analysis.get("entity") or "Unknown")
    summary = str(analysis.get("summary") or "Doc")
    safe_entity = "".join(c for c in entity if c.isalnum() or c in [" ", "_", "-"]).strip().replace(" ", "_")
    safe_summary = "".join(c for c in summary if c.isalnum() or c in [" ", "_", "-"]).strip().replace(" ", "_")
    if date == "0000-00-00" or not date:
        safe_summary = f"{safe_summary}_(NoDate)"
    return f"{date} - {safe_entity} - {safe_summary}{ext}"


def low_confidence_filename(source_id: str) -> str:
    return f"{source_id}.md"


def route_needs_low_confidence(confidence: str, target_id: str | None) -> bool:
    return normalize_confidence(confidence) != "High" or not target_id


def record_drive_low_confidence(
    *,
    file_id: str,
    current_name: str,
    source_folder_path: str,
    created_time: str,
    analysis: dict,
    proposed_name: str,
    status: str = "Pending Reprocess",
) -> str:
    filename = low_confidence_filename(file_id)
    memory = EntityMemory.load_from_drive(LOW_CONFIDENCE_MEMORY_CATEGORY, filename)
    memory.name = f"Drive File: {current_name}"
    memory.entity_id = memory.entity_id or low_confidence_entity_id("drive_file", file_id)
    confidence = normalize_confidence(analysis.get("confidence"))
    proposed_folder = analysis.get("folder_path") or ""
    memory.set_summary(
        analysis.get("reasoning")
        or "Low-confidence Drive classification pending review or reprocessing."
    )
    memory.set_field("Source Type", "Drive File")
    memory.set_field("File ID", file_id)
    memory.set_field("Current Name", current_name)
    memory.set_field("Source Folder Path", source_folder_path or "Unknown")
    memory.set_field("Created Time", created_time or "")
    memory.set_field("Proposed Entity", analysis.get("entity") or "Unknown")
    memory.set_field("Proposed Summary", analysis.get("summary") or "Unknown")
    memory.set_field("Proposed Folder Path", proposed_folder)
    memory.set_field("Proposed Name", proposed_name or current_name)
    memory.set_field("Confidence", confidence)
    memory.set_field("Status", status)
    memory.set_field("Last Evaluated", datetime.now(timezone.utc).isoformat())

    attempts = int(memory.fields.get("Attempts") or "0") + 1
    memory.set_field("Attempts", str(attempts))

    memory.add_source(f"Drive file ID {file_id}")
    memory.add_timeline_event(
        f"Recorded low-confidence classification [{confidence}] → "
        f"{proposed_folder or 'Unknown'} / {proposed_name or current_name}"
    )
    memory.save_to_drive(LOW_CONFIDENCE_MEMORY_CATEGORY, filename)
    return filename


def route_drive_file_to_low_confidence(
    *,
    service,
    file_id: str,
    current_name: str,
    source_folder_id: str,
    source_folder_path: str,
    created_time: str,
    analysis: dict,
    proposed_name: str,
) -> dict:
    bucket_id = _resolve_path(service, LOW_CONFIDENCE_DRIVE_PATH)
    if bucket_id != source_folder_id:
        move_file(service, file_id, bucket_id, current_name)

    memory_filename = record_drive_low_confidence(
        file_id=file_id,
        current_name=current_name,
        source_folder_path=source_folder_path,
        created_time=created_time,
        analysis=analysis,
        proposed_name=proposed_name,
    )
    return {
        "bucket_id": bucket_id,
        "memory_filename": memory_filename,
        "confidence": normalize_confidence(analysis.get("confidence")),
    }


def reprocess_low_confidence_drive_files(
    *,
    limit: int = 0,
    execute: bool = False,
    service=None,
) -> list[dict]:
    if service is None:
        service = get_drive_service()

    folder_paths_str = get_category_prompt_str()
    results: list[dict] = []
    count = 0

    for filename in sorted(list_memory_files(LOW_CONFIDENCE_MEMORY_CATEGORY)):
        if limit and count >= limit:
            break

        memory = EntityMemory.load_from_drive(LOW_CONFIDENCE_MEMORY_CATEGORY, filename)
        if memory.fields.get("Source Type") != "Drive File":
            continue
        if memory.fields.get("Status") == "Promoted":
            continue

        file_id = memory.fields.get("File ID", "")
        if not file_id:
            continue

        meta = service.files().get(
            fileId=file_id,
            fields="id,name,mimeType,createdTime,parents",
        ).execute()
        current_name = meta.get("name", memory.fields.get("Current Name", file_id))
        mime = meta.get("mimeType", "text/plain")
        created_time = meta.get("createdTime", memory.fields.get("Created Time", ""))
        parents = meta.get("parents", [])
        source_folder_id = parents[0] if parents else ""

        content = download_file_content(service, file_id, mime)
        if not content:
            continue

        context_hint = (
            f"File in folder: {memory.fields.get('Source Folder Path', LOW_CONFIDENCE_DRIVE_PATH)}. "
            f"Created: {created_time}"
        )
        analysis, _tokens = analyze_with_gemini(
            content,
            mime,
            current_name,
            folder_paths_str,
            context_hint,
            file_id=file_id,
            use_free_tier=True,
        )

        proposed_name = generate_new_name(analysis, current_name, created_time)
        confidence = normalize_confidence(analysis.get("confidence"))
        target_path = analysis.get("folder_path") or ""
        target_id = resolve_folder_id(target_path) if target_path else None

        promoted = False
        if execute and confidence == "High" and target_id:
            if proposed_name != current_name:
                service.files().update(fileId=file_id, body={"name": proposed_name}).execute()
            if target_id != source_folder_id:
                move_file(service, file_id, target_id, proposed_name)
            promoted = True

        memory.name = f"Drive File: {current_name}"
        memory.set_summary(
            analysis.get("reasoning")
            or "Low-confidence Drive classification pending review or reprocessing."
        )
        memory.set_field("Current Name", current_name)
        memory.set_field("Created Time", created_time or "")
        memory.set_field("Proposed Entity", analysis.get("entity") or "Unknown")
        memory.set_field("Proposed Summary", analysis.get("summary") or "Unknown")
        memory.set_field("Proposed Folder Path", target_path)
        memory.set_field("Proposed Name", proposed_name or current_name)
        memory.set_field("Confidence", confidence)
        memory.set_field("Status", "Promoted" if promoted else "Pending Reprocess")
        memory.set_field("Last Evaluated", datetime.now(timezone.utc).isoformat())
        memory.set_field("Attempts", str(int(memory.fields.get("Attempts") or "0") + 1))
        memory.add_timeline_event(
            (
                f"Promoted to {target_path} as {proposed_name}"
                if promoted
                else f"Reprocessed [{confidence}] → {target_path or 'Unknown'} / {proposed_name}"
            )
        )
        memory.save_to_drive(LOW_CONFIDENCE_MEMORY_CATEGORY, filename)

        results.append(
            {
                "file_id": file_id,
                "filename": filename,
                "promoted": promoted,
                "confidence": confidence,
                "target_path": target_path,
                "proposed_name": proposed_name,
            }
        )
        count += 1

    return results
