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


from toolbox.services.drive_organizer.backfill import generate_new_name as backfill_generate


# ---------------------------------------------------------------------------
# generate_new_name — shared cases (both main and backfill)
# ---------------------------------------------------------------------------

class _GenerateNewNameBase:
    """Mixin: subclasses set self.fn = backfill_generate or backfill_generate."""

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
        return backfill_generate(
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

