#!/usr/bin/env python3
"""
Gmail Ingest
Fetches emails since last run (or 24h fallback) for PKM processing by Samwise.

Sources:
  - Plaud voice recordings (no-reply@plaud.ai)
  - CC meeting summaries (to:takhan+cc@gmail.com)
  - Travel: broad keyword search

Output: ~/.openclaw/workspace/inbox/YYYY-MM-DD.md
State:  toolbox/config/gmail_ingest_state.json
"""

import base64
import json
import logging
import os
import re
import sys
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path

TOOLBOX_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(TOOLBOX_ROOT.parent))

from toolbox.lib.google_api import GoogleAuth

CONFIG_DIR = TOOLBOX_ROOT / "config"
STATE_FILE = CONFIG_DIR / "gmail_ingest_state.json"
OUTPUT_DIR = Path.home() / ".openclaw" / "workspace" / "inbox"

SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.modify",
]

SEARCH_QUERIES = {
    "plaud": "from:no-reply@plaud.ai",
    "cc_summaries": "from:takhan+cc@gmail.com OR to:takhan+cc@gmail.com",
    "travel": (
        "(confirmation OR itinerary OR booking OR reservation"
        ' OR "e-ticket" OR "boarding pass" OR "check-in"'
        " OR hotel OR flight OR airline)"
    ),
}

MAX_RESULTS_PER_QUERY = 50
BODY_CAPTURE_LIMIT = 3000   # chars stored per email
BODY_RENDER_LIMIT = 1500    # chars shown in output markdown
TRANSCRIPT_RENDER_LIMIT = 2000

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("gmail_ingest")


# ---------------------------------------------------------------------------
# State
# ---------------------------------------------------------------------------

def load_state():
    if STATE_FILE.exists():
        with open(STATE_FILE) as f:
            return json.load(f)
    return {}


def save_state(state):
    tmp = str(STATE_FILE) + ".tmp"
    with open(tmp, "w") as f:
        json.dump(state, f, indent=2)
    os.rename(tmp, str(STATE_FILE))


def get_search_window(state):
    """Return epoch seconds for the Gmail `after:` filter."""
    last_run = state.get("last_run_ts")
    if last_run:
        return int(last_run)
    return int((datetime.now(timezone.utc) - timedelta(hours=24)).timestamp())


# ---------------------------------------------------------------------------
# Gmail helpers
# ---------------------------------------------------------------------------

def get_gmail_service():
    auth = GoogleAuth(base_dir=str(TOOLBOX_ROOT))
    creds = auth.get_credentials(token_filename="token.json", scopes=SCOPES)
    from googleapiclient.discovery import build
    return build("gmail", "v1", credentials=creds)


def _strip_html(data):
    html = base64.urlsafe_b64decode(data).decode("utf-8", errors="replace")
    html = re.sub(r"<style[^>]*>.*?</style>", " ", html, flags=re.DOTALL | re.IGNORECASE)
    html = re.sub(r"<script[^>]*>.*?</script>", " ", html, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"<[^>]+>", " ", html)
    return re.sub(r"\s+", " ", text).strip()


def extract_body(payload, prefer_html=False):
    """Return readable body text. Set prefer_html=True for HTML-only senders like CC."""
    collected = {}

    def _search(part):
        mime = part.get("mimeType", "")
        data = part.get("body", {}).get("data", "")

        if mime == "text/plain" and data:
            text = base64.urlsafe_b64decode(data).decode("utf-8", errors="replace").strip()
            if text and text != "...":
                collected["plain"] = text

        if mime == "text/html" and data:
            collected["html"] = _strip_html(data)

        for subpart in part.get("parts", []):
            _search(subpart)

    _search(payload)

    if prefer_html:
        return collected.get("html") or collected.get("plain") or ""
    return collected.get("plain") or collected.get("html") or ""


def extract_attachments(service, msg_id, payload):
    """Extract text attachment content (used for Plaud transcripts)."""
    attachments = []

    def _find(parts):
        for part in parts:
            filename = part.get("filename", "")
            mime = part.get("mimeType", "")
            att_id = part.get("body", {}).get("attachmentId")

            if filename and att_id:
                content = None
                if filename.lower().endswith(".txt"):
                    try:
                        att = service.users().messages().attachments().get(
                            userId="me", messageId=msg_id, id=att_id
                        ).execute()
                        content = base64.urlsafe_b64decode(att["data"]).decode(
                            "utf-8", errors="replace"
                        )
                    except Exception as e:
                        logger.warning(f"Failed to fetch attachment {filename}: {e}")

                attachments.append({"filename": filename, "mime": mime, "content": content})

            if part.get("parts"):
                _find(part["parts"])

    _find(payload.get("parts", []))
    return attachments


def fetch_message_ids(service, query, after_ts):
    full_query = f"{query} after:{after_ts}"
    results = service.users().messages().list(
        userId="me",
        q=full_query,
        maxResults=MAX_RESULTS_PER_QUERY,
        includeSpamTrash=True,
    ).execute()
    return results.get("messages", [])


