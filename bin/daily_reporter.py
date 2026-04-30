#!/usr/bin/env python3
"""
Generates docs/life/YYYY-MM-DD.md for the previous calendar day.
Reads from Google Drive Memory files and local config/log files.
"""
import os
import sys
import re
import json
import subprocess
from datetime import date, timedelta, datetime
from pathlib import Path

# Fix sys.path for toolbox modules
REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT.parent))

from toolbox.lib.drive_utils import get_drive_service
from toolbox.lib.log_manager import log
from toolbox.lib.reporter_utils import (
    LIFE_DOCS_REPO, rebuild_site, get_memory_blocks,
    build_stat_card, build_row, logger
)

LIFE_DOCS_DIR = LIFE_DOCS_REPO / 'docs' / 'life'

HAWAII_DEPART = date(2026, 4, 22)
HAWAII_RETURN = date(2026, 5, 4)

def _trip_stat_html(today: date) -> str:
    if today < HAWAII_DEPART:
        n = (HAWAII_DEPART - today).days
        label = 'day to Hawaii' if n == 1 else 'days to Hawaii'
        return f'  <div class="lifedoc-stat">\n    <span class="num">{n}</span>\n    <span class="sub">{label}</span>\n  </div>'
    if today <= HAWAII_RETURN:
        n = (today - HAWAII_DEPART).days + 1
        return f'  <div class="lifedoc-stat">\n    <span class="num">{n}</span>\n    <span class="sub">day in Hawaii 🌴</span>\n  </div>'
    return ''  # trip over — omit stat


def update_home_index(today: date, money_lines: list[str], reading_lines: list[str]) -> None:
    """Regenerate the dynamic header and hero card in docs/index.md."""
    import re as _re
    index_path = LIFE_DOCS_REPO / 'docs' / 'index.md'
    if not index_path.exists():
        return

    # Most recent log file
    log_files = sorted((LIFE_DOCS_REPO / 'docs' / 'life').glob('????-??-??.md'))
    if not log_files:
        return
    log_date_str = log_files[-1].stem

    # ── Subtitle ─────────────────────────────────────────────────────────────
    day_fmt = today.strftime('%a %-d %b')
    subtitle = (
        f'<p class="subtitle">{day_fmt} · {today.year} — most recent log: '
        f'<a href="life/{log_date_str}.md">{log_date_str}</a></p>'
    )

    # ── Money rows ────────────────────────────────────────────────────────────
    money_rows = ''
    money_total = 0.0
    for line in money_lines:
        # Markdown link format: • [text](url) rest
        ml = _re.match(r'• \[(.+?)\]\((.+?)\)\s*(.*)', line)
        if ml:
            link_text, url, rest = ml.group(1), ml.group(2), ml.group(3).strip()
            parts = link_text.rsplit(' — ', 1)
            display = parts[0] if len(parts) > 1 else link_text
            detail = parts[1] if len(parts) > 1 else rest.strip('[]') if rest else ''
            money_rows += build_row(display, url=url, detail=detail) + '\n'
            continue
        # Dollar amount: • Vendor — $X.XX Type
        m = _re.match(r'• (.+?) — \$?([\d.]+) (.+)', line)
        if m:
            vendor, amt_s, typ = m.group(1), m.group(2), m.group(3)
            money_total += float(amt_s)
            money_rows += (
                f'<div class="lifedoc-row">\n'
                f'  <span class="time">—</span>\n'
                f'  <span class="label">{vendor} <span class="chip dim">{typ.lower()}</span></span>\n'
                f'  <span class="amount">${float(amt_s):.2f}</span>\n'
                f'</div>\n'
            )
            continue
        # Fallback: • Vendor — Type
        m2 = _re.match(r'• (.+?) — (.+)', line)
        if m2:
            vendor, typ = m2.group(1), m2.group(2)
            money_rows += build_row(vendor, detail=typ) + '\n'

    money_chip = f'<span class="chip neutral">${money_total:.2f} last log</span>' if money_total else '<span class="chip dim">no data</span>'
    money_section = f'<div class="lifedoc-section"><span>Money</span>{money_chip}</div>\n\n{money_rows}'

    # ── Reading rows ──────────────────────────────────────────────────────────
    reading_rows = ''
    for line in reading_lines:
        m = _re.match(r'• "(.+?)" by (.+?) — .+', line)
        if m:
            title, author = m.group(1)[:60], m.group(2)[:40]
            reading_rows += (
                f'<div class="lifedoc-row">\n'
                f'  <span class="label">{title}<div class="sub">{author} · article</div></span>\n'
                f'  <span class="chip ok">read</span>\n'
                f'</div>\n'
            )
    n_read = len(reading_lines)
    read_chip = f'<span class="chip neutral">{n_read} today</span>' if n_read else '<span class="chip dim">no data</span>'
    reading_section = f'<div class="lifedoc-section"><span>Reading</span>{read_chip}</div>\n\n{reading_rows}'

    # ── Days-logged spark ─────────────────────────────────────────────────────
    logged = {f.stem for f in log_files}
    last7 = [(today - timedelta(days=i)).isoformat() for i in range(6, -1, -1)]
    n_logged = sum(1 for d in last7 if d in logged)
    spark_bars = ''.join(
        '<div class="bar ok" style="height: 100%"></div>' if d in logged else '<div class="bar"></div>'
        for d in last7
    )
    spark_html = (
        f'<div class="lifedoc-spark">\n'
        f'  <div class="bars">{spark_bars}</div>\n'
        f'  <div class="label">{n_logged}/7 days logged</div>\n'
        f'</div>'
    )

    # ── Stat cards ────────────────────────────────────────────────────────────
    trip_stat = _trip_stat_html(today)
    stats_html = (
        f'<div class="lifedoc-stats">\n'
        f'{trip_stat}'
        f'  <div class="lifedoc-stat">\n'
        f'    <span class="num">0</span>\n'
        f'    <span class="sub">active tasks 📝</span>\n'
        f'  </div>\n'
        f'</div>'
    )

    # ── Final Assemble ────────────────────────────────────────────────────────
    new_content = (
        f'# Life Dashboard\n\n'
        f'{subtitle}\n\n'
        f'<div class="lifedoc-hero">\n'
        f'  {spark_html}\n'
        f'  {stats_html}\n'
        f'</div>\n\n'
        f'{money_section}\n'
        f'{reading_section}\n'
    )

    full_text = index_path.read_text()
    # Replace everything from # Life Dashboard until the next section if it exists, or till end
    # Actually, the index has content after the hero. Let's use a delimiter or regex.
    pattern = r'# Life Dashboard.*?(?=\n##|\Z)'
    updated = _re.sub(pattern, new_content.strip(), full_text, flags=_re.DOTALL)
    index_path.write_text(updated)
    logger.info("Updated docs/index.md", extra={"log_date": log_date_str, "days_logged": f"{n_logged}/7"})


