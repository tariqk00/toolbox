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

# Setup paths
TOOLBOX_ROOT = Path(__file__).resolve().parent.parent
LIFE_DOCS_REPO = Path.home() / 'github' / 'tariqk00' / 'life-docs'
LIFE_DOCS_DIR = LIFE_DOCS_REPO / 'docs' / 'life'
MKDOCS = TOOLBOX_ROOT / 'google-drive' / 'venv' / 'bin' / 'mkdocs'

# Fix sys.path for toolbox modules
sys.path.insert(0, str(TOOLBOX_ROOT.parent))
from toolbox.lib.drive_utils import get_drive_service, DRIVE_TREE

def parse_blocks_for_date(content: str, date_str: str) -> list[str]:
    """Return all ## blocks whose header starts with the given date."""
    blocks = content.split('\n---')
    return [b.strip() for b in blocks if b.strip().startswith(f'## {date_str}')]

def list_files_in_folder(service, folder_id: str) -> list[dict]:
    query = f"'{folder_id}' in parents and trashed = false"
    try:
        results = service.files().list(q=query, fields='files(id, name)').execute()
        return results.get('files', [])
    except Exception as e:
        print(f"Error listing files in {folder_id}: {e}")
        return []

def download_file(service, file_id: str) -> str:
    try:
        content = service.files().get_media(fileId=file_id).execute()
        return content.decode('utf-8') if isinstance(content, bytes) else content
    except Exception as e:
        print(f"Error downloading {file_id}: {e}")
        return ""

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
    log_date_str = log_files[-1].stem  # e.g. "2026-04-19"

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
        # Format: "• Vendor — [$X.XX] [Type]" or "• Vendor — Type"
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
        else:
            m2 = _re.match(r'• (.+?) — (.+)', line)
            if m2:
                vendor, typ = m2.group(1), m2.group(2)
                money_rows += (
                    f'<div class="lifedoc-row">\n'
                    f'  <span class="time">—</span>\n'
                    f'  <span class="label">{vendor} <span class="chip dim">{typ.lower()}</span></span>\n'
                    f'</div>\n'
                )

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

    # ── Trip stat ─────────────────────────────────────────────────────────────
    trip_stat = _trip_stat_html(today)

    # ── Assemble hero card ────────────────────────────────────────────────────
    no_money = '<p style="color:var(--text-dim);font-size:12px">No receipts logged.</p>' if not money_rows else ''
    no_read = '<p style="color:var(--text-dim);font-size:12px">No reading logged.</p>' if not reading_rows else ''

    new_hero = f'''\
<div class="lifedoc-card hero" markdown>

<div class="card-header">
  <span class="card-title">Today\'s Log</span>
  <a class="card-link" href="life/{log_date_str}.md">open full log →</a>
</div>

<div class="lifedoc-sections">

<div class="lifedoc-section-block">

{money_section}{no_money}
</div>

<div class="lifedoc-section-block">

{reading_section}{no_read}
</div>

<!-- Future sections drop in here as additional .lifedoc-section-block divs -->

</div>

<div class="lifedoc-stat-row">
  <div class="lifedoc-stat">
    <span class="num">0</span>
    <span class="sub">Inbox · 0 to action</span>
  </div>
{trip_stat}
  <div class="lifedoc-stat">
    <div class="spark" title="Days with logs · last 7">
      {spark_bars}
    </div>
    <span class="sub">{n_logged} of 7 days logged</span>
  </div>
</div>

</div>'''

    content = index_path.read_text()
    content = _re.sub(
        r'<!-- BEGIN_DYNAMIC_HEADER -->.*?<!-- END_DYNAMIC_HEADER -->',
        f'<!-- BEGIN_DYNAMIC_HEADER -->\n{subtitle}\n<!-- END_DYNAMIC_HEADER -->',
        content, flags=_re.DOTALL,
    )
    content = _re.sub(
        r'<!-- BEGIN_HERO -->.*?<!-- END_HERO -->',
        f'<!-- BEGIN_HERO -->\n{new_hero}\n<!-- END_HERO -->',
        content, flags=_re.DOTALL,
    )
    index_path.write_text(content)
    print(f'Updated docs/index.md → {log_date_str}, {n_logged}/7 days logged')


