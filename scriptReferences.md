# Codebase Map (scriptReferences)

This file is auto-generated. It provides a high-level overview of the available modules and scripts.
**Agent Instruction:** Use this map to locate relevant functionality before falling back to global search.

| File / Module | Description / Contents |
| :--- | :--- |
| **[toolbox/bin/create_archive_plaud_folder.py](toolbox/bin/create_archive_plaud_folder.py)** | Creates the 'Plaud_Transcripts' folder within the designated Archive directory. |

| **[toolbox/bin/create_folders.py](toolbox/bin/create_folders.py)** | Batch creates standard subfolder structures (Tracking, Paycheck, ID) |

| **[toolbox/bin/create_other_folder.py](toolbox/bin/create_other_folder.py)** | Ensures the '99 - Other' folder exists at the root (or specified location). |

| **[toolbox/bin/create_plaud_folder.py](toolbox/bin/create_plaud_folder.py)** | Creates the 'Plaud' folder within the PKM (Personal Knowledge Management) structure. |

| **[toolbox/bin/create_staging_folder.py](toolbox/bin/create_staging_folder.py)** | Creates the '00 - Staging' folder if it does not exist. |

| **[toolbox/bin/create_transcripts_folder.py](toolbox/bin/create_transcripts_folder.py)** | Creates a 'Transcripts' subfolder within the main Plaud directory. |

| **[toolbox/bin/find_folders_v2.py](toolbox/bin/find_folders_v2.py)** | Refined diagnostic script that uses the shared `drive_organizer` module |

| **[toolbox/bin/find_missing_transcripts.py](toolbox/bin/find_missing_transcripts.py)** | Performs a global Drive search for files with 'transcript' in the name. |

| **[toolbox/bin/find_plaud_id.py](toolbox/bin/find_plaud_id.py)** | Locates the 'Plaud' folder within the PKM structure and prints its ID. |

| **[toolbox/bin/generate_staging_report.py](toolbox/bin/generate_staging_report.py)** |  |

| **[toolbox/bin/group_plaud_files.py](toolbox/bin/group_plaud_files.py)** | Analyzes files in the Plaud cabinet to identify related groups (e.g., Audio + Transcript). |
| |   - `def list_and_group_files`:  |

| **[toolbox/bin/identify_parent.py](toolbox/bin/identify_parent.py)** | Resolves a Google Drive Folder ID to its human-readable Name. |

| **[toolbox/bin/list_direct_children.py](toolbox/bin/list_direct_children.py)** | Lists all direct child files/folders of a hardcoded Parent ID. |

| **[toolbox/bin/list_nested_plaud.py](toolbox/bin/list_nested_plaud.py)** | Diagnostic tool to list contents of a specific nested 'Plaud' folder. |

| **[toolbox/bin/list_pkm_ids.py](toolbox/bin/list_pkm_ids.py)** | Searches for the 'Plaud' folder specifically within the PKM hierarchy |

| **[toolbox/bin/list_pkm_structure.py](toolbox/bin/list_pkm_structure.py)** | Recursively lists the folder structure of the Second Brain (PKM). |
| |   - `def list_folder_tree`:  |

| **[toolbox/bin/list_real_plaud.py](toolbox/bin/list_real_plaud.py)** | Lists and groups files in the authoritative 'Plaud' folder. |

| **[toolbox/bin/list_subfolder_contents.py](toolbox/bin/list_subfolder_contents.py)** | Performs a deep scan of subfolders within a specific parent (Inbox/Cabinet). |
| |   - `def list_deep_contents`:  |

| **[toolbox/bin/plaud_cleanup_dryrun.py](toolbox/bin/plaud_cleanup_dryrun.py)** | Analyzes the state of Plaud files to distinguish between Transcripts (Archive) |

| **[toolbox/bin/update_cache.py](toolbox/bin/update_cache.py)** |  |
| |   - `def load_cache`: <br>  - `def save_cache`:  |

| **[toolbox/services/drive_organizer/main.py](toolbox/services/drive_organizer/main.py)** | Main entry point for the Drive Organizer service. |
| |   - `class RunStats`: <br>  - `def log_to_sheet`: Logs to Google Sheet.<br>  - `def generate_new_name`: <br>  - `def scan_folder`: <br>  - `def sync_logs_to_drive`:  |

