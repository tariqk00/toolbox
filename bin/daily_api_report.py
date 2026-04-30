#!/usr/bin/env python3
"""
Daily API and optimization report.
Summarizes yesterday's cost log and structured service activity, then sends
the result to Telegram.
"""
from __future__ import annotations

import json
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from toolbox.lib.log_manager import LogManager, log
from toolbox.lib.quota_manager import COST_LOG_PATH
from toolbox.lib.telegram import escape, send_message

REPORT_SERVICE = "daily-api-report"
CORE_APPS = (
    "ai-sorter",
    "email-extractor",
    "inbox-scanner",
    "daily-reporter",
    "work-reporter",
    "token-monitor",
)


def _activity_log_path() -> Path:
    return Path(LogManager.default_log_dir()) / "activity.jsonl"


def _iter_jsonl(path: Path):
    if not path.exists():
        return
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError:
                continue


def _parse_timestamp(value: str) -> datetime | None:
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def build_usage_summary(report_date: str, cost_log_path: str | Path = COST_LOG_PATH) -> dict:
    path = Path(cost_log_path)
    runs = defaultdict(lambda: {"runs": 0, "tokens": 0, "cost": 0.0, "files": 0})

    for rec in _iter_jsonl(path) or ():
        if rec.get("date") != report_date:
            continue
        run_type = rec.get("run_type", "unknown")
        row = runs[run_type]
        row["runs"] += 1
        row["tokens"] += int(rec.get("tokens_used", 0) or 0)
        row["cost"] += float(rec.get("cost_usd_est", 0.0) or 0.0)
        row["files"] += int(rec.get("files_processed", 0) or 0)

    total_tokens = sum(v["tokens"] for v in runs.values())
    total_cost = round(sum(v["cost"] for v in runs.values()), 6)
    total_files = sum(v["files"] for v in runs.values())
    tokens_per_file = round(total_tokens / total_files, 1) if total_files else 0.0

    heaviest = None
    for run_type, data in runs.items():
        if data["files"] <= 0:
            continue
        tpf = data["tokens"] / data["files"]
        candidate = (run_type, round(tpf, 1), data["runs"])
        if heaviest is None or candidate[1] > heaviest[1]:
            heaviest = candidate

    return {
        "report_date": report_date,
        "runs": dict(sorted(runs.items())),
        "total_tokens": total_tokens,
        "total_cost": total_cost,
        "total_files": total_files,
        "tokens_per_file": tokens_per_file,
        "heaviest_run": heaviest,
    }


def build_service_summary(report_date: str, activity_log_path: str | Path | None = None) -> dict:
    path = Path(activity_log_path) if activity_log_path else _activity_log_path()
    services = {
        app: {"runs": 0, "success": 0, "failure": 0, "latest_status": None, "latest_event": None}
        for app in CORE_APPS
    }
    auth_failures = 0

    for entry in _iter_jsonl(path) or ():
        ts = _parse_timestamp(entry.get("timestamp", ""))
        if not ts or ts.date().isoformat() != report_date:
            continue

        app = entry.get("app")
        event = entry.get("event")
        status = entry.get("status")
        if event and event.startswith("AUTH_") and status in {"FAILURE", "RETRY"}:
            auth_failures += 1

        if app not in services:
            continue

        if event == "RUN_COMPLETE":
            services[app]["runs"] += 1
            if status == "SUCCESS":
                services[app]["success"] += 1
            else:
                services[app]["failure"] += 1
            services[app]["latest_status"] = status
            services[app]["latest_event"] = event
        elif app == "token-monitor" and event == "TOKEN_MONITOR":
            services[app]["latest_status"] = status
            services[app]["latest_event"] = event
            if status == "ALERT":
                services[app]["failure"] += 1
            elif status == "SUCCESS":
                services[app]["success"] += 1

    failing = [app for app, data in services.items() if data["failure"] > 0]
    healthy = [app for app, data in services.items() if data["success"] > 0 and data["failure"] == 0]
    return {
        "report_date": report_date,
        "services": services,
        "auth_failures": auth_failures,
        "failing_services": failing,
        "healthy_services": healthy,
    }


