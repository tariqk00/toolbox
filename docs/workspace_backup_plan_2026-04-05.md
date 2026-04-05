# workspace-backup Completion Plan — 2026-04-05

## Current State

### What Exists

File: `/home/tariqk/github/tariqk00/toolbox/workspace_backup.py`

The script is a stub that:
1. Defines the workspace path: `/home/tariqk/.openclaw/workspace`
2. Creates a timestamped ZIP file at `/tmp/workspace_backup_YYYYMMDD_HHMMSS.zip`
3. Walks the workspace directory, adding all files while excluding `.git` directories
4. Has a hardcoded exclusion for `memory/2026-04-03.md` (a temporary exclusion from a specific date — should be removed)
5. Prints the backup path
6. Does NOT upload to Drive — the upload is explicitly commented out as a TODO

### What's Missing

1. **Drive upload** — the main functional gap; the script produces a ZIP but doesn't send it anywhere
2. **Hardcoded date exclusion** — `memory/2026-04-03.md` exclusion is temporary/debug; remove it
3. **No hardcoded path portability** — uses `/home/tariqk/` directly (violates portability rules)
4. **No Telegram notification** — no success/failure notification
5. **No error handling** — no try/except around ZIP creation or upload
6. **No state tracking** — no record of last successful backup
7. **No systemd service or timer** — not yet deployed
8. **Not in setup repo's deploy_nuc.sh** — not registered for deployment

### Workspace Size

Current workspace: `~280KB` (small, safe for regular Drive uploads)

---

## 2. What Needs to Be Completed

### workspace_backup.py (full rewrite)

```python
import os
import sys
import zipfile
import datetime

# Toolbox path for shared libs
_toolbox = os.path.dirname(os.path.abspath(__file__))
if _toolbox not in sys.path:
    sys.path.insert(0, _toolbox)

from lib.drive_utils import get_drive_service
from lib.telegram import send_message
from googleapiclient.http import MediaFileUpload

WORKSPACE_PATH = os.path.expanduser("~/.openclaw/workspace")
DRIVE_FOLDER_PATH = "01 - Second Brain/OpenClaw Backups"  # create this folder
BACKUP_PREFIX = "openclaw-workspace"

def backup_workspace():
    timestamp = datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
    backup_filename = f"/tmp/{BACKUP_PREFIX}-{timestamp}.zip"
    
    try:
        # Create ZIP (relative paths from ~/.openclaw/)
        with zipfile.ZipFile(backup_filename, 'w', zipfile.ZIP_DEFLATED) as zipf:
            for root, dirs, files in os.walk(WORKSPACE_PATH):
                # Exclude .git directories
                dirs[:] = [d for d in dirs if d != '.git']
                for file in files:
                    full_path = os.path.join(root, file)
                    rel_path = os.path.relpath(full_path, os.path.expanduser("~/.openclaw"))
                    zipf.write(full_path, rel_path)
        
        # Upload to Drive
        service = get_drive_service()
        folder_id = _get_or_create_folder(service, DRIVE_FOLDER_PATH)
        
        drive_filename = f"{BACKUP_PREFIX}-{timestamp}.zip"
        file_metadata = {'name': drive_filename, 'parents': [folder_id]}
        media = MediaFileUpload(backup_filename, mimetype='application/zip', resumable=True)
        uploaded = service.files().create(
            body=file_metadata, media_body=media, fields='id,name'
        ).execute()
        
        # Cleanup temp file
        os.remove(backup_filename)
        
        send_message(
            f"OpenClaw workspace backup complete: {drive_filename}",
            service="nuc-ops"
        )
        print(f"Backup uploaded: {uploaded['name']} (id: {uploaded['id']})")
        return uploaded['id']
        
    except Exception as e:
        send_message(f"OpenClaw workspace backup FAILED: {e}", service="nuc-ops")
        raise

def _get_or_create_folder(service, path):
    """Walk the path and get/create folders."""
    parts = path.strip('/').split('/')
    parent_id = 'root'
    for part in parts:
        query = (f"name = '{part}' and mimeType = 'application/vnd.google-apps.folder' "
                 f"and '{parent_id}' in parents and trashed = false")
        result = service.files().list(q=query, fields='files(id)').execute()
        files = result.get('files', [])
        if files:
            parent_id = files[0]['id']
        else:
            meta = {'name': part, 'mimeType': 'application/vnd.google-apps.folder',
                    'parents': [parent_id]}
            folder = service.files().create(body=meta, fields='id').execute()
            parent_id = folder['id']
    return parent_id

if __name__ == "__main__":
    backup_workspace()
```

