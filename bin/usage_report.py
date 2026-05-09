#!/usr/bin/env python3
"""
Gemini spend reporting helper.

Reads the shared cost ledger and summarizes Gemini usage by source so OpenClaw
and Python script/service callers can be compared without a separate spend log.
"""
import argparse
import json
import os
import sys
from collections import defaultdict
from datetime import datetime, timezone, timedelta

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PARENT_DIR = os.path.dirname(BASE_DIR)
if PARENT_DIR not in sys.path:
    sys.path.insert(0, PARENT_DIR)

from toolbox.lib.quota_manager import COST_LOG_PATH


def _parse_record_day(record: dict) -> str | None:
    stamp = record.get("timestamp") or record.get("date")
    if not stamp:
        return None
    try:
        normalized = stamp.replace("Z", "+00:00")
        return datetime.fromisoformat(normalized).astimezone(timezone.utc).date().isoformat()
    except Exception:
        return stamp[:10] if len(stamp) >= 10 else None


def _record_source(record: dict) -> str:
    return record.get("source") or record.get("run_type") or "unknown"


def load_cost_records(path: str = COST_LOG_PATH) -> list[dict]:
    records: list[dict] = []
    if not os.path.exists(path):
        return records

    with open(path) as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return records


def summarize_cost_records(records: list[dict], days: int = 7) -> dict[str, dict[str, float | int]]:
    cutoff = None
    if days is not None:
        cutoff = (datetime.now(timezone.utc).date() - timedelta(days=days)).isoformat()

    totals: dict[str, dict[str, float | int]] = defaultdict(lambda: {"records": 0, "tokens": 0, "cost": 0.0})
    for record in records:
        rec_day = _parse_record_day(record)
        if cutoff and rec_day and rec_day < cutoff:
            continue

        source = _record_source(record)
        totals[source]["records"] += 1
        totals[source]["tokens"] += int(record.get("tokens_used", record.get("actual_tokens", 0)) or 0)
        totals[source]["cost"] += float(record.get("cost_usd_est", record.get("cost_usd", 0.0)) or 0.0)

    return dict(totals)


def format_summary(totals: dict[str, dict[str, float | int]], days: int = 7) -> str:
    if not totals:
        return f"Gemini spend ({days}d): no usage records"

    lines = [f"Gemini spend ({days}d):"]
    grand_tokens = 0
    grand_cost = 0.0
    for source, data in sorted(totals.items()):
        lines.append(
            f"  {source}: {data['records']} records, {data['tokens']:,} tokens, ~${data['cost']:.4f}"
        )
        grand_tokens += int(data["tokens"])
        grand_cost += float(data["cost"])
    lines.append(f"  Total: {grand_tokens:,} tokens, ~${grand_cost:.4f}")
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Summarize Gemini spend by source.")
    parser.add_argument("--days", type=int, default=7, help="Number of recent days to include.")
    args = parser.parse_args()

    records = load_cost_records()
    totals = summarize_cost_records(records, days=args.days)
    print(format_summary(totals, days=args.days))


if __name__ == "__main__":
    main()
