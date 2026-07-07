from __future__ import annotations

import json
import logging
import os
import sys
from datetime import UTC, datetime

_RESERVED_LOG_RECORD_FIELDS = set(logging.LogRecord("", 0, "", 0, "", (), None).__dict__.keys()) | {"message", "asctime"}
_CONFIGURED_SENTINEL = "_job_market_intelligence_logging_configured"
_ORIGINAL_MAKE_RECORD = logging.Logger.makeRecord


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, object] = {
            "timestamp": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        for key, value in record.__dict__.items():
            if key in _RESERVED_LOG_RECORD_FIELDS or key.startswith("_"):
                continue
            payload[key] = value
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False, default=str)


def _safe_make_record(self, name, level, fn, lno, msg, args, exc_info, func=None, extra=None, sinfo=None):
    if extra:
        extra = {
            (f"extra_{key}" if key in _RESERVED_LOG_RECORD_FIELDS else key): value
            for key, value in extra.items()
        }
    return _ORIGINAL_MAKE_RECORD(self, name, level, fn, lno, msg, args, exc_info, func, extra, sinfo)


def configure_logging(level: int | str | None = None) -> None:
    root = logging.getLogger()
    if getattr(root, _CONFIGURED_SENTINEL, False):
        return

    resolved_level = level or os.getenv("JMI_LOG_LEVEL", "INFO")
    logging.Logger.makeRecord = _safe_make_record  # type: ignore[assignment]

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())

    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(resolved_level)

    for logger_name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        logger = logging.getLogger(logger_name)
        logger.handlers.clear()
        logger.propagate = True
        logger.setLevel(resolved_level)

    setattr(root, _CONFIGURED_SENTINEL, True)
