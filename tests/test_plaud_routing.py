import json
import base64
from datetime import datetime

# Mock n8n Item
item = {
    "json": {
        "subject": "[PLAUD-AutoFlow] Meeting with Client",
        "date": "Mon, 14 Feb 2026 12:00:00 GMT",
        "snippet": "Here is the summary..."
    },
    "binary": {
        "attachment_0": {
            "fileName": "transcript.txt",
            "mimeType": "text/plain",
            "data": base64.b64encode(b"Transcript content here").decode('utf-8')
        },
        "attachment_1": {
            "fileName": "recording.mp3",
            "mimeType": "audio/mpeg",
            "data": "..."
        }
    }
}

# --- Logic Mimicking 'Route Attachments' Node ---
email = item['json']
subject = email.get('subject', 'No Subject')
date_str = email.get('date')

if date_str:
    # Parsing date (simplified for Python example, assuming format matches)
    try:
        date_obj = datetime.strptime(date_str, "%a, %d %b %Y %H:%M:%S %Z")
    except ValueError:
        date_obj = datetime.now()
else:
    date_obj = datetime.now()

formatted_date = date_obj.strftime("%Y-%m-%d %H:%M")
# Replacing forbidden chars for filename
base_filename = f"{formatted_date} {subject}".replace("/", "").replace("\\", "").replace(":", "").replace("*", "").replace("?", "").replace('"', "").replace("<", "").replace(">", "").replace("|", "")

attachments = []
transcript_text = ''

for key, file in item['binary'].items():
    is_transcript = file['mimeType'] == 'text/plain' or file['fileName'].endswith('.txt') or file['fileName'].endswith('.md')
    
    # Route to Transcripts or Plaud Root
    if is_transcript:
        target_folder_id = '1ZZf0FAoIXR6T_PzlibUEp7fQxiUbrZST' # Transcripts
    else:
        target_folder_id = '1lDD6SUh918U6oXjOBB5I9SjFVDAlqjzR' # Plaud Root

    attachments.append({
        "json": {
            "fileName": f"{base_filename} - {file['fileName']}",
            "folderId": target_folder_id
        },
        "binary": {
            "data": file
        }
    })

    if is_transcript and not transcript_text:
        transcript_text = base64.b64decode(file['data']).decode('utf-8')

result = [
    attachments,
    [{
        "json": {
            "transcriptText": transcript_text,
            "subject": subject,
            "date": formatted_date,
            "baseFilename": base_filename
        }
    }]
]

# ------------------------------------------

print("Generated Attachments:")
for a in result[0]:
    print(f"  - File: {a['json']['fileName']}")
    print(f"    Folder: {a['json']['folderId']}")

print("\nGemini Input:")
print(json.dumps(result[1][0]['json'], indent=2))
