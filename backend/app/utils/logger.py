"""
Logging helpers for the backend application.
"""

from __future__ import annotations

import logging
import os
import sys
from datetime import datetime
from logging.handlers import RotatingFileHandler
from typing import TextIO


LOG_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
    "logs",
)
_UTF8_RECONFIGURE_ATTEMPTED = False


def _try_reconfigure_utf8(stream: TextIO) -> None:
    if not hasattr(stream, "reconfigure"):
        return
    try:
        stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, OSError, ValueError):
        return


def _ensure_utf8_stdio() -> None:
    global _UTF8_RECONFIGURE_ATTEMPTED
    if sys.platform != "win32":
        return
    if _UTF8_RECONFIGURE_ATTEMPTED:
        return
    _UTF8_RECONFIGURE_ATTEMPTED = True
    _try_reconfigure_utf8(sys.stdout)
    _try_reconfigure_utf8(sys.stderr)


def setup_logger(name: str = "mirofish", level: int = logging.DEBUG) -> logging.Logger:
    os.makedirs(LOG_DIR, exist_ok=True)
    logger = logging.getLogger(name)
    logger.setLevel(level)
    logger.propagate = False
    if logger.handlers:
        return logger

    detailed_formatter = logging.Formatter(
        "[%(asctime)s] %(levelname)s [%(name)s.%(funcName)s:%(lineno)d] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    simple_formatter = logging.Formatter(
        "[%(asctime)s] %(levelname)s: %(message)s",
        datefmt="%H:%M:%S",
    )

    log_filename = f"{datetime.now():%Y-%m-%d}.log"
    file_handler = RotatingFileHandler(
        os.path.join(LOG_DIR, log_filename),
        maxBytes=10 * 1024 * 1024,
        backupCount=5,
        encoding="utf-8",
    )
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(detailed_formatter)

    _ensure_utf8_stdio()
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(simple_formatter)

    logger.addHandler(file_handler)
    logger.addHandler(console_handler)
    return logger


def get_logger(name: str = "mirofish") -> logging.Logger:
    logger = logging.getLogger(name)
    if logger.handlers:
        return logger
    return setup_logger(name)


logger = setup_logger()


def debug(msg, *args, **kwargs):
    logger.debug(msg, *args, **kwargs)


def info(msg, *args, **kwargs):
    logger.info(msg, *args, **kwargs)


def warning(msg, *args, **kwargs):
    logger.warning(msg, *args, **kwargs)


def error(msg, *args, **kwargs):
    logger.error(msg, *args, **kwargs)


def critical(msg, *args, **kwargs):
    logger.critical(msg, *args, **kwargs)
