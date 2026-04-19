#!/usr/bin/env python3
"""
Generates all pages under `docs/work/` in the life-docs repo and rebuilds the site.
Output: backlog.md, changelog.md, sessions.md, health.md
"""
import os
import subprocess
import json
import glob
import re
from pathlib import Path
from datetime import datetime, timedelta

# Setup paths
TOOLBOX_ROOT = Path(__file__).resolve().parent.parent
LIFE_DOCS_REPO = Path.home() / 'github' / 'tariqk00' / 'life-docs'
WORK_DOCS_DIR = LIFE_DOCS_REPO / 'docs' / 'work'
MKDOCS = TOOLBOX_ROOT / 'google-drive' / 'venv' / 'bin' / 'mkdocs'

def build_backlog():
    repos = ['tariqk00/toolbox', 'tariqk00/setup', 'tariqk00/plaud']
    priorities = {'now': [], 'next': [], 'later': [], 'deferred': []}
    
    for repo in repos:
        try:
            res = subprocess.run(
                ['gh', 'issue', 'list', '--repo', repo, '--state', 'open', '--json', 'number,title,labels,url', '--limit', '100'],
                capture_output=True, text=True, check=True
            )
            issues = json.loads(res.stdout)
        except Exception as e:
            print(f"Failed to fetch issues for {repo}: {e}")
            continue
            
        for issue in issues:
            labels = [lbl['name'].lower() for lbl in issue.get('labels', [])]
            
            prio = 'later' # default
            for p in ['now', 'next', 'later', 'deferred']:
                if p in labels:
                    prio = p
                    break
                    
            item = f"- [{repo}#{issue['number']}]({issue['url']}) — {issue['title']}"
            priorities[prio].append(item)
            
    lines = ["# Backlog\n"]
    for p in ['now', 'next', 'later', 'deferred']:
        lines.append(f"## {p.capitalize()}")
        if priorities[p]:
            lines.extend(priorities[p])
        else:
            lines.append("_No issues_")
        lines.append("")
        
    lines.append(f"_Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}_")
    (WORK_DOCS_DIR / 'backlog.md').write_text("\n".join(lines))

def build_changelog():
    repos = {
        'toolbox': Path.home() / 'github' / 'tariqk00' / 'toolbox',
        'setup': Path.home() / 'github' / 'tariqk00' / 'setup',
        'plaud': Path.home() / 'github' / 'tariqk00' / 'plaud'
    }
    
    lines = ["# Changelog (last 30 days)\n"]
    for name, path in repos.items():
        lines.append(f"## {name}")
        if not path.exists():
            lines.append(f"_Repository {name} not found locally._\n")
            continue
            
        try:
            res = subprocess.run(
                ['git', '-C', str(path), 'log', '--since=30 days ago', '--no-merges', '--format=%ad — %s', '--date=short'],
                capture_output=True, text=True, check=True
            )
            if res.stdout.strip():
                for log_line in res.stdout.strip().split('\n'):
                    lines.append(f"- {log_line}")
            else:
                lines.append("_No changes_")
        except Exception as e:
            lines.append(f"_Error fetching git log: {e}_")
        lines.append("")
        
    lines.append(f"_Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}_")
    (WORK_DOCS_DIR / 'changelog.md').write_text("\n".join(lines))

def build_sessions():
    session_dir = Path.home() / '.claude' / 'session-data'
    lines = ["# Sessions (last 15)\n"]
    
    if session_dir.exists():
        files = sorted(session_dir.glob('*.tmp'), key=os.path.getmtime, reverse=True)[:15]
        for f in files:
            content = f.read_text()
            
            # Extract date from filename: YYYY-MM-DD
            date_match = re.search(r'^(\d{4}-\d{2}-\d{2})', f.name)
            date_str = date_match.group(1) if date_match else "Unknown Date"
            
            # Extract topic
            topic_match = re.search(r'\*\*Topic:\*\*\s*(.+)', content)
            topic = topic_match.group(1).strip() if topic_match else "Unknown Topic"
            
            # Extract what worked (first bullet under ## What WORKED)
            what_worked = "No data"
            worked_section = re.search(r'## What WORKED\n(.*?)(?=##|\Z)', content, re.DOTALL)
            if worked_section:
                bullet_match = re.search(r'^[-*]\s+(.+)', worked_section.group(1).strip(), re.MULTILINE)
                if bullet_match:
                    what_worked = bullet_match.group(1).strip()
                    
            lines.append(f"## {date_str} — {topic}")
            lines.append(f"- {what_worked}\n")
    else:
        lines.append("_No sessions found_")
        
    lines.append(f"\n_Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}_")
    (WORK_DOCS_DIR / 'sessions.md').write_text("\n".join(lines))

