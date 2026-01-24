"""
Generates a new OAuth 2.0 Authorization URL for user consent.
Run this when needing to re-authenticate or add scopes.
"""
from __future__ import print_function
import os
from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = [
    'https://www.googleapis.com/auth/drive',
    'https://www.googleapis.com/auth/spreadsheets'
]

def get_auth_url():
    creds = None
    if os.path.exists('credentials.json'):
        flow = InstalledAppFlow.from_client_secrets_file(
            'credentials.json', SCOPES)
        # Force prompt to ensure we get a new refresh token if needed, though usually not needed for scope update unless access type is offline
        # "urn:ietf:wg:oauth:2.0:oob" is deprecated, using local server but since this is headlness, we print URL.
        # Actually for OOB deprecation, we must use a fixed redirect or localhost.
        # Assuming user can copy paste.
        flow.redirect_uri = 'urn:ietf:wg:oauth:2.0:oob' 
        auth_url, _ = flow.authorization_url(prompt='consent')
        
        print(f"\n--- AUTHORIZATION URL ---\n{auth_url}\n-------------------------")
        print("\nPlease visit the URL, authorize the app, and paste the code below.")

if __name__ == '__main__':
    get_auth_url()
