# Project Journal

- 2026-03-27: refactor: centralized hardcoded Drive/Sheets folder IDs into `config/folder_config.json` under a `system` key — removed constants from `lib/drive_utils.py` and `services/drive_organizer/monthly_review.py`
- 2026-03-27: fix: corrected `RECOMMENDATIONS_PATH` in `monthly_review.py` — was pointing to `google-drive/` (wrong), now uses `config/` (consistent with `ai_engine.py`)
- 2026-03-27: chore: created `bin/__init__.py` with `setup_path()` helper per ARCHITECTURE.md (marks bin/ as a proper package)
- 2026-03-27: chore: archived 6 one-off folder-creation scripts to `bin/archive/` — these ran once and are not part of active automation

- 2026-01-31: Improved Plaud n8n workflow: increased message limit to 10 and enabled processing of "read" emails to recover missed historical items (previously skipped due to "Unread Only" setting).
- docs: Added MCP server configuration and n8n workflow documentation to SYSTEM_PROMPT.md, ENV_SETUP.md, and scriptReferences.md
- feat: Created Readwise Daily Digest v3 workflow with Gemini AI summaries and Google Chat webhook (techs4good.org)
- 2026-02-12: NUC audit: google_api.py made headless-safe, added retry with backoff, replaced deprecated OOB flow with run_local_server
- 2026-02-14: fix: Fixed "Plaud End-to-End (AI-Powered)" workflow — Prepare Routing was accessing `choices[0].message.content` (OpenAI format) instead of `text` (chainLlm output). Deleted unused "Plaud Gemini Automation" prototype from n8n.
- 2026-02-14: feat: Created `garmin/` module for daily Garmin Connect activity sync to Google Drive (Health/Fitness/Garmin).
- 2026-02-14: fix: Fixed sys.path and Drive folder targeting in garmin sync (uses existing `04 - Health` folder, year-level flat structure).
- 2026-02-14: feat: Added monthly Google Doc summary generation to garmin sync for NotebookLM consumption.
- 2026-02-14: feat: Created `trainheroic/` module for extracting workout data from app screenshots via Gemini Vision API.
- 2026-02-14: feat: Added descriptive file naming to TrainHeroic extraction (date, week, day), --rename flag for backlog files.
- 2026-02-15: fix: synced valid Google Drive token to NUC for ai-sorter service and verified system health.
- 2026-02-15: fix: comprehensive restoration of Plaud, Garmin, and TrainHeroic services on NUC by syncing tokens and secrets.

feat(sorter): improved AI categorization, added Google Doc support, and global limit controls.feat: Assess and deploy OpenClaw to NUC with Docker guardrails.
2026-02-16 docs: configured Chromebook CLI for remote OpenClaw access via NUC gateway
2026-02-16 feat: optimized OpenClaw on NUC to use Gemini 2.0 Flash for improved performance
- 2026-02-16: docs: created BACKLOG.md in toolbox/docs and added IDE optimization tasks.
