"""
Telegram notification helper.
Sends messages to a configured chat (channel or group) via the Bot API.
Config: config/telegram_config.json (gitignored)
"""
import json
import logging
import os
import urllib.request
import urllib.error

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
