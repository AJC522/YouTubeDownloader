"""Application logging configuration.

Technical errors and diagnostics are written to a rotating log file so users can
troubleshoot problems without the details cluttering the GUI. The log lives in a
per-user application data directory rather than a hardcoded path.
"""

from __future__ import annotations

import logging
import os
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

APP_NAME = "VideoDownloadManager"
LOG_FILE_NAME = "video_download_manager.log"


def get_app_data_dir() -> Path:
    """Return (and create) the per-user directory for app data and logs.

    The location follows common OS conventions and avoids hardcoded paths:
    ``%APPDATA%`` on Windows, ``~/Library/Application Support`` on macOS, and
    ``$XDG_DATA_HOME`` (or ``~/.local/share``) on Linux.
    """

    if os.name == "nt":  # Windows
        base = os.environ.get("APPDATA", str(Path.home() / "AppData" / "Roaming"))
    elif sys.platform == "darwin":  # macOS
        base = str(Path.home() / "Library" / "Application Support")
    else:  # Linux and other POSIX systems
        base = os.environ.get("XDG_DATA_HOME", str(Path.home() / ".local" / "share"))

    app_dir = Path(base) / APP_NAME
    app_dir.mkdir(parents=True, exist_ok=True)
    return app_dir


def get_log_file_path() -> Path:
    """Return the absolute path to the log file."""
    return get_app_data_dir() / LOG_FILE_NAME


def setup_logger() -> logging.Logger:
    """Configure and return the application's root logger.

    Calling this more than once is safe; handlers are only attached on the first
    invocation to avoid duplicate log lines.
    """

    logger = logging.getLogger(APP_NAME)
    logger.setLevel(logging.DEBUG)

    if logger.handlers:  # Already configured.
        return logger

    formatter = logging.Formatter(
        "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
    )

    # Rotating file handler keeps the log from growing without bound.
    file_handler = RotatingFileHandler(
        get_log_file_path(), maxBytes=1_000_000, backupCount=3, encoding="utf-8"
    )
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    # Console handler is handy during development.
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    logger.debug("Logger initialised. Log file: %s", get_log_file_path())
    return logger


# A module-level logger other modules can import directly.
logger = setup_logger()
