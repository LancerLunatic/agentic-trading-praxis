import logging
import sys
import json
from datetime import datetime

class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        log_data = {
            "timestamp": datetime.fromtimestamp(record.created).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno
        }
        if record.exc_info:
            log_data["exception"] = self.formatException(record.exc_info)
        # If there are extra fields passed to the record, append them to the top level JSON
        if hasattr(record, "extra_fields") and isinstance(record.extra_fields, dict):
            log_data.update(record.extra_fields)
        return json.dumps(log_data, default=str)

class StructuredLogger:
    def __init__(self, logger: logging.Logger):
        self._logger = logger
        
    def info(self, msg, **kwargs):
        self._logger.info(msg, extra={"extra_fields": kwargs})
        
    def error(self, msg, **kwargs):
        self._logger.error(msg, extra={"extra_fields": kwargs})
        
    def warning(self, msg, **kwargs):
        self._logger.warning(msg, extra={"extra_fields": kwargs})
        
    def debug(self, msg, **kwargs):
        self._logger.debug(msg, extra={"extra_fields": kwargs})

# Setup default logger to stdout
logger_instance = logging.getLogger("trading_system")
logger_instance.setLevel(logging.INFO)

# Avoid adding multiple handlers if setup is called multiple times
if not logger_instance.handlers:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    logger_instance.addHandler(handler)
    
# Propagate to root logger to capture standard outputs if needed
# but disable default root logger output to avoid double logging
logging.getLogger().handlers = []

logger = StructuredLogger(logger_instance)

def get_logger(name: str) -> StructuredLogger:
    sub_logger = logging.getLogger(name)
    sub_logger.setLevel(logging.INFO)
    if not sub_logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(JsonFormatter())
        sub_logger.addHandler(handler)
    return StructuredLogger(sub_logger)
