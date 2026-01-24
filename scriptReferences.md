# Codebase Map (scriptReferences)

This file is auto-generated. It provides a high-level overview of the available modules and scripts.
**Agent Instruction:** Use this map to locate relevant functionality before falling back to global search.

| File / Module | Description / Contents |
| :--- | :--- |
| **[toolbox/check_folder.py](toolbox/check_folder.py)** | Checks if a specific Google Drive folder exists by ID. |

| **[toolbox/create_archive_plaud_folder.py](toolbox/create_archive_plaud_folder.py)** | Creates the 'Plaud_Transcripts' folder within the designated Archive directory. |

| **[toolbox/create_folders.py](toolbox/create_folders.py)** | Batch creates standard subfolder structures (Tracking, Paycheck, ID) |

| **[toolbox/create_other_folder.py](toolbox/create_other_folder.py)** | Ensures the '99 - Other' folder exists at the root (or specified location). |

| **[toolbox/create_plaud_folder.py](toolbox/create_plaud_folder.py)** | Creates the 'Plaud' folder within the PKM (Personal Knowledge Management) structure. |

| **[toolbox/create_staging_folder.py](toolbox/create_staging_folder.py)** | Creates the '00 - Staging' folder if it does not exist. |

| **[toolbox/create_transcripts_folder.py](toolbox/create_transcripts_folder.py)** | Creates a 'Transcripts' subfolder within the main Plaud directory. |

| **[toolbox/find_folders.py](toolbox/find_folders.py)** | Diagnostic script to verify if high-priority folders (Finance, Personal) |

| **[toolbox/find_folders_v2.py](toolbox/find_folders_v2.py)** | Refined diagnostic script that uses the shared `drive_organizer` module |

| **[toolbox/find_missing_transcripts.py](toolbox/find_missing_transcripts.py)** | Performs a global Drive search for files with 'transcript' in the name. |

| **[toolbox/find_plaud_id.py](toolbox/find_plaud_id.py)** | Locates the 'Plaud' folder within the PKM structure and prints its ID. |

| **[toolbox/generate_staging_report.py](toolbox/generate_staging_report.py)** | Parses `sorter_dry_run.csv` to generate a markdown table of proposed file moves. |

| **[toolbox/group_plaud_files.py](toolbox/group_plaud_files.py)** | Analyzes files in the Plaud cabinet to identify related groups (e.g., Audio + Transcript). |
| |   - `def list_and_group_files`:  |

| **[toolbox/identify_parent.py](toolbox/identify_parent.py)** | Resolves a Google Drive Folder ID to its human-readable Name. |

| **[toolbox/list_direct_children.py](toolbox/list_direct_children.py)** | Lists all direct child files/folders of a hardcoded Parent ID. |

| **[toolbox/list_nested_plaud.py](toolbox/list_nested_plaud.py)** | Diagnostic tool to list contents of a specific nested 'Plaud' folder. |

| **[toolbox/list_pkm_ids.py](toolbox/list_pkm_ids.py)** | Searches for the 'Plaud' folder specifically within the PKM hierarchy |

| **[toolbox/list_pkm_structure.py](toolbox/list_pkm_structure.py)** | Recursively lists the folder structure of the Second Brain (PKM). |
| |   - `def list_folder_tree`:  |

| **[toolbox/list_real_plaud.py](toolbox/list_real_plaud.py)** | Lists and groups files in the authoritative 'Plaud' folder. |

| **[toolbox/list_subfolder_contents.py](toolbox/list_subfolder_contents.py)** | Performs a deep scan of subfolders within a specific parent (Inbox/Cabinet). |
| |   - `def list_deep_contents`:  |

| **[toolbox/plaud_cleanup_dryrun.py](toolbox/plaud_cleanup_dryrun.py)** | Analyzes the state of Plaud files to distinguish between Transcripts (Archive) |

| **[toolbox/update_cache.py](toolbox/update_cache.py)** | Manually updates the `gemini_cache.json` database based on user overrides |
| |   - `def load_cache`: <br>  - `def save_cache`:  |

| **[toolbox/google-drive/analyze_stack_patterns.py](toolbox/google-drive/analyze_stack_patterns.py)** | Audits a specific 'Stack' folder using regex patterns to categorize files. |
| |   - `def get_service`: <br>  - `def categorize_name`: <br>  - `def audit_stack`:  |

| **[toolbox/google-drive/auth.py](toolbox/google-drive/auth.py)** | Centralized authentication wrapper. |
| |   - `def authenticate`:  |

