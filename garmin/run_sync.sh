#!/usr/bin/env bash
# Runner script for Garmin activity sync.
# Activates the project venv and runs the sync script.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
TOOLBOX_DIR="$(dirname "$SCRIPT_DIR")"

# Activate venv
source "$SCRIPT_DIR/venv/bin/activate"

# Run sync (defaults to yesterday)
python "$SCRIPT_DIR/sync.py" "$@"
