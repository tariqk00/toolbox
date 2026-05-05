#!/bin/bash
# Wrapper to run anova.py with the toolbox venv (has websockets)
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
VENV="$( dirname "$( dirname "$SCRIPT_DIR" )" )/venv/bin/python3"

exec "$VENV" "$SCRIPT_DIR/anova.py" "$@"
