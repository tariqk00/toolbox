from toolbox.lib.google_api import GoogleAuth
import os
GoogleAuth(base_dir=os.getcwd()).get_credentials(
    token_filename="token_uptown.json",
    credentials_filename="config/credentials.json",
    scopes=["https://www.googleapis.com/auth/gmail.readonly"],
)
