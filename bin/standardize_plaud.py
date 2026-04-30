#!/usr/bin/env python3
"""
Intelligently categorizes and standardizes Plaud recording storage.
Categorizes into: Work, Personal, Finance, Health, or Other.
Routes to: 01 - Second Brain/Memory/Plaud/[Category]/[Year]/[YYYY-MM-DD - Subject].md
"""
import sys
import os
import re
import json
from datetime import datetime
from pathlib import Path

# Setup paths
REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT.parent))

from toolbox.lib.llm import call_json

CATEGORIZATION_PROMPT = """\
Categorize this voice recording transcript into exactly one of these categories:
- Work: Professional tasks, software engineering, business meetings.
- Personal: Family, hobbies, household errands, general life.
- Finance: Banking, investment, spending, taxes, Uptown Edenton management.
- Health: Fitness, medical, sleep, nutrition.
- Other: Anything that doesn't fit the above.

Subject: {subject}
Content:
{text}

Return ONLY valid JSON:
{{
  "category": "Work" | "Personal" | "Finance" | "Health" | "Other",
  "rationale": "one sentence explanation"
}}
"""

def get_category(subject: str, text: str) -> str:
    """Use LLM to determine the recording category."""
    result = call_json(CATEGORIZATION_PROMPT.format(
        subject=subject,
        text=text[:4000]
    ))
    cat = result.get('category', 'Other')
    # Normalize
    valid = ['Work', 'Personal', 'Finance', 'Health', 'Other']
    return cat if cat in valid else 'Other'

def get_standard_path(category: str, doc_date: str) -> str:
    """Return the standardized folder path: Plaud/[Category]/[Year]"""
    try:
        year = doc_date.split('-')[0]
    except Exception:
        year = datetime.now().strftime('%Y')
    return f"Plaud/{category}/{year}"

if __name__ == "__main__":
    # This script is primarily used as a library by the Plaud processor,
    # but can be extended for batch organization later.
    print("Standardize Plaud Library Loaded.")