| **[toolbox/google-drive/check_inbox_sizes.py](toolbox/google-drive/check_inbox_sizes.py)** | Lists files in the 'Incoming & Inbox' folder with metadata (Size, Created Time). |
| |   - `def check_sizes`:  |

| **[toolbox/google-drive/check_today.py](toolbox/google-drive/check_today.py)** | Queries the Google Sheet Activity Log for operations performed "Today". |
| |   - `def check_today`:  |

| **[toolbox/google-drive/create_folder.py](toolbox/google-drive/create_folder.py)** | Creates the 'Work' folder within the Second Brain structure. |
| |   - `def create_work_folder`:  |

| **[toolbox/google-drive/discover_qnap.py](toolbox/google-drive/discover_qnap.py)** | Explores the QNAP backup folder structure on Google Drive. |
| |   - `def get_drive_service`: <br>  - `def find_folder`: <br>  - `def list_contents`:  |

| **[toolbox/google-drive/drive_organizer.py](toolbox/google-drive/drive_organizer.py)** | Main entry point for the Drive Organizer service. |
| |   - `class RunStats`: <br>  - `def log_to_sheet`: Logs to Google Sheet.<br>  - `def generate_new_name`: <br>  - `def scan_folder`: <br>  - `def sync_logs_to_drive`:  |

| **[toolbox/google-drive/exchange_token.py](toolbox/google-drive/exchange_token.py)** | One-off utility to exchange an OAuth authorization code for a Refresh Token. |
| |   - `def get_token`:  |

| **[toolbox/google-drive/execute_exports_migration.py](toolbox/google-drive/execute_exports_migration.py)** | Executed migration of legacy export files (Kindle, Plaud, Pocket, Evernote) |
| |   - `def get_service`: <br>  - `def find_folder_id`: <br>  - `def ensure_path`: Traverses or creates folder path from root_id.<br>  - `def move_file`: <br>  - `def main`:  |

| **[toolbox/google-drive/extract_mystery_text.py](toolbox/google-drive/extract_mystery_text.py)** | Extracts the first 2000 characters of text from PDF files in the 'Stack'. |
| |   - `def get_service`: <br>  - `def extract_text`: <br>  - `def main`:  |

| **[toolbox/google-drive/finalize_stack_move.py](toolbox/google-drive/finalize_stack_move.py)** | Executes the final migration of files from the 'Stack' to their target categories |
| |   - `def get_service`: <br>  - `def categorize`: <br>  - `def move_files`:  |

| **[toolbox/google-drive/find_id.py](toolbox/google-drive/find_id.py)** | Simple utility to look up a Google Drive Folder ID by its name. |
| |   - `def find_folder`:  |

| **[toolbox/google-drive/generate_report.py](toolbox/google-drive/generate_report.py)** | Converts the `sorter_dry_run.csv` log into a formatted Markdown report (`dry_run_report.md`). |
| |   - `def generate_report`:  |

| **[toolbox/google-drive/generate_url.py](toolbox/google-drive/generate_url.py)** | Generates a new OAuth 2.0 Authorization URL for user consent. |
| |   - `def get_auth_url`:  |

| **[toolbox/google-drive/journal_processor.py](toolbox/google-drive/journal_processor.py)** | Processes raw transcripts using Gemini to generate structured "Knowledge Log" entries. |
| |   - `def get_gemini_folder_id`: Finds or creates the Gemini folder in the Inbox.<br>  - `def process_transcript`: Uses Gemini to process the transcript into a journal entry.<br>  - `def upload_to_drive`: Uploads the journal entry to Google Drive.<br>  - `def main`:  |

| **[toolbox/google-drive/list_buckets.py](toolbox/google-drive/list_buckets.py)** | Lists the top-level "Numbered Buckets" (e.g., 01 - Second Brain, 02 - Personal) |
| |   - `def get_service`: <br>  - `def list_root_buckets`:  |

| **[toolbox/google-drive/list_roots.py](toolbox/google-drive/list_roots.py)** | Lists all folders present at the root level of Google Drive. |
| |   - `def list_root_folders`:  |

| **[toolbox/google-drive/migrate_to_sheets.py](toolbox/google-drive/migrate_to_sheets.py)** | One-time migration script to move local CSV logs (`renaming_history.csv`) |
| |   - `def get_sheets_service`: <br>  - `def migrate`:  |

