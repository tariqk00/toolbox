# Google Drive AI Sorter (Legacy)

> **This directory is archived.** The active Drive sorter has moved to `toolbox/services/drive_organizer/` with a modular structure (`main.py`, `lib/ai_engine.py`, `lib/drive_utils.py`). The scripts here completed their one-time use and are no longer part of active automation.

This directory contains the original Python scripts and configuration for the AI-powered Google Drive organizer.

## Components

- `drive_organizer.py`: Main script. Uses Gemini 2.0 Flash to analyze, rename, and move files.
- `sorter_dry_run.csv`: Generated plan from a scan.
- `renaming_history.csv`: Log of all executed renames.
- `ai-sorter.service` & `ai-sorter.timer`: Systemd units for automation.

## Usage

### Dry Run (Scan Only)

```bash
python3 drive_organizer.py --scan
```

### Dry Run (Inbox)

```bash
python3 drive_organizer.py --inbox
```

### Execute (Apply Changes)

```bash
python3 drive_organizer.py --inbox --execute
```

## Automation Setup (NUC)

The system is designed to run as a systemd **User Service** (lingering enabled).

1. **Deploy Units**:

   ```bash
   mkdir -p ~/.config/systemd/user
   cp ai-sorter.service ~/.config/systemd/user/
   cp ai-sorter.timer ~/.config/systemd/user/
   ```

2. **Enable Timer**:

   ```bash
   systemctl --user daemon-reload
   systemctl --user enable --now ai-sorter.timer
   ```

3. **Check Status**:
   ```bash
   systemctl --user list-timers
   systemctl --user status ai-sorter.timer
   ```
