#!/bin/bash
# run_staging.sh
# Runs the AI Sorter in Staging mode (Rename & Move)
# Usage: ./run_staging.sh [--dry-run]

# Check for dry-run
PYTHON_BIN="/home/takhan/github/tariqk00/toolbox/google-drive/venv/bin/python3"

if [ "$1" == "--dry-run" ]; then
    echo "Running in DRY-RUN mode..."
    $PYTHON_BIN /home/takhan/github/tariqk00/toolbox/google-drive/drive_organizer.py --staging
else
    echo "Running in EXECUTE mode..."
    $PYTHON_BIN /home/takhan/github/tariqk00/toolbox/google-drive/drive_organizer.py --staging --execute
fi
