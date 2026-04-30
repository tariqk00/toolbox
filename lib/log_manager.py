import os
import json
import logging
from logging.handlers import RotatingFileHandler
import threading
from datetime import datetime, timezone
import uuid


def _utc_now_iso():
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _json_dumps(payload):
    return json.dumps(payload, default=str)


class JsonlFormatter(logging.Formatter):
    """Custom formatter to output log records as JSONL."""
    def format(self, record):
        app_name = getattr(record, 'app_name', None)
        if not app_name:
            app_name = record.name.split("toolbox.", 1)[-1] if record.name.startswith("toolbox.") else record.name
        entry = {
            "timestamp": _utc_now_iso(),
            "app": app_name or 'toolbox',
            "level": record.levelname,
            "module": record.module,
            "message": record.getMessage(),
        }
        if hasattr(record, 'event_type'):
            entry["event"] = record.event_type
        if hasattr(record, 'status'):
            entry["status"] = record.status
        if hasattr(record, 'correlation_id') and record.correlation_id:
            entry["correlation_id"] = record.correlation_id
        if hasattr(record, 'extra_data') and record.extra_data is not None:
            entry["data"] = record.extra_data
        if record.exc_info:
            entry["exception"] = self.formatException(record.exc_info)

        return _json_dumps(entry)

class LogManager:
    """
    Unified Logging System for the Toolbox.
    - Writes structured JSONL logs to a local file.
    - Supports rotation.
    - Thread-safe and Multi-instance.
    """
    _instances = {}
    _lock = threading.Lock()

    def __init__(self, app_name="toolbox", log_dir=None):
        if hasattr(self, 'initialized'):
            return
            
        self.app_name = app_name
        self.correlation_id = None
        
        # Determine Log Directory
        self.log_dir = log_dir or self.default_log_dir()

        if not os.path.exists(self.log_dir):
            os.makedirs(self.log_dir, exist_ok=True)

        self.log_file = os.path.join(self.log_dir, "activity.jsonl")
        
        # internal python logger setup
        self.logger = logging.getLogger(f"toolbox.{app_name}")
        self.logger.setLevel(logging.INFO)
        self.logger.propagate = False # Prevent double logging if root logger is configured
        
        # Avoid adding handlers multiple times
        if not self.logger.handlers:
            # Console Handler (Human readable)
            ch = logging.StreamHandler()
            ch.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
            self.logger.addHandler(ch)
            
            # File Handler (JSONL)
            self.file_handler = RotatingFileHandler(
                self.log_file, maxBytes=10*1024*1024, backupCount=7
            )
            self.file_handler.setFormatter(JsonlFormatter())
            self.logger.addHandler(self.file_handler)

        self.initialized = True

    @staticmethod
    def default_log_dir():
        if os.path.exists("/opt/tariqk00"):
            return "/opt/tariqk00/logs"
        home = os.path.expanduser("~")
        return os.path.join(home, ".local", "state", "tariqk", "logs")

    @classmethod
    def get_instance(cls, app_name="toolbox", log_dir=None):
        with cls._lock:
            if app_name not in cls._instances:
                cls._instances[app_name] = cls(app_name, log_dir=log_dir)
            return cls._instances[app_name]

    def set_correlation_id(self, cid=None):
        self.correlation_id = cid or str(uuid.uuid4())
        return self.correlation_id

    def build_entry(self, event_type, status, message, data=None, level="INFO"):
        return {
            "timestamp": _utc_now_iso(),
            "app": self.app_name,
            "level": level,
            "event": event_type,
            "status": status,
            "message": message,
            "data": data or {},
            "correlation_id": self.correlation_id,
        }

    def log_event(self, event_type, status, message, data=None, level="INFO"):
        """
        Log a structured event specifically for JSONL consumption.
        """
        entry = self.build_entry(event_type, status, message, data=data, level=level)
        log_method = getattr(self.logger, level.lower(), self.logger.info)
        log_method(
            message,
            extra={
                "app_name": self.app_name,
                "event_type": event_type,
                "status": status,
                "extra_data": entry["data"],
                "correlation_id": entry["correlation_id"],
            },
        )

# Usage Helper
def log(event_type, status, message, data=None, level="INFO", app_name="toolbox", log_dir=None):
    manager = LogManager.get_instance(app_name, log_dir=log_dir)
    manager.log_event(event_type, status, message, data, level)
