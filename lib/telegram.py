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
from dotenv import load_dotenv

logger = logging.getLogger("DriveSorter.Telegram")

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_DIR = os.path.join(BASE_DIR, 'config')

# Load centralized secrets
load_dotenv(os.path.join(CONFIG_DIR, 'secrets.env'))

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


CONFIG_PATH = os.path.join(CONFIG_DIR, 'telegram_config.json')
DEDUP_WINDOW_SECONDS = 30 * 60

_config_cache = None

_ERROR_CATEGORIES = {'error', 'critical', 'warning'}
_NOTIFICATION_CATEGORIES = {'notification', 'info', 'success'}

def _load_config():
    global _config_cache
    if _config_cache is not None:
        return _config_cache

    # Try environment first (secrets.env)
    env_keys = [
        'TELEGRAM_BOT_TOKEN',
        'TELEGRAM_CHAT_ID',
        'TELEGRAM_BOT_TOKEN_ERRORS',
        'TELEGRAM_CHAT_ID_ERRORS',
        'TELEGRAM_BOT_TOKEN_NOTIFICATIONS',
        'TELEGRAM_CHAT_ID_NOTIFICATIONS',
        'TELEGRAM_BOT_TOKEN_ALERTS',
        'TELEGRAM_CHAT_ID_ALERTS',
        'TELEGRAM_BOT_TOKEN_SERVICES',
        'TELEGRAM_CHAT_ID_SERVICES',
    ]
    env_config = {key.lower(): os.getenv(key) for key in env_keys if os.getenv(key)}
    if env_config:
        config = {}
        if env_config.get('telegram_bot_token'):
            config['bot_token'] = env_config['telegram_bot_token']
        if env_config.get('telegram_chat_id'):
            config['chat_id'] = env_config['telegram_chat_id']
        if env_config.get('telegram_bot_token_errors'):
            config['bot_token_errors'] = env_config['telegram_bot_token_errors']
        if env_config.get('telegram_chat_id_errors'):
            config['chat_id_errors'] = env_config['telegram_chat_id_errors']
        if env_config.get('telegram_bot_token_notifications'):
            config['bot_token_notifications'] = env_config['telegram_bot_token_notifications']
        if env_config.get('telegram_chat_id_notifications'):
            config['chat_id_notifications'] = env_config['telegram_chat_id_notifications']
        if env_config.get('telegram_bot_token_alerts'):
            config['bot_token_alerts'] = env_config['telegram_bot_token_alerts']
        if env_config.get('telegram_chat_id_alerts'):
            config['chat_id_alerts'] = env_config['telegram_chat_id_alerts']
        if env_config.get('telegram_bot_token_services'):
            config['bot_token_services'] = env_config['telegram_bot_token_services']
        if env_config.get('telegram_chat_id_services'):
            config['chat_id_services'] = env_config['telegram_chat_id_services']
        _config_cache = config
        return _config_cache

    try:
        if os.path.exists(CONFIG_PATH):
            with open(CONFIG_PATH) as f:
                _config_cache = json.load(f)
            return _config_cache
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


def _dedup_key(text: str, service: str | None, category: str | None) -> str:
    import hashlib
    payload = f'{service or ""}|{_route_bucket(category)}|{_normalise_for_dedup(text)}'
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


def _should_send(
    text: str,
    service: str | None,
    category: str | None,
    window_seconds: int | None = None,
) -> bool:
    if os.getenv('TELEGRAM_DEDUP', '').lower() == 'off':
        return True
    if window_seconds is None:
        window_seconds = int(os.getenv('TELEGRAM_DEDUP_WINDOW_SECONDS', DEDUP_WINDOW_SECONDS))
    if window_seconds <= 0:
        return True

    now = time.time()
    path = _dedup_state_path()
    state = _load_dedup_state(path)
    key = _dedup_key(text, service, category)
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


def _route_bucket(category: str | None) -> str:
    normalized = (category or 'notification').strip().lower()
    if normalized in _ERROR_CATEGORIES:
        return 'errors'
    if normalized in _NOTIFICATION_CATEGORIES:
        return 'notifications'
    return normalized


def _resolve_destination(config: dict, category: str | None) -> tuple[str | None, str | None]:
    bucket = _route_bucket(category)
    token = config.get(f'bot_token_{bucket}')
    chat_id = config.get(f'chat_id_{bucket}')

    if bucket == 'errors':
        token = token or config.get('bot_token_alerts')
        chat_id = chat_id or config.get('chat_id_alerts')
    elif bucket == 'notifications':
        token = token or config.get('bot_token_services')
        chat_id = chat_id or config.get('chat_id_services')

    return token or config.get('bot_token'), chat_id or config.get('chat_id')


# Invisible Tag Markers (Zero-Width Characters)
# Start/End: U+200B (ZWSP)
# Data 0: U+200C (ZWNJ)
# Data 1: U+200D (ZWJ)
ZWSP = "\u200b"
ZWNJ = "\u200c"
ZWJ  = "\u200d"


def _encode_origin(origin: str) -> str:
    """Encode origin name into a sequence of invisible characters."""
    binary = "".join(format(ord(c), '08b') for c in origin)
    encoded = "".join(ZWNJ if b == '0' else ZWJ for b in binary)
    return f"{ZWSP}{encoded}{ZWSP}"


def _decode_origin(text: str) -> str | None:
    """Extract and decode origin name from invisible characters."""
    match = re.search(f"{ZWSP}([{ZWNJ}{ZWJ}]+){ZWSP}", text)
    if not match:
        return None
    encoded = match.group(1)
    try:
        binary_chunks = [encoded[i:i+8] for i in range(0, len(encoded), 8)]
        chars = [chr(int("".join('0' if b == ZWNJ else '1' for b in chunk), 2)) for chunk in binary_chunks]
        return "".join(chars)
    except Exception:
        return None


def send_message(text: str, service: str = None, parse_mode: str = 'HTML', category: str = 'notification', origin: str = None) -> bool:
    """
    Send a message to the configured Telegram channel for the given category.
    If service is provided, prepends "[service] " to the message.
    If origin is provided, appends hidden metadata for automation tracking.
    Returns True on success, False on failure (never raises).
    """
    config = _load_config()
    if not config:
        return False

    bot_token, chat_id = _resolve_destination(config, category)
    if not bot_token or not chat_id:
        logger.error("Telegram config missing bot_token or chat_id for category=%s.", category)
        return False

    if service:
        text = f"[{service}] {text}"

    # Origin tagging (hidden metadata via zero-width characters)
    tag_origin = origin or service or "toolbox"
    text = f"{text}{_encode_origin(tag_origin)}"

    if not _should_send(text, service, category):
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


def is_automation_generated(text: str) -> str | None:
    """
    Returns the origin name if the text contains an automation tag, else None.
    Uses hidden zero-width character decoding.
    """
    return _decode_origin(text)
