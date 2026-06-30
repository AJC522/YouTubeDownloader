"""Tests for settings load/save/update behaviour."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from app.settings import Settings


class SettingsTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.path = Path(self._tmp.name) / "settings.json"

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_first_run_seeds_defaults_and_writes_file(self) -> None:
        settings = Settings(file_path=self.path)
        self.assertTrue(self.path.exists())
        self.assertEqual(settings.get("last_output_format"), "MP4 video")
        # A download directory is always seeded.
        self.assertTrue(settings.get("download_directory"))

    def test_set_persists_to_disk(self) -> None:
        settings = Settings(file_path=self.path)
        settings.set("download_directory", "/some/where")

        reloaded = Settings(file_path=self.path)
        self.assertEqual(reloaded.get("download_directory"), "/some/where")

    def test_update_persists_multiple_keys_at_once(self) -> None:
        settings = Settings(file_path=self.path)
        settings.update(
            {
                "last_output_format": "MP3 audio",
                "last_audio_quality": "192 kbps",
            }
        )

        reloaded = Settings(file_path=self.path)
        self.assertEqual(reloaded.get("last_output_format"), "MP3 audio")
        self.assertEqual(reloaded.get("last_audio_quality"), "192 kbps")

    def test_corrupt_file_falls_back_to_defaults(self) -> None:
        self.path.write_text("{ this is not valid json", encoding="utf-8")
        settings = Settings(file_path=self.path)
        self.assertEqual(settings.get("last_output_format"), "MP4 video")
        self.assertTrue(settings.get("download_directory"))

    def test_missing_download_directory_is_backfilled(self) -> None:
        self.path.write_text(json.dumps({"download_directory": ""}), encoding="utf-8")
        settings = Settings(file_path=self.path)
        self.assertTrue(settings.get("download_directory"))


if __name__ == "__main__":
    unittest.main()
