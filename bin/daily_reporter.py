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
                amt = amt_m.group(1) if amt_m else 'Unknown'
                typ = type_m.group(1) if type_m else 'Unknown'
                receipts.append(f"• {vendor} — {amt} {typ}")
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
            if data.get('date') == yesterday:
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
        # find where to insert
        insert_idx = 0
        for i, line in enumerate(lines):
            if line.startswith('- ['):
                insert_idx = i
                break
        if insert_idx > 0:
            link = f"- [{yesterday}]({yesterday}.md) — {yesterday_date.strftime('%a %d %b')}"
            # Check if it's already there
            if link not in lines:
                lines.insert(insert_idx, link)
                # Keep last 30
                list_start = insert_idx
                list_end = list_start
                while list_end < len(lines) and lines[list_end].startswith('- ['):
                    list_end += 1
                if list_end - list_start > 30:
                    lines = lines[:list_start + 30] + lines[list_end:]
                index_path.write_text("\n".join(lines))
                
    # Build and Push
    print("Building site and pushing to Git...")
    try:
        subprocess.run(['git', 'pull', '--rebase'], cwd=LIFE_DOCS_REPO, check=True)
        subprocess.run(['mkdocs', 'build', '--quiet'], cwd=LIFE_DOCS_REPO, check=True)
        subprocess.run(['git', 'add', 'docs/life/'], cwd=LIFE_DOCS_REPO, check=True)
        subprocess.run(['git', 'commit', '-m', f"daily: {yesterday}"], cwd=LIFE_DOCS_REPO, check=False)
        subprocess.run(['git', 'push'], cwd=LIFE_DOCS_REPO, check=True)
        print("Success.")
    except subprocess.CalledProcessError as e:
        print(f"Git/Build operation failed: {e}")

if __name__ == '__main__':
    main()
