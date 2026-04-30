import json
import logging
from pathlib import Path

from toolbox.lib import log_manager


def _reset_manager(app_name: str):
    instance = log_manager.LogManager._instances.pop(app_name, None)
    logger = logging.getLogger(f"toolbox.{app_name}")
    for handler in list(logger.handlers):
        handler.close()
        logger.removeHandler(handler)
    return instance


def test_log_event_writes_structured_jsonl(tmp_path):
    app_name = "test-jsonl"
    _reset_manager(app_name)
    manager = log_manager.LogManager.get_instance(app_name, log_dir=str(tmp_path))
    manager.set_correlation_id("cid-123")

    manager.log_event("RUN_COMPLETE", "SUCCESS", "Sorter finished", {"processed": 3})

    line = (tmp_path / "activity.jsonl").read_text().strip().splitlines()[-1]
    payload = json.loads(line)
    assert payload["app"] == app_name
    assert payload["event"] == "RUN_COMPLETE"
    assert payload["status"] == "SUCCESS"
    assert payload["message"] == "Sorter finished"
    assert payload["data"]["processed"] == 3
    assert payload["correlation_id"] == "cid-123"


def test_plain_logger_message_is_wrapped_as_json(tmp_path):
    app_name = "test-plain"
    _reset_manager(app_name)
    manager = log_manager.LogManager.get_instance(app_name, log_dir=str(tmp_path))

    manager.logger.info("plain message")

    line = (tmp_path / "activity.jsonl").read_text().strip().splitlines()[-1]
    payload = json.loads(line)
    assert payload["app"] == app_name
    assert payload["message"] == "plain message"
    assert "event" not in payload


def test_log_helper_accepts_non_json_native_data(tmp_path):
    app_name = "test-helper"
    _reset_manager(app_name)

    log_manager.log(
        "TOKEN_MONITOR",
        "SUCCESS",
        "Refreshed tokens",
        data={"path": Path("/tmp/token.json")},
        app_name=app_name,
        log_dir=str(tmp_path),
    )

    line = (tmp_path / "activity.jsonl").read_text().strip().splitlines()[-1]
    payload = json.loads(line)
    assert payload["event"] == "TOKEN_MONITOR"
    assert payload["data"]["path"] == "/tmp/token.json"
