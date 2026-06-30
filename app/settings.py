"""Persistent application settings.

Settings are stored as JSON in the per-user application data directory so the
app can remember things like the last selected download folder between runs.
No paths are hardcoded; everything is derived from the user's home directory.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict

from .logger import get_app_data_dir, logger

SETTINGS_FILE_NAME = "settings.json"


class Settings:
    """Load, access and persist user settings backed by a JSON file."""

    #: Default values applied when a key is missing from the settings file.
    DEFAULTS: Dict[str, Any] = {
        # Fall back to the OS "Downloads" folder, or the home directory.
        "download_directory": "",
        "last_output_format": "MP4 video",
        "last_video_quality": "Best available",
        "last_audio_quality": "Best available",
    }

    def __init__(self, file_path: Path | None = None) -> None:
        self._file_path = file_path or (get_app_data_dir() / SETTINGS_FILE_NAME)
        self._data: Dict[str, Any] = dict(self.DEFAULTS)
        self.load()

    @property
    def file_path(self) -> Path:
        return self._file_path

    def load(self) -> None:
        """Read settings from disk, merging over the defaults."""
        if not self._file_path.exists():
            # First run: seed a sensible default download directory.
            self._data["download_directory"] = self._default_download_dir()
            self.save()
            return

        try:
            with self._file_path.open("r", encoding="utf-8") as handle:
                stored = json.load(handle)
            if isinstance(stored, dict):
                self._data.update(stored)
            logger.debug("Loaded settings from %s", self._file_path)
        except (OSError, json.JSONDecodeError) as exc:
            # Corrupt or unreadable file: fall back to defaults but keep going.
            logger.warning("Could not read settings (%s); using defaults.", exc)
            self._data = dict(self.DEFAULTS)
            self._data["download_directory"] = self._default_download_dir()

        # Guarantee a usable download directory.
        if not self._data.get("download_directory"):
            self._data["download_directory"] = self._default_download_dir()

    def save(self) -> None:
        """Write the current settings to disk."""
        try:
            with self._file_path.open("w", encoding="utf-8") as handle:
                json.dump(self._data, handle, indent=2)
            logger.debug("Saved settings to %s", self._file_path)
        except OSError as exc:
            logger.error("Failed to save settings: %s", exc)

    def get(self, key: str, default: Any = None) -> Any:
        return self._data.get(key, default)

    def set(self, key: str, value: Any) -> None:
        """Update a single setting and persist immediately."""
        self._data[key] = value
        self.save()

    @staticmethod
    def _default_download_dir() -> str:
        """Best-effort guess at the user's Downloads folder."""
        downloads = Path.home() / "Downloads"
        return str(downloads if downloads.exists() else Path.home())
