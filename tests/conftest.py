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

@pytest.fixture(autouse=True)
def setup_env():
    """Ensure environment is ready for tests."""
    # Add any global environment mocks or setup here
    pass
