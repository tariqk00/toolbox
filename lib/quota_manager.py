"""
Shared daily Gemini token quota tracker.
Both main.py (hourly sorter) and backfill.py write here after each Gemini call.
Uses write-to-temp-then-rename for atomic updates (safe if both run concurrently).
Config: config/quota_state.json
"""
import os
import json
import logging
import tempfile
from datetime import datetime

logger = logging.getLogger("DriveSorter.AI.Quota")

# --- CONFIG ---
# This file is in toolbox/lib/quota_manager.py
# Base dir is toolbox/
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
QUOTA_PATH = os.path.join(BASE_DIR, 'config', 'quota_state.json')
COST_LOG_PATH = os.path.join(BASE_DIR, 'logs', 'cost_log.jsonl')

DAILY_BUDGET = 1500000  # Default 1.5M tokens
FILES_PER_RUN = 100     # Default files to process per run

def load() -> dict:
    """Load current quota state."""
    today = datetime.now().strftime('%Y-%m-%d')
    if os.path.exists(QUOTA_PATH):
        try:
            with open(QUOTA_PATH, 'r') as f:
                state = json.load(f)
                if state.get('date') == today:
                    return state
        except Exception as e:
            logger.error(f"Error loading quota_state.json: {e}")

    # First use today — reset daily counters, preserve config fields
    return {
        "date": today,
        "total_tokens_used": 0,
        "total_usd_used": 0.0,
        "daily_budget": DAILY_BUDGET,
        "files_per_run": FILES_PER_RUN,
        "sorter_calls_today": 0,
    }


def save(state: dict) -> None:
    """Atomically write quota state."""
    os.makedirs(os.path.dirname(QUOTA_PATH), exist_ok=True)
    dir_ = os.path.dirname(QUOTA_PATH)
    try:
        with tempfile.NamedTemporaryFile('w', dir=dir_, delete=False, suffix='.tmp') as f:
            json.dump(state, f, indent=2)
            tmp_path = f.name
        os.replace(tmp_path, QUOTA_PATH)
    except Exception as e:
        logger.error(f"Failed to save quota_state.json: {e}")


def record_tokens(tokens: int) -> dict:
    """Add tokens to today's total and persist. Returns updated state."""
    state = load()
    state["total_tokens_used"] = state.get("total_tokens_used", 0) + tokens
    save(state)
    return state


def record_llm_usage(tokens: int, usd_cost: float) -> dict:
    """Record both tokens and USD cost for a single LLM call."""
    state = load()
    state["total_tokens_used"] = state.get("total_tokens_used", 0) + tokens
    state["total_usd_used"] = state.get("total_usd_used", 0.0) + usd_cost
    save(state)
    return state


def get_total_usd_used() -> float:
    """Return today's total USD usage."""
    return load().get("total_usd_used", 0.0)


def remaining() -> int:
    """How many tokens are left in today's budget."""
    state = load()
    return max(0, state.get("daily_budget", DAILY_BUDGET) - state.get("total_tokens_used", 0))


def is_exhausted() -> bool:
    """Check if we've hit the daily token limit."""
    return remaining() <= 0


def record_call() -> None:
    """Track calls to Gemini per day (for RPD monitoring)."""
    state = load()
    state['sorter_calls_today'] = state.get('sorter_calls_today', 0) + 1
    save(state)


def is_rpd_exhausted() -> bool:
    """Check if we've exceeded the free-tier RPD (e.g. 1500 calls/day)."""
    state = load()
    # 1400 as safety margin before falling back to paid
    return state.get('sorter_calls_today', 0) >= 1400


def log_cost(run_type_or_record: str | dict, files_processed: int = 0, tokens_used: int = 0) -> None:
    """
    Append a cost record to cost_log.jsonl.
    Supports both legacy positional args and the new single-dict record format.
    """
    if isinstance(run_type_or_record, dict):
        record = run_type_or_record
    else:
        # Legacy positional path
        cost = (tokens_used * 0.10) / 1_000_000 # Default rate
        record = {
            "date": datetime.now().strftime('%Y-%m-%d'),
            "run_type": run_type_or_record,
            "files_processed": files_processed,
            "tokens_used": tokens_used,
            "cost_usd_est": round(cost, 6),
        }

    os.makedirs(os.path.dirname(COST_LOG_PATH), exist_ok=True)
    try:
        with open(COST_LOG_PATH, 'a') as f:
            f.write(json.dumps(record) + '\n')
    except Exception as e:
        logger.error(f"Failed to write cost_log.jsonl: {e}")
