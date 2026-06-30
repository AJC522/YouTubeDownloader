"""Tests for the yt-dlp option building and error translation logic."""

from __future__ import annotations

import os
import unittest

from app.downloader import Downloader
from app.models import AudioQuality, DownloadItem, OutputFormat, VideoQuality


class FriendlyErrorTests(unittest.TestCase):
    def _map(self, message: str) -> str:
        return Downloader._friendly_error(Exception(message))

    def test_private_video(self) -> None:
        self.assertIn("private", self._map("ERROR: This video is private").lower())

    def test_age_restricted(self) -> None:
        self.assertIn(
            "age-restricted",
            self._map("Sign in to confirm your age; age restricted").lower(),
        )

    def test_format_error_takes_priority_over_unavailable(self) -> None:
        # "requested format is not available" must not be swallowed by the
        # generic "not available" branch.
        msg = self._map("Requested format is not available")
        self.assertIn("format/resolution", msg.lower())

    def test_network_error(self) -> None:
        self.assertIn("network", self._map("Connection timed out").lower())

    def test_unsupported_url(self) -> None:
        self.assertIn("not supported", self._map("Unsupported URL: foo").lower())

    def test_generic_fallback(self) -> None:
        self.assertTrue(self._map("something odd").startswith("Download failed:"))


class VideoOptionsTests(unittest.TestCase):
    def test_best_quality_has_no_height_filter(self) -> None:
        opts = Downloader._video_options(VideoQuality.BEST)
        self.assertNotIn("height", opts["format"])
        self.assertEqual(opts["merge_output_format"], "mp4")

    def test_capped_quality_includes_height_filter(self) -> None:
        opts = Downloader._video_options(VideoQuality.P720)
        self.assertIn("height<=720", opts["format"])
        # Falls back to a plain best stream as the final option.
        self.assertTrue(opts["format"].endswith("/best"))


class AudioOptionsTests(unittest.TestCase):
    def test_best_quality_uses_zero(self) -> None:
        opts = Downloader._audio_options(AudioQuality.BEST)
        pp = opts["postprocessors"][0]
        self.assertEqual(pp["preferredquality"], "0")
        self.assertEqual(pp["preferredcodec"], "mp3")

    def test_specific_bitrate(self) -> None:
        opts = Downloader._audio_options(AudioQuality.K128)
        self.assertEqual(opts["postprocessors"][0]["preferredquality"], "128")


class BuildOptionsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.downloader = Downloader()

    def test_video_item_options(self) -> None:
        item = DownloadItem(
            url="https://example.com/v", output_format=OutputFormat.MP4
        )
        opts = self.downloader._build_ytdlp_options(item, "/tmp/out")
        self.assertTrue(opts["noplaylist"])
        self.assertEqual(opts["outtmpl"], os.path.join("/tmp/out", "%(title)s.%(ext)s"))
        self.assertIn("merge_output_format", opts)
        self.assertEqual(len(opts["progress_hooks"]), 1)

    def test_audio_item_options(self) -> None:
        item = DownloadItem(
            url="https://example.com/a", output_format=OutputFormat.MP3
        )
        opts = self.downloader._build_ytdlp_options(item, "/tmp/out")
        # MP3 path selects audio extraction, not video merging.
        self.assertEqual(opts["format"], "bestaudio/best")
        self.assertNotIn("merge_output_format", opts)


class CancelStateTests(unittest.TestCase):
    def test_cancel_flag_round_trip(self) -> None:
        downloader = Downloader()
        self.assertFalse(downloader._cancel_requested.is_set())
        downloader.request_cancel()
        self.assertTrue(downloader._cancel_requested.is_set())
        downloader.reset_cancel()
        self.assertFalse(downloader._cancel_requested.is_set())


if __name__ == "__main__":
    unittest.main()
