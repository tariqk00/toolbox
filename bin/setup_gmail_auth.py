
import sys
import os
import json
try:
    from urllib.parse import urlparse, parse_qs
except ImportError:
    from urlparse import urlparse, parse_qs

# Add repo root to path
current_dir = os.path.dirname(os.path.abspath(__file__))
repo_root = os.path.dirname(os.path.dirname(current_dir))
if repo_root not in sys.path:
    sys.path.append(repo_root)

from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = ['https://www.googleapis.com/auth/gmail.readonly', 'https://www.googleapis.com/auth/gmail.modify']
CREDENTIALS_FILE = os.path.join(repo_root, 'toolbox/config/credentials.json')
TOKEN_FILE = os.path.join(repo_root, 'toolbox/config/token.json')

def setup():
    print("Setting up Gmail Authentication (Manual Localhost Mode)...")
    
    if not os.path.exists(CREDENTIALS_FILE):
        print(f"Error: {CREDENTIALS_FILE} not found.")
        return

    flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_FILE, SCOPES)
    
    # We MUST use a redirect URI that matches the console configuration.
    # The config shows only "http://localhost" (no port specified, which implies port 80? or any port?)
    # Usually "http://localhost" in valid redirect URIs allows any port for installed apps, 
    # BUT if we want to manual copy paste, we should stick to what is exactly there.
    # Let's try http://localhost first.
    
    flow.redirect_uri = 'http://localhost'

    auth_url, _ = flow.authorization_url(prompt='consent', access_type='offline')
    
    print(f"\n1. Visit this URL to authorize: \n\n{auth_url}\n")
    print("2. You will be redirected to a 'localhost' address.")
    print("   - If the page fails to load (Connection Refused), that is EXPECTED.")
    print("   - Look at the URL bar of your browser.")
    print("   - Copy the EVERYTHING in the address bar (starting with http://localhost/?code=...)")
    
    code_input = input("\n3. Paste the full redirected URL (or just the code) here: ").strip()
    
    # Extract code if full URL is pasted
    if 'code=' in code_input:
        try:
            # Handle cases where user pastes just the query part or full url
            if '?' in code_input:
                query = code_input.split('?')[1]
            else:
                query = code_input
            
            params = parse_qs(query)
            if 'code' in params:
                code = params['code'][0]
            else:
                code = code_input # Fallback
        except:
            code = code_input
    else:
        code = code_input

    try:
        flow.fetch_token(code=code)
        creds = flow.credentials
        
        with open(TOKEN_FILE, 'w') as token:
            token.write(creds.to_json())
        
        print(f"\nSUCCESS: Authenticated and saved {TOKEN_FILE}!")
        
    except Exception as e:
        print(f"\nAuthentication Failed: {e}")

if __name__ == "__main__":
    setup()
