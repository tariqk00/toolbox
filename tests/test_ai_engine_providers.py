"""
Tests for the ai_engine provider chain introduced with Groq integration.

Verifies routing decisions:
  - text/plain → Groq (not Gemini)
  - GROQ_PROVIDER=off → text/plain falls through to Gemini
  - Groq ProviderSkip → falls through to Gemini
  - Groq JSON parse failure → falls through to Gemini
  - Native PDF (extractable text) → extracted text → Groq
  - Scanned PDF (no text) → Gemini
  - docx with text → extracted text → Groq
  - Empty docx → returns Empty_Document, no provider called
  - pptx with text → extracted text → Groq

All tests are offline — no real Groq or Gemini API calls.
"""
import os
import unittest
from unittest.mock import patch, MagicMock


GOOD_JSON = (
    '{"doc_date":"2026-01-01","entity":"Test",'
    '"folder_path":"01 - Second Brain","summary":"Test note","confidence":"High"}'
)
GOOD_RESULT = {
    "doc_date": "2026-01-01",
    "entity": "Test",
    "folder_path": "01 - Second Brain",
    "summary": "Test note",
    "confidence": "High",
}

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _fake_gemini_client(captured: dict):
    """Build a mock Gemini client that records the call and returns a valid response."""
    def fake_generate_content(model, contents, config=None):
        captured['gemini_called'] = True
        captured['gemini_config'] = config
        resp = MagicMock()
        resp.text = GOOD_JSON
        usage = MagicMock()
        usage.total_token_count = 50
        usage.prompt_token_count = 40
        usage.candidates_token_count = 10
        resp.usage_metadata = usage
        return resp

    client = MagicMock()
    client.models.generate_content.side_effect = fake_generate_content
    return client


def _run_analyze(content_bytes, mime_type, filename, groq_side_effect=None,
                 env_overrides=None, groq_provider_off=False):
    """
    Run analyze_with_gemini with both Groq and Gemini mocked.

    Returns (result, tokens, groq_captured, gemini_captured).
    groq_side_effect: if set, GroqProvider.analyze raises this exception.
    """
    from toolbox.lib import ai_engine
    from toolbox.lib.providers.groq import GroqProvider
    from toolbox.lib.providers.base import ProviderSkip

    groq_captured = {}
    gemini_captured = {}

    def fake_groq_analyze(self_inner, cb, mt, prompt):
        # Mirror the real analyze() — check GROQ_PROVIDER before recording the call
        if os.getenv('GROQ_PROVIDER') == 'off':
            raise ProviderSkip("Groq disabled via GROQ_PROVIDER=off")
        groq_captured['called'] = True
        groq_captured['content_bytes'] = cb
        if groq_side_effect is not None:
            raise groq_side_effect
        return GOOD_JSON, 10

    fake_client = _fake_gemini_client(gemini_captured)

    env = {'GROQ_PROVIDER': 'off'} if groq_provider_off else {}
    if env_overrides:
        env.update(env_overrides)

    with patch.object(ai_engine, 'GEMINI_API_KEY', 'fake-key'), \
         patch.object(ai_engine, 'GEMINI_CACHE', {}), \
         patch.object(ai_engine, '_client', None), \
         patch.dict('os.environ', env, clear=False), \
         patch.object(GroqProvider, 'analyze', fake_groq_analyze), \
         patch('google.genai.Client', return_value=fake_client):
        result, tokens = ai_engine.analyze_with_gemini(
            content_bytes, mime_type, filename, '01 - Second Brain'
        )

    return result, tokens, groq_captured, gemini_captured


# ---------------------------------------------------------------------------
# Text routing
# ---------------------------------------------------------------------------

