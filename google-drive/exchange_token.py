import os
import json
from google_auth_oauthlib.flow import InstalledAppFlow

# Allow insecure transport for local development
os.environ['OAUTHLIB_INSECURE_TRANSPORT'] = '1'

SCOPES = ['https://www.googleapis.com/auth/drive']
client_secrets = '/home/takhan/github/tariqk00/plaud/credentials.json'
token_path = '/home/takhan/github/tariqk00/toolbox/google-drive/token_full_drive.json'
REDIRECT_URI = 'http://localhost:8080/'

def exchange_code():
    # The authorization URL provided by the user
    # http://localhost:8080/?state=iw8pTPYwH7Ju5xazjSgQ8GRDGYTHxa&code=4/0ATX87lPJBY_dGmuRJ5s7JMSVis6P610qEpYue3ql9VXYcgaTpB0zzR9IkeQPnF4bmMzN0A&scope=https://www.googleapis.com/auth/drive
    
    auth_response = "http://localhost:8080/?state=iw8pTPYwH7Ju5xazjSgQ8GRDGYTHxa&code=4/0ATX87lPJBY_dGmuRJ5s7JMSVis6P610qEpYue3ql9VXYcgaTpB0zzR9IkeQPnF4bmMzN0A&scope=https://www.googleapis.com/auth/drive"
    
    flow = InstalledAppFlow.from_client_secrets_file(
        client_secrets, 
        SCOPES,
        redirect_uri=REDIRECT_URI
    )
    
    # Extract code from URL manually to be safe, or let flow handle it
    flow.fetch_token(authorization_response=auth_response)
    
    creds = flow.credentials
    with open(token_path, 'w') as token:
        token.write(creds.to_json())
    
    print(f"Token saved to {token_path}")

if __name__ == '__main__':
    exchange_code()