def main():
    yesterday_date = date.today() - timedelta(days=1)
    yesterday = yesterday_date.isoformat()
    
    log("RUN_START", "START", "Daily reporter started", data={
        "report_date": yesterday,
    }, app_name="reporting")
    logger.info(f"Generating report for {yesterday}...")
    service = get_drive_service()
    
    sections = {
        'Money': [],
        'Reading': [],
        'Travel': [],
        'Inbox': [],
    }
    
    # Use reporter_utils to fetch memory blocks
    # 1. Money (Orders + Receipts)
    for category in ['Orders', 'Receipts']:
        blocks = get_memory_blocks(service, f'{category}/Amazon.md', yesterday)
        blocks += get_memory_blocks(service, f'{category}/General.md', yesterday)
        for b in blocks:
            # Extract bullet points
            lines = [l.strip() for l in b.split('\n') if l.strip().startswith('•')]
            sections['Money'].extend(lines)
    log("REPORT_SECTION", "SUCCESS", "Built Money section", data={
        "section": "Money",
        "items": len(sections['Money']),
    }, app_name="reporting")
            
    # 2. Travel
    travel_blocks = get_memory_blocks(service, 'Travel.md', yesterday)
    for b in travel_blocks:
        for line in b.split('\n'):
            line = line.strip()
            if line.startswith('•'):
                # Format: • [label](url) [status]
                m = re.match(r'• \[(.+?)\]\((.+?)\) \[(.+?)\]', line)
                if m:
                    label, url, status = m.groups()
                    sections['Travel'].append(f"• [{label}]({url}) [{status}]")
                else:
                    sections['Travel'].append(line)
    log("REPORT_SECTION", "SUCCESS", "Built Travel section", data={
        "section": "Travel",
        "items": len(sections['Travel']),
    }, app_name="reporting")
                
    # 3. Inbox (Action Required)
    inbox_blocks = get_memory_blocks(service, 'Inbox/Action Required.md', yesterday)
    for b in inbox_blocks:
        # Extract headings as items
        for line in b.split('\n'):
            line = line.strip()
            if line.startswith('### '):
                subject = line.replace('### ', '').strip()
                sections['Inbox'].append(f"• {subject}")
    log("REPORT_SECTION", "SUCCESS", "Built Inbox section", data={
        "section": "Inbox",
        "items": len(sections['Inbox']),
    }, app_name="reporting")
    
    # 4. Readwise (local config)
    last_digest = REPO_ROOT / 'config' / 'readwise_last_digest.json'
    if last_digest.exists():
        try:
            data = json.loads(last_digest.read_text())
            # Readwise digest might have arrived 'yesterday'
            if data.get('date') == yesterday:
                for a in data.get('articles', []):
                    title = a.get('title', 'Unknown')
                    author = a.get('author', 'Unknown')
                    summary = a.get('summary', '').replace('\n', ' ')
                    sections['Reading'].append(f'• "{title}" by {author} — {summary}')
        except Exception as e:
            print(f"Error reading readwise digest: {e}")
            log("REPORT_SECTION", "FAILURE", "Failed reading Readwise digest", data={
                "section": "Reading",
                "error_type": type(e).__name__,
            }, level="ERROR", app_name="reporting")
    log("REPORT_SECTION", "SUCCESS", "Built Reading section", data={
        "section": "Reading",
        "items": len(sections['Reading']),
    }, app_name="reporting")
            
    # Output markdown
    LIFE_DOCS_DIR.mkdir(parents=True, exist_ok=True)
    out_lines = [f"# {yesterday}\n"]
    
    has_data = False
    for sec_name in ['Inbox', 'Money', 'Travel', 'Reading']:
        if sections[sec_name]:
            has_data = True
            out_lines.append(f"## {sec_name}")
            out_lines.extend(sections[sec_name])
            out_lines.append("")
            
    if not has_data:
        out_lines.append("_No activity recorded for this date._\n")
        
    out_lines.append("---")
    out_lines.append(f"_Generated {datetime.now().strftime('%Y-%m-%d %H:%M')}_")
    
    md_path = LIFE_DOCS_DIR / f"{yesterday}.md"
    md_path.write_text("\n".join(out_lines))
    
    # Update life/index.md (The list of all logs)
    index_path = LIFE_DOCS_DIR / 'index.md'
    if index_path.exists():
        lines = index_path.read_text().split('\n')
        link = f"- [{yesterday}]({yesterday}.md) — {yesterday_date.strftime('%a %d %b')}"
        if link not in lines:
            insert_idx = next((i for i, l in enumerate(lines) if l.startswith('- [')), None)
            if insert_idx is None:
                header_idx = next((i for i, l in enumerate(lines) if l.startswith('# ')), 0)
                insert_idx = header_idx + 1
            lines.insert(insert_idx, link)
            # Keep last 30 entries
            list_start = insert_idx
            list_end = list_start
            while list_end < len(lines) and lines[list_end].startswith('- ['):
                list_end += 1
            if list_end - list_start > 30:
                lines = lines[:list_start + 30] + lines[list_end:]
            index_path.write_text("\n".join(lines))
                
    # Update main index.md (The Dashboard)
    update_home_index(
        today=date.today(),
        money_lines=[l for l in sections.get('Money', []) if l.startswith('•')],
        reading_lines=[l for l in sections.get('Reading', []) if l.startswith('•')],
    )

    # Build and Push
    logger.info("Building site and pushing to Git...")
    publish_success = False
    if rebuild_site():
        try:
            subprocess.run(['git', 'add', 'docs/life/', 'docs/index.md'], cwd=LIFE_DOCS_REPO, check=True)
            subprocess.run(['git', 'commit', '-m', f"daily: {yesterday}"], cwd=LIFE_DOCS_REPO, check=False)
            subprocess.run(['git', 'push'], cwd=LIFE_DOCS_REPO, check=True)
            logger.info("Successfully pushed daily report to Git.")
            log("GIT_PUBLISH", "SUCCESS", "Published daily report to life-docs", data={
                "report_date": yesterday,
            }, app_name="reporting")
            publish_success = True
        except subprocess.CalledProcessError as e:
            logger.error(f"Git operation failed: {e}")
            log("GIT_PUBLISH", "FAILURE", "Failed publishing daily report to life-docs", data={
                "report_date": yesterday,
                "error_type": type(e).__name__,
            }, level="ERROR", app_name="reporting")

    total_items = sum(len(items) for items in sections.values())
    log("RUN_COMPLETE", "SUCCESS" if publish_success else "ERROR", 
        f"Daily reporter finished for {yesterday}", data={
        "report_date": yesterday,
        "sections": {name: len(items) for name, items in sections.items()},
        "total_items": total_items,
    }, app_name="daily-reporter")

if __name__ == '__main__':
    subprocess.run(['git', 'pull', '--rebase'], cwd=LIFE_DOCS_REPO, check=True)
    main()