class TestTextRouting(unittest.TestCase):

    def test_text_plain_goes_to_groq(self):
        result, _, groq_cap, gemini_cap = _run_analyze(
            b'Hello world', 'text/plain', 'note.txt'
        )
        self.assertTrue(groq_cap.get('called'), "Groq should have been called for text/plain")
        self.assertFalse(gemini_cap.get('gemini_called'), "Gemini should NOT be called for text/plain")
        self.assertEqual(result['confidence'], 'High')

    def test_text_plain_groq_provider_off_goes_to_gemini(self):
        result, _, groq_cap, gemini_cap = _run_analyze(
            b'Hello world', 'text/plain', 'note.txt', groq_provider_off=True
        )
        self.assertFalse(groq_cap.get('called'), "Groq should be skipped when GROQ_PROVIDER=off")
        self.assertTrue(gemini_cap.get('gemini_called'), "Gemini should be called as fallback")

    def test_text_plain_groq_rate_limit_falls_through_to_gemini(self):
        from toolbox.lib.providers.base import ProviderSkip
        result, _, groq_cap, gemini_cap = _run_analyze(
            b'Hello world', 'text/plain', 'note.txt',
            groq_side_effect=ProviderSkip("Groq rate limited: 429")
        )
        self.assertTrue(groq_cap.get('called'), "Groq was attempted")
        self.assertTrue(gemini_cap.get('gemini_called'), "Gemini picked up after Groq ProviderSkip")

    def test_text_plain_groq_bad_json_falls_through_to_gemini(self):
        """If Groq returns unparseable JSON, fall through to Gemini."""
        from toolbox.lib import ai_engine
        from toolbox.lib.providers.groq import GroqProvider

        groq_captured = {}
        gemini_captured = {}

        def bad_json_groq(self_inner, cb, mt, prompt):
            groq_captured['called'] = True
            return 'not json at all %%%', 5

        fake_client = _fake_gemini_client(gemini_captured)

        with patch.object(ai_engine, 'GEMINI_API_KEY', 'fake-key'), \
             patch.object(ai_engine, 'GEMINI_CACHE', {}), \
             patch.object(ai_engine, '_client', None), \
             patch.object(GroqProvider, 'analyze', bad_json_groq), \
             patch('google.genai.Client', return_value=fake_client):
            result, _ = ai_engine.analyze_with_gemini(
                b'Hello', 'text/plain', 'note.txt', '01 - Second Brain'
            )

        self.assertTrue(groq_captured.get('called'))
        self.assertTrue(gemini_captured.get('gemini_called'))


# ---------------------------------------------------------------------------
# PDF routing
# ---------------------------------------------------------------------------

class TestPdfRouting(unittest.TestCase):

    def test_native_pdf_routes_to_groq(self):
        """PDF with extractable text should go to Groq after text extraction."""
        # Build a minimal valid PDF with enough text to exceed the threshold
        text_content = 'This is a test invoice document. ' * 20  # ~660 chars
        # Fake a PDF that pypdf can parse — use mock instead of real PDF bytes
        from toolbox.lib import ai_engine

        with patch.object(ai_engine, '_extract_pdf_text', return_value=text_content):
            result, _, groq_cap, gemini_cap = _run_analyze(
                b'%PDF-fake', 'application/pdf', 'invoice.pdf'
            )

        self.assertTrue(groq_cap.get('called'), "Native PDF should route to Groq")
        self.assertFalse(gemini_cap.get('gemini_called'), "Gemini should not be called for native PDF")
        # Groq should receive the extracted text, not raw PDF bytes
        self.assertIn(b'invoice', groq_cap.get('content_bytes', b'').lower())

    def test_scanned_pdf_routes_to_gemini(self):
        """PDF with no extractable text (scanned) should go to Gemini."""
        from toolbox.lib import ai_engine

        with patch.object(ai_engine, '_extract_pdf_text', return_value=''):
            result, _, groq_cap, gemini_cap = _run_analyze(
                b'%PDF-fake', 'application/pdf', 'scan.pdf'
            )

        self.assertFalse(groq_cap.get('called'), "Groq should not be called for scanned PDF")
        self.assertTrue(gemini_cap.get('gemini_called'), "Scanned PDF should route to Gemini")


# ---------------------------------------------------------------------------
# Office format routing
# ---------------------------------------------------------------------------

