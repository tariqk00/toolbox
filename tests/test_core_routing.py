"""
Regression tests for core routing logic — all offline, no API calls.

Covers:
- generate_new_name() in both main.py and backfill.py
- Rule-based shortcuts in analyze_with_gemini() (Plaud, Journal, MM-DD)
- Gemini cache hit behaviour

Run from repo root:
  python3 -m pytest toolbox/tests/test_core_routing.py -v
"""
import os
import sys
import unittest
from unittest.mock import patch

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from toolbox.services.drive_organizer.main import generate_new_name as main_generate
from toolbox.services.drive_organizer.backfill import generate_new_name as backfill_generate


# ---------------------------------------------------------------------------
# generate_new_name — shared cases (both main and backfill)
# ---------------------------------------------------------------------------

class _GenerateNewNameBase:
    """Mixin: subclasses set self.fn = main_generate or backfill_generate."""

    def call(self, analysis, original_name, created_time=None):
        return self.fn(analysis, original_name, created_time or "")

    # --- Normal / happy path ---

    def test_normal_produces_standard_format(self):
        result = self.call(
            {"doc_date": "2026-03-15", "entity": "Chase", "summary": "Bank Statement"},
            "statement.pdf"
        )
        self.assertEqual(result, "2026-03-15 - Chase - Bank_Statement.pdf")

    def test_extension_preserved(self):
        result = self.call(
            {"doc_date": "2026-01-01", "entity": "IRS", "summary": "Tax Return"},
            "taxes.pdf"
        )
        self.assertTrue(result.endswith(".pdf"))

    def test_spaces_in_entity_become_underscores(self):
        result = self.call(
            {"doc_date": "2026-01-01", "entity": "Bank of America", "summary": "Statement"},
            "file.pdf"
        )
        self.assertIn("Bank_of_America", result)

    def test_spaces_in_summary_become_underscores(self):
        result = self.call(
            {"doc_date": "2026-01-01", "entity": "Chase", "summary": "Monthly Internet Bill"},
            "file.pdf"
        )
        self.assertIn("Monthly_Internet_Bill", result)

    # --- Date fallback chain ---

    def test_no_date_falls_back_to_filename(self):
        result = self.call(
            {"doc_date": "0000-00-00", "entity": "Chase", "summary": "Statement"},
            "2025-11-01 Chase Statement.pdf"
        )
        self.assertTrue(result.startswith("2025-11-01"))

    def test_no_date_falls_back_to_created_time(self):
        result = self.call(
            {"doc_date": "0000-00-00", "entity": "Chase", "summary": "Statement"},
            "no_date_in_name.pdf",
            created_time="2024-06-15T10:30:00Z"
        )
        self.assertTrue(result.startswith("2024-06-15"))

    def test_no_date_anywhere_appends_nodate(self):
        result = self.call(
            {"doc_date": "0000-00-00", "entity": "Chase", "summary": "Statement"},
            "nodatename.pdf"
        )
        self.assertIn("_(NoDate)", result)

    def test_missing_date_key_appends_nodate(self):
        result = self.call(
            {"entity": "Chase", "summary": "Statement"},
            "nodatename.pdf"
        )
        self.assertIn("_(NoDate)", result)

    # --- Person tagging ---

    def test_known_person_dawn_included(self):
        result = self.call(
            {"doc_date": "2026-01-01", "entity": "BCBS", "summary": "EOB", "person": "dawn"},
            "file.pdf"
        )
        self.assertIn("Dawn", result)
        # Order: date - entity - person - summary
        parts = result.split(" - ")
        self.assertEqual(parts[2], "Dawn")

    def test_known_person_thomas_included(self):
        result = self.call(
            {"doc_date": "2026-01-01", "entity": "School", "summary": "Report", "person": "Thomas"},
            "file.pdf"
        )
        self.assertIn("Thomas", result)

    def test_known_person_sofia_included(self):
        result = self.call(
            {"doc_date": "2026-01-01", "entity": "Dr Smith", "summary": "Visit", "person": "SOFIA"},
            "file.pdf"
        )
        self.assertIn("Sofia", result)

    def test_unknown_person_not_included(self):
        result = self.call(
            {"doc_date": "2026-01-01", "entity": "BCBS", "summary": "EOB", "person": "Tariq"},
            "file.pdf"
        )
        self.assertNotIn("Tariq", result)
        # Should be 3-part name: date - entity - summary
        self.assertEqual(result.count(" - "), 2)

    def test_null_person_not_included(self):
        result = self.call(
            {"doc_date": "2026-01-01", "entity": "BCBS", "summary": "EOB", "person": None},
            "file.pdf"
        )
        self.assertEqual(result.count(" - "), 2)

    # --- Null/missing fields ---

    def test_none_entity_defaults_to_unknown(self):
        result = self.call(
            {"doc_date": "2026-01-01", "entity": None, "summary": "Doc"},
            "file.pdf"
        )
        self.assertIn("Unknown", result)

    def test_none_summary_defaults_to_doc(self):
        result = self.call(
            {"doc_date": "2026-01-01", "entity": "Chase", "summary": None},
            "file.pdf"
        )
        self.assertIn("Doc", result)


