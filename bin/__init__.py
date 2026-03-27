"""
Toolbox bin package.

Provides setup_path() for scripts that need to resolve the repo root
when run directly (outside a virtualenv where toolbox is installed).

Usage in a bin script:
    from toolbox.bin import setup_path
    setup_path()
    from toolbox.lib.drive_utils import get_drive_service
"""
import os
import sys


def setup_path():
    """Add the repo root (parent of toolbox/) to sys.path."""
    repo_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    if repo_root not in sys.path:
        sys.path.insert(0, repo_root)
    return repo_root
