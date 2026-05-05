#!/bin/bash
# run_staging.sh
# Runs the AI Sorter in Staging mode (Rename & Move)
# Usage: ./run_staging.sh [--dry-run]

# Check for dry-run
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
REPO_ROOT="$SCRIPT_DIR"
PYTHON_BIN="$REPO_ROOT/venv/bin/python3"
TARGET_SCRIPT="$REPO_ROOT/google-drive/drive_organizer.py"

if [ "$1" == "--dry-run" ]; then
    echo "Running in DRY-RUN mode..."
    "$PYTHON_BIN" "$TARGET_SCRIPT" --staging
else
    echo "Running in EXECUTE mode..."
    "$PYTHON_BIN" "$TARGET_SCRIPT" --staging --execute
fi
