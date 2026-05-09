# Codebase Map (scriptReferences)

This file is auto-generated. It provides a high-level overview of the available modules and scripts.
**Agent Instruction:** Use this map to locate relevant functionality before falling back to global search.

| File / Module | Description / Contents |
| :--- | :--- |
| **[toolbox/bin/analyze_finances.py](toolbox/bin/analyze_finances.py)** | Automated Spending Analysis |
| |   - `def normalize_dataframe`: Normalize the dataframe columns based on typical bank structures.<br>  - `def generate_markdown_report`: Generate a markdown report in life-docs.<br>  - `def main`:  |

| **[toolbox/bin/benchmark_ollama.py](toolbox/bin/benchmark_ollama.py)** |  |
| |   - `def run_benchmark`:  |

| **[toolbox/bin/daily_reporter.py](toolbox/bin/daily_reporter.py)** | Generates docs/life/YYYY-MM-DD.md for the previous calendar day. |
| |   - `def _trip_stat_html`: <br>  - `def update_home_index`: Regenerate the dynamic header and hero card in docs/index.md.<br>  - `def main`:  |

| **[toolbox/bin/dedup_drive.py](toolbox/bin/dedup_drive.py)** | Drive dedup utility. |
| |   - `def resolve_path`: Walk a slash-separated path from Drive root, return folder ID.<br>  - `def list_files`: List all non-trashed files (not folders) in a folder, handling pagination.<br>  - `def trash_file`: <br>  - `def move_file`: <br>  - `def folder_is_empty`: <br>  - `def dedup_within_folder`: Group files in folder by name. Keep newest, trash rest.<br>  - `def consolidate_folders`: For each file in source:<br>  - `def main`:  |

| **[toolbox/bin/dedup_memory.py](toolbox/bin/dedup_memory.py)** | One-time deduplication of existing Memory files. |
| |   - `def _resolve_folder`: Resolve a slash-separated path to a folder ID, starting from root.<br>  - `def _list_md_files`: Return all .md files in folder_id as list of {id, name}.<br>  - `def _download`: <br>  - `def _upload`: <br>  - `def _split_blocks`: Split content into blocks by '---' separator.<br>  - `def _rejoin`: <br>  - `def _travel_key`: (date, vendor, trip_type) from a Travel.md block.<br>  - `def _order_key`: Order number from header; fallback: date + vendor.<br>  - `def _receipt_key`: Date + amount; fallback: date + vendor.<br>  - `def dedup_content`: Return (deduped_content, n_removed).<br>  - `def dedup_file`: Download, dedup, and re-upload one file. Returns number of blocks removed.<br>  - `def run_travel`: <br>  - `def run_orders`: <br>  - `def run_receipts`: <br>  - `def main`:  |

| **[toolbox/bin/generate_combined_token.py](toolbox/bin/generate_combined_token.py)** | Legacy helper for one-off recovery of a combined Drive + Gmail token. |
| |   - `def main`:  |

| **[toolbox/bin/list_direct_children.py](toolbox/bin/list_direct_children.py)** | Lists all direct child files/folders of a hardcoded Parent ID. |

| **[toolbox/bin/llm_gateway_proxy.py](toolbox/bin/llm_gateway_proxy.py)** | OpenAI-compatible proxy for LLMGateway. |
| |   - `class LLMGatewayProxyHandler`: <br>  - `def run`:  |

| **[toolbox/bin/monitor_tokens.py](toolbox/bin/monitor_tokens.py)** | Token Monitor |
| |   - `def check_token`: <br>  - `def main`:  |

| **[toolbox/bin/oc_model_stats.py](toolbox/bin/oc_model_stats.py)** | Daily OpenClaw model usage report. |
| |   - `def fetch_logs`: <br>  - `def parse_usage`: Returns (model_counts, fallback_counts).<br>  - `def format_message`: <br>  - `def main`:  |

| **[toolbox/bin/readwise_digest.py](toolbox/bin/readwise_digest.py)** | Readwise Daily Digest — fetches top unread articles, summarizes via Gemini, sends to Telegram. |
| |   - `def _load_key`: <br>  - `def _load_state`: <br>  - `def _save_state`: <br>  - `def _prune_state`: <br>  - `def _fetch_articles`: Fetch all unread articles from Readwise Reader, handling pagination.<br>  - `def _select_articles`: Pick TOP_N articles: 1 newest unsurfaced + 2 random from the rest.<br>  - `def _summarize`: Get a 2-sentence Gemini summary, falling back to existing summary.<br>  - `def _format_message`: <br>  - `def run`:  |

| **[toolbox/bin/setup_gmail_auth.py](toolbox/bin/setup_gmail_auth.py)** |  |
| |   - `def setup`:  |

| **[toolbox/bin/verify_llm_live.py](toolbox/bin/verify_llm_live.py)** |  |
| |   - `def test_live_routing`:  |

