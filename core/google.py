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
            
    def get_credentials(self, token_filename='token_full_drive.json', credentials_filename='google-drive/credentials.json', scopes=None):
        if scopes is None:
            scopes = ['https://www.googleapis.com/auth/drive']
            
        token_path = os.path.join(self.base_dir, token_filename)
        # Search for credentials in multiple common spots if mostly hardcoded
        creds_path = os.path.join(self.base_dir, credentials_filename)
        
        # Fallback for simpler structures
        if not os.path.exists(creds_path):
             creds_path = os.path.join(self.base_dir, 'credentials.json')

        creds = None
        if os.path.exists(token_path):
            creds = Credentials.from_authorized_user_file(token_path, scopes)
            
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                if not os.path.exists(creds_path):
                    raise FileNotFoundError(f"Client secrets not found at {creds_path}")
                    
                flow = InstalledAppFlow.from_client_secrets_file(creds_path, scopes)
                flow.redirect_uri = 'urn:ietf:wg:oauth:2.0:oob'
                auth_url, _ = flow.authorization_url(prompt='consent')
                print(f"Authorize this app: {auth_url}")
                code = input("Enter the authorization code: ")
                flow.fetch_token(code=code)
                creds = flow.credentials
                
            # Save the credentials for the next run
            with open(token_path, 'w') as token:
                token.write(creds.to_json())
                
        return creds

    def get_service(self, api_name, api_version, creds=None):
        if not creds:
            creds = self.get_credentials()
        return build(api_name, api_version, credentials=creds)
