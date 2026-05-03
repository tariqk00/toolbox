"""
Daily OpenClaw model usage report.
Reads yesterday's journalctl logs, tallies calls per model, and sends via Telegram.
"""
import subprocess
import re
from collections import defaultdict
from datetime import date, timedelta

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from lib.telegram import send_message, escape

YESTERDAY = (date.today() - timedelta(days=1)).isoformat()


def fetch_logs(since: str) -> str:
    result = subprocess.run(
        ["journalctl", "--user", "-u", "openclaw-gateway",
         "--since", since, "--until", "today", "--no-pager", "-q"],
        capture_output=True, text=True
    )
    return result.stdout


def parse_usage(logs: str) -> tuple[dict, dict]:
    """Returns (model_counts, fallback_counts)."""
    model_counts = defaultdict(int)
    fallback_counts = defaultdict(int)

    for line in logs.splitlines():
        # Completed calls (successes only)
        if "embedded run agent end" in line and "isError=false" in line:
            m = re.search(r'model=(\S+)\s+provider=(\S+)', line)
            if m:
                model_counts[f"{m.group(2)}/{m.group(1)}"] += 1

        # Fallback decisions (captures when a model failed and what happened next)
        if "[model-fallback/decision]" in line:
            if "candidate_failed" in line:
                m = re.search(r'candidate=(\S+)\s+reason=(\S+)', line)
                if m:
                    fallback_counts[f"{m.group(1)} ({m.group(2)})"] += 1
            elif "candidate_succeeded" in line:
                # This counts successful fallbacks toward usage to accurately reflect total volume
                m = re.search(r'candidate=(\S+)', line)
                if m:
                    model_counts[m.group(1)] += 1

    return dict(model_counts), dict(fallback_counts)


def format_message(model_counts: dict, fallback_counts: dict, report_date: str) -> str:
    total = sum(model_counts.values())
    lines = [f"<b>OpenClaw model usage — {report_date}</b>"]

    if not total:
        lines.append("No calls recorded.")
        return "\n".join(lines)

    lines.append(f"Total calls: {total}")
    lines.append("")
    lines.append("<b>By model:</b>")
    for model, count in sorted(model_counts.items(), key=lambda x: -x[1]):
        pct = round(count / total * 100)
        lines.append(f"  {escape(model)}: {count} ({pct}%)")

    if fallback_counts:
        lines.append("")
        lines.append("<b>Fallbacks:</b>")
        for reason, count in sorted(fallback_counts.items(), key=lambda x: -x[1]):
            lines.append(f"  {escape(reason)}: {count}")
    else:
        lines.append("")
        lines.append("No fallbacks.")

    return "\n".join(lines)


def main():
    logs = fetch_logs(YESTERDAY)
    model_counts, fallback_counts = parse_usage(logs)
    msg = format_message(model_counts, fallback_counts, YESTERDAY)
    ok = send_message(msg, service="oc-model-stats")
    if not ok:
        print(msg)
        sys.exit(1)


if __name__ == "__main__":
    main()
