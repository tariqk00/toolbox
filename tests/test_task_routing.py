
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

# Mock LLM and Drive
sys.modules['toolbox.lib.llm'] = MagicMock()
sys.modules['toolbox.lib.drive_utils'] = MagicMock()
sys.modules['toolbox.lib.tasks'] = MagicMock()

from toolbox.lib.task_utils import add_task, classify_and_route_task

def test_routing_logic():
    print("Testing task routing logic...")
    
    with patch('toolbox.lib.llm.call_json') as mock_llm:
        # 1. Technical Task
        mock_llm.return_value = {
            "destination": "github",
            "repository": "tariqk00/toolbox",
            "rationale": "This is a bug fix request."
        }
        route = classify_and_route_task("Fix bug in scanner", "Scanner is crashing", "Plaud: Log")
        print(f"Technical Route: {route}")
        assert route['destination'] == 'github'
        assert route['repository'] == 'tariqk00/toolbox'

        # 2. Life Task
        mock_llm.return_value = {
            "destination": "google_tasks",
            "rationale": "This is a grocery list item."
        }
        route = classify_and_route_task("Buy milk", "We are out of milk", "Plaud: Voice")
        print(f"Life Route: {route}")
        assert route['destination'] == 'google_tasks'

    print("Routing logic tests passed!\n")

@patch('toolbox.lib.task_utils.get_action_required_content', return_value="")
@patch('toolbox.lib.task_utils.classify_and_route_task')
@patch('toolbox.lib.task_utils.add_task_to_github')
@patch('toolbox.lib.task_utils.TaskClient')
def test_add_task_routing(mock_client, mock_github, mock_route, mock_content):
    print("Testing add_task with auto_route...")
    
    # Test Github Routing
    mock_route.return_value = {
        "destination": "github",
        "repository": "tariqk00/toolbox",
        "rationale": "Technical task detected"
    }
    
    add_task(
        subject="Fix the api",
        sender="Plaud",
        reason="It broke",
        auto_route=True
    )
    
    mock_github.assert_called_once()
    print("GitHub routing in add_task passed!")

    # Test Google Tasks Routing
    mock_route.return_value = {
        "destination": "google_tasks",
        "rationale": "Personal task detected"
    }
    
    add_task(
        subject="Call Mom",
        sender="Plaud",
        reason="Birthday",
        auto_route=True
    )
    
    # Should call TaskClient (mocked) to sync to Google Tasks
    mock_client.assert_called()
    print("Google Tasks routing in add_task passed!")

if __name__ == "__main__":
    try:
        test_routing_logic()
        test_add_task_routing()
        print("\nAll routing tests passed!")
    except Exception as e:
        print(f"Tests failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
