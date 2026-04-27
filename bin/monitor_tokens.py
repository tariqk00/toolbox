#!/usr/bin/env python3
"""
Token Monitor
Checks the validity of OAuth tokens in toolbox/config and alerts via Telegram if any are expired or broken.
"""
import os
import sys
import json
import datetime
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request

# Ensure toolbox imports work
current_dir = os.path.dirname(os.path.abspath(__file__))
repo_root = os.path.dirname(current_dir)
if repo_root not in sys.path:
    sys.path.append(repo_root)

from toolbox.lib.telegram import send_message
from toolbox.lib.log_manager import log

CONFIG_DIR = os.path.join(repo_root, 'config')

def check_token(token_file):
    token_path = os.path.join(CONFIG_DIR, token_file)
    if not os.path.exists(token_path):
        return False, "File missing"
    
    try:
        creds = Credentials.from_authorized_user_file(token_path)
        if creds.valid:
            return True, "Valid"
        
        if creds.expired and creds.refresh_token:
            creds.refresh(Request())
            if creds.valid:
                # Save refreshed token
                with open(token_path, 'w') as f:
                    f.write(creds.to_json())
                return True, "Valid (Refreshed)"
            
        return False, "Expired or invalid refresh token"
    except Exception as e:
        return False, f"Error: {e}"

def main():
    log("TOKEN_MONITOR", "START", "Checking token validity")
    tokens_to_check = [
        "token_gmail_plaud.json",
        "token_drive_sorter.json",
        "token_gmail_uptown.json"
    ]
    
    metadata_path = os.path.join(CONFIG_DIR, "token_metadata.json")
    metadata = {}
    if os.path.exists(metadata_path):
        try:
            with open(metadata_path, 'r') as f:
                metadata = json.load(f)
        except Exception:
            pass

    errors = []
    
    for token in tokens_to_check:
        valid, status = check_token(token)
        log("TOKEN_MONITOR", "CHECK", f"{token}: {status}")
        
        if not valid:
            errors.append(f"❌ <b>{token}</b>: {status}")
            
    if errors:
        alert_msg = "⚠️ <b>Google OAuth Token Alert</b>\n\nThe following tokens have expired or are invalid. Please run <code>refresh_all_tokens.py</code> via SSH to fix them:\n\n" + "\n".join(errors)
        log("TOKEN_MONITOR", "ALERT", "Sending Telegram alert for broken tokens")
        send_message(alert_msg)
    else:
        log("TOKEN_MONITOR", "SUCCESS", "All tokens are valid")

if __name__ == "__main__":
    main()
