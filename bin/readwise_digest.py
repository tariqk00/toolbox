"""
Readwise Daily Digest — fetches top unread articles, summarizes via Gemini, sends to Telegram.

- Fetches all unread articles from Readwise Reader (location=later, category=article)
- Excludes articles already surfaced in recent runs (dedup via state file)
- Picks top 3 newest unsurfaced; fills from oldest surfaced if needed
- Summarizes each via Gemini (free→paid fallback)
- Sends to Telegram with title, author, summary, and link
- Prunes surfaced IDs older than 30 days from state
"""
import json
import logging
import os
import random
import sys
import urllib.request
import urllib.error
from datetime import date, timedelta

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)
if os.path.dirname(BASE_DIR) not in sys.path:
    sys.path.insert(0, os.path.dirname(BASE_DIR))

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(name)s %(message)s')
logger = logging.getLogger('ReadwiseDigest')

from toolbox.lib.gemini import call_gemini
from toolbox.lib.telegram import send_message, escape

KEY_PATH = os.path.join(BASE_DIR, 'config', 'readwise_api_secret')
STATE_PATH = os.path.join(BASE_DIR, 'config', 'readwise_digest_state.json')

READWISE_API = 'https://readwise.io/api/v3/list/'
TOP_N = 3
PRUNE_DAYS = 30

SUMMARY_PROMPT = """\
Summarize this article in exactly 2 sentences. Be specific about what the article covers and why it matters.

Title: {title}
Author: {author}
Existing summary: {summary}
URL: {url}

Return only the 2-sentence summary, no preamble."""


def _load_key() -> str:
    try:
        return open(KEY_PATH).read().strip()
    except FileNotFoundError:
        logger.error(f'Readwise API key not found at {KEY_PATH}')
        sys.exit(1)


def _load_state() -> dict:
    try:
        with open(STATE_PATH) as f:
            return json.load(f)
    except Exception:
        return {}


def _save_state(state: dict) -> None:
    tmp = STATE_PATH + '.tmp'
    with open(tmp, 'w') as f:
        json.dump(state, f, indent=2)
    os.replace(tmp, STATE_PATH)


def _prune_state(state: dict) -> dict:
    cutoff = (date.today() - timedelta(days=PRUNE_DAYS)).isoformat()
    surfaced = state.get('surfaced', {})
    state['surfaced'] = {k: v for k, v in surfaced.items() if v >= cutoff}
    return state


def _fetch_articles(key: str) -> list[dict]:
    """Fetch all unread articles from Readwise Reader, handling pagination."""
    articles = []
    cursor = None
    headers = {'Authorization': f'Token {key}'}

    while True:
        params = 'location=later&category=article'
        if cursor:
            params += f'&pageCursor={cursor}'
        url = f'{READWISE_API}?{params}'

        req = urllib.request.Request(url, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                data = json.loads(resp.read())
        except urllib.error.HTTPError as e:
            logger.error(f'Readwise API error {e.code}: {e.reason}')
            break
        except Exception as e:
            logger.error(f'Readwise fetch failed: {e}')
            break

        for item in data.get('results', []):
            if (item.get('reading_progress') or 0) == 0:
                articles.append(item)

        cursor = data.get('nextPageCursor')
        if not cursor:
            break

    logger.info(f'Fetched {len(articles)} unread articles from Readwise')
    return articles


def _select_articles(articles: list[dict], surfaced: dict) -> list[dict]:
    """
    Pick TOP_N articles: 1 newest unsurfaced + 2 random from the rest.
    Falls back to oldest surfaced articles if not enough fresh ones.
    """
    unsurfaced = [a for a in articles if str(a['id']) not in surfaced]
    already_surfaced = [a for a in articles if str(a['id']) in surfaced]

    unsurfaced.sort(key=lambda a: a.get('saved_at', ''), reverse=True)
    already_surfaced.sort(key=lambda a: surfaced.get(str(a['id']), ''))

    selected = []
    if unsurfaced:
        selected.append(unsurfaced[0])  # 1 newest
        pool = unsurfaced[1:]
        remaining = TOP_N - 1
        if len(pool) >= remaining:
            selected += random.sample(pool, remaining)
        else:
            selected += pool

    if len(selected) < TOP_N:
        selected += already_surfaced[:TOP_N - len(selected)]

    return selected


def _summarize(article: dict) -> str:
    """Get a 2-sentence Gemini summary, falling back to existing summary."""
    existing = article.get('summary') or ''
    prompt = SUMMARY_PROMPT.format(
        title=article.get('title', 'Unknown'),
        author=article.get('author') or 'Unknown',
        summary=existing[:500] if existing else 'None provided',
        url=article.get('url', ''),
    )
    result = call_gemini(prompt)
    return result if result else (existing[:200] if existing else 'No summary available.')


def _format_message(articles: list[dict], summaries: list[str]) -> str:
    lines = ['<b>Reading Digest</b>\n']
    for i, (article, summary) in enumerate(zip(articles, summaries), 1):
        title = escape(article.get('title') or 'Untitled')
        author = escape(article.get('author') or 'Unknown')
        url = article.get('url', '')
        if url:
            lines.append(f'{i}. <a href="{url}">{title}</a>')
        else:
            lines.append(f'{i}. <b>{title}</b>')
        lines.append(f'   <i>by {author}</i>')
        lines.append(f'   {escape(summary)}')
        lines.append('')
    return '\n'.join(lines).strip()


def run():
    key = _load_key()
    state = _load_state()
    state = _prune_state(state)
    surfaced = state.get('surfaced', {})

    articles = _fetch_articles(key)
    if not articles:
        logger.info('No unread articles in Readwise.')
        return

    selected = _select_articles(articles, surfaced)
    if not selected:
        logger.info('Nothing to surface today.')
        return

    summaries = []
    for article in selected:
        summary = _summarize(article)
        summaries.append(summary)
        logger.info(f'Summarized: {article.get("title", "?")[:60]}')

    msg = _format_message(selected, summaries)
    send_message(msg, service='readwise-digest')

    # Record surfaced IDs
    today = date.today().isoformat()
    for article in selected:
        surfaced[str(article['id'])] = today
    state['surfaced'] = surfaced
    
    # Export for life-docs daily_reporter
    digest_export = {
        "date": today,
        "articles": [
            {
                "title": a.get("title", "Untitled"),
                "author": a.get("author", "Unknown"),
                "url": a.get("url", ""),
                "summary": s
            }
            for a, s in zip(selected, summaries)
        ]
    }
    digest_path = os.path.join(BASE_DIR, 'config', 'readwise_last_digest.json')
    try:
        with open(digest_path, 'w') as f:
            json.dump(digest_export, f, indent=2)
    except Exception as e:
        logger.error(f"Failed to write readwise_last_digest.json: {e}")

    _save_state(state)
    logger.info(f'Done. Surfaced {len(selected)} articles.')


if __name__ == '__main__':
    run()
