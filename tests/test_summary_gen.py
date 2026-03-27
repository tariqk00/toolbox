import base64
import json

# Mock Data simulating n8n state
# This mimics what the 'Create Summary File' node sees
mock_gemini_output = "Here is a summary of the meeting..."

# Mocking the upstream node data that n8n specific syntax $('...').item.json would retrieve
mock_upstream_metadata = {
    "subject": "[PLAUD-AutoFlow] Project Sync",
    "date": "2026-02-14 14:00",
    "baseFilename": "2026-02-14 1400 Project Sync"
}

# --- Code from 'Create Summary File' Node ---
text = mock_gemini_output

# In n8n, these would come from $('Route Attachments').item.json
subject = mock_upstream_metadata['subject']
date = mock_upstream_metadata['date']
base_filename = mock_upstream_metadata['baseFilename']

content = f"# {subject}\n**Date:** {date}\n**From:** PLAUD.AI\n\n---\n\n{text}"

# Node.js Buffer.from(content).toString('base64') -> Python equivalent
binary_data = base64.b64encode(content.encode('utf-8')).decode('utf-8')

result = [
  {
    "json": {
       "fileName": f"{base_filename} - AI Summary.md"
    },
    "binary": {
      "data": {
        "data": binary_data,
        "mimeType": "text/markdown",
        "fileName": "report.md"
      }
    }
  }
]
# ------------------------------------------

print("Generated Summary File Item:")
print(json.dumps(result[0]['json'], indent=2))

print("\nFile Content (Decoded):")
print(base64.b64decode(result[0]['binary']['data']['data']).decode('utf-8'))
