
import sys
import os
from pathlib import Path
from unittest.mock import MagicMock, patch

# Setup paths
TEST_DIR = Path(__file__).resolve().parent
REPO_ROOT = TEST_DIR.parent
# Add the parent of the repository to sys.path to support 'from toolbox.lib...'
if str(REPO_ROOT.parent) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT.parent))

# Mock internal lib dependencies
sys.modules['google'] = MagicMock()
sys.modules['google.oauth2'] = MagicMock()
sys.modules['google.oauth2.credentials'] = MagicMock()
sys.modules['googleapiclient'] = MagicMock()
sys.modules['googleapiclient.discovery'] = MagicMock()
sys.modules['googleapiclient.http'] = MagicMock()
sys.modules['googleapiclient.errors'] = MagicMock()
sys.modules['dotenv'] = MagicMock()
sys.modules['toolbox.lib.log_manager'] = MagicMock()
sys.modules['toolbox.lib.telegram'] = MagicMock()
sys.modules['toolbox.lib.google_api'] = MagicMock()

from toolbox.services.email_extractor import main

def test_route_result_logic():
    print("Testing low-confidence routing logic...")
    
    summaries = {'receipts': []}
    low_confidence = []
    
    # 1. High confidence result
    high_conf = {'summary': 'High Conf', 'confidence': 1.0, 'category': 'receipts'}
    main._route_result(high_conf, summaries, 'receipts', low_confidence)
    assert summaries['receipts'] == ['High Conf']
    assert len(low_confidence) == 0
    print("High confidence routing passed!")

    # 2. Low confidence result
    low_conf = {'summary': 'Low Conf', 'confidence': 0.5, 'category': 'receipts'}
    main._route_result(low_conf, summaries, 'receipts', low_confidence)
    assert "[LOW CONFIDENCE] Low Conf" in summaries['receipts'][1]
    assert len(low_confidence) == 1
    assert low_confidence[0]['summary'] == 'Low Conf'
    print("Low confidence routing passed!")

if __name__ == "__main__":
    try:
        test_route_result_logic()
        print("\nAll routing tests passed!")
    except Exception as e:
        print(f"Tests failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
