# Workspace Rules: Toolbox (Automation & Logic)

> **Standard Update**: See `docs/ARCHITECTURE.md` for the new modular architecture standards (Fitness Automation Pattern).

## Context
This repository houses the application logic: Python scripts, n8n workflows, and AI tool integrations.

### Documentation Entry Point
Always refer to the master [INDEX.md](file:///home/tariqk/repos/personal/setup/docs/INDEX.md) for global system context.

## Guidelines

### 1. Python Environment
### 1. Python Environment
- **Virtual Environment**: Use per-module venvs (e.g., `toolbox/garmin/venv`) as defined in `docs/ARCHITECTURE.md`.
- **Legacy**: `toolbox/google-drive/venv` is for legacy scripts only.
- **Dependencies**: Manage via `requirements.txt` in the specific module folder.

### 2. Script Reuse Policy
- 🛑 **STOP**: Before creating a NEW script, check `toolbox/scriptReferences.md`.
- **Goal**: Reuse existing logic in `lib/` or `bin/` whenever possible.
- **Maintenance**: Update `scriptReferences.md` when adding new tools (use `scripts/generate_references.py`).

### 3. Development Workflow
- **Test Locally**: Run scripts on the Chromebook first.
- **Dry Run**: Implement and use `--dry-run` flags for destructive operations (file moves, deletions).
- **Paths**: Use relative paths from repo root or absolute paths resolved dynamically.

### 4. Directory Structure
- `bin/`: Executable CLI tools (entry points).
- `lib/`: Shared modules and classes.
- `n8n/`: Workflow JSONs (Version Controlled).
- `services/`: Long-running daemons.
