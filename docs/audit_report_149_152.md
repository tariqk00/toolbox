# Audit Report: OpenClaw & LLM Gateway (#149 / #152)

*Note: As requested, no implementation or code changes will be performed based on this report. This document serves purely as an audit of the current state. Any required changes identified here should be tracked via a new GitHub issue.*

## 1. Executive Summary
This audit reviews the implementation of the cost-optimized LLM routing and budget governance system introduced in Issue #149 and PR #152. 

**Key Finding:** The new `LLMGateway` and its tiered configuration (`llm_routing.yaml`) are **fully bypassed in production.** OpenClaw relies on its own hardcoded JSON configuration, and the Python automation scripts (`toolbox`, `plaud`) are still utilizing legacy abstraction layers (`ai_engine.py` and `llm.py`). Furthermore, the intended model hierarchy is misaligned across tools, and DeepSeek is entirely absent from the configuration.

## 2. Current Effective Model Hierarchy
Based on system traces and configuration files, the actual hierarchy in production differs wildly from the intended routing layer:

*   **OpenClaw Background/Heartbeat:** Uses `ollama/gemma4:e4b` (via the `gemma-reader` alias) and falls back to generic `gemini-2.0-flash` for generic background interactions.
*   **OpenClaw Chat/Main:** Primarily driven by `groq/llama-3.3-70b-versatile` with fallbacks to `google/gemini-flash-lite-latest` and `anthropic/claude-haiku-4-5`.
*   **Python Automations (Drive Organizer, Inbox Scanner):** Fallback chain strictly hardcoded in `ai_engine.py`: `Ollama` → `Groq` → `Gemini` (SDK default, risking premium model usage).

## 3. Intended Hierarchy (from #149 / #152)
As defined in `toolbox/config/llm_routing.yaml`:
*   **Background/Heartbeat:** `cheapest` tier (Ollama `gemma4:e2b` or Gemini `2.5-flash-lite`).
*   **Automation/Sub-Agents:** `efficiency` tier (Groq `llama-3.3-70b-versatile` or Gemini `2.0-flash`).
*   **Coding:** `coding` tier (Groq `llama-3.3-70b-versatile`).
*   **Long-Context:** `long-context` tier (Gemini `2.0-flash`).
*   **Final/High-Stakes:** `frontier` tier (Gemini `1.5-pro`).

## 4. Mismatches
1.  **OpenClaw Isolation:** OpenClaw (`openclaw.json`) maintains an entirely separate configuration from `llm_routing.yaml`. It does not respect the tiered approach or the budget caps defined in the Gateway.
2.  **Legacy Python Usage:** `JOURNAL.md` notes that migration of scripts is to be done incrementally. Currently, **0 scripts** have been migrated. Files like `main.py` and `digests.py` still import `toolbox.lib.llm` and `toolbox.lib.ai_engine` directly.
3.  **Outdated Frontier Model:** The `llm_routing.yaml` defines `gemini-1.5-pro` as the frontier, which is expensive and outdated compared to available models (like `gemini-3.1-pro-preview` which OpenClaw has access to).

## 5. Whether Gateway Routing is in the Actual Execution Path
**No.** The LLM Gateway is currently functioning only in isolation via test scripts (e.g., `verify_llm_live.py`). 
*   **Evidence:** `grep_search` across `toolbox/` and `plaud/` confirms `call_llm` and `LLMGateway` are imported *only* in `test_llm_gateway.py` and the live verification script. Production services continue to call `analyze_file`.

## 6. Cost / Token Risk Areas
1.  **Bypassed Budget Governance:** Because production scripts use `ai_engine.py`, the budget enforcement logic (Daily $2.00 limit, per-task $0.20 limit) in the Gateway is ignored.
2.  **Ambiguous Aliases:** The legacy `GeminiProvider` in `ai_engine.py` defaults to generic SDK models if not explicitly specified. This risks accidental fallback to premium reasoning models during bulk automation runs if Groq fails.
3.  **Rate Limit Thrashing:** `logs/llm_routing.jsonl` shows aggressive rate-limit blocking for Groq (`429 Rate limit` on attempt 1, 2, and 3) during test runs, indicating that if the Gateway were live, the fallbacks would trigger frequently, driving up costs.

## 7. DeepSeek Availability
**Not Configured.** 
DeepSeek is entirely absent from the workspace. It is not mentioned in `openclaw.json`, `llm_routing.yaml`, or any provider logic. The only references to "deepseek" in the environment are deep within the vendor code of Python libraries (`google-genai` and `opentelemetry` site-packages).

## 8. Recommended Changes (Proposed Only)
1.  **Migrate Python Scripts:** Execute the planned follow-up from `JOURNAL.md` to replace all instances of `from toolbox.lib.ai_engine import analyze_file` with the new `LLMGateway.call()` method.
2.  **Align OpenClaw:** Either update OpenClaw to call the Python `LLMGateway` via a REST/shell shim, or manually synchronize its model aliases in `openclaw.json` to mirror the tiers in `llm_routing.yaml`.
3.  **Retire Gemini 1.5 Pro:** Update `llm_routing.yaml` to point the `frontier` tier to `gemini-3.1-pro-preview` (which OpenClaw already has keys for) or `claude-sonnet-4-5`.
4.  **Add DeepSeek:** Provision API keys and add DeepSeek to the `efficiency` or `coding` tiers in `llm_routing.yaml` if it is desired as a workhorse.

## 9. Evidence Log
*   **OpenClaw Config:** `setup/hosts/nuc-server/openclaw/openclaw.json` (Shows hardcoded `groq/llama-3.3-70b-versatile` and lack of Gateway mapping).
*   **Python Migration State:** `grep` for `LLMGateway` in `toolbox/` yielded matches only in tests and documentation.
*   **Routing Logs:** `toolbox/logs/llm_routing.jsonl` verified that the Gateway is working but only logging localized test events.
*   **DeepSeek Absence:** Global regex search for `deepseek` yielded exactly 0 hits outside of standard library `site-packages`.