| **[toolbox/bin/weekly_ops.py](toolbox/bin/weekly_ops.py)** | Crawls Google Drive folder structure from configured root IDs and writes |
| |   - `def load_roots`: <br>  - `def should_include`: Returns False if the path should be excluded from the tree.<br>  - `def should_recurse`: Returns False if we should stop crawling children of this path.<br>  - `def crawl_folder`: Recursively crawls a folder, building path_to_id and tree.<br>  - `def get_root_name`: Fetches the display name of a folder by ID.<br>  - `def _weekly_spend_summary`: Read cost_log.jsonl and return a 7-day spend summary string.<br>  - `def main`:  |

| **[toolbox/bin/work_reporter.py](toolbox/bin/work_reporter.py)** | Generates all pages under `docs/work/` in the life-docs repo and rebuilds the site. |
| |   - `def build_backlog`: <br>  - `def build_changelog`: <br>  - `def build_sessions`: <br>  - `def build_health`: <br>  - `def main`:  |

| **[toolbox/bin/anova/anova.py](toolbox/bin/anova/anova.py)** | Anova Oven Control - Fixed command structure |
| |   - `class AnovaDevice`:  |

| **[toolbox/bin/archive/create_archive_plaud_folder.py](toolbox/bin/archive/create_archive_plaud_folder.py)** | Creates the 'Plaud_Transcripts' folder within the designated Archive directory. |

| **[toolbox/bin/archive/create_folders.py](toolbox/bin/archive/create_folders.py)** | Batch creates standard subfolder structures (Tracking, Paycheck, ID) |

| **[toolbox/bin/archive/create_other_folder.py](toolbox/bin/archive/create_other_folder.py)** | Ensures the '99 - Other' folder exists at the root (or specified location). |

| **[toolbox/bin/archive/create_plaud_folder.py](toolbox/bin/archive/create_plaud_folder.py)** | Creates the 'Plaud' folder within the PKM (Personal Knowledge Management) structure. |

| **[toolbox/bin/archive/create_staging_folder.py](toolbox/bin/archive/create_staging_folder.py)** | Creates the '00 - Staging' folder if it does not exist. |

| **[toolbox/bin/archive/create_transcripts_folder.py](toolbox/bin/archive/create_transcripts_folder.py)** | Creates a 'Transcripts' subfolder within the main Plaud directory. |

| **[toolbox/services/email_extractor/enrichment.py](toolbox/services/email_extractor/enrichment.py)** | Optional Groq enrichment pass for email extraction pipeline. |
| |   - `def _is_enabled`: <br>  - `def _call_groq`: Call Groq and return raw text, or '' on failure.<br>  - `def _parse_json`: <br>  - `def enrich_receipt`: Return enriched Telegram summary for a receipt/payment.<br>  - `def enrich_order`: Return enriched Telegram summary for an order.<br>  - `def enrich_trip`: Return enriched Telegram summary for a travel booking. |

| **[toolbox/services/email_extractor/main.py](toolbox/services/email_extractor/main.py)** | Email extraction pipeline — daily Gmail scan → 01 - Second Brain/Memory/ in Drive. |
| |   - `def _route_result`: Route a processing result to either the main summary or the low-confidence bucket.<br>  - `def run`:  |

| **[toolbox/services/email_extractor/reset_memory.py](toolbox/services/email_extractor/reset_memory.py)** | Reset email extractor memory files in Drive and local state. |
| |   - `def _find_folder`: <br>  - `def _resolve_path`: <br>  - `def _list_md_files`: Recursively list all .md files under folder_id.<br>  - `def run`:  |

| **[toolbox/services/email_extractor/scanner.py](toolbox/services/email_extractor/scanner.py)** | Gmail scanner for the email extraction pipeline. |
| |   - `def get_gmail_service`: <br>  - `def load_config`: <br>  - `def load_state`: <br>  - `def save_state`: <br>  - `def _build_sender_query`: Build a Gmail from: query for a set of senders and optional domains.<br>  - `def _fetch_messages`: Fetch all messages matching query + date constraint, with pagination.<br>  - `class _HTMLTextExtractor`: Strip HTML tags, preserve links as [url], add newlines at block elements.<br>  - `def html_to_text`: Returns (plain_text, links_list).<br>  - `def _extract_body`: Recursively extract plain text and HTML from a message payload.<br>  - `def _extract_attachments`: Recursively extract attachments from a message payload.<br>  - `def parse_gmail_message`: Parse a raw Gmail message resource into the shared email dict shape.<br>  - `def get_attachment`: Fetch the raw bytes of an attachment.<br>  - `def get_full_email`: Fetch and parse a full email message.<br>  - `def _sender_email`: Extract bare email from 'Name <email>' or plain email.<br>  - `def _match_sender`: Return vendor name if sender matches, else None.<br>  - `def fetch_category_emails`: Fetch and parse emails for a given category. |