| **[toolbox/google-drive/organize_qnap.py](toolbox/google-drive/organize_qnap.py)** | Parsing engine for QNAP backups. Reads `qnap_analysis.json` and sorts files |
| |   - `def get_drive_service`: <br>  - `def parse_path_context`: <br>  - `def get_or_create_folder`: <br>  - `def move_file`: <br>  - `def run_organization`:  |

| **[toolbox/google-drive/run_test_suite.py](toolbox/google-drive/run_test_suite.py)** | Verification wrapper. Runs the `scan_folder` logic against a dedicated |

| **[toolbox/google-drive/verify_n8n_output.py](toolbox/google-drive/verify_n8n_output.py)** | Checks for the existence of specific n8n dump files (JSON) in the designated folder. |
| |   - `def verify_drive_folder`:  |

| **[toolbox/google-drive/tests/run_tests.py](toolbox/google-drive/tests/run_tests.py)** | Test Runner. |
| |   - `def patch_folder_map`: <br>  - `def load_config`: <br>  - `def verify_file_count`: <br>  - `def verify_file_exists`: <br>  - `def main`:  |

| **[toolbox/google-drive/tests/setup_test_env.py](toolbox/google-drive/tests/setup_test_env.py)** | Test Environment Setup. |
| |   - `def find_or_create_folder`: <br>  - `def delete_children`: <br>  - `def upload_file`: <br>  - `def main`:  |

| **[toolbox/scripts/generate_references.py](toolbox/scripts/generate_references.py)** | Documentation Generator. |
| |   - `def get_docstring_summary`: Extracts the first line or summary from a docstring.<br>  - `def analyze_file`: Parses a Python file and returns a summary of its contents.<br>  - `def main`:  |

| **[toolbox/core/ai.py](toolbox/core/ai.py)** | AI Abstraction Layer. |
| |   - `def load_api_key`: <br>  - `def load_cache`: <br>  - `def save_cache`: <br>  - `def save_recommendation`: Logs a recommended category path that doesn't have a specific folder yet.<br>  - `def get_ai_supported_mime`: Returns a Gemini-supported MIME type or None if unsupported.<br>  - `def analyze_with_gemini`: Sends content to Gemini-1.5-Flash for analysis using the new google.genai SDK. |

| **[toolbox/core/drive.py](toolbox/core/drive.py)** | Google Drive API Wrapper. |
| |   - `def load_folder_config`: <br>  - `def get_drive_service`: <br>  - `def get_sheets_service`: <br>  - `def get_category_list`: Builds a flat list of categories and sub-categories.<br>  - `def get_category_prompt_str`: <br>  - `def resolve_folder_id`: Resolves a category string to a folder ID.<br>  - `def get_folder_path`: <br>  - `def download_file_content`: Downloads content to memory.<br>  - `def move_file`:  |

| **[toolbox/core/google.py](toolbox/core/google.py)** | Authentication Handler. |
| |   - `class GoogleAuth`:  |

| **[plaud/drive_mcp.py](plaud/drive_mcp.py)** | FastMCP Server implementation for Google Drive. |
| |   - `def get_drive_service`: <br>  - `def get_or_create_folder`: Get the ID of a folder path (e.g., 'Filing Cabinet/Plaud').<br>  - `def upload_file`: Upload a text file (like Markdown) to a specific Google Drive folder.<br>  - `def upload_binary_file`: Upload a binary file (from base64 string) to a specific Google Drive folder. |

| **[plaud/gmail_mcp.py](plaud/gmail_mcp.py)** | FastMCP Server implementation for Gmail. |
| |   - `def get_gmail_service`: <br>  - `def search_plaud_emails`: Search for Plaud.ai emails matching the specific criteria.<br>  - `def get_email_content`: Retrieve the full content of an email, including body and attachment metadata.<br>  - `def download_attachment`: Download an attachment by ID and return the base64 encoded content.<br>  - `def archive_email_thread`: Archive a specific email thread by removing the INBOX label. |

| **[plaud/list_files.py](plaud/list_files.py)** | Diagnostic script to list files in the 'Filing Cabinet/Plaud' folder |
| |   - `def list_plaud_files`:  |

| **[plaud/plaud_automation.py](plaud/plaud_automation.py)** | Main automation workflow for Plaud.ai. |
| |   - `def format_date_time`: <br>  - `def main`:  |

| **[plaud/refresh_tokens_console.py](plaud/refresh_tokens_console.py)** | Interactive console tool to manually refresh Google OAuth tokens |
| |   - `def refresh_gmail`: <br>  - `def refresh_drive`:  |
