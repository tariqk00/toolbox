
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

# Setup paths
TEST_DIR = Path(__file__).resolve().parent
REPO_ROOT = TEST_DIR.parent
if str(REPO_ROOT.parent) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT.parent))

from toolbox.lib.reporter_utils import (
    ReportSection, build_stat_card, build_row, get_memory_blocks, rebuild_site
)

def test_report_section():
    print("Testing ReportSection...")
    sec = ReportSection("My Section", level=3)
    sec.add_item("- Item 1")
    sec.add_item("- Item 2")
    rendered = sec.render()
    print(f"Rendered Section:\n{rendered}")
    assert "### My Section" in rendered
    assert "- Item 1" in rendered
    assert "- Item 2" in rendered
    print("ReportSection test passed!")

def test_html_helpers():
    print("\nTesting HTML helpers...")
    stat = build_stat_card(10, "Tasks", "📝")
    print(f"Stat Card:\n{stat}")
    assert "10" in stat
    assert "Tasks" in stat
    assert "📝" in stat

    row = build_row("Amazon", url="http://amazon.com", detail="Order")
    print(f"Row:\n{row}")
    assert "Amazon" in row
    assert "http://amazon.com" in row
    assert "order" in row # detail is lowercased
    print("HTML helpers test passed!")

@patch('toolbox.services.email_extractor.writers.get_memory_content')
def test_get_memory_blocks(mock_get_content):
    print("\nTesting get_memory_blocks...")
    mock_content = """\
## 2026-04-30
- Block 1 item A
- Block 1 item B

---

## 2026-04-30
- Block 2 item C

---

## 2026-04-29
- Old block
"""
    mock_get_content.return_value = mock_content
    
    blocks = get_memory_blocks(None, "Orders/Amazon.md", "2026-04-30")
    print(f"Found {len(blocks)} blocks for 2026-04-30")
    assert len(blocks) == 2
    assert "Block 1 item A" in blocks[0]
    assert "Block 2 item C" in blocks[1]
    assert "Old block" not in "".join(blocks)
    print("get_memory_blocks test passed!")

@patch('subprocess.run')
def test_rebuild_site(mock_run):
    print("\nTesting rebuild_site...")
    # Mock successful run
    mock_run.return_value = MagicMock(returncode=0)
    
    with patch('pathlib.Path.exists', return_value=True):
        res = rebuild_site()
        assert res is True
        mock_run.assert_called_once()
        print("rebuild_site (success) test passed!")

    # Mock failed run
    import subprocess
    mock_run.side_effect = subprocess.CalledProcessError(1, 'cmd', stderr=b'error')
    with patch('pathlib.Path.exists', return_value=True):
        res = rebuild_site()
        assert res is False
        print("rebuild_site (failure) test passed!")

if __name__ == "__main__":
    try:
        test_report_section()
        test_html_helpers()
        test_get_memory_blocks()
        test_rebuild_site()
        print("\nAll reporter framework tests passed!")
    except Exception as e:
        print(f"Tests failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