def build_health():
    services = [
        'ai-sorter', 'email-extractor', 'inbox-scanner',
        'plaud-direct', 'workout-extract', 'system-check',
        'weekly-ops', 'n8n-backup',
    ]
    
    lines = ["# System Health (last 7 days)\n"]
    lines.append("## Service Error Counts")
    lines.append("| Service | Errors | |")
    lines.append("|---------|--------|-|")
    
    for svc in services:
        try:
            res = subprocess.run(
                ['journalctl', '--user', '-u', svc, '--since', '7 days ago', '--no-pager', '-q'],
                capture_output=True, text=True
            )
            count = 0
            for line in res.stdout.split('\n'):
                line_lower = line.lower()
                if any(k in line_lower for k in ['error', 'fail', 'traceback', 'exception', 'critical']):
                    count += 1
                    
            status = "⚠" if count > 0 else "✓"
            lines.append(f"| {svc} | {count} | {status} |")
        except Exception:
            lines.append(f"| {svc} | ? | ? |")
            
    lines.append("\n## API Spend (last 7 days)")
    lines.append("| Date | Tokens | Cost (est.) |")
    lines.append("|------|--------|-------------|")
    
    cost_log = TOOLBOX_ROOT / 'logs' / 'cost_log.jsonl'
    total_cost = 0.0
    
    if cost_log.exists():
        from collections import defaultdict
        daily_stats = defaultdict(lambda: {"tokens": 0, "cost": 0.0})
        
        cutoff_date = (datetime.now() - timedelta(days=7)).strftime('%Y-%m-%d')
        
        with open(cost_log) as f:
            for line in f:
                if not line.strip(): continue
                try:
                    data = json.loads(line)
                    date_str = data.get('timestamp', '')[:10]
                    if date_str >= cutoff_date:
                        daily_stats[date_str]['tokens'] += data.get('total_tokens', 0)
                        daily_stats[date_str]['cost'] += data.get('cost_usd_est', 0.0)
                        total_cost += data.get('cost_usd_est', 0.0)
                except Exception:
                    continue
                    
        for date_str in sorted(daily_stats.keys(), reverse=True):
            tokens = daily_stats[date_str]['tokens']
            cost = daily_stats[date_str]['cost']
            lines.append(f"| {date_str} | {tokens:,} | ${cost:.6f} |")
            
    lines.append(f"\n**7-day total: ${total_cost:.4f}**\n")
    lines.append(f"_Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}_")
    
    (WORK_DOCS_DIR / 'health.md').write_text("\n".join(lines))

def build_site_and_push():
    print("Building site and pushing to Git...")
    try:
        subprocess.run([str(MKDOCS), 'build', '--quiet'], cwd=LIFE_DOCS_REPO, check=True)
        subprocess.run(['git', 'add', 'docs/work/'], cwd=LIFE_DOCS_REPO, check=True)
        subprocess.run(['git', 'commit', '-m', f"work: {datetime.now().strftime('%Y-%m-%d')}"], cwd=LIFE_DOCS_REPO, check=False)
        subprocess.run(['git', 'push'], cwd=LIFE_DOCS_REPO, check=True)
        print("Success.")
    except subprocess.CalledProcessError as e:
        print(f"Git/Build operation failed: {e}")

if __name__ == '__main__':
    # Pull before generating to avoid dirty-tree conflict on rebase
    subprocess.run(['git', 'pull', '--rebase'], cwd=LIFE_DOCS_REPO, check=True)
    WORK_DOCS_DIR.mkdir(parents=True, exist_ok=True)
    build_backlog()
    build_changelog()
    build_sessions()
    build_health()
    build_site_and_push()
