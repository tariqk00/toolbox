"""
Telegram notification helper.
Sends messages to a configured chat (channel or group) via the Bot API.
Config: config/telegram_config.json (gitignored)
"""
import json
import logging
import os
import re
import time
import urllib.request
import urllib.error
from pathlib import Path

logger = logging.getLogger("DriveSorter.Telegram")

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

MONIT_URL = 'http://172.30.0.169:2812'


def monit_link(label: str = 'Monit') -> str:
    return f'<a href="{MONIT_URL}">{escape(label)}</a>'


def drive_file_link(file_id: str, label: str) -> str:
    url = f'https://drive.google.com/file/d/{file_id}'
    return f'<a href="{url}">{escape(label)}</a>'


def drive_folder_link(folder_id: str, label: str) -> str:
    url = f'https://drive.google.com/drive/folders/{folder_id}'
    return f'<a href="{url}">{escape(label)}</a>'


def escape(text: str) -> str:
    """Escape text for Telegram HTML parse_mode."""
    return str(text).replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')


CONFIG_PATH = os.path.join(BASE_DIR, 'config', 'telegram_config.json')
DEDUP_WINDOW_SECONDS = 30 * 60

_config_cache = None

def _load_config():
    global _config_cache
    if _config_cache is not None:
        return _config_cache
    try:
        with open(CONFIG_PATH) as f:
            _config_cache = json.load(f)
        return _config_cache
    except FileNotFoundError:
        logger.warning(f"Telegram config not found at {CONFIG_PATH}. Notifications disabled.")
        return None
    except Exception as e:
        logger.error(f"Failed to load Telegram config: {e}")
        return None


def _dedup_state_path() -> Path:
    override = os.getenv('TELEGRAM_DEDUP_STATE')
    if override:
        return Path(override)
    return Path.home() / '.cache' / 'toolbox' / 'telegram_dedup.json'


def _normalise_for_dedup(text: str) -> str:
    text = re.sub(r'\d{4}-\d{2}-\d{2}[T ][0-9:.,+-]+', '<timestamp>', text)
    text = re.sub(r'\bpid\s*\d+\b', 'pid <n>', text, flags=re.IGNORECASE)
    text = re.sub(r'\[[0-9]{3,}\]', '[pid]', text)
    text = re.sub(r'\b[0-9a-f]{8,}\b', '<id>', text, flags=re.IGNORECASE)
    text = re.sub(r'\s+', ' ', text)
    return text.strip().lower()


def _dedup_key(text: str, service: str | None) -> str:
    import hashlib
    payload = f'{service or ""}|{_normalise_for_dedup(text)}'
    return hashlib.sha1(payload.encode()).hexdigest()


def _load_dedup_state(path: Path) -> dict:
    try:
        return json.loads(path.read_text())
    except Exception:
        return {}


def _save_dedup_state(path: Path, state: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + '.tmp')
    tmp.write_text(json.dumps(state, indent=2, sort_keys=True))
    tmp.replace(path)


def _should_send(text: str, service: str | None, window_seconds: int | None = None) -> bool:
    if os.getenv('TELEGRAM_DEDUP', '').lower() == 'off':
        return True
    if window_seconds is None:
        window_seconds = int(os.getenv('TELEGRAM_DEDUP_WINDOW_SECONDS', DEDUP_WINDOW_SECONDS))
    if window_seconds <= 0:
        return True

    now = time.time()
    path = _dedup_state_path()
    state = _load_dedup_state(path)
    key = _dedup_key(text, service)
    last_seen = float(state.get(key, 0) or 0)
    if last_seen and now - last_seen < window_seconds:
        logger.info("Suppressing duplicate Telegram alert for service=%s", service or "default")
        return False

    cutoff = now - (window_seconds * 4)
    state = {k: v for k, v in state.items() if float(v or 0) >= cutoff}
    state[key] = now
    try:
        _save_dedup_state(path, state)
    except Exception as e:
        logger.warning("Telegram dedup state update failed: %s", e)
    return True


def send_message(text: str, service: str = None, parse_mode: str = 'HTML') -> bool:
    """
    Send a message to the configured ops channel.
    If service is provided, prepends "[service] " to the message.
    Returns True on success, False on failure (never raises).
    """
    config = _load_config()
    if not config:
        return False

    bot_token = config.get('bot_token')
    chat_id = config.get('chat_id')
    if not bot_token or not chat_id:
        logger.error("Telegram config missing bot_token or chat_id.")
        return False

    if service:
        text = f"[{service}] {text}"

    if not _should_send(text, service):
        return True

    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    payload = {"chat_id": chat_id, "text": text}
    if parse_mode:
        payload["parse_mode"] = parse_mode

    try:
        data = json.dumps(payload).encode()
        req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            result = json.loads(resp.read())
            if not result.get("ok"):
                logger.error(f"Telegram API error: {result}")
                return False
        return True
    except urllib.error.HTTPError as e:
        logger.error(f"Telegram HTTP error {e.code}: {e.read().decode()}")
        return False
    except Exception as e:
        logger.error(f"Telegram send failed: {e}")
        return False
