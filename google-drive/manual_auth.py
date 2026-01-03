import os.path
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = ['https://www.googleapis.com/auth/drive']
client_secrets = '/home/takhan/github/tariqk00/plaud/credentials.json'
token_path = '/home/takhan/github/tariqk00/toolbox/google-drive/token_full_drive.json'

def get_manual_token():
    flow = InstalledAppFlow.from_client_secrets_file(client_secrets, SCOPES, redirect_uri='urn:ietf:wg:oauth:2.0:oob')
    auth_url, _ = flow.authorization_url(prompt='consent')
    
    print("--- STEP 1: AUTHORIZE ---")
    print(f"URL: {auth_url}")
    print("\n--- STEP 2: PASTE CODE ---")
    # In this environment, I can't use input(). I'll have the user paste it into a file.
    print("Please paste the 'code' from the redirect into a file named 'auth_code.txt' in this directory.")
    
get_manual_token()