def get_email_details(service, msg_id, fetch_attachments=False, **kwargs):
    message = service.users().messages().get(userId="me", id=msg_id).execute()
    payload = message["payload"]
    headers = {h["name"]: h["value"] for h in payload.get("headers", [])}

    date_str = headers.get("Date", "")
    try:
        dt = parsedate_to_datetime(date_str)
        date_formatted = dt.strftime("%Y-%m-%d %H:%M")
    except Exception:
        date_formatted = date_str

    prefer_html = kwargs.get("prefer_html", False)
    body = extract_body(payload, prefer_html=prefer_html)

    result = {
        "id": msg_id,
        "subject": headers.get("Subject", "(no subject)"),
        "from": headers.get("From", ""),
        "to": headers.get("To", ""),
        "date": date_formatted,
        "body": body[:BODY_CAPTURE_LIMIT],
        "labels": message.get("labelIds", []),
    }

    if fetch_attachments:
        result["attachments"] = extract_attachments(service, msg_id, payload)

    return result


# ---------------------------------------------------------------------------
# Markdown output
# ---------------------------------------------------------------------------

CATEGORY_TITLES = {
    "plaud": "## Plaud Voice Recordings",
    "cc_summaries": "## CC Meeting Summaries",
    "travel": "## Travel",
}


def label_note(labels):
    if "TRASH" in labels:
        return " *(deleted)*"
    if "SENT" in labels and "INBOX" not in labels:
        return " *(sent)*"
    return ""


def render_markdown(date_str, emails_by_category):
    lines = [
        f"# Gmail Ingest — {date_str}",
        f"_Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}_",
        "",
    ]

    for category, emails in emails_by_category.items():
        lines.append(CATEGORY_TITLES.get(category, f"## {category}"))
        lines.append("")

        if not emails:
            lines.append("_None_")
            lines.append("")
            continue

        for email in emails:
            note = label_note(email.get("labels", []))
            lines.append(f"### {email['subject']}{note}")
            lines.append(f"- **From:** {email['from']}")
            lines.append(f"- **Date:** {email['date']}")
            lines.append("")

            if category == "plaud":
                atts = email.get("attachments", [])
                transcript = next(
                    (a for a in atts if a.get("content") and "transcript" in a["filename"].lower()),
                    None,
                )
                if transcript:
                    content = transcript["content"]
                    lines.append(f"**{transcript['filename']}:**")
                    lines.append("")
                    lines.append("```")
                    lines.append(content[:TRANSCRIPT_RENDER_LIMIT])
                    if len(content) > TRANSCRIPT_RENDER_LIMIT:
                        lines.append(f"... [{len(content) - TRANSCRIPT_RENDER_LIMIT} chars truncated]")
                    lines.append("```")
                    lines.append("")
                elif email.get("body"):
                    lines.append(email["body"][:BODY_RENDER_LIMIT])
                    lines.append("")
            else:
                body = email.get("body", "")
                if body:
                    lines.append(body[:BODY_RENDER_LIMIT])
                    if len(body) > BODY_RENDER_LIMIT:
                        lines.append(f"\n_[{len(body) - BODY_RENDER_LIMIT} chars truncated]_")
                    lines.append("")

            lines.append("---")
            lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    logger.info("Starting Gmail ingest")

    state = load_state()
    after_ts = get_search_window(state)
    after_dt = datetime.fromtimestamp(after_ts, tz=timezone.utc)
    logger.info(f"Search window: since {after_dt.strftime('%Y-%m-%d %H:%M UTC')}")

    service = get_gmail_service()

    emails_by_category = {}
    for category, query in SEARCH_QUERIES.items():
        logger.info(f"Fetching: {category}")
        messages = fetch_message_ids(service, query, after_ts)
        logger.info(f"  {len(messages)} message(s)")

        emails = []
        for msg in messages:
            try:
                email = get_email_details(
                    service, msg["id"],
                    fetch_attachments=(category == "plaud"),
                    prefer_html=(category == "cc_summaries"),
                )
                emails.append(email)
            except Exception as e:
                logger.warning(f"  Skipped {msg['id']}: {e}")

        emails_by_category[category] = emails

    # Write output
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    today = datetime.now().strftime("%Y-%m-%d")
    output_file = OUTPUT_DIR / f"{today}.md"

    content = render_markdown(today, emails_by_category)
    tmp_file = str(output_file) + ".tmp"
    with open(tmp_file, "w") as f:
        f.write(content)
    os.rename(tmp_file, str(output_file))

    # Update state
    state["last_run_ts"] = int(datetime.now(timezone.utc).timestamp())
    state["last_run_date"] = datetime.now().strftime("%Y-%m-%d %H:%M")
    save_state(state)

    # Summary (stdout for Samwise to read)
    total = sum(len(v) for v in emails_by_category.values())
    print(f"\n=== INGEST SUMMARY ===")
    for category, emails in emails_by_category.items():
        print(f"  {category}: {len(emails)} email(s)")
    print(f"  output: {output_file}")
    print(f"  window: since {after_dt.strftime('%Y-%m-%d %H:%M UTC')}")
    print(f"======================")

    return output_file


if __name__ == "__main__":
    main()
