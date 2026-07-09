"""Tests for the yt-dlp option building and error translation logic."""

from __future__ import annotations

import os
import unittest

from app.downloader import Downloader, find_ffmpeg
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

    def test_bot_check_suggests_updating_ytdlp(self) -> None:
        msg = self._map("Sign in to confirm you're not a bot")
        self.assertIn("yt-dlp", msg.lower())

    def test_http_403_suggests_updating_ytdlp(self) -> None:
        msg = self._map("unable to download video data: HTTP Error 403: Forbidden")
        self.assertIn("yt-dlp", msg.lower())

    def test_extraction_failure_suggests_updating_ytdlp(self) -> None:
        msg = self._map("ERROR: Unable to extract player version")
        self.assertIn("yt-dlp", msg.lower())

    def test_http_404_is_not_found(self) -> None:
        msg = self._map("HTTP Error 404: File not found")
        self.assertIn("could not be found", msg.lower())

    def test_network_error(self) -> None:
        self.assertIn("network", self._map("Connection timed out").lower())

    def test_unsupported_url(self) -> None:
        self.assertIn("not supported", self._map("Unsupported URL: foo").lower())

    def test_generic_fallback(self) -> None:
        self.assertTrue(self._map("something odd").startswith("Download failed:"))


class FormatErrorDetectionTests(unittest.TestCase):
    def test_detects_format_unavailable(self) -> None:
        self.assertTrue(
            Downloader._is_format_error(
                Exception("ERROR: Requested format is not available")
            )
        )

    def test_ignores_other_errors(self) -> None:
        self.assertFalse(Downloader._is_format_error(Exception("HTTP Error 403")))


class VideoOptionsTests(unittest.TestCase):
    def test_best_quality_has_no_height_filter(self) -> None:
        opts = Downloader._video_options(VideoQuality.BEST)
        self.assertNotIn("height", opts["format"])
        self.assertEqual(opts["merge_output_format"], "mp4")

    def test_capped_quality_includes_height_filter(self) -> None:
        opts = Downloader._video_options(VideoQuality.P720)
        self.assertIn("height<=720", opts["format"])
        # Falls back to a plain best file as the final option.
        self.assertTrue(opts["format"].endswith("/b"))

    def test_prefers_mp4_native_codecs(self) -> None:
        opts = Downloader._video_options(VideoQuality.P1080)
        self.assertIn("[ext=mp4]", opts["format"])
        self.assertIn("[ext=m4a]", opts["format"])

    def test_without_ffmpeg_only_single_file_formats(self) -> None:
        # No ffmpeg means separate streams can't be merged, so no "+" selectors
        # and no post-processing.
        opts = Downloader._video_options(VideoQuality.P720, have_ffmpeg=False)
        self.assertNotIn("+", opts["format"])
        self.assertNotIn("postprocessors", opts)
        self.assertNotIn("merge_output_format", opts)

    def test_fallback_uses_most_compatible_selector(self) -> None:
        opts = Downloader._video_options(VideoQuality.P720, fallback=True)
        self.assertEqual(opts["format"], "b")


class AudioOptionsTests(unittest.TestCase):
    def test_best_quality_uses_zero(self) -> None:
        opts = Downloader._audio_options(AudioQuality.BEST)
        pp = opts["postprocessors"][0]
        self.assertEqual(pp["preferredquality"], "0")
        self.assertEqual(pp["preferredcodec"], "mp3")

    def test_specific_bitrate(self) -> None:
        opts = Downloader._audio_options(AudioQuality.K128)
        self.assertEqual(opts["postprocessors"][0]["preferredquality"], "128")

    def test_fallback_accepts_any_file(self) -> None:
        opts = Downloader._audio_options(AudioQuality.BEST, fallback=True)
        self.assertEqual(opts["format"], "b")


class BuildOptionsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.downloader = Downloader()

    def test_video_item_options(self) -> None:
        item = DownloadItem(
            url="https://example.com/v", output_format=OutputFormat.MP4
        )
        opts = self.downloader._build_ytdlp_options(
            item, "/tmp/out", ffmpeg_path="/opt/ffmpeg"
        )
        self.assertTrue(opts["noplaylist"])
        self.assertEqual(opts["outtmpl"], os.path.join("/tmp/out", "%(title)s.%(ext)s"))
        self.assertIn("merge_output_format", opts)
        self.assertEqual(opts["ffmpeg_location"], "/opt/ffmpeg")
        self.assertEqual(len(opts["progress_hooks"]), 1)

    def test_audio_item_options(self) -> None:
        item = DownloadItem(
            url="https://example.com/a", output_format=OutputFormat.MP3
        )
        opts = self.downloader._build_ytdlp_options(
            item, "/tmp/out", ffmpeg_path="/opt/ffmpeg"
        )
        # MP3 path selects audio extraction, not video merging.
        self.assertEqual(opts["format"], "bestaudio/best")
        self.assertNotIn("merge_output_format", opts)

    def test_no_ffmpeg_omits_location(self) -> None:
        item = DownloadItem(
            url="https://example.com/v", output_format=OutputFormat.MP4
        )
        opts = self.downloader._build_ytdlp_options(item, "/tmp/out", None)
        self.assertNotIn("ffmpeg_location", opts)
        self.assertNotIn("postprocessors", opts)


class FfmpegDiscoveryTests(unittest.TestCase):
    def test_find_ffmpeg_returns_existing_path_or_none(self) -> None:
        # find_ffmpeg() must never raise; it returns a real path or None.
        path = find_ffmpeg()
        if path is not None:
            self.assertTrue(os.path.exists(path))


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
