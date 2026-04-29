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
import sys
from pathlib import Path
from datetime import datetime, timedelta

# Fix sys.path for toolbox modules
REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT.parent))

from toolbox.lib.reporter_utils import (
    LIFE_DOCS_REPO, rebuild_site, ReportSection, logger
)

WORK_DOCS_DIR = LIFE_DOCS_REPO / 'docs' / 'work'

def build_backlog():
    repos = ['tariqk00/toolbox', 'tariqk00/setup', 'tariqk00/plaud', 'tariqk00/life-docs']
    priorities = {'now': [], 'next': [], 'later': [], 'deferred': []}
    
    for repo in repos:
        try:
            res = subprocess.run(
                ['gh', 'issue', 'list', '--repo', repo, '--state', 'open', '--json', 'number,title,labels,url', '--limit', '100'],
                capture_output=True, text=True, check=True
            )
            issues = json.loads(res.stdout)
        except Exception as e:
            logger.error(f"Failed to fetch issues for {repo}: {e}")
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
            
    sections = []
    for p in ['now', 'next', 'later', 'deferred']:
        sec = ReportSection(p.capitalize(), level=2)
        if priorities[p]:
            for item in priorities[p]:
                sec.add_item(item)
        else:
            sec.add_item("_No issues_")
        sections.append(sec.render())
        
    content = "# Backlog\n\n" + "\n".join(sections)
    content += f"\n_Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}_\n"
    (WORK_DOCS_DIR / 'backlog.md').write_text(content)

def build_changelog():
    repos = {
        'toolbox': Path.home() / 'github' / 'tariqk00' / 'toolbox',
        'setup': Path.home() / 'github' / 'tariqk00' / 'setup',
        'plaud': Path.home() / 'github' / 'tariqk00' / 'plaud'
    }
    
    content = "# Changelog (last 30 days)\n\n"
    for name, path in repos.items():
        sec = ReportSection(name, level=2)
        if not path.exists():
            sec.add_item(f"_Repository {name} not found locally._")
        else:
            try:
                res = subprocess.run(
                    ['git', '-C', str(path), 'log', '--since=30 days ago', '--no-merges', '--format=%ad — %s', '--date=short'],
                    capture_output=True, text=True, check=True
                )
                if res.stdout.strip():
                    for log_line in res.stdout.strip().split('\n'):
                        sec.add_item(f"- {log_line}")
                else:
                    sec.add_item("_No changes_")
            except Exception as e:
                sec.add_item(f"_Error fetching git log: {e}_")
        content += sec.render() + "\n"
        
    content += f"\n_Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}_\n"
    (WORK_DOCS_DIR / 'changelog.md').write_text(content)

def build_sessions():
    session_dir = Path.home() / '.claude' / 'session-data'
    content = "# Sessions (last 15)\n\n"
    
    if session_dir.exists():
        files = sorted(session_dir.glob('*.tmp'), key=os.path.getmtime, reverse=True)[:15]
        for f in files:
            try:
                raw_text = f.read_text()
                # Extract date from filename: YYYY-MM-DD
                date_match = re.search(r'^(\d{4}-\d{2}-\d{2})', f.name)
                date_str = date_match.group(1) if date_match else "Unknown Date"
                
                # Extract summary/first line
                summary = raw_text.split('\n')[0][:100].strip('# ')
                content += f"- **{date_str}** — {summary}\n"
            except Exception:
                continue
    else:
        content += "_No session data found._\n"
        
    content += f"\n_Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}_\n"
    (WORK_DOCS_DIR / 'sessions.md').write_text(content)

def build_health():
    # Simple placeholder for now, could be expanded to parse activity.jsonl
    content = "# System Health\n\n"
    content += "## Active Services\n"
    
    services = ['email-extractor', 'inbox-scanner', 'drive-organizer']
    for s in services:
        content += f"- {s}: [Checking...]\n"
        
    content += f"\n_Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}_\n"
    (WORK_DOCS_DIR / 'health.md').write_text(content)

def main():
    WORK_DOCS_DIR.mkdir(parents=True, exist_ok=True)
    
    logger.info("Fetching backlog...")
    build_backlog()
    
    logger.info("Fetching changelog...")
    build_changelog()
    
    logger.info("Fetching sessions...")
    build_sessions()
    
    logger.info("Building health report...")
    build_health()
    
    logger.info("Building site and pushing...")
    if rebuild_site():
        try:
            subprocess.run(['git', 'add', 'docs/work/'], cwd=LIFE_DOCS_REPO, check=True)
            subprocess.run(['git', 'commit', '-m', "work: update reports"], cwd=LIFE_DOCS_REPO, check=False)
            subprocess.run(['git', 'push'], cwd=LIFE_DOCS_REPO, check=True)
            logger.info("Successfully pushed work reports to Git.")
        except subprocess.CalledProcessError as e:
            logger.error(f"Git operation failed: {e}")

if __name__ == '__main__':
    subprocess.run(['git', 'pull', '--rebase'], cwd=LIFE_DOCS_REPO, check=True)
    main()
