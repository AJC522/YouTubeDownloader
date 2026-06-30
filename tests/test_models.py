"""Tests for the core data models."""

from __future__ import annotations

import unittest

from app.models import (
    AudioQuality,
    DownloadItem,
    DownloadStatus,
    OutputFormat,
    VideoQuality,
)


class OutputFormatTests(unittest.TestCase):
    def test_audio_only_flag(self) -> None:
        self.assertTrue(OutputFormat.MP3.is_audio_only)
        self.assertFalse(OutputFormat.MP4.is_audio_only)

    def test_file_extension(self) -> None:
        self.assertEqual(OutputFormat.MP3.file_extension, "mp3")
        self.assertEqual(OutputFormat.MP4.file_extension, "mp4")


class QualityTests(unittest.TestCase):
    def test_video_quality_carries_height(self) -> None:
        self.assertIsNone(VideoQuality.BEST.max_height)
        self.assertEqual(VideoQuality.P720.max_height, 720)
        self.assertEqual(VideoQuality.P720.label, "720p")

    def test_audio_quality_carries_bitrate(self) -> None:
        self.assertIsNone(AudioQuality.BEST.bitrate_kbps)
        self.assertEqual(AudioQuality.K192.bitrate_kbps, 192)
        self.assertEqual(AudioQuality.K192.label, "192 kbps")


class DownloadStatusTests(unittest.TestCase):
    def test_terminal_states(self) -> None:
        self.assertTrue(DownloadStatus.COMPLETED.is_terminal)
        self.assertTrue(DownloadStatus.FAILED.is_terminal)
        self.assertTrue(DownloadStatus.CANCELED.is_terminal)
        self.assertFalse(DownloadStatus.PENDING.is_terminal)
        self.assertFalse(DownloadStatus.DOWNLOADING.is_terminal)


class DownloadItemTests(unittest.TestCase):
    def test_quality_label_follows_format(self) -> None:
        video = DownloadItem(
            url="https://example.com/v",
            output_format=OutputFormat.MP4,
            video_quality=VideoQuality.P1080,
            audio_quality=AudioQuality.K320,
        )
        audio = DownloadItem(
            url="https://example.com/a",
            output_format=OutputFormat.MP3,
            video_quality=VideoQuality.P1080,
            audio_quality=AudioQuality.K320,
        )
        self.assertEqual(video.quality_label, "1080p")
        self.assertEqual(audio.quality_label, "320 kbps")

    def test_item_ids_are_unique(self) -> None:
        first = DownloadItem(url="https://example.com/1")
        second = DownloadItem(url="https://example.com/2")
        self.assertNotEqual(first.item_id, second.item_id)

    def test_defaults(self) -> None:
        item = DownloadItem(url="https://example.com/x")
        self.assertEqual(item.status, DownloadStatus.PENDING)
        self.assertEqual(item.progress, 0.0)
        self.assertEqual(item.save_path, "")


if __name__ == "__main__":
    unittest.main()