### Key Design Decisions

- **Drive target**: `01 - Second Brain/OpenClaw Backups` — keeps workspace backups near the Second Brain content they support. Alternative: `Filing Cabinet/Backups/OpenClaw`. Create the folder on first run.
- **Retention**: Drive keeps all versions indefinitely. Consider a cleanup step to delete backups older than 30 days (Drive quota management). For now, accept unlimited retention at ~280KB/backup.
- **Authentication**: Uses `get_drive_service()` from `toolbox/lib/drive_utils.py` — the same Drive service used by all toolbox scripts. No new credentials needed.
- **Venv**: Use `toolbox/google-drive/venv/bin/python3` — this venv already has `google-api-python-client` installed. Alternatively, move the script to a proper `toolbox/workspace-backup/` module per the ARCHITECTURE.md standards, but a single-file approach in `toolbox/` is acceptable for a simple backup script.
- **Portability**: Use `os.path.expanduser("~")` instead of hardcoded `/home/tariqk/`.

---

## 3. Systemd Service and Timer Files

Following the pattern from existing services in `/home/tariqk/github/tariqk00/setup/hosts/nuc-server/systemd/`.

### `workspace-backup.service`

```ini
[Unit]
Description=Backup OpenClaw Workspace to Google Drive
After=network.target
OnFailure=notify-failure@%n.service

[Service]
Type=oneshot
ExecStart=%h/github/tariqk00/toolbox/google-drive/venv/bin/python3 %h/github/tariqk00/toolbox/workspace_backup.py
WorkingDirectory=%h/github/tariqk00/toolbox
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=default.target
```

**Note on WorkingDirectory:** The script uses `lib.drive_utils` which resolves token paths relative to the working directory. Keeping `WorkingDirectory=%h/github/tariqk00/toolbox` matches how the existing toolbox scripts run.

### `workspace-backup.timer`

```ini
[Unit]
Description=Daily OpenClaw Workspace Backup

[Timer]
OnCalendar=*-*-* 03:00:00
Persistent=true

[Install]
WantedBy=timers.target
```

**Schedule rationale:** 3:00 AM daily — after plaud-automation (07:00), after n8n-backup (02:00), before garmin-sync. Low traffic window.

### File Locations

Both files go in:
```
/home/tariqk/github/tariqk00/setup/hosts/nuc-server/systemd/workspace-backup.service
/home/tariqk/github/tariqk00/setup/hosts/nuc-server/systemd/workspace-backup.timer
```

---

## 4. Changes to deploy_nuc.sh

Add one `install_service` call in the "Install Service Files" section (step 4), after the existing service installs:

```bash
# Install workspace-backup
install_service "$BASE_DIR/setup/hosts/nuc-server/systemd/workspace-backup" "workspace-backup"
```

Insert after line 108 (after `workout-extract`):
```bash
# Install workspace backup
install_service "$BASE_DIR/setup/hosts/nuc-server/systemd/workspace-backup" "workspace-backup"
```

**That's the only change to deploy_nuc.sh.** The existing `install_service` function handles copying, path-patching (`%h` → `$HOME`), and enabling the timer.

After deploy, manual first-run to verify:
```bash
systemctl --user start workspace-backup.service
journalctl --user -u workspace-backup.service -n 50
```

---

## 5. Portability Note

The existing `workspace_backup.py` has two portability issues:

1. `workspace_path = "/home/tariqk/.openclaw/workspace"` — hardcoded path. Fix: `os.path.expanduser("~/.openclaw/workspace")`
2. `os.path.relpath(os.path.join(root, file), "/home/tariqk/")` — hardcoded home. Fix: `os.path.relpath(..., os.path.expanduser("~"))`

These will cause `test_portability.py` to fail and block `deploy_nuc.sh`. The rewrite above fixes both.

---

## 6. Implementation Checklist

- [ ] Rewrite `toolbox/workspace_backup.py` (Drive upload + portability fixes + Telegram notification)
- [ ] Create `setup/hosts/nuc-server/systemd/workspace-backup.service`
- [ ] Create `setup/hosts/nuc-server/systemd/workspace-backup.timer`
- [ ] Add `install_service` call to `setup/deploy_nuc.sh`
- [ ] Run `bash deploy_nuc.sh` to deploy
- [ ] Manual test: `systemctl --user start workspace-backup.service`
- [ ] Verify Drive folder `01 - Second Brain/OpenClaw Backups` was created
- [ ] Verify Telegram notification received
- [ ] Check `systemctl --user list-timers` shows `workspace-backup.timer` next fire time
