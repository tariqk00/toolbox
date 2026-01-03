import os
from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = ['https://www.googleapis.com/auth/drive']
client_secrets = '/home/takhan/github/tariqk00/plaud/credentials.json'

# Use a standard localhost redirect URI
REDIRECT_URI = 'http://localhost:8080/'

flow = InstalledAppFlow.from_client_secrets_file(
    client_secrets, 
    SCOPES,
    redirect_uri=REDIRECT_URI
)

url, _ = flow.authorization_url(prompt='consent', access_type='offline')
print(f"AUTH_URL_START\n{url}\nAUTH_URL_END")