def main():
    yesterday_date = date.today() - timedelta(days=1)
    yesterday = yesterday_date.isoformat()
    service = get_drive_service()
    
    sections = {
        'Inbox': [],
        'Money': [],
        'Travel': [],
        'Reading': []
    }
    
    # Data source 1 & 2: Receipts and Orders
    money_sections = []
    
    # Receipts
    receipts_folder_id = DRIVE_TREE.get('path_to_id', {}).get('01 - Second Brain/Memory/Receipts')
    if receipts_folder_id:
        receipts = []
        files = list_files_in_folder(service, receipts_folder_id)
        for f in files:
            content = download_file(service, f['id'])
            blocks = parse_blocks_for_date(content, yesterday)
            for b in blocks:
                vendor = f['name'].replace('.md', '')
                amt_m = re.search(r'\*\*Amount:\*\*\s*(.+)', b)
                type_m = re.search(r'\*\*Type:\*\*\s*\[(.+?)\]', b)
                amt = (amt_m.group(1).strip() if amt_m else '').strip()
                typ = (type_m.group(1).strip() if type_m else '').strip()
                label = f"{amt} {typ}".strip() if amt else typ or 'Payment'
                receipts.append(f"• {vendor} — {label}")
        if receipts:
            money_sections.append("**Receipts**\n" + "\n".join(receipts))
            
    # Orders
    orders_folder_id = DRIVE_TREE.get('path_to_id', {}).get('01 - Second Brain/Memory/Orders')
    if orders_folder_id:
        orders = []
        files = list_files_in_folder(service, orders_folder_id)
        for f in files:
            content = download_file(service, f['id'])
            blocks = parse_blocks_for_date(content, yesterday)
            for b in blocks:
                vendor_m = re.search(r'\*\*Vendor:\*\*\s*(.+)', b)
                header = b.split('\n')[0]
                order_m = re.search(r'Order #(\S+)', header)
                status_m = re.search(r'\*\*Status:\*\*\s*\[(.+?)\]', b)
                
                vendor = vendor_m.group(1) if vendor_m else 'Unknown Vendor'
                order = order_m.group(1) if order_m else 'Unknown'
                status = status_m.group(1) if status_m else 'Unknown'
                
                orders.append(f"• {vendor} — Order #{order} [{status}]")
        if orders:
            money_sections.append("**Orders**\n" + "\n".join(orders))
            
    if money_sections:
        sections['Money'] = "\n\n".join(money_sections).split('\n')
        
    # Data source 3: Travel
    memory_folder_id = DRIVE_TREE.get('path_to_id', {}).get('01 - Second Brain/Memory')
    if memory_folder_id:
        files = list_files_in_folder(service, memory_folder_id)
        travel_file = next((f for f in files if f['name'] == 'Travel.md'), None)
        if travel_file:
            content = download_file(service, travel_file['id'])
            blocks = parse_blocks_for_date(content, yesterday)
            for b in blocks:
                header = b.split('\n')[0]
                # Format: ## YYYY-MM-DD — Type — Destination
                parts = header.split('—')
                typ_dest = ' — '.join(p.strip() for p in parts[1:]) if len(parts) > 1 else 'Unknown Trip'
                vendor_m = re.search(r'\*\*Vendor:\*\*\s*(.+)', b)
                status_m = re.search(r'\*\*Status:\*\*\s*\[(.+?)\]', b)
                vendor = vendor_m.group(1) if vendor_m else 'Unknown Vendor'
                status = status_m.group(1) if status_m else 'Unknown'
                sections['Travel'].append(f"• {vendor} — {typ_dest} [{status}]")
                
    # Data source 4: Inbox
    inbox_folder_id = DRIVE_TREE.get('path_to_id', {}).get('01 - Second Brain/Inbox')
    if inbox_folder_id:
        files = list_files_in_folder(service, inbox_folder_id)
        action_file = next((f for f in files if f['name'] == 'Action Required.md'), None)
        if action_file:
            content = download_file(service, action_file['id'])
            # extract lines starting with • [ or - [
            items = []
            for line in content.split('\n'):
                line = line.strip()
                if line.startswith('• [') or line.startswith('- ['):
                    items.append(line)
            sections['Inbox'] = items[:10]
            
    # Data source 5: Readwise
    last_digest = TOOLBOX_ROOT / 'config' / 'readwise_last_digest.json'
    if last_digest.exists():
        try:
            data = json.loads(last_digest.read_text())
            if data.get('date') == date.today().isoformat():
                for a in data.get('articles', []):
                    title = a.get('title', 'Unknown')
                    author = a.get('author', 'Unknown')
                    summary = a.get('summary', '').replace('\n', ' ')
                    sections['Reading'].append(f'• "{title}" by {author} — {summary}')
        except Exception as e:
            print(f"Error reading readwise digest: {e}")
            
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
    
    # Update index
    index_path = LIFE_DOCS_DIR / 'index.md'
    if index_path.exists():
        lines = index_path.read_text().split('\n')
        link = f"- [{yesterday}]({yesterday}.md) — {yesterday_date.strftime('%a %d %b')}"
        if link not in lines:
            # Find first existing entry, or insert after the header line
            insert_idx = next((i for i, l in enumerate(lines) if l.startswith('- [')), None)
            if insert_idx is None:
                # First run: no entries yet — find header and insert after it
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
                
    # Update home page index.md dynamic sections
    update_home_index(
        today=date.today(),
        money_lines=[l for l in sections.get('Money', []) if l.startswith('•')],
        reading_lines=[l for l in sections.get('Reading', []) if l.startswith('•')],
    )

    # Build and Push
    print("Building site and pushing to Git...")
    try:
        subprocess.run([str(MKDOCS), 'build', '--quiet'], cwd=LIFE_DOCS_REPO, check=True)
        subprocess.run(['git', 'add', 'docs/life/'], cwd=LIFE_DOCS_REPO, check=True)
        subprocess.run(['git', 'commit', '-m', f"daily: {yesterday}"], cwd=LIFE_DOCS_REPO, check=False)
        subprocess.run(['git', 'push'], cwd=LIFE_DOCS_REPO, check=True)
        print("Success.")
    except subprocess.CalledProcessError as e:
        print(f"Git/Build operation failed: {e}")

if __name__ == '__main__':
    # Pull before generating to avoid dirty-tree conflict on rebase
    subprocess.run(['git', 'pull', '--rebase'], cwd=LIFE_DOCS_REPO, check=True)
    main()
