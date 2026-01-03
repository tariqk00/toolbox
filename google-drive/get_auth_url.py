import os
from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = ['https://www.googleapis.com/auth/drive']
client_secrets = '/home/takhan/github/tariqk00/plaud/credentials.json'

flow = InstalledAppFlow.from_client_secrets_file(client_secrets, SCOPES)
# This will print the URL and wait for the code
# Since run_local_server is problematic, I'll use run_console() if it existed, but it was removed.
# The alternative is to manually handle the flow.
url, _ = flow.authorization_url(prompt='consent')
print(f"AUTH_URL_START\n{url}\nAUTH_URL_END")

# For the code part, I'll have to ask the user.