| **[toolbox/services/email_extractor/writers.py](toolbox/services/email_extractor/writers.py)** | Drive markdown writer for the email extraction pipeline. |
| |   - `def _find_or_create_folder`: <br>  - `def _resolve_path`: Resolve a Drive path like '01 - Second Brain/Memory/Orders' to a folder ID.<br>  - `def _get_file_in_folder`: Return file ID if filename exists in folder, else None.<br>  - `def get_memory_content`: Download and return the current text content of a Memory file.<br>  - `def list_memory_files`: Return {filename: file_id} for all files in a memory folder.<br>  - `def set_memory_content`: Create or replace the full contents of a Memory file.<br>  - `def block_exists`: Return True if `content` already contains a markdown block (separated by<br>  - `def update_in_memory`: Replace old_text with new_text in an existing memory file.<br>  - `def append_to_memory`: Append new_content to Memory/{category}/{filename}. |

| **[toolbox/services/email_extractor/categories/digests.py](toolbox/services/email_extractor/categories/digests.py)** | Digests category processor. |
| |   - `def _call_llm`: <br>  - `def _is_known_sender`: Return source name if known, else None.<br>  - `def process`:  |

| **[toolbox/services/email_extractor/categories/google_brief.py](toolbox/services/email_extractor/categories/google_brief.py)** | Google CC Daily Brief processor. |
| |   - `def _extract_brief_details`: <br>  - `def _push_to_tasks`: <br>  - `def process`:  |

| **[toolbox/services/email_extractor/categories/orders.py](toolbox/services/email_extractor/categories/orders.py)** | Orders category processor. |
| |   - `def _is_order_email`: <br>  - `def _get_body`: <br>  - `def _prep_for_llm`: Strip noise before sending to LLM: HTML entities, invisible chars, URLs, whitespace.<br>  - `def _extract_order_number`: <br>  - `def _extract_pillpack_shipment_key`: <br>  - `def _extract_status`: <br>  - `def _item_key`: <br>  - `def _format_item_line`: <br>  - `def _extract_carrier`: Detect carrier name from shipping email body.<br>  - `def _normalize_delivery_date`: <br>  - `def _extract_delivery_date`: <br>  - `def _extract_tracking`: <br>  - `def _shipping_details`: <br>  - `def _order_url`: Return a direct order URL for vendors that support it, else empty string.<br>  - `def _extract_total_fallback`: <br>  - `def _looks_like_product_line`: <br>  - `def _looks_like_section_header`: <br>  - `def _looks_like_name_only_product_line`: <br>  - `def _extract_qty_nearby`: <br>  - `def _extract_items_fallback`: <br>  - `def _merge_extracted_order_data`: <br>  - `def _fallback_extract_items`: Deterministic fallback for item extraction if LLM fails.<br>  - `def _extract_items_llm`: Ask Gemini to extract items, total, and tracking from an order email.<br>  - `def process`:  |

| **[toolbox/services/email_extractor/categories/plaud.py](toolbox/services/email_extractor/categories/plaud.py)** | Plaud category processor for Email Extractor. |
| |   - `def _parse_date_and_subject`: Robust date and subject parsing from Plaud emails.<br>  - `def _extract_details_llm`: Use LLM to extract summary, outline, and actionables.<br>  - `def _categorize_recording`: Route Plaud notes into a stable top-level category.<br>  - `def _standard_folder_path`: Return the standardized folder path under Memory/Plaud.<br>  - `def _build_markdown`: <br>  - `def process`:  |

| **[toolbox/services/email_extractor/categories/receipts.py](toolbox/services/email_extractor/categories/receipts.py)** | Receipts category processor. |
| |   - `def _extract_amount`: <br>  - `def _extract_account`: <br>  - `def _normalize_date`: <br>  - `def _extract_date_by_label`: <br>  - `def _extract_payment_method`: <br>  - `def _extract_transaction_date`: <br>  - `def _extract_transaction_time`: <br>  - `def _derive_category`: <br>  - `def _extract_financial_type`: <br>  - `def _extract_financial_details`: <br>  - `def _is_reminder`: <br>  - `def _extract_uber_rider`: Extract rider from '[Family] Your trip' or '[Personal] Your trip' + name in body.<br>  - `def _extract_type`: <br>  - `def process`:  |

| **[toolbox/services/email_extractor/categories/sweep.py](toolbox/services/email_extractor/categories/sweep.py)** | Weekly email sweep — discovers new senders not covered by existing categories. |
| |   - `def _classify_email`: <br>  - `def _collect_known_senders`: <br>  - `def _sender_email`: <br>  - `def _is_known`: <br>  - `def run`:  |

| **[toolbox/services/email_extractor/categories/trips.py](toolbox/services/email_extractor/categories/trips.py)** | Trips category processor. |
| |   - `def _prep_body`: <br>  - `def _extract_confirmation`: <br>  - `def _extract_trip_type`: <br>  - `def _extract_destination`: <br>  - `def _extract_status`: <br>  - `def _trip_url`: <br>  - `def _extract_trip_details_llm`: Use LLM Gateway to extract type-specific itinerary details.<br>  - `def _build_return_section`: Build the ### Return block for a flight's return leg.<br>  - `def _build_block`: Build a full itinerary block.<br>  - `def process`:  |

| **[toolbox/services/inbox_scanner/actions.py](toolbox/services/inbox_scanner/actions.py)** | Drive writer and Telegram notifier for inbox_scanner. |
| |   - `def write_action_required`: Write action required items to Drive log and Google Tasks with dedup.<br>  - `def write_inquiries`: Write inquiry items to Drive log.<br>  - `def send_immediate_alert`: Send immediate Telegram alert for high-priority action required.<br>  - `def handle_monitored_inquiry`: Structured extraction + dedicated Drive log + immediate Telegram alert for monitored senders.<br>  - `def send_uptown_inquiry_alert`: Send two Telegram messages for a new Uptown Edenton inquiry: details + shadow response.<br>  - `def send_uptown_nudge`: Alert that an inquiry has not been responded to within the timeout window.<br>  - `def send_uptown_missed_inquiry_alert`: Heads-up that an inquiry was responded to but not captured by initial automation.<br>  - `def write_uptown_inquiries`: Write Uptown Edenton inquiries to Memory/Properties/Uptown Edenton Inquiries.md.<br>  - `def _render_uptown_inquiry_block`: <br>  - `def _split_blocks`: <br>  - `def _join_blocks`: <br>  - `def _block_thread_id`: <br>  - `def _block_header`: <br>  - `def upsert_uptown_inquiry_entry`: <br>  - `def sync_uptown_inquiry_index`: Update Uptown inquiry index with KB filename links and responded status.<br>  - `def send_run_summary`: Send end-of-run Telegram summary. |

| **[toolbox/services/inbox_scanner/classifier.py](toolbox/services/inbox_scanner/classifier.py)** | LLM-based email classifier for inbox_scanner. |
| |   - `def classify_email`:  |

| **[toolbox/services/inbox_scanner/main.py](toolbox/services/inbox_scanner/main.py)** | General inbox scanner — scans inbox since last run, classifies unhandled emails, |
| |   - `def load_mailbox_config`: <br>  - `def load_state`: <br>  - `def save_state`: <br>  - `def get_gmail_service`: <br>  - `def collect_known_senders`: Build set of sender emails/domains already handled by email_extractor.<br>  - `def _sender_email`: <br>  - `def _is_known_sender`: <br>  - `def fetch_inbox_since`: Fetch all inbox message IDs since after_date (YYYY/MM/DD), or full inbox if None.<br>  - `def _check_uptown_responses`: Check open Uptown inquiries for replies; nudge if unresponded after timeout.<br>  - `def run`:  |

| **[toolbox/services/inbox_scanner/uptown_response_kb.py](toolbox/services/inbox_scanner/uptown_response_kb.py)** | Uptown response knowledge-base sync and retrieval helpers. |
| |   - `def _sender_email`: <br>  - `def _sender_name`: <br>  - `def _normalize_whitespace`: <br>  - `def _clean_body_text`: <br>  - `def _message_body`: <br>  - `def _subject_base`: <br>  - `def _tokenize`: <br>  - `def _contains_hint`: <br>  - `def _is_identity_match`: <br>  - `def _is_lead_message`: <br>  - `def _is_substantive_response`: <br>  - `def _source_label`: <br>  - `def _lead_name_from_text`: <br>  - `def _filename_slug`: <br>  - `def build_kb_entry`: <br>  - `def kb_filename`: <br>  - `def render_kb_markdown`: <br>  - `def _parse_kb_markdown`: <br>  - `def _candidate_thread_ids`: <br>  - `def sync_response_kb`: <br>  - `def load_kb_entries`: <br>  - `def _score_entry`: <br>  - `def build_prompt_examples`:  |

| **[toolbox/services/inbox_scanner/categories/action_required.py](toolbox/services/inbox_scanner/categories/action_required.py)** | Action Required category processor. |
| |   - `class ActionRequiredProcessor`:  |

| **[toolbox/services/inbox_scanner/categories/base.py](toolbox/services/inbox_scanner/categories/base.py)** | Abstract base for inbox scanner category processors. |
| |   - `class CategoryProcessor`:  |

| **[toolbox/services/inbox_scanner/categories/inquiry.py](toolbox/services/inbox_scanner/categories/inquiry.py)** | Inquiry category processor. |
| |   - `class InquiryProcessor`:  |

| **[toolbox/services/inbox_scanner/categories/uptown_inquiry.py](toolbox/services/inbox_scanner/categories/uptown_inquiry.py)** | Uptown Edenton inquiry processor. |
| |   - `def _sender_email`: <br>  - `def _get_plain_body`: <br>  - `class UptownInquiryProcessor`:  |

| **[toolbox/services/workout-extract/gym_extract.py](toolbox/services/workout-extract/gym_extract.py)** | Gym Workout Screenshot Extractor. |
| |   - `def load_health_folder_id`: <br>  - `def get_or_create_folder`: Create nested folders under parent_id. Returns final folder ID.<br>  - `def sanitize`: <br>  - `def date_from_screenshot_name`: <br>  - `def build_filename`: <br>  - `def list_screenshots`: List all PNG files in a folder and its year/month subfolders.<br>  - `def _list_subfolders`: <br>  - `def get_processed_screenshots`: Scan existing JSONs in the output tree to find already-processed screenshot names.<br>  - `def download_image`: <br>  - `def extract_with_gemini`: <br>  - `def upload_json`: <br>  - `def move_and_rename`: <br>  - `def extract_from_source`: Extract gym sessions from a single source folder.<br>  - `def extract_all`: Extract from all configured sources. Returns combined list of sessions. |

| **[toolbox/services/workout-extract/main.py](toolbox/services/workout-extract/main.py)** | Workout Extract Service — Entry Point. |
| |   - `def load_gemini_key`: <br>  - `def get_drive_service`: <br>  - `def run`: <br>  - `def run_with_error_reporting`: <br>  - `def parse_args`:  |

| **[toolbox/services/workout-extract/merger.py](toolbox/services/workout-extract/merger.py)** | Workout Record Merger. |
| |   - `def load_health_folder_id`: <br>  - `def get_or_create_folder`: <br>  - `def create_unified_record`: Merge gym session data with biometric data into a unified workout record.<br>  - `def _build_filename`: <br>  - `def save_unified_record`: Save unified workout record to Drive under Health/Fitness/Workouts/YYYY/MM/. |

| **[toolbox/services/drive_organizer/backfill.py](toolbox/services/drive_organizer/backfill.py)** | AI Drive Sorter — Backfill Job. |
| |   - `def load_state`: <br>  - `def save_state`: <br>  - `def log_to_sheet`: <br>  - `def generate_new_name`: <br>  - `def build_extra_folder_map`: Crawl backfill_extra_roots (Media, Archive) and return a path→id map.<br>  - `def _crawl_for_backfill`: <br>  - `def _get_extra_folder_map`: Return cached Media/Archive folder map, rebuilding only if >24h old.<br>  - `def _all_tracked_ids`: All folder IDs we care about: sorter tree + extra roots, minus inbox.<br>  - `def _combined_id_to_path`: <br>  - `def build_delta_queue`: Use Drive Changes API to find only files added/modified since last queue build.<br>  - `def build_queue`: Crawl all Drive folders and return list of unprocessed file dicts.<br>  - `def count_only`: <br>  - `def secs_until_midnight`: <br>  - `def near_midnight`: <br>  - `def run`: <br>  - `def parse_args`:  |

| **[toolbox/services/drive_organizer/main.py](toolbox/services/drive_organizer/main.py)** | Main entry point for the Drive Organizer service. |
| |   - `class RunStats`: <br>  - `def load_state`: <br>  - `def save_state`: <br>  - `def _skip_mime_types`: <br>  - `def log_to_sheet`: Placeholder for legacy sheet logging if needed.<br>  - `def _maybe_flag_new_trip`: If AI thinks it's a trip but we don't have the folder, notify.<br>  - `def check_duplicate`: Check if a file with same name or same MD5 exists in the target folder.<br>  - `def post_process_memory`: Update entity memory with organized file metadata.<br>  - `def scan_folder`: <br>  - `def sweep_drive_root`: Special mode to only look at root and move obvious stuff to Inbox.<br>  - `def parse_args`: <br>  - `def run`:  |

| **[toolbox/services/drive_organizer/monthly_review.py](toolbox/services/drive_organizer/monthly_review.py)** |  |
| |   - `def get_recent_activity`: Fetches last 30 days of activity from Google Sheets.<br>  - `def get_folder_stats`: Counts files in each folder from the drive tree.<br>  - `def generate_report`:  |

| **[toolbox/lib/ai_engine.py](toolbox/lib/ai_engine.py)** | AI Abstraction Layer. |
| |   - `def analyze_file`: Redirect to LLMGateway.call_json_llm<br>  - `def analyze_with_gemini`: Old signature used by backfill.py<br>  - `def call`: Simple text-in, text-out interface.<br>  - `def call_json`: Simple text-in, dict-out interface.<br>  - `def get_ai_supported_mime`: Moved to drive_utils, provided here as a shim. |

| **[toolbox/lib/drive_utils.py](toolbox/lib/drive_utils.py)** | Google Drive API Wrapper. |
| |   - `def load_folder_config`: <br>  - `def load_drive_tree`: <br>  - `def get_ai_supported_mime`: Returns a Gemini-supported MIME type or None if unsupported.<br>  - `def get_drive_service`: <br>  - `def get_sheets_service`: <br>  - `def get_category_prompt_str`: Returns a sorted newline-separated list of all folder paths from drive_tree.json.<br>  - `def resolve_folder_id`: Resolves a folder path string to a Drive folder ID via direct lookup in drive_tree.json.<br>  - `def get_folder_path`: <br>  - `def download_file_content`: Downloads content to memory.<br>  - `def escape_query_string`: Escapes single quotes and backslashes for Google Drive API queries.<br>  - `def _find_or_create_folder`: <br>  - `def _resolve_path`: <br>  - `def _get_file_in_folder`: <br>  - `def append_to_file`: Append content to a file in Drive, creating it if needed.<br>  - `def move_file`:  |

| **[toolbox/lib/entity_ids.py](toolbox/lib/entity_ids.py)** | Deterministic entity ID helpers for cross-pipeline identity. |
| |   - `def canonicalize_key`: Normalize key parts into a stable canonical string.<br>  - `def build_entity_id`: Return a deterministic entity_id for a domain/key pair.<br>  - `def order_entity_id`: <br>  - `def travel_entity_id`: <br>  - `def calendar_entity_id`: <br>  - `def plaud_entity_id`: <br>  - `def task_entity_id`: <br>  - `def render_entity_comment`: Emit a hidden markdown marker for entity identity. |

| **[toolbox/lib/entity_memory.py](toolbox/lib/entity_memory.py)** | Standardized entity memory markdown schema and updater. |
| |   - `class EntityMemory`:  |

| **[toolbox/lib/gemini.py](toolbox/lib/gemini.py)** | Gemini interface wrapper. |
| |   - `def call_gemini`: Redirect to LLMGateway.call with 'automation' task type. |

| **[toolbox/lib/google_api.py](toolbox/lib/google_api.py)** | Authentication Handler. |
| |   - `class GoogleAuth`:  |

| **[toolbox/lib/llm.py](toolbox/lib/llm.py)** | Unified LLM interface wrapper. |
| |   - `def call`: Redirect to LLMGateway.call with 'automation' task type.<br>  - `def call_json`: Redirect to LLMGateway.call with 'automation' task type and parse JSON. |

| **[toolbox/lib/llm_gateway.py](toolbox/lib/llm_gateway.py)** | Cost-optimized LLM routing and budget governance gateway. |
| |   - `class LLMGateway`: <br>  - `def call_llm`: <br>  - `def _parse_json`: Robustly extract JSON from LLM markdown-wrapped text.<br>  - `def call_json_llm`: Helper for legacy scripts expecting (json_dict, reasoning, tokens). |

| **[toolbox/lib/log_manager.py](toolbox/lib/log_manager.py)** |  |
| |   - `def _utc_now_iso`: <br>  - `def _json_dumps`: <br>  - `class JsonlFormatter`: Custom formatter to output log records as JSONL.<br>  - `class LogManager`: Unified Logging System for the Toolbox.<br>  - `def log`:  |

| **[toolbox/lib/meeting_utils.py](toolbox/lib/meeting_utils.py)** | Meeting de-duplication helpers shared by ingestion streams. |
| |   - `def normalize_meeting_title`: Normalize a meeting-ish email subject into a comparison title.<br>  - `def meeting_key`: Return a stable date/title key for cross-source meeting de-duplication.<br>  - `def dedupe_meeting_emails`: Filter duplicate meeting emails across categories and update state.<br>  - `def is_duplicate_meeting`: Compatibility hook for future Drive-backed session de-duplication.<br>  - `def sync_plaud_session`: Return whether a Plaud session should be ingested. |

| **[toolbox/lib/quota_manager.py](toolbox/lib/quota_manager.py)** | Shared daily Gemini token quota tracker. |
| |   - `def load`: Load current quota state.<br>  - `def save`: Atomically write quota state.<br>  - `def record_tokens`: Add tokens to today's total and persist. Returns updated state.<br>  - `def record_llm_usage`: Record both tokens and USD cost for a single LLM call.<br>  - `def get_total_usd_used`: Return today's total USD usage.<br>  - `def remaining`: How many tokens are left in today's budget.<br>  - `def is_exhausted`: Check if we've hit the daily token limit.<br>  - `def record_call`: Track calls to Gemini per day (for RPD monitoring).<br>  - `def is_rpd_exhausted`: Check if we've exceeded the free-tier RPD (e.g. 1500 calls/day).<br>  - `def log_cost`: Append a cost record to cost_log.jsonl. |

| **[toolbox/lib/reporter_utils.py](toolbox/lib/reporter_utils.py)** | Shared utilities for life-docs reporters (Daily, Work, etc). |
| |   - `def get_memory_blocks`: Fetch a memory file from Drive and extract blocks for a specific date.<br>  - `def build_stat_card`: Build a life-docs HTML stat card.<br>  - `def build_row`: Build a life-docs HTML row.<br>  - `def rebuild_site`: Run mkdocs build in the life-docs repo.<br>  - `class ReportSection`: A section within a markdown report. |

| **[toolbox/lib/task_utils.py](toolbox/lib/task_utils.py)** | Shared helpers for centralized task management and de-duplicated task creation. |
| |   - `class TaskPriority`: <br>  - `class TaskClient`: Cached client for Google Tasks API.<br>  - `def normalize_task_title`: Return a stable comparison key for a task title.<br>  - `def existing_task_titles`: Return normalized titles of open tasks in a Google Tasks list.<br>  - `def create_unique_tasks`: Create tasks, skipping open-list duplicates and same-batch duplicates.<br>  - `def dedupe_action_items`: Return action-required items without same-batch subject/sender duplicates.<br>  - `def get_action_required_content`: Read current Action Required.md content from Drive for deduplication.<br>  - `def is_duplicate_task`: Check if a task with similar subject already exists in markdown content.<br>  - `def dedupe_action_items`: Deduplicate action items by normalized subject and sender.<br>  - `def create_unique_tasks`: Create only tasks that are not already open and not duplicated in the same batch.<br>  - `def add_task`: Unified task creation interface.<br>  - `def list_google_tasks`: Return all active tasks in a Google Tasks list.<br>  - `def complete_google_task`: Mark a Google Task as completed. |

| **[toolbox/lib/tasks.py](toolbox/lib/tasks.py)** | Google Tasks API helper. |
| |   - `def get_tasks_service`: <br>  - `def get_or_create_list`: Return task list ID for the named list, creating it if needed.<br>  - `def create_task`: Create a task in the given list. |

| **[toolbox/lib/telegram.py](toolbox/lib/telegram.py)** | Telegram notification helper. |
| |   - `def monit_link`: <br>  - `def drive_file_link`: <br>  - `def drive_folder_link`: <br>  - `def escape`: Escape text for Telegram HTML parse_mode.<br>  - `def _load_config`: <br>  - `def _dedup_state_path`: <br>  - `def _normalise_for_dedup`: <br>  - `def _dedup_key`: <br>  - `def _load_dedup_state`: <br>  - `def _save_dedup_state`: <br>  - `def _should_send`: <br>  - `def _route_bucket`: <br>  - `def _resolve_destination`: <br>  - `def send_message`: Send a message to the configured Telegram channel for the given category. |

| **[toolbox/lib/providers/base.py](toolbox/lib/providers/base.py)** | Abstract base class for AI classification providers. |
| |   - `class ProviderSkip`: Raised when a provider should be skipped entirely (disabled, missing key, unsupported mime).<br>  - `class RateLimitError`: Raised on 429 / RPM / TPM limits — signals the gateway to retry with backoff.<br>  - `class AIProvider`:  |

| **[toolbox/lib/providers/deepseek.py](toolbox/lib/providers/deepseek.py)** | DeepSeek provider — remote inference via DeepSeek API (OpenAI compatible). |
| |   - `def _get_client`: <br>  - `class DeepSeekProvider`:  |

| **[toolbox/lib/providers/gemini.py](toolbox/lib/providers/gemini.py)** | Gemini provider — remote inference, supports text, PDF, and images. |
| |   - `def _get_client`: <br>  - `class GeminiProvider`:  |

| **[toolbox/lib/providers/groq.py](toolbox/lib/providers/groq.py)** | Groq provider — remote inference, text-only, high rate limits. |
| |   - `def _get_client`: <br>  - `class GroqProvider`:  |

| **[toolbox/lib/providers/ollama.py](toolbox/lib/providers/ollama.py)** | Ollama provider — local inference, text-only. |
| |   - `class OllamaProvider`:  |

| **[plaud/test_filename_parsing.py](plaud/test_filename_parsing.py)** |  |
| |   - `def test_parsing`:  |

| **[plaud/bin/list_files.py](plaud/bin/list_files.py)** |  |
| |   - `def list_plaud_files`:  |

| **[plaud/bin/plaud_direct.py](plaud/bin/plaud_direct.py)** | Plaud direct API integration. |
| |   - `def load_state`: <br>  - `def save_state`: <br>  - `def load_token`: <br>  - `def get_headers`: <br>  - `def list_recordings`: Fetch all recordings, newest first.<br>  - `def get_detail`: <br>  - `def _fetch_gzipped_json`: Fetch a URL that returns gzip-compressed JSON.<br>  - `def fetch_transcript`: Download and parse a transcript JSON into readable text.<br>  - `def fetch_summary`: Download and extract ai_content from a summary JSON.<br>  - `def fetch_outline`: Download and parse an outline JSON into a topic bullet list.<br>  - `def parse_recording`: Return (doc_date, safe_subject) from a recording dict.<br>  - `def fetch_content`: Fetch all content types for a recording. Returns dict with all sections.<br>  - `def build_markdown`: <br>  - `def extract_actionables`: Run Groq extraction on outline + summary.<br>  - `def push_plaud_tasks`: Push action items to Google Tasks 'Plaud' list. Returns count created.<br>  - `def main`:  |

| **[plaud/bin/refresh_tokens.py](plaud/bin/refresh_tokens.py)** |  |
| |   - `def refresh_gmail`: <br>  - `def refresh_drive`:  |

| **[plaud/src/automation.py](plaud/src/automation.py)** | Main automation workflow for Plaud.ai. |
| |   - `def parse_date_and_subject`: <br>  - `def main`:  |

| **[plaud/src/mcp_server/drive.py](plaud/src/mcp_server/drive.py)** | FastMCP Server implementation for Google Drive. |
| |   - `def get_drive_service`: <br>  - `def get_or_create_folder`: Get the ID of a folder path (e.g., 'Filing Cabinet/Plaud').<br>  - `def upload_file`: Upload a text file (like Markdown) to a specific Google Drive folder.<br>  - `def upload_binary_file`: Upload a binary file (from base64 string) to a specific Google Drive folder. |

| **[plaud/src/mcp_server/gmail.py](plaud/src/mcp_server/gmail.py)** | FastMCP Server implementation for Gmail. |
| |   - `def get_gmail_service`: <br>  - `def search_plaud_emails`: Search for Plaud.ai emails matching the specific criteria.<br>  - `def get_email_content`: Retrieve the full content of an email, including body and attachment metadata.<br>  - `def download_attachment`: Download an attachment by ID and return the base64 encoded content.<br>  - `def archive_email_thread`: Archive a specific email thread: remove INBOX label and mark as read. |

| **[toolbox/scripts/fix_imports.py](toolbox/scripts/fix_imports.py)** |  |
| |   - `def fix_file`: <br>  - `def main`:  |

| **[toolbox/scripts/fix_paths.py](toolbox/scripts/fix_paths.py)** |  |
| |   - `def fix_file`: <br>  - `def main`:  |

| **[toolbox/scripts/generate_references.py](toolbox/scripts/generate_references.py)** | Documentation Generator. |
| |   - `def get_docstring_summary`: Extracts the first line or summary from a docstring.<br>  - `def analyze_file`: Parses a Python file and returns a summary of its contents.<br>  - `def main`:  |

| **[toolbox/scripts/verify_auth_patch.py](toolbox/scripts/verify_auth_patch.py)** |  |
| |   - `def verify`:  |

| **[setup/scripts/error_monitor.py](setup/scripts/error_monitor.py)** | Service error monitor — scans user systemd journals for errors since last run, |
| |   - `def is_actionable_error_line`: Return True for journal lines that indicate service failure.<br>  - `def load_state`: <br>  - `def save_state`: <br>  - `def journal_errors_since`: Return error lines from a service's journal since `since` (journalctl --since value).<br>  - `def normalize_signature_line`: Strip volatile journal prefixes so recurring incidents hash the same.<br>  - `def primary_error_signature`: Return the most diagnostic normalized error line from a journal batch.<br>  - `def fingerprint`: Stable hash for a batch of errors from a service — used for dedup.<br>  - `def fingerprint_marker`: <br>  - `def find_open_issue_by_fingerprint`: Return an existing open toolbox bug URL for this fingerprint, if any.<br>  - `def create_github_issue`: File a GitHub issue in tariqk00/toolbox. Returns (issue URL, was_created).<br>  - `def send_telegram`: Send to NUCOps channel via toolbox bot.<br>  - `def send_oc_dm`: Send a direct message to the user via OC's bot.<br>  - `def write_cc_handoff`: Append filed issues to ~/.claude/oc-to-cc.md for CC to pick up at session start.<br>  - `def main`:  |

| **[setup/scripts/notify_failure.py](setup/scripts/notify_failure.py)** | Systemd failure notifier. |
| |   - `def main`:  |

| **[setup/scripts/system_check.py](setup/scripts/system_check.py)** |  |
| |   - `class SystemChecker`:  |

| **[setup/scripts/test_portability.py](setup/scripts/test_portability.py)** | Regression test: verify no machine-specific hardcoded paths sneak back in. |
| |   - `def get_tracked_files`: <br>  - `def should_skip`: <br>  - `def check_forbidden_strings`: <br>  - `def check_json_valid`: <br>  - `def check_python_compiles`: <br>  - `def check_openclaw_config`: Check for deprecated/invalid keys and verify required proxy config in OpenClaw template.<br>  - `def main`:  |
