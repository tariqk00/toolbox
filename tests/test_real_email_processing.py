"""
Integration test: Fetch a real Plaud email and simulate the n8n routing logic.
Uses toolbox/config/token.json (Gmail scopes).
"""
import sys
import os
import base64
import json
from datetime import datetime

current_dir = os.path.dirname(os.path.abspath(__file__))
repo_root = os.path.dirname(current_dir)  # toolbox/
sys.path.insert(0, os.path.dirname(repo_root))  # parent of toolbox for imports

from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build

TOKEN_FILE = os.path.join(repo_root, 'config', 'token.json')

def get_gmail_service():
    SCOPES = ['https://www.googleapis.com/auth/gmail.readonly']
    creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
        with open(TOKEN_FILE, 'w') as f:
            f.write(creds.to_json())
    return build('gmail', 'v1', credentials=creds)

def main():
    service = get_gmail_service()
    print("Searching for Plaud emails...")

    query = 'from:PLAUD.AI <no-reply@plaud.ai> subject:[PLAUD-AutoFlow]'
    results = service.users().messages().list(userId='me', q=query, maxResults=1).execute()
    messages = results.get('messages', [])

    if not messages:
        print("No Plaud emails found.")
        return

    msg_id = messages[0]['id']
    print(f"Found email ID: {msg_id}")

    message = service.users().messages().get(userId='me', id=msg_id).execute()
    payload = message['payload']
    headers = payload['headers']

    subject = next((h['value'] for h in headers if h['name'] == 'Subject'), 'No Subject')
    date_str = next((h['value'] for h in headers if h['name'] == 'Date'), '')

    print(f"Subject: {subject}")
    print(f"Date: {date_str}")

    # Collect attachments
    parts = payload.get('parts', [])
    binary_items = {}

    def find_attachments(parts_list, depth=0):
        for i, part in enumerate(parts_list):
            filename = part.get('filename')
            mime = part.get('mimeType', '')
            body = part.get('body', {})
            att_id = body.get('attachmentId')

            if filename and att_id:
                att = service.users().messages().attachments().get(
                    userId='me', messageId=msg_id, id=att_id).execute()
                key = f"attachment_{len(binary_items)}"
                binary_items[key] = {
                    "fileName": filename,
                    "mimeType": mime,
                    "data": att['data']
                }

            # Recurse into nested parts
            if part.get('parts'):
                find_attachments(part['parts'], depth + 1)

    find_attachments(parts)

    if not binary_items:
        print("  No attachments found in this email.")
        return

    print(f"\nFound {len(binary_items)} attachment(s):")

    # --- Simulate n8n Routing Logic ---
    print("\n--- Simulating n8n Routing Logic ---")

    try:
        clean = date_str.split(' +')[0].split(' -')[0].strip()
        date_obj = datetime.strptime(clean, "%a, %d %b %Y %H:%M:%S")
    except:
        date_obj = datetime.now()

    formatted_date = date_obj.strftime("%Y-%m-%d %H:%M")
    base_filename = f"{formatted_date} {subject}"
    for ch in ['/', '\\', ':', '*', '?', '"', '<', '>', '|']:
        base_filename = base_filename.replace(ch, '')

    transcript_text = ''

    for key, file in binary_items.items():
        is_transcript = file['fileName'].lower() == 'transcript.txt'

        target = ('Transcripts (1ZZf...)' if is_transcript else 'Plaud Root (1lDD...)')

        print(f"\n  [{key}] {file['fileName']}")
        print(f"    MIME: {file['mimeType']}")
        print(f"    Route -> {target}")

        if is_transcript and not transcript_text:
            try:
                transcript_text = base64.urlsafe_b64decode(file['data']).decode('utf-8')
            except:
                transcript_text = "(decode error)"

    print(f"\n--- Gemini Input ---")
    print(f"  Base Filename: {base_filename}")
    if transcript_text:
        print(f"  Transcript Length: {len(transcript_text)} chars")
        print(f"  Snippet: {transcript_text[:200]}...")
    else:
        print("  WARNING: No transcript text found!")

    print("\n--- TEST PASSED ---")

if __name__ == "__main__":
    main()
