# Backlog

## Technical Debt & Optimization
- [ ] **Disable Unused IDE Extensions**: Remove or disable the "Extension Pack for Java", Maven, and Red Hat Java extensions on Chromebook to stop JDK prompts and improve IDE performance.
- [ ] **Centralized Token Refresh**: Improve `refresh_all_tokens.py` to support automatic syncing to the NUC after successful local refresh.
- [ ] **Unified Logging**: Redirect all service logs (Plaud, Garmin, AI Sorter) to a single dashboard or unified JSON log for easier monitoring.

## Drive Cleanup (Ignored Folders)

These folders are excluded from the AI sorter's routing tree because they're either too deep, legacy archives, or auto-managed by other services. Each is a self-contained cleanup project — follow the workflow in `docs/drive-file-organization.md`.

- [ ] **`05 - Media/QNAP831X`** — ~89 folders of photos/videos migrated from the old QNAP NAS. Already partially organized (`Organized/`, `Landscapes/`, `Misc/`). Goal: standardize to `YYYY/MM - Event` structure, archive metadata per 3-tier workflow, then add root back to sorter tree.

- [ ] **`05 - Media/Google Photos`** — 22 year folders (1988–2019) from a Google Photos export. Goal: verify contents match actual photos library, deduplicate, decide if this folder is redundant or should be kept as a manual archive.

- [ ] **`07 - Archive/Source_Dumps`** — 82 subfolders of raw AI-generated and source content dumps. Goal: audit what's in here, promote anything useful to `01 - Second Brain`, delete the rest.

- [ ] **`03 - Finance/Taxes/2003–2025`** — Year subfolders currently depth-capped. Goal: verify each year folder is complete (returns filed, supporting docs present), then decide whether to let the sorter route directly to year folders or keep manual.

- [ ] **`02 - Personal & ID/Kids/Soccer`** — Old Lindenhurst soccer team email attachments (2012–2013) imported from Classic Sites. Goal: review and either archive to Media or delete — unlikely to need new files routed here.

## Drive as a Knowledge Base (Open Question)

The Drive is now well-organised — Plaud transcripts, work notes, finance docs, health data all in the right places. The open question is: **how do you actually use this corpus?**

Options to noodle on:

- **OpenClaw + Drive MCP** — the `mcp-servers/gdrive/` server already exists. Could give OpenClaw (Samwise) direct search + retrieval over the full Drive, turning it into a personal knowledge assistant that can answer questions from your own files.

- **NotebookLM** — already used for Garmin summaries. Could point it at broader Drive folders (Second Brain, Work) for on-demand synthesis without building anything.

- **Claude/Gemini Pro via API** — build a lightweight query interface (CLI or simple web app) that lets you ask questions across Drive content. Could live in `toolbox/` as a new module.

- **Evergreen digest** — rather than querying on demand, a scheduled job that surfaces relevant content proactively (weekly "what did you capture this week?" across Plaud + Second Brain).

- **Custom app** — if the use case grows beyond personal queries (sharing, collaboration, richer UI), a proper app becomes worth it.

**No action yet** — needs more thinking on the right interaction model before building. Revisit once the Drive cleanup backlog makes progress and the corpus is cleaner.

## Feature Requests
- [ ] **Logseq Sync**: Automate the conversion of Plaud transcript Markdown files into daily journal entries for Logseq.
- [ ] **Inbox Statistics**: Generate a weekly report of inbox volume, processing speed, and AI categorization confidence.
