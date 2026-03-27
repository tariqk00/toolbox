# Toolbox Agent Standards

This document defines the architectural standards for automation scripts in the `toolbox` repository. All new feature development should follow the **"Fitness Automation"** pattern established in Feb 2026.

## 1. Project Structure

Move away from monolithic `bin/` or `google-drive/` folders. Each distinct domain or integration should have its own self-contained module.

```text
toolbox/
├── [domain]/                 # e.g., garmin, trainheroic, finance
│   ├── __init__.py           # Makes it a package
│   ├── main.py               # Entry point (or specific script name)
│   ├── requirements.txt      # Domain-specific dependencies
│   ├── venv/                 # Local virtual environment (gitignored)
│   └── lib/                  # Internal helpers
├── config/
│   ├── secrets.env           # Secrets (gitignored)
│   └── folder_config.json    # Shared configuration
└── lib/                      # Shared library code (logging, drive, etc.)
```

## 2. Python Environment

- **Isolation**: Each module MUST have its own `venv`. do NOT share a global `toolbox` venv.
- **Dependencies**: Explicitly list all dependencies in `[domain]/requirements.txt`.
- **run_command**: When executing, always use the specific venv python:
    ```bash
    toolbox/[domain]/venv/bin/python toolbox/[domain]/script.py
    ```

## 3. Configuration & Secrets

- **Secrets**: NEVER hardcode API keys or passwords.
    - Use `python-dotenv` to load from `toolbox/config/secrets.env`.
    - Add new keys to `toolbox/config/secrets.env.template`.
- **Configs**: Use `toolbox/config/folder_config.json` for directory IDs and mappings.

## 4. Automation & Deployment (NUC)

- **Systemd**: Use `systemd` user units for scheduling.
- **Location**: Service files go in `setup/services/`.
- **Naming**: `[domain]-[action].service` and `[domain]-[action].timer`.
- **Deployment**:
    - Symlink service files to `~/.config/systemd/user/`.
    - Use a deployment script (e.g., `setup/scripts/deploy_fitness.sh`) to automate linking and enabling.

## 5. Coding Standards

- **Idempotency**: Scripts must be safe to run multiple times (e.g., skip existing files).
- **Dry Run**: Always implement a `--dry-run` flag for destructive actions.
- **Logging**: Use standard `logging` library. Print to stdout/stderr (captured by journald).
- **Type Hinting**: Use Python type hints for better AI context.

## 6. Migration Guide

When updating legacy scripts (in `bin/` or `google-drive/`):
1.  Create a new domain folder.
2.  Move valid logic to the new folder.
3.  Create a fresh `requirements.txt`.
4.  Update the `setup/` repo with new service files.