def build_optimization_signals(usage: dict, services: dict) -> list[str]:
    signals = []
    if usage["total_tokens"] > 0 and usage["total_files"] > 0:
        signals.append(
            f"Efficiency: {usage['total_tokens']:,} tokens across {usage['total_files']} files "
            f"({usage['tokens_per_file']:.1f}/file)"
        )
    elif usage["total_tokens"] > 0:
        signals.append(f"Usage recorded without file counts: {usage['total_tokens']:,} tokens")
    else:
        signals.append("No API token usage recorded")

    if usage["heaviest_run"]:
        run_type, per_file, runs = usage["heaviest_run"]
        signals.append(f"Heaviest run: {run_type} at {per_file:.1f} tokens/file across {runs} run(s)")

    if services["failing_services"]:
        signals.append(f"Service failures: {', '.join(sorted(services['failing_services']))}")
    else:
        signals.append("No structured service failures recorded")

    if services["auth_failures"]:
        signals.append(f"Auth churn: {services['auth_failures']} auth failure/retry event(s)")

    return signals


def format_message(report_date: str, usage: dict, services: dict, signals: list[str]) -> str:
    lines = [f"<b>Daily API &amp; Optimization Report — {escape(report_date)}</b>", ""]

    lines.append("<b>API Usage</b>")
    if usage["runs"]:
        for run_type, data in usage["runs"].items():
            lines.append(
                f"• {escape(run_type)}: {data['runs']} run(s), "
                f"{data['tokens']:,} tokens, {data['files']} files, ~${data['cost']:.4f}"
            )
        lines.append(
            f"• Total: {usage['total_tokens']:,} tokens, {usage['total_files']} files, "
            f"~${usage['total_cost']:.4f}"
        )
    else:
        lines.append("• No cost log activity recorded")

    lines.append("")
    lines.append("<b>Service Health</b>")
    for app in CORE_APPS:
        data = services["services"][app]
        if data["runs"] == 0 and data["latest_event"] is None:
            continue
        status = data["latest_status"] or "UNKNOWN"
        lines.append(
            f"• {escape(app)}: status={escape(status)} runs={data['runs']} "
            f"ok={data['success']} fail={data['failure']}"
        )
    if services["auth_failures"]:
        lines.append(f"• auth failures/retries: {services['auth_failures']}")

    lines.append("")
    lines.append("<b>Optimization Signals</b>")
    for signal in signals:
        lines.append(f"• {escape(signal)}")

    return "\n".join(lines)


def main(report_date: str | None = None) -> bool:
    if report_date is None:
        report_date = (date.today() - timedelta(days=1)).isoformat()

    log("RUN_START", "START", "Daily API report started", data={"report_date": report_date}, app_name=REPORT_SERVICE)

    usage = build_usage_summary(report_date)
    log("REPORT_SECTION", "SUCCESS", "Built API usage section", data={
        "report_date": report_date,
        "runs": len(usage["runs"]),
        "tokens": usage["total_tokens"],
    }, app_name=REPORT_SERVICE)

    services = build_service_summary(report_date)
    log("REPORT_SECTION", "SUCCESS", "Built service health section", data={
        "report_date": report_date,
        "tracked_services": len(CORE_APPS),
        "failing_services": len(services["failing_services"]),
    }, app_name=REPORT_SERVICE)

    signals = build_optimization_signals(usage, services)
    log("REPORT_SECTION", "SUCCESS", "Built optimization signals section", data={
        "report_date": report_date,
        "signals": len(signals),
    }, app_name=REPORT_SERVICE)

    message = format_message(report_date, usage, services, signals)
    delivered = send_message(message, service=REPORT_SERVICE)
    log(
        "RUN_COMPLETE",
        "SUCCESS" if delivered else "FAILURE",
        "Daily API report finished",
        data={
            "report_date": report_date,
            "delivered": delivered,
            "tokens": usage["total_tokens"],
            "failing_services": len(services["failing_services"]),
        },
        level="INFO" if delivered else "ERROR",
        app_name=REPORT_SERVICE,
    )
    return delivered


if __name__ == "__main__":
    raise SystemExit(0 if main() else 1)
