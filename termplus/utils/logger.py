"""Structured logging setup with file rotation."""

from __future__ import annotations

import errno
import logging
import os
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

_LOG_FORMAT = "%(asctime)s [%(levelname)-8s] %(name)s: %(message)s"
_LOG_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"


def setup_logging(log_dir: Path, level: int = logging.INFO) -> None:
    """Configure root logger with console and rotating file handlers.

    Args:
        log_dir: Directory for log files.
        level: Logging level (default INFO).
    """
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / "termplus.log"

    root = logging.getLogger()
    root.setLevel(level)

    # Clear any existing handlers
    root.handlers.clear()

    # Console handler
    console = logging.StreamHandler(sys.stdout)
    console.setLevel(level)
    console.setFormatter(logging.Formatter(_LOG_FORMAT, _LOG_DATE_FORMAT))
    root.addHandler(console)

    # Rotating file handler - 5 MB per file, keep 3 backups.
    # On Windows another instance can lock termplus.log, so fallback
    # to a per-process file instead of failing app startup.
    file_handler: RotatingFileHandler | None = None
    for candidate in (log_file, log_dir / f"termplus-{os.getpid()}.log"):
        try:
            file_handler = RotatingFileHandler(
                candidate,
                maxBytes=5 * 1024 * 1024,
                backupCount=3,
                encoding="utf-8",
            )
            break
        except PermissionError:
            continue
        except OSError as exc:
            if exc.errno in (errno.EACCES, errno.EPERM):
                continue
            raise

    if file_handler is not None:
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(logging.Formatter(_LOG_FORMAT, _LOG_DATE_FORMAT))
        root.addHandler(file_handler)
    else:
        root.warning("File logging disabled: could not open log files in %s", log_dir)

    logging.getLogger("paramiko").setLevel(logging.WARNING)
    logging.getLogger("PySide6").setLevel(logging.WARNING)
