#!/bin/bash
# Standardized venv creation for toolbox modules.
# Usage: ./setup_venv.sh [path_to_venv] [optional_extra_requirements_file]

set -e

VENV_PATH=${1:-"./venv"}
EXTRA_REQS=$2
REPO_ROOT=$(cd "$(dirname "$0")/.." && pwd)
SHARED_VENV="$REPO_ROOT/venv"

echo "--- Setting up venv at $VENV_PATH ---"

# Create venv if it doesn't exist
if [ ! -d "$VENV_PATH" ]; then
    python3 -m venv "$VENV_PATH"
fi

# Upgrade pip
"$VENV_PATH/bin/pip" install --upgrade pip

# Install toolbox in editable mode (handles core dependencies)
"$VENV_PATH/bin/pip" install -e "$REPO_ROOT"

# Install main toolbox requirements
if [ -f "$REPO_ROOT/requirements.txt" ]; then
    "$VENV_PATH/bin/pip" install -r "$REPO_ROOT/requirements.txt"
fi

# Install dev requirements for the shared toolbox runtime or explicitly requested extras.
if [ "$(realpath "$VENV_PATH")" = "$(realpath "$SHARED_VENV")" ] || [ -n "$EXTRA_REQS" ]; then
    echo "Installing dev dependencies..."
    "$VENV_PATH/bin/pip" install -r "$REPO_ROOT/requirements-dev.txt"
fi

# Install extra requirements if provided
if [ -n "$EXTRA_REQS" ] && [ -f "$EXTRA_REQS" ]; then
    echo "Installing extra dependencies from $EXTRA_REQS..."
    "$VENV_PATH/bin/pip" install -r "$EXTRA_REQS"
fi

echo "--- venv setup complete ---"
echo "To activate: source $VENV_PATH/bin/activate"
