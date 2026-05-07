import json
from unittest.mock import MagicMock


class _FakeResponse:
    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self):
        return b'{"ok": true}'


def _configure(monkeypatch, tmp_path):
    from toolbox.lib import telegram
    telegram._config_cache = {'bot_token': 'token', 'chat_id': 'chat'}
    monkeypatch.setenv('TELEGRAM_DEDUP_STATE', str(tmp_path / 'dedup.json'))
    monkeypatch.setenv('TELEGRAM_DEDUP_WINDOW_SECONDS', '1800')
    monkeypatch.delenv('TELEGRAM_DEDUP', raising=False)
    return telegram


def test_send_message_suppresses_duplicate_alert(monkeypatch, tmp_path):
    telegram = _configure(monkeypatch, tmp_path)
    sent = MagicMock(return_value=_FakeResponse())
    monkeypatch.setattr(telegram.urllib.request, 'urlopen', sent)

    text = '<b>service failed</b>\nRuntimeError: same root cause'

    assert telegram.send_message(text, service='ai-sorter', category='notification')
    assert telegram.send_message(text, service='ai-sorter', category='notification')

    assert sent.call_count == 1
    state = json.loads((tmp_path / 'dedup.json').read_text())
    assert len(state) == 1


def test_send_message_normalizes_timestamps_for_dedup(monkeypatch, tmp_path):
    telegram = _configure(monkeypatch, tmp_path)
    sent = MagicMock(return_value=_FakeResponse())
    monkeypatch.setattr(telegram.urllib.request, 'urlopen', sent)

    assert telegram.send_message('failed at 2026-04-25T01:00:00 pid 1234', service='build', category='notification')
    assert telegram.send_message('failed at 2026-04-25T01:05:00 pid 5678', service='build', category='notification')

    assert sent.call_count == 1


def test_send_message_allows_duplicate_after_window(monkeypatch, tmp_path):
    telegram = _configure(monkeypatch, tmp_path)
    sent = MagicMock(return_value=_FakeResponse())
    monkeypatch.setattr(telegram.urllib.request, 'urlopen', sent)

    now = [1000.0]
    monkeypatch.setattr(telegram.time, 'time', lambda: now[0])

    assert telegram.send_message('same failure', service='svc', category='notification')
    now[0] += 1801
    assert telegram.send_message('same failure', service='svc', category='notification')

    assert sent.call_count == 2


def test_dedup_can_be_disabled(monkeypatch, tmp_path):
    telegram = _configure(monkeypatch, tmp_path)
    monkeypatch.setenv('TELEGRAM_DEDUP', 'off')
    sent = MagicMock(return_value=_FakeResponse())
    monkeypatch.setattr(telegram.urllib.request, 'urlopen', sent)

    assert telegram.send_message('same failure', service='svc', category='notification')
    assert telegram.send_message('same failure', service='svc', category='notification')

    assert sent.call_count == 2


def test_send_message_routes_errors_to_error_chat(monkeypatch, tmp_path):
    telegram = _configure(monkeypatch, tmp_path)
    telegram._config_cache = {
        'bot_token': 'default-token',
        'chat_id': 'default-chat',
        'chat_id_errors': 'errors-chat',
    }
    sent = MagicMock(return_value=_FakeResponse())
    monkeypatch.setattr(telegram.urllib.request, 'urlopen', sent)

    assert telegram.send_message('disk full', service='svc', category='error')

    req = sent.call_args.args[0]
    payload = json.loads(req.data.decode())
    assert payload['chat_id'] == 'errors-chat'


def test_send_message_defaults_unknown_category_to_default_chat(monkeypatch, tmp_path):
    telegram = _configure(monkeypatch, tmp_path)
    telegram._config_cache = {
        'bot_token': 'default-token',
        'chat_id': 'default-chat',
        'chat_id_errors': 'errors-chat',
    }
    sent = MagicMock(return_value=_FakeResponse())
    monkeypatch.setattr(telegram.urllib.request, 'urlopen', sent)

    assert telegram.send_message('hello', service='svc', category='custom')

    req = sent.call_args.args[0]
    payload = json.loads(req.data.decode())
    assert payload['chat_id'] == 'default-chat'