class TestMainGenerateNewName(_GenerateNewNameBase, unittest.TestCase):
    fn = staticmethod(main_generate)


class TestBackfillGenerateNewName(_GenerateNewNameBase, unittest.TestCase):
    fn = staticmethod(backfill_generate)


# ---------------------------------------------------------------------------
# Special characters — main and backfill use different sanitizers so test both
# ---------------------------------------------------------------------------

def _entity_part(result):
    """Extract the entity segment from 'date - entity - summary.ext'."""
    return result.split(" - ")[1]

def _summary_part(result):
    """Extract the summary+ext segment from 'date - entity - summary.ext'."""
    return result.split(" - ")[2]


class TestSanitizationMain(unittest.TestCase):
    def call(self, entity, summary):
        return main_generate(
            {"doc_date": "2026-01-01", "entity": entity, "summary": summary},
            "file.pdf", ""
        )

    def test_special_chars_stripped_from_entity(self):
        result = self.call("AT&T Corp.", "Bill")
        self.assertNotIn("&", _entity_part(result))
        self.assertNotIn(".", _entity_part(result))

    def test_special_chars_stripped_from_summary(self):
        result = self.call("Chase", "Q1/Q2 Statement!")
        self.assertNotIn("/", _summary_part(result))
        self.assertNotIn("!", _summary_part(result))


class TestSanitizationBackfill(unittest.TestCase):
    def call(self, entity, summary):
        return backfill_generate(
            {"doc_date": "2026-01-01", "entity": entity, "summary": summary},
            "file.pdf", ""
        )

    def test_special_chars_stripped_from_entity(self):
        result = self.call("AT&T Corp.", "Bill")
        self.assertNotIn("&", _entity_part(result))

    def test_special_chars_stripped_from_summary(self):
        result = self.call("Chase", "Q1/Q2 Statement!")
        self.assertNotIn("/", _summary_part(result))
        self.assertNotIn("!", _summary_part(result))


# ---------------------------------------------------------------------------
# analyze_with_gemini — rule-based shortcuts (no Gemini call, 0 tokens)
# ---------------------------------------------------------------------------

