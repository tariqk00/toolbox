
import sys
import os
from unittest.mock import MagicMock

# Setup paths
TEST_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(TEST_DIR)
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from services.email_extractor.categories import plaud

def test_parse_logic():
    print("Testing date and subject parsing...")
    
    cases = [
        ("2026-04-26", "[PLAUD-AutoFlow] 04-25 My Meeting", "2026-04-25", "My Meeting"),
        ("2026-04-26", "Fwd: [PLAUD-AutoFlow] Interview with Tariq", "2026-04-26", "Interview with Tariq"),
        ("2026-04-26", "[PLAUD-AutoFlow] [plaud-summary] Project X 04/20", "2026-04-20", "Project X"),
        ("2026-04-26", "[PLAUD-AutoFlow]   ", "2026-04-26", "Meeting Recording"),
    ]
    
    for date_in, subj_in, exp_date, exp_subj in cases:
        got_date, got_subj = plaud._parse_date_and_subject(date_in, subj_in)
        print(f"In: '{subj_in}' -> Date: {got_date}, Subj: '{got_subj}'")
        assert got_date == exp_date
        assert got_subj == exp_subj
    print("Parsing tests passed!\n")

def test_markdown_build():
    print("Testing markdown generation...")
    details = {
        "summary": "This is a summary.",
        "outline": "- Key point 1\n- Key point 2",
        "decisions": ["Decision A", "Decision B"]
    }
    md = plaud._build_markdown("Test Subject", "2026-04-26", details, "Original transcript text.")
    print(md)
    assert "# Test Subject" in md
    assert "## Summary" in md
    assert "Decision A" in md
    assert "Original transcript text." in md
    print("Markdown generation tests passed!\n")

if __name__ == "__main__":
    try:
        test_parse_logic()
        test_markdown_build()
        print("All local tests passed!")
    except Exception as e:
        print(f"Tests failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
