"""Deterministic entity ID helpers for cross-pipeline identity."""
from __future__ import annotations

import hashlib
import re


def canonicalize_key(*parts: object) -> str:
    """Normalize key parts into a stable canonical string."""
    normalized = []
    for part in parts:
        text = str(part or "").strip().lower()
        text = re.sub(r"\s+", " ", text)
        if text:
            normalized.append(text)
    return "|".join(normalized)


def build_entity_id(domain: str, canonical_key: str) -> str:
    """Return a deterministic entity_id for a domain/key pair."""
    digest = hashlib.sha1(f"{domain}:{canonical_key}".encode("utf-8")).hexdigest()[:12]
    safe_domain = re.sub(r"[^a-z0-9]+", "_", domain.lower()).strip("_")
    return f"{safe_domain}_{digest}"


def order_entity_id(vendor: str, order_key: str) -> str:
    return build_entity_id("orders", canonicalize_key(vendor, order_key))


def travel_entity_id(vendor: str, trip_type: str, confirmation: str, travel_date: str, label: str) -> str:
    return build_entity_id("travel", canonicalize_key(vendor, trip_type, confirmation, travel_date, label))


def calendar_entity_id(source: str, title: str, when: str, location: str) -> str:
    return build_entity_id("calendar", canonicalize_key(source, title, when, location))


def plaud_entity_id(subject: str, doc_date: str) -> str:
    return build_entity_id("plaud", canonicalize_key(subject, doc_date))


def task_entity_id(source: str, subject: str, due_date: str) -> str:
    return build_entity_id("tasks", canonicalize_key(source, subject, due_date))


def low_confidence_entity_id(source_type: str, source_id: str) -> str:
    return build_entity_id("low_confidence", canonicalize_key(source_type, source_id))


def render_entity_comment(entity_id: str) -> str:
    """Emit a hidden markdown marker for entity identity."""
    return f"<!-- entity_id: {entity_id} -->"