class TestRuleBasedShortcuts(unittest.TestCase):
    """
    Rule-based paths in analyze_with_gemini fire before any API call.
    Patch GEMINI_API_KEY so the function doesn't raise on missing key,
    and verify the correct result + 0 tokens are returned.
    """

    def _call(self, filename, content=b"irrelevant", mime="text/plain"):
        from toolbox.lib import ai_engine
        with patch.object(ai_engine, 'GEMINI_API_KEY', 'fake-key'), \
             patch.object(ai_engine, 'GEMINI_CACHE', {}):
            return ai_engine.analyze_with_gemini(content, mime, filename, "01 - Second Brain")

    # --- Plaud summary export ---

    def test_summary_txt_routed_to_plaud(self):
        result, tokens = self._call("03-15 Morning Meeting summary.txt")
        self.assertEqual(tokens, 0)
        self.assertEqual(result['folder_path'], "01 - Second Brain/Plaud")
        self.assertEqual(result['confidence'], "High")
        self.assertEqual(result['entity'], "Plaud_Export")

    def test_transcript_txt_routed_to_plaud_transcripts(self):
        result, tokens = self._call("03-15 Morning Meeting transcript.txt")
        self.assertEqual(tokens, 0)
        self.assertEqual(result['folder_path'], "01 - Second Brain/Plaud/Transcripts")

    def test_summary_txt_case_insensitive(self):
        result, tokens = self._call("Meeting SUMMARY.TXT")
        self.assertEqual(tokens, 0)
        self.assertEqual(result['folder_path'], "01 - Second Brain/Plaud")

    # --- Gemini Journal ---

    def test_journal_filename_routed_to_gemini_folder(self):
        result, tokens = self._call("2026-03-20 - Journal - Morning thoughts.md")
        self.assertEqual(tokens, 0)
        self.assertEqual(result['folder_path'], "01 - Second Brain/Gemini")
        self.assertEqual(result['entity'], "Journal")
        self.assertEqual(result['confidence'], "High")

    def test_journal_date_extracted_from_filename(self):
        result, tokens = self._call("2026-04-01 - Journal - April fools.md")
        self.assertEqual(result['doc_date'], "2026-04-01")

    def test_journal_summary_extracted_from_filename(self):
        result, tokens = self._call("2026-04-01 - Journal - April fools.md")
        self.assertEqual(result['summary'], "April fools")

    def test_journal_malformed_falls_back_gracefully(self):
        # Fewer than 3 parts after split — shouldn't crash
        result, tokens = self._call("x - Journal - .md")
        self.assertEqual(tokens, 0)
        self.assertEqual(result['folder_path'], "01 - Second Brain/Gemini")

    # --- MM-DD heuristic ---

    def test_mm_dd_prefix_routed_to_plaud(self):
        result, tokens = self._call("03-14 Team standup notes.txt")
        self.assertEqual(tokens, 0)
        self.assertEqual(result['folder_path'], "01 - Second Brain/Plaud")
        self.assertEqual(result['entity'], "Plaud_Note")
        self.assertEqual(result['confidence'], "High")

    def test_mm_dd_date_constructed_correctly(self):
        result, tokens = self._call("07-04 Independence Day notes.txt")
        self.assertEqual(result['doc_date'], "2026-07-04")

    def test_non_mm_dd_prefix_not_matched(self):
        # A filename starting with 4-digit year should NOT match MM-DD
        from toolbox.lib import ai_engine
        with patch.object(ai_engine, 'GEMINI_API_KEY', 'fake-key'), \
             patch.object(ai_engine, 'GEMINI_CACHE', {}), \
             patch.object(ai_engine, 'get_ai_supported_mime', return_value=None):
            result, tokens = ai_engine.analyze_with_gemini(
                b"content", "text/plain", "2026-01-01 Some Doc.txt", "01 - Second Brain"
            )
        # Should NOT hit MM-DD rule; should fall through to mime check
        self.assertNotEqual(result.get('entity'), 'Plaud_Note')

    # --- Cache hit ---

    def test_cache_hit_returns_zero_tokens(self):
        from toolbox.lib import ai_engine
        cached = {"doc_date": "2026-01-01", "entity": "Cached", "folder_path": "X",
                  "summary": "Hit", "confidence": "High"}
        with patch.object(ai_engine, 'GEMINI_API_KEY', 'fake-key'), \
             patch.object(ai_engine, 'GEMINI_CACHE', {"file-123": cached}):
            result, tokens = ai_engine.analyze_with_gemini(
                b"content", "application/pdf", "doc.pdf", "paths", file_id="file-123"
            )
        self.assertEqual(tokens, 0)
        self.assertEqual(result['entity'], "Cached")

    def test_cache_hit_skips_api_call(self):
        from toolbox.lib import ai_engine
        cached = {"doc_date": "2026-01-01", "entity": "Cached", "folder_path": "X",
                  "summary": "Hit", "confidence": "High"}
        api_called = []
        with patch.object(ai_engine, 'GEMINI_API_KEY', 'fake-key'), \
             patch.object(ai_engine, 'GEMINI_CACHE', {"file-abc": cached}), \
             patch('google.genai.Client') as mock_client:
            ai_engine.analyze_with_gemini(
                b"content", "application/pdf", "doc.pdf", "paths", file_id="file-abc"
            )
            mock_client.assert_not_called()

    def test_unknown_mime_returns_low_confidence_no_api_call(self):
        from toolbox.lib import ai_engine
        with patch.object(ai_engine, 'GEMINI_API_KEY', 'fake-key'), \
             patch.object(ai_engine, 'GEMINI_CACHE', {}), \
             patch('google.genai.Client') as mock_client:
            result, tokens = ai_engine.analyze_with_gemini(
                b"data", "audio/mpeg", "recording.mp3", "paths"
            )
        self.assertEqual(tokens, 0)
        self.assertEqual(result['confidence'], "Low")
        mock_client.assert_not_called()


if __name__ == '__main__':
    unittest.main(verbosity=2)
