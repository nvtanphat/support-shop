"""Structured JSON logging configuration."""

from __future__ import annotations

import json
import logging
import sys
from typing import Any


class JSONFormatter(logging.Formatter):
    """Formats log records as single-line JSON objects."""

    def format(self, record: logging.LogRecord) -> str:
        log_data: dict[str, Any] = {
            "timestamp": self.formatTime(record, self.datefmt),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        # Add contextual fields if present
        for key in ("event", "request_id", "trace_id", "error_code", "customer_id", "conversation_id"):
            val = getattr(record, key, None)
            if val is not None:
                log_data[key] = str(val)

        if record.exc_info and record.exc_text:
            log_data["exception"] = record.exc_text

        return json.dumps(log_data, ensure_ascii=False)


def setup_logging(level: str = "INFO") -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JSONFormatter())
    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(level.upper())
    # Suppress verbose loggers
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)
