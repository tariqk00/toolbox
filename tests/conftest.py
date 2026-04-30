import os
import sys
import pytest

# Ensure repo roots are in sys.path
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PARENT_DIR = os.path.dirname(BASE_DIR)

if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)
if PARENT_DIR not in sys.path:
    sys.path.insert(0, PARENT_DIR)


def pytest_addoption(parser):
    parser.addoption(
        "--smoke",
        action="store_true",
        default=False,
        help="run live smoke tests",
    )


def pytest_collection_modifyitems(config, items):
    if config.getoption("--smoke"):
        return

    skip_smoke = pytest.mark.skip(reason="use --smoke to run live smoke tests")
    for item in items:
        if "smoke" in item.keywords:
            item.add_marker(skip_smoke)


@pytest.fixture(autouse=True)
def setup_env():
    """Ensure environment is ready for tests."""
    # Add any global environment mocks or setup here
    pass
