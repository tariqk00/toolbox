# Implementation Plan: Fix Test Suite Mocks Post-LLMGateway Refactor (Issue #162)

## Overview
Commit `2f5c9c4` (PR #154) replaced the monolithic `ai_engine.py` with a tiered `LLMGateway` architecture, removing legacy attributes (like `GEMINI_API_KEY`) and delegating file extraction to either native API attachments or external parsers. The test suite wasn't fully updated to reflect these architectural changes, resulting in `AttributeError` failures when `unittest.mock.patch` attempts to stub non-existent functions. 

This document outlines the systematic plan to resolve the 59 failing tests, ensuring the test suite is green and fully aligned with the new architecture.

## Core Mocking & Testing Guidelines (CRITICAL)
1. **Mock at the Gateway Boundary:** Use `patch('toolbox.services.drive_organizer.main.call_json_llm')` instead of mocking internal provider logic.
2. **Expected Return Shape:** The mocked `call_json_llm` must return `(data_dict, reasoning_string, token_count)`.
3. **Validate Current Behavior:** Test the actual production behavior (real routing, actual naming logic, side effects). Do **not** reintroduce compatibility wrappers.
4. **Do Not Mask Regressions:** Do not broadly update test assertions to match new output unless a change in formatting was an explicit, intended part of the new architecture.
5. **No Legacy Assumptions:** Remove all tests/mocks validating deprecated helpers such as `generate_new_name`, `should_sweep_root`, `normalize_confidence`, or `quota_manager.record_tokens`.

## Phase 1: Update Core AI Gateway Mocks (`test_ai_engine_providers.py`)
**Problem:** Tests are attempting to mock `ai_engine.GEMINI_API_KEY` and legacy extraction helpers like `_extract_pdf_text`, `_extract_docx_text`, and `_extract_pptx_text`.
**Action:**
1.  **Remove Legacy Environment Mocks:** Eliminate `patch.object(ai_engine, 'GEMINI_API_KEY')`. Use `os.environ` or proper mock boundaries if API keys are required by the test.
2.  **Align File Extraction Tests:** Remove tests validating manual text extraction wrappers (`_extract_pdf_text`, etc.). Replace them with tests verifying that `llm_gateway.call_json_llm` correctly forwards the payload/MIME type.
3.  **Update Routing Assertions:** Verify that text goes to `GroqProvider` and PDFs/Images go to `GeminiProvider` by asserting on the gateway routing behavior.

## Phase 2: Fix Drive Organizer Mocks (`test_sorter.py`)
**Problem:** Tests reference missing helpers (`analyze_with_gemini`, `generate_new_name`, `should_sweep_root`, `normalize_confidence`).
**Action:**
1.  Replace all instances of `patch.object(main, 'analyze_with_gemini')` with `patch('toolbox.services.drive_organizer.main.call_json_llm')`.
2.  Update the return values to the correct tuple structure: `(data_dict, reasoning_string, token_count)`.
3.  Remove or rewrite tests targeting the removed `should_sweep_root`, `normalize_confidence`, and `generate_new_name` helpers, focusing instead on the integrated behavior.

## Phase 3: Fix Tier 1 Optimizations & Quota Manager (`test_tier1_optimizations.py`)
**Problem:** `quota_manager` API changed (e.g., `SORTER_RESERVED` and `record_tokens` are gone; `is_budget_exhausted` is now `is_rpd_exhausted`).
**Action:**
1.  Update the test assertions to use the new token management APIs (e.g., `is_rpd_exhausted`).
2.  Update the mock for `get_ai_supported_mime` to point to `toolbox.lib.drive_utils.get_ai_supported_mime`.
3.  Remove legacy `ai_engine.GEMINI_API_KEY` patches and replace them with standard `call_json_llm` boundary mocks.

## Phase 4: Fix Tier 2 & Tier 3 Logic (`test_tier2_tier3.py`)
**Problem:** `GEMINI_API_KEY` errors, and a `StopIteration` error in `TestBuildDeltaQueue` because `ID_TO_PATH` is empty during the test run.
**Action:**
1.  Remove `GEMINI_API_KEY` patches.
2.  Mock `toolbox.lib.drive_utils.ID_TO_PATH` explicitly in `TestBuildDeltaQueue` with a static dictionary so that `next(iter(ID_TO_PATH.keys()))` works.

## Phase 5: Fix Miscellaneous Service Tests
**Problem:** `test_google_brief.py` fails with a `NoneType` assertion, and `test_receipts_financial.py` has failing substring assertions.
**Action:**
1.  **Google Brief:** The processor handles `None` from the LLM, but the mock verification logic failed. Ensure the assertion accurately validates the resilient output without relaxing the constraints.
2.  **Financial Receipts:** Investigate the failing substring assertions (`assertIn`). Only update them if the underlying output format was intentionally changed by the new gateway; otherwise, identify the regression in the formatting logic and fix it in the service code.

## Execution Strategy
1.  Run the test suite module-by-module (e.g., `pytest tests/test_sorter.py`).
2.  Apply the defined fixes for the specific module.
3.  Enforce strict validation: **No skipped tests, no relaxed assertions without explicit justification.**
4.  Verify the module passes 100%.
5.  Commit the fix for that module.
6.  Repeat until all 59 failing tests are cleanly resolved.
