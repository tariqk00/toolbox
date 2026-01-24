"""
Analyzes the state of Plaud files to distinguish between Transcripts (Archive) 
and Notes (Active Plaud). Generates a cleanup report.
"""

import sys
import os
import re


import sys
import os
# Add repo root to path
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if REPO_ROOT not in sys.path:
    sys.path.append(REPO_ROOT)

from toolbox.lib.drive_utils import get_drive_service

service = get_drive_service()
SOURCE_ID = "1NiTBFVY_u9MmSv1LJJOIZERiwlJgOPB9"
ARCHIVE_TARGET = "1Qx7lKAh7t-w8fyhxkRKN9bGoIVYPWrJB" # Plaud_Transcripts
ACTIVE_TARGET = "1lDD6SUh918U6oXjOBB5I9SjFVDAlqjzR" # Plaud

print("Fetching file list...")
results = service.files().list(
    q=f"'{SOURCE_ID}' in parents and trashed = false",
    fields="files(id, name, mimeType)",
    pageSize=500
).execute()
files = results.get('files', [])

print(f"Total Files: {len(files)}")
print(f"{'Original Name':<60} | {'Group (Base)':<40} | {'Type':<10} | {'Target Location'}")
print("-" * 140)

# Regex to find timestamp prefix: "202x-xx-xx ... -"
# or "202x-xx-xx [HH:MM] "
# Simplify: 
# 1. Detect if name starts with date.
# 2. Extract Base Name (Subject).
# 3. Detect Type (Transcript vs Summary/Note).

# Parse and Group first
grouped_events = {} # Key: Timestamp String (e.g. "2026-01-08 03:06") -> { 'transcripts': [], 'notes': [] }

for f in files:
    name = f['name']
    
    # Extract Date/Time from filename
    # Patterns: 
    # 1. "... - YYYY-MM-DD_HHMM_..." (Plaud Export)
    # 2. "YYYY-MM-DD - PLAUDAI - ..." (Renamed Note)
    # 3. "YYYY-MM-DD [HH:MM] ..." (Original Plaud)
    
    event_date = "Unknown"
    
    # Try finding YYYY-MM-DD
    date_match = re.search(r'(202[0-9]-[0-1][0-9]-[0-3][0-9])', name)
    if date_match:
        event_date = date_match.group(1)
        # Try finding HHMM or HH:MM after date
        time_match = re.search(r'[_ ]([0-2][0-9][0-5][0-9])[_ ]', name) # _HHMM_
        if time_match:
             event_date += " " + time_match.group(1)
    
    if event_date not in grouped_events:
        grouped_events[event_date] = {'transcripts': [], 'notes': []}
        
    is_transcript = 'transcript' in name.lower() or (name.endswith('.txt') and 'summary' not in name.lower())
    
    if is_transcript:
        grouped_events[event_date]['transcripts'].append(name)
    else:
        grouped_events[event_date]['notes'].append(name)

# Sort by Date Descending
sorted_keys = sorted(grouped_events.keys(), reverse=True)

report_path = "plaud_report.md"
with open(report_path, "w") as f:
    f.write("# Plaud File Analysis Report\n\n")
    f.write(f"| {'Date':<16} | {'Source Transcript (Archive)':<50} | {'Derived Notes (Active Plaud)':<50} |\n")
    f.write(f"| :--- | :--- | :--- |\n")

    for date in sorted_keys:
        group = grouped_events[date]
        transcripts = group['transcripts']
        notes = group['notes']
        
        max_rows = max(len(transcripts), len(notes))
        if max_rows == 0: continue
        
        for i in range(max_rows):
            t_name = transcripts[i] if i < len(transcripts) else ""
            n_name = notes[i] if i < len(notes) else ""
            
            # Escape pipes for markdown
            t_name = t_name.replace("|", "\|")
            n_name = n_name.replace("|", "\|")
            
            d_disp = date if i == 0 else ""
            
            f.write(f"| **{d_disp}** | `{t_name}` | `{n_name}` |\n")

print(f"Report generated at {os.path.abspath(report_path)}")

