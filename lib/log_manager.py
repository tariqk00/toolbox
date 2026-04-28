
import os
import json
import logging
from logging.handlers import RotatingFileHandler
import threading
from datetime import datetime
import uuid

class JsonlFormatter(logging.Formatter):
    """Custom formatter to output log records as JSONL."""
    def format(self, record):
        # If the message is already a JSON string (from log_event), use it
        try:
            if isinstance(record.msg, str) and record.msg.startswith('{') and record.msg.endswith('}'):
                # Try to parse to verify it's JSON
                json.loads(record.msg)
                return record.msg
        except:
            pass
            
        # Otherwise, wrap the standard log record in a JSON structure
        entry = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "app": getattr(record, 'app_name', 'toolbox'),
            "level": record.levelname,
            "module": record.module,
            "message": record.getMessage(),
        }
        
        # Add correlation ID if present
        correlation_id = getattr(record, 'correlation_id', None)
        if correlation_id:
            entry["correlation_id"] = correlation_id
            
        # Add extra data if present
        if hasattr(record, 'extra_data'):
            entry["data"] = record.extra_data
            
        return json.dumps(entry)

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
        if log_dir:
            self.log_dir = log_dir
        else:
            # Default to /opt/tariqk00/logs on NUC, or ~/.local/state/tariqk/logs on Dev
            if os.path.exists("/opt/tariqk00"):
                self.log_dir = "/opt/tariqk00/logs"
            else:
                home = os.path.expanduser("~")
                self.log_dir = os.path.join(home, ".local", "state", "tariqk", "logs")

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

    @classmethod
    def get_instance(cls, app_name="toolbox"):
        with cls._lock:
            if app_name not in cls._instances:
                cls._instances[app_name] = cls(app_name)
            return cls._instances[app_name]

    def set_correlation_id(self, cid=None):
        self.correlation_id = cid or str(uuid.uuid4())
        return self.correlation_id

    def log_event(self, event_type, status, message, data=None, level="INFO"):
        """
        Log a structured event specifically for JSONL consumption.
        """
        if data is None:
            data = {}

        entry = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "app": self.app_name,
            "level": level,
            "event": event_type,
            "status": status,
            "message": message,
            "data": data
        }
        
        if self.correlation_id:
            entry["correlation_id"] = self.correlation_id

        # Serialize
        json_line = json.dumps(entry)

        # Log via standard python logger. 
        # The file handler's JsonlFormatter will see this is already JSON and pass it through.
        # The console handler will print the JSON string (which is fine for debug).
        log_method = getattr(self.logger, level.lower(), self.logger.info)
        log_method(json_line)

# Usage Helper
def log(event_type, status, message, data=None, level="INFO", app_name="toolbox"):
    manager = LogManager.get_instance(app_name)
    manager.log_event(event_type, status, message, data, level)
