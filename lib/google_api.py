"""
Authentication Handler.
Manages OAuth 2.0 flows, token storage, and Service Object creation for Drive/Gmail/Sheets.
Headless-safe: will never call input() in non-TTY environments.
"""
import os
import sys
import time
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build

MAX_REFRESH_RETRIES = 3
RETRY_BACKOFF_BASE = 2  # seconds


class GoogleAuth:
    def __init__(self, base_dir=None):
        if base_dir:
            self.base_dir = base_dir
        else:
            self.base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    def _is_interactive(self):
        """Check if running in an interactive terminal."""
        return sys.stdin.isatty() and sys.stdout.isatty()

    def _refresh_with_retry(self, creds, log):
        """Refresh token with exponential backoff."""
        for attempt in range(1, MAX_REFRESH_RETRIES + 1):
            try:
                creds.refresh(Request())
                log("AUTH_REFRESH", "SUCCESS", f"Token refreshed (attempt {attempt}).")
                return True
            except Exception as e:
                if attempt < MAX_REFRESH_RETRIES:
                    wait = RETRY_BACKOFF_BASE ** attempt
                    log("AUTH_REFRESH", "RETRY", f"Refresh attempt {attempt} failed: {e}. Retrying in {wait}s...",
                        level="WARNING")
                    time.sleep(wait)
                else:
                    log("AUTH_REFRESH", "FAILURE", f"All {MAX_REFRESH_RETRIES} refresh attempts failed: {e}",
                        level="ERROR")
                    raise

    def ensure_valid_token(self, token_filename='token_full_drive.json', scopes=None):
        """Pre-flight check: returns True if token is valid or refreshable, False otherwise."""
        from toolbox.lib.log_manager import log

        if scopes is None:
            scopes = ['https://www.googleapis.com/auth/drive']

        token_path = os.path.join(self.base_dir, 'config', token_filename)
        if not os.path.exists(token_path):
            log("AUTH_CHECK", "FAILURE", "Token file not found.", {"path": token_path}, level="ERROR")
            return False

        try:
            creds = Credentials.from_authorized_user_file(token_path, scopes)
            if creds.valid:
                return True
            if creds.expired and creds.refresh_token:
                creds.refresh(Request())
                return creds.valid
        except Exception as e:
            log("AUTH_CHECK", "FAILURE", f"Token validation failed: {e}", level="ERROR")
        return False

    def get_credentials(self, token_filename='token_full_drive.json', credentials_filename='config/credentials.json', scopes=None):
        from toolbox.lib.log_manager import log

        if scopes is None:
            scopes = ['https://www.googleapis.com/auth/drive']

        token_path = os.path.join(self.base_dir, 'config', token_filename)
        creds_path = os.path.join(self.base_dir, credentials_filename)

        if not os.path.exists(creds_path):
            creds_path = os.path.join(self.base_dir, 'config/credentials.json')

        creds = None
        if os.path.exists(token_path):
            try:
                creds = Credentials.from_authorized_user_file(token_path, scopes)
            except Exception as e:
                log("AUTH_LOAD", "FAILURE", f"Failed to load token file: {e}", {"path": token_path}, level="ERROR")

        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                log("AUTH_REFRESH", "START", "Token expired, refreshing...", {"token_file": token_filename})
                self._refresh_with_retry(creds, log)
            else:
                if not os.path.exists(creds_path):
                    msg = f"Client secrets not found at {creds_path}"
                    log("AUTH_FLOW", "FAILURE", msg, level="ERROR")
                    raise FileNotFoundError(msg)

                if not self._is_interactive():
                    msg = (
                        "Interactive auth required but running in headless mode. "
                        "Run this script manually in a terminal to authorize, "
                        f"or provide a valid token at {token_path}"
                    )
                    log("AUTH_FLOW", "FAILURE", msg, level="ERROR")
                    raise RuntimeError(msg)

                log("AUTH_FLOW", "START", "Starting interactive auth flow (local server).")
                flow = InstalledAppFlow.from_client_secrets_file(creds_path, scopes)
                creds = flow.run_local_server(
                    port=0,
                    access_type='offline',
                    prompt='consent',
                )

            # Atomic Save
            try:
                tmp_path = token_path + ".tmp"
                with open(tmp_path, 'w') as token:
                    token.write(creds.to_json())
                os.rename(tmp_path, token_path)
                log("AUTH_SAVE", "SUCCESS", "Credentials saved via atomic write.", {"path": token_path})
            except Exception as e:
                log("AUTH_SAVE", "FAILURE", f"Failed to save credentials: {e}", {"path": token_path}, level="ERROR")

        return creds

    def get_service(self, api_name, api_version, creds=None):
        if not creds:
            creds = self.get_credentials()
        return build(api_name, api_version, credentials=creds)
