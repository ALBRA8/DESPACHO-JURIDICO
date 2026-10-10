"""
Logging estructurado para ALBRA.

Usa structlog si está disponible; si no, fallback a stdlib logging con
formato JSON-friendly. La idea: cada log es un evento con campos.
"""
from __future__ import annotations

import json
import logging
import sys
from typing import Any

_DEFAULT_FORMAT = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"


def _build_handler(level: str, fmt: str) -> logging.Handler:
    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(level)
    if fmt == "json":
        class JsonFormatter(logging.Formatter):
            def format(self, record: logging.LogRecord) -> str:
                payload: dict[str, Any] = {
                    "ts": self.formatTime(record),
                    "level": record.levelname,
                    "logger": record.name,
                    "msg": record.getMessage(),
                }
                if record.exc_info:
                    payload["exc"] = self.formatException(record.exc_info)
                for k, v in getattr(record, "_albra_extra", {}).items():
                    payload[k] = v
                return json.dumps(payload, default=str, ensure_ascii=False)
        handler.setFormatter(JsonFormatter())
    else:
        handler.setFormatter(logging.Formatter(_DEFAULT_FORMAT))
    return handler


def setup_logging(level: str = "INFO", fmt: str = "console") -> None:
    """Configura el logging root una sola vez."""
    root = logging.getLogger()
    if getattr(root, "_albra_configured", False):
        return
    root.handlers.clear()
    root.addHandler(_build_handler(level, fmt))
    root.setLevel(level)
    root._albra_configured = True  # type: ignore[attr-defined]


class _Logger:
    """Wrapper que acepta kwargs extra y los inyecta en el record."""

    def __init__(self, name: str) -> None:
        self._logger = logging.getLogger(name)

    def _log(self, lvl: int, msg: str, **kwargs: Any) -> None:
        extra = {"_albra_extra": kwargs}
        self._logger.log(lvl, msg, extra=extra, stacklevel=3)

    def debug(self, msg: str, **kwargs: Any) -> None:
        self._log(logging.DEBUG, msg, **kwargs)

    def info(self, msg: str, **kwargs: Any) -> None:
        self._log(logging.INFO, msg, **kwargs)

    def warning(self, msg: str, **kwargs: Any) -> None:
        self._log(logging.WARNING, msg, **kwargs)

    def error(self, msg: str, **kwargs: Any) -> None:
        self._log(logging.ERROR, msg, **kwargs)

    def critical(self, msg: str, **kwargs: Any) -> None:
        self._log(logging.CRITICAL, msg, **kwargs)

    def exception(self, msg: str, **kwargs: Any) -> None:
        extra = {"_albra_extra": kwargs}
        self._logger.exception(msg, extra=extra)


def get_logger(name: str = "albra") -> _Logger:
    setup_logging()
    return _Logger(name)
