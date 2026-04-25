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

    assert telegram.send_message(text, service='ai-sorter')
    assert telegram.send_message(text, service='ai-sorter')

    assert sent.call_count == 1
    state = json.loads((tmp_path / 'dedup.json').read_text())
    assert len(state) == 1


def test_send_message_normalizes_timestamps_for_dedup(monkeypatch, tmp_path):
    telegram = _configure(monkeypatch, tmp_path)
    sent = MagicMock(return_value=_FakeResponse())
    monkeypatch.setattr(telegram.urllib.request, 'urlopen', sent)

    assert telegram.send_message('failed at 2026-04-25T01:00:00 pid 1234', service='build')
    assert telegram.send_message('failed at 2026-04-25T01:05:00 pid 5678', service='build')

    assert sent.call_count == 1


def test_send_message_allows_duplicate_after_window(monkeypatch, tmp_path):
    telegram = _configure(monkeypatch, tmp_path)
    sent = MagicMock(return_value=_FakeResponse())
    monkeypatch.setattr(telegram.urllib.request, 'urlopen', sent)

    now = [1000.0]
    monkeypatch.setattr(telegram.time, 'time', lambda: now[0])

    assert telegram.send_message('same failure', service='svc')
    now[0] += 1801
    assert telegram.send_message('same failure', service='svc')

    assert sent.call_count == 2


def test_dedup_can_be_disabled(monkeypatch, tmp_path):
    telegram = _configure(monkeypatch, tmp_path)
    monkeypatch.setenv('TELEGRAM_DEDUP', 'off')
    sent = MagicMock(return_value=_FakeResponse())
    monkeypatch.setattr(telegram.urllib.request, 'urlopen', sent)

    assert telegram.send_message('same failure', service='svc')
    assert telegram.send_message('same failure', service='svc')

    assert sent.call_count == 2
