import os
import json
import time
import logging
from logging.handlers import RotatingFileHandler
import threading
from datetime import datetime

class LogManager:
    """
    Unified Logging System for the Toolbox.
    - Writes structured JSONL logs to a local file.
    - Supports rotation.
    - Thread-safe.
    """
    _instance = None
    _lock = threading.Lock()

    def __init__(self, app_name="toolbox", log_dir=None):
        if hasattr(self, 'initialized'):
            return
            
        self.app_name = app_name
        
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
        self.logger = logging.getLogger(app_name)
        self.logger.setLevel(logging.INFO)
        
        # Avoid adding handlers multiple times
        if not self.logger.handlers:
            # Console Handler (Human readable)
            ch = logging.StreamHandler()
            ch.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
            self.logger.addHandler(ch)
            
            # File Handler (JSONL) -- We will manually format this
            self.file_handler = RotatingFileHandler(
                self.log_file, maxBytes=10*1024*1024, backupCount=7
            )
            self.file_handler.setFormatter(logging.Formatter('%(message)s'))
            self.logger.addHandler(self.file_handler)

        self.initialized = True

    @classmethod
    def get_instance(cls, app_name="toolbox"):
        with cls._lock:
            if cls._instance is None:
                cls._instance = cls(app_name)
            return cls._instance

    def log_event(self, event_type, status, message, data=None, level="INFO"):
        """
        Log a structured event.
        
        Args:
            event_type (str): Category (e.g., 'AUTH_REFRESH', 'FILE_MOVE')
            status (str): 'SUCCESS', 'FAILURE', 'WARNING'
            message (str): Human readable description
            data (dict): key-value pairs of context
            level (str): INFO, WARNING, ERROR, DEBUG
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

        # Serialize
        json_line = json.dumps(entry)

        # Log via standard python logger (which handles rotation/concurrency via handler)
        if level == "ERROR":
            self.logger.error(json_line)
        elif level == "WARNING":
            self.logger.warning(json_line)
        elif level == "DEBUG":
            self.logger.debug(json_line)
        else:
            self.logger.info(json_line)

# Usage Helper
def log(event_type, status, message, data=None, level="INFO", app_name="toolbox"):
    manager = LogManager.get_instance(app_name)
    manager.log_event(event_type, status, message, data, level)
