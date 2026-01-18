from google_auth_oauthlib.flow import InstalledAppFlow
import sys

SCOPES = [
    'https://www.googleapis.com/auth/drive',
    'https://www.googleapis.com/auth/spreadsheets'
]

CODE = "4/1ASc3gC3wfVdi_WLrCX13t83VvOGoXstPEz0cjZR5kdRF_gIP9-YBlizV6bw"

def get_token():
    flow = InstalledAppFlow.from_client_secrets_file(
        'credentials.json', SCOPES)
    # We must set the redirect_uri to match what was used to generate the URL
    flow.redirect_uri = 'urn:ietf:wg:oauth:2.0:oob'
    
    flow.fetch_token(code=CODE)
    
    with open('token_full_drive.json', 'w') as token:
        token.write(flow.credentials.to_json())
    
    print("Successfully generated token_full_drive.json")

if __name__ == '__main__':
    get_token()
