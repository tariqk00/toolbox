import os
import sys
import json
import datetime
import argparse
from google.genai import types
from google import genai
from drive_organizer import get_drive_service, load_api_key, SECRET_PATH

# --- CONFIG ---
# Folder IDs from discovery
INBOX_ID = '1c-7Wv9J-FPpc3tph7Ax1xx5bMI-5jcaG'
# Default Gemini folder name in Inbox
GEMINI_FOLDER_NAME = "Gemini"

JOURNAL_PROMPT = """
Convert the following chat transcript into a structured Knowledge Log suitable for my personal knowledge base.
Guidelines:
Group by Semantic Topic: (e.g., [[HomeLab]], [[Finance]], [[Health]]).
Extract High-Value Info: Focus on capturing the solution or the fact, not the conversation about it.
Format: Clean Markdown. Use Bold for key concepts or tools.
Output Sections:
## 📅 Daily Context: 1-2 lines on what I was working on today.
## ✅ Tasks & Commitments: A checkbox list of actionable items generated today.
## 🧠 Knowledge Captured:
Topic Name: Concise summary of the solution or insight. (Include specific commands, prices, or hard data).
## 🚫 What We Skipped: Briefly note any ideas or tools we discarded (to avoid re-researching them later).

Transcript:
{transcript}
"""

def get_gemini_folder_id(service, parent_id):
    """Finds or creates the Gemini folder in the Inbox."""
    query = f"name = '{GEMINI_FOLDER_NAME}' and '{parent_id}' in parents and mimeType = 'application/vnd.google-apps.folder' and trashed = false"
    results = service.files().list(q=query, fields="files(id, name)").execute()
    files = results.get('files', [])
    
    if files:
        return files[0]['id']
    else:
        # Create it if it doesn't exist
        file_metadata = {
            'name': GEMINI_FOLDER_NAME,
            'mimeType': 'application/vnd.google-apps.folder',
            'parents': [parent_id]
        }
        folder = service.files().create(body=file_metadata, fields='id').execute()
        return folder.get('id')

def process_transcript(transcript):
    """Uses Gemini to process the transcript into a journal entry."""
    api_key = load_api_key()
    if not api_key:
        print("Error: Gemini API key not found.")
        sys.exit(1)
        
    client = genai.Client(api_key=api_key)
    
    print("Processing transcript with Gemini...")
    response = client.models.generate_content(
        model='gemini-2.0-flash',
        contents=[JOURNAL_PROMPT.format(transcript=transcript)]
    )
    
    return response.text

def upload_to_drive(content, title):
    """Uploads the journal entry to Google Drive."""
    service = get_drive_service()
    folder_id = get_gemini_folder_id(service, INBOX_ID)
    
    date_str = datetime.date.today().strftime("%Y-%m-%d")
    filename = f"{date_str} - Journal - {title}.md"
    
    from googleapiclient.http import MediaIoBaseUpload
    import io
    
    file_metadata = {
        'name': filename,
        'parents': [folder_id],
        'mimeType': 'text/markdown'
    }
    
    media = MediaIoBaseUpload(io.BytesIO(content.encode('utf-8')), mimetype='text/markdown')
    
    file = service.files().create(body=file_metadata, media_body=media, fields='id, name').execute()
    print(f"Successfully uploaded: {file.get('name')} (ID: {file.get('id')})")
    return file.get('id')

def main():
    parser = argparse.ArgumentParser(description="Process Gemini transcripts into structured journals.")
    parser.add_argument("--input", help="Path to transcript file or '-' for stdin", required=True)
    parser.add_argument("--title", help="Subject/Topic for the journal entry", default="Daily_Session")
    
    args = parser.parse_args()
    
    if args.input == '-':
        print("Reading transcript from stdin (Ctrl+D to finish)...")
        transcript = sys.stdin.read()
    else:
        with open(args.input, 'r') as f:
            transcript = f.read()
            
    if not transcript.strip():
        print("Error: Empty transcript.")
        sys.exit(1)
        
    journal_content = process_transcript(transcript)
    upload_to_drive(journal_content, args.title)

if __name__ == "__main__":
    main()
