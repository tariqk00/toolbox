"""
Generate a combined token with both Drive and Gmail scopes.
Run this in YOUR terminal (not via agent) so the browser redirect works:

  /home/tariqk/repos/personal/toolbox/google-drive/venv/bin/python3 \\
    /home/tariqk/repos/personal/toolbox/bin/generate_combined_token.py
"""
from google_auth_oauthlib.flow import InstalledAppFlow
import os

SCOPES = [
    'https://www.googleapis.com/auth/drive',
    'https://www.googleapis.com/auth/spreadsheets',
    'https://www.googleapis.com/auth/gmail.readonly',
    'https://www.googleapis.com/auth/gmail.modify',
]

CONFIG_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'config')
CREDENTIALS_FILE = os.path.join(CONFIG_DIR, 'credentials.json')
TOKEN_FILE = os.path.join(CONFIG_DIR, 'token_combined.json')

def main():
    print(f"Generating combined token with scopes: {SCOPES}")
    flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_FILE, SCOPES)
    creds = flow.run_local_server(port=0, access_type='offline', prompt='consent')

    with open(TOKEN_FILE, 'w') as f:
        f.write(creds.to_json())

    print(f"SUCCESS: Saved {TOKEN_FILE}")

if __name__ == '__main__':
    main()
