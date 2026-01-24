import os
import sys

# Ensure local toolbox package is importable if running script directly
current_dir = os.path.dirname(os.path.abspath(__file__))
repo_root = os.path.dirname(os.path.dirname(current_dir))
if repo_root not in sys.path:
    sys.path.append(repo_root)

from toolbox.core.google import GoogleAuth

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

def authenticate():
    print("Starting authentication flow via Shared Core...")
    auth = GoogleAuth(base_dir=BASE_DIR)
    # We pass relative paths assuming base_dir is toolbox/google-drive
    creds = auth.get_credentials(token_filename='token_full_drive.json', credentials_filename='credentials.json')
    print(f"Authentication successful! Scopes: {creds.scopes}")

if __name__ == '__main__':
    authenticate()
