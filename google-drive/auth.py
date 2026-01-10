from google_auth_oauthlib.flow import InstalledAppFlow
import os

SCOPES = ['https://www.googleapis.com/auth/drive']
CREDENTIALS_FILE = '/home/takhan/github/tariqk00/toolbox/google-drive/credentials.json'
TOKEN_FILE = '/home/takhan/github/tariqk00/toolbox/google-drive/token_full_drive.json'

def authenticate():
    print("Starting authentication flow...")
    if not os.path.exists(CREDENTIALS_FILE):
        print(f"Error: {CREDENTIALS_FILE} not found.")
        return

    flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_FILE, SCOPES)
    # prompt='consent' forces a refresh token to be returned
    flow.redirect_uri = 'urn:ietf:wg:oauth:2.0:oob'
    
    auth_url, _ = flow.authorization_url(prompt='consent')
    
    print(f"\nPlease visit this URL to authorize this application:\n{auth_url}\n")
    
    code = input("Enter the authorization code: ").strip()
    
    flow.fetch_token(code=code)
    
    with open(TOKEN_FILE, 'w') as token:
        token.write(flow.credentials.to_json())
    
    print(f"\nAuthentication successful! Token saved to {TOKEN_FILE}")

if __name__ == '__main__':
    authenticate()