| **[toolbox/lib/ai_engine.py](toolbox/lib/ai_engine.py)** | AI Abstraction Layer. |
| |   - `def load_api_key`: <br>  - `def load_cache`: <br>  - `def save_cache`: <br>  - `def save_recommendation`: Logs a recommended category path that doesn't have a specific folder yet.<br>  - `def get_ai_supported_mime`: Returns a Gemini-supported MIME type or None if unsupported.<br>  - `def analyze_with_gemini`: Sends content to Gemini-1.5-Flash for analysis using the new google.genai SDK. |

| **[toolbox/lib/drive_utils.py](toolbox/lib/drive_utils.py)** | Google Drive API Wrapper. |
| |   - `def load_folder_config`: <br>  - `def get_drive_service`: <br>  - `def get_sheets_service`: <br>  - `def get_category_list`: Builds a flat list of categories and sub-categories.<br>  - `def get_category_prompt_str`: <br>  - `def resolve_folder_id`: Resolves a category string to a folder ID.<br>  - `def get_folder_path`: <br>  - `def download_file_content`: Downloads content to memory.<br>  - `def move_file`:  |

| **[toolbox/lib/google_api.py](toolbox/lib/google_api.py)** | Authentication Handler. |
| |   - `class GoogleAuth`:  |

| **[toolbox/lib/log_manager.py](toolbox/lib/log_manager.py)** |  |
| |   - `class LogManager`: Unified Logging System for the Toolbox.<br>  - `def log`:  |

| **[plaud/bin/list_files.py](plaud/bin/list_files.py)** |  |
| |   - `def list_plaud_files`:  |

| **[plaud/bin/refresh_tokens.py](plaud/bin/refresh_tokens.py)** |  |
| |   - `def refresh_gmail`: <br>  - `def refresh_drive`:  |

| **[plaud/src/automation.py](plaud/src/automation.py)** | Main automation workflow for Plaud.ai. |
| |   - `def format_date_time`: <br>  - `def main`:  |

| **[plaud/src/mcp_server/drive.py](plaud/src/mcp_server/drive.py)** | FastMCP Server implementation for Google Drive. |
| |   - `def get_drive_service`: <br>  - `def get_or_create_folder`: Get the ID of a folder path (e.g., 'Filing Cabinet/Plaud').<br>  - `def upload_file`: Upload a text file (like Markdown) to a specific Google Drive folder.<br>  - `def upload_binary_file`: Upload a binary file (from base64 string) to a specific Google Drive folder. |

| **[plaud/src/mcp_server/gmail.py](plaud/src/mcp_server/gmail.py)** | FastMCP Server implementation for Gmail. |
| |   - `def get_gmail_service`: <br>  - `def search_plaud_emails`: Search for Plaud.ai emails matching the specific criteria.<br>  - `def get_email_content`: Retrieve the full content of an email, including body and attachment metadata.<br>  - `def download_attachment`: Download an attachment by ID and return the base64 encoded content.<br>  - `def archive_email_thread`: Archive a specific email thread by removing the INBOX label. |

| **[toolbox/scripts/fix_imports.py](toolbox/scripts/fix_imports.py)** |  |
| |   - `def fix_file`: <br>  - `def main`:  |

| **[toolbox/scripts/fix_paths.py](toolbox/scripts/fix_paths.py)** |  |
| |   - `def fix_file`: <br>  - `def main`:  |

| **[toolbox/scripts/generate_references.py](toolbox/scripts/generate_references.py)** | Documentation Generator. |
| |   - `def get_docstring_summary`: Extracts the first line or summary from a docstring.<br>  - `def analyze_file`: Parses a Python file and returns a summary of its contents.<br>  - `def main`:  |

| **[toolbox/scripts/verify_auth_patch.py](toolbox/scripts/verify_auth_patch.py)** |  |
| |   - `def verify`:  |

| **[setup/scripts/system_check.py](setup/scripts/system_check.py)** |  |
| |   - `def print_status`: <br>  - `class SystemChecker`:  |
