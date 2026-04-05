"""
Shared daily Gemini token quota tracker.
Both main.py (hourly sorter) and backfill.py write here after each Gemini call.
Uses write-to-temp-then-rename for atomic updates (safe if both run concurrently).
Config: config/quota_state.json (auto-created on first use)
"""
import json
import logging
import os
import tempfile
from datetime import date

logger = logging.getLogger("DriveSorter.Quota")

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
QUOTA_PATH = os.path.join(BASE_DIR, 'config', 'quota_state.json')

DAILY_BUDGET = 500_000
SORTER_RESERVED = 50_000   # tokens kept back for the hourly sorter; backfill stops before this
FILES_PER_RUN = 50
SORTER_RPD_LIMIT = 900     # free tier cap (1,000 RPD - 100 buffer)

# Cost log
COST_LOG_PATH = os.path.join(BASE_DIR, 'logs', 'cost_log.jsonl')
# Gemini Flash blended rate (approximate; input ~$0.075/1M, output ~$0.30/1M)
COST_PER_M_TOKENS = 0.10


def _today() -> str:
    return date.today().isoformat()


def load() -> dict:
    """Load quota state, resetting daily counters if date has changed."""
    today = _today()
    if os.path.exists(QUOTA_PATH):
        try:
            with open(QUOTA_PATH) as f:
                state = json.load(f)
            if state.get("date") == today:
                return state
        except Exception as e:
            logger.warning(f"Could not read quota_state.json: {e}")

    # First use today — reset daily counters, preserve config fields
    return {
        "date": today,
        "total_tokens_used": 0,
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


def remaining() -> int:
    """How many tokens are left in today's budget."""
    state = load()
    return max(0, state.get("daily_budget", DAILY_BUDGET) - state.get("total_tokens_used", 0))


def is_budget_exhausted() -> bool:
    return remaining() <= 0


def backfill_remaining() -> int:
    """Tokens available to backfill — excludes the sorter's reserved slice."""
    return max(0, remaining() - SORTER_RESERVED)


def is_backfill_budget_exhausted() -> bool:
    return backfill_remaining() <= 0


def record_call() -> dict:
    """Increment the sorter's free-tier RPD counter and persist. Returns updated state."""
    state = load()
    state["sorter_calls_today"] = state.get("sorter_calls_today", 0) + 1
    save(state)
    return state


def sorter_calls_remaining() -> int:
    state = load()
    return max(0, SORTER_RPD_LIMIT - state.get("sorter_calls_today", 0))


def is_rpd_exhausted() -> bool:
    return sorter_calls_remaining() <= 0


def log_cost(run_type: str, files_processed: int, tokens_used: int) -> None:
    """Append a cost record to logs/cost_log.jsonl."""
    cost = (tokens_used * COST_PER_M_TOKENS) / 1_000_000
    record = {
        "date": _today(),
        "run_type": run_type,
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
