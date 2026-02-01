"""
Authentication Handler.
Manages OAuth 2.0 flows, token storage, and Service Object creation for Drive/Gmail/Sheets.
"""
import os
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build

class GoogleAuth:
    def __init__(self, base_dir=None):
        if base_dir:
            self.base_dir = base_dir
        else:
            # Default to repo root or reliable config loc
            # Assuming this file is in toolbox/core/google.py
            # Repo root would be ../../
            self.base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            
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
                try:
                    creds.refresh(Request())
                    log("AUTH_REFRESH", "SUCCESS", "Token refreshed successfully.")
                except Exception as e:
                    log("AUTH_REFRESH", "FAILURE", f"Token refresh failed: {e}", level="ERROR")
                    raise e
            else:
                if not os.path.exists(creds_path):
                    msg = f"Client secrets not found at {creds_path}"
                    log("AUTH_FLOW", "FAILURE", msg, level="ERROR")
                    raise FileNotFoundError(msg)
                    
                log("AUTH_FLOW", "START", "Starting OOB Auth Flow (Interactive).")
                print("WARNING: Interactive Auth Required. Check Logs.")
                
                flow = InstalledAppFlow.from_client_secrets_file(creds_path, scopes)
                flow.redirect_uri = 'urn:ietf:wg:oauth:2.0:oob'
                auth_url, _ = flow.authorization_url(prompt='consent')
                print(f"Authorize this app: {auth_url}")
                code = input("Enter the authorization code: ")
                flow.fetch_token(code=code)
                creds = flow.credentials
                
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
