"""
Pytest configuration for toolbox test suite.

- Adds repo root to sys.path so `from toolbox.x import y` works from any test file.
- Registers --smoke flag; smoke tests are skipped by default.
"""
import os
import sys

# Ensure `toolbox` package is importable: tests/ → toolbox/ → parent (repo root)
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)


def pytest_addoption(parser):
    parser.addoption(
        "--smoke",
        action="store_true",
        default=False,
        help="Run smoke tests against live Google Drive (requires valid credentials)",
    )


def pytest_configure(config):
    config.addinivalue_line(
        "markers",
        "smoke: live Drive integration tests — run with --smoke flag only",
    )


def pytest_collection_modifyitems(config, items):
    if not config.getoption("--smoke"):
        skip_smoke = __import__("pytest").mark.skip(reason="pass --smoke to run live Drive tests")
        for item in items:
            if "smoke" in item.keywords:
                item.add_marker(skip_smoke)
