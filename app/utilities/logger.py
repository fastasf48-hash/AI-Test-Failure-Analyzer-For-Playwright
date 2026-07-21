"""Structured, rotating logging shared by every module.

We configure logging once via `get_logger(__name__)` per module (the standard
library caches loggers by name, so repeated calls are cheap) rather than
reaching for `print`. Rotating file handlers keep `logs/app.log` bounded so a
long-lived dashboard process never grows an unbounded log file.
"""

from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler

from app.config.settings import get_settings

_LOG_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

_configured = False


def _configure_root() -> None:
    global _configured
    if _configured:
        return

    settings = get_settings()
    settings.log_dir.mkdir(parents=True, exist_ok=True)

    formatter = logging.Formatter(_LOG_FORMAT, datefmt=_DATE_FORMAT)

    file_handler = RotatingFileHandler(
        settings.log_dir / "app.log",
        maxBytes=5 * 1024 * 1024,  # 5 MB per file
        backupCount=5,
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)

    root = logging.getLogger()
    root.setLevel(settings.log_level)
    root.addHandler(file_handler)
    root.addHandler(console_handler)

    _configured = True


def get_logger(name: str) -> logging.Logger:
    """Return a module-scoped logger, configuring shared handlers on first use."""
    _configure_root()
    return logging.getLogger(name)