class TestOfficeFormatRouting(unittest.TestCase):

    DOCX_MIME = 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'
    PPTX_MIME = 'application/vnd.openxmlformats-officedocument.presentationml.presentation'

    def test_docx_with_text_routes_to_groq(self):
        from toolbox.lib import ai_engine
        text = 'Meeting notes from Q1 planning. ' * 15

        with patch.object(ai_engine, '_extract_docx_text', return_value=text):
            result, _, groq_cap, gemini_cap = _run_analyze(
                b'PK\x03\x04fake-docx', self.DOCX_MIME, 'notes.docx'
            )

        self.assertTrue(groq_cap.get('called'), "docx with text should route to Groq")
        self.assertFalse(gemini_cap.get('gemini_called'))

    def test_empty_docx_returns_low_confidence(self):
        from toolbox.lib import ai_engine

        with patch.object(ai_engine, '_extract_docx_text', return_value=''):
            result, _, groq_cap, gemini_cap = _run_analyze(
                b'PK\x03\x04fake-docx', self.DOCX_MIME, 'empty.docx'
            )

        self.assertFalse(groq_cap.get('called'))
        self.assertFalse(gemini_cap.get('gemini_called'))
        self.assertEqual(result['summary'], 'Empty_Document')
        self.assertEqual(result['confidence'], 'Low')

    def test_pptx_with_text_routes_to_groq(self):
        from toolbox.lib import ai_engine
        text = 'Q2 Strategy Presentation slides content. ' * 10

        with patch.object(ai_engine, '_extract_pptx_text', return_value=text):
            result, _, groq_cap, gemini_cap = _run_analyze(
                b'PK\x03\x04fake-pptx', self.PPTX_MIME, 'deck.pptx'
            )

        self.assertTrue(groq_cap.get('called'), "pptx with text should route to Groq")
        self.assertFalse(gemini_cap.get('gemini_called'))

    def test_empty_pptx_returns_low_confidence(self):
        from toolbox.lib import ai_engine

        with patch.object(ai_engine, '_extract_pptx_text', return_value=''):
            result, _, groq_cap, gemini_cap = _run_analyze(
                b'PK\x03\x04fake-pptx', self.PPTX_MIME, 'empty.pptx'
            )

        self.assertEqual(result['summary'], 'Empty_Document')
        self.assertFalse(groq_cap.get('called'))
        self.assertFalse(gemini_cap.get('gemini_called'))


# ---------------------------------------------------------------------------
# Rule-based shortcuts (no provider should be called)
# ---------------------------------------------------------------------------

class TestRuleShortcuts(unittest.TestCase):

    def _run_rule(self, filename, mime='text/plain'):
        from toolbox.lib import ai_engine
        from toolbox.lib.providers.groq import GroqProvider
        groq_called = []
        gemini_called = []

        def track_groq(self_inner, cb, mt, prompt):
            groq_called.append(True)
            return GOOD_JSON, 0

        fake_client = MagicMock()
        fake_client.models.generate_content.side_effect = lambda *a, **kw: gemini_called.append(True)

        with patch.object(ai_engine, 'GEMINI_API_KEY', 'fake-key'), \
             patch.object(ai_engine, 'GEMINI_CACHE', {}), \
             patch.object(GroqProvider, 'analyze', track_groq), \
             patch('google.genai.Client', return_value=fake_client):
            result, _ = ai_engine.analyze_with_gemini(
                b'content', mime, filename, '01 - Second Brain'
            )
        return result, groq_called, gemini_called

    def test_plaud_summary_txt_shortcut(self):
        result, groq, gemini = self._run_rule('2026-01-17_1234_summary.txt')
        self.assertEqual(result['entity'], 'Plaud_Export')
        self.assertFalse(groq)
        self.assertFalse(gemini)

    def test_gemini_journal_shortcut(self):
        result, groq, gemini = self._run_rule('2026-03-08 - Journal - My Thoughts.md')
        self.assertEqual(result['entity'], 'Journal')
        self.assertFalse(groq)
        self.assertFalse(gemini)

    def test_mm_dd_pattern_shortcut(self):
        result, groq, gemini = self._run_rule('04-13 Meeting Notes.md')
        self.assertEqual(result['entity'], 'Plaud_Note')
        self.assertFalse(groq)
        self.assertFalse(gemini)

    def test_unsupported_mime_shortcut(self):
        result, groq, gemini = self._run_rule('audio.mp3', mime='audio/mpeg')
        self.assertEqual(result['confidence'], 'Low')
        self.assertFalse(groq)
        self.assertFalse(gemini)


if __name__ == '__main__':
    unittest.main()
