"""Data models for the Video Download Manager.

This module keeps the application's core data structures independent of both the
GUI and the download backend so they can be reused and tested in isolation.
"""

from __future__ import annotations

import enum
import itertools
from dataclasses import dataclass, field
from typing import Optional


class OutputFormat(enum.Enum):
    """Supported output formats.

    The value is the human-readable label shown in the GUI dropdown. The design
    is intentionally enum-based so additional formats can be added later simply
    by extending this enum and the format logic in ``downloader.py``.
    """

    MP4 = "MP4 video"
    MP3 = "MP3 audio"

    @property
    def is_audio_only(self) -> bool:
        """Return ``True`` when the format produces an audio-only file."""
        return self is OutputFormat.MP3

    @property
    def file_extension(self) -> str:
        """Return the target file extension (without a leading dot)."""
        return "mp3" if self.is_audio_only else "mp4"


class VideoQuality(enum.Enum):
    """Preferred video resolution for MP4 downloads.

    ``BEST`` means "best available". The remaining members carry the maximum
    vertical resolution (in pixels) used to build the yt-dlp format selector.
    """

    BEST = ("Best available", None)
    P1080 = ("1080p", 1080)
    P720 = ("720p", 720)
    P480 = ("480p", 480)
    P360 = ("360p", 360)

    def __init__(self, label: str, max_height: Optional[int]) -> None:
        self.label = label
        self.max_height = max_height


class AudioQuality(enum.Enum):
    """Preferred audio bitrate for MP3 extraction.

    ``BEST`` lets yt-dlp/ffmpeg pick the best available quality. The other
    members carry the target bitrate in kbps.
    """

    BEST = ("Best available", None)
    K320 = ("320 kbps", 320)
    K192 = ("192 kbps", 192)
    K128 = ("128 kbps", 128)

    def __init__(self, label: str, bitrate_kbps: Optional[int]) -> None:
        self.label = label
        self.bitrate_kbps = bitrate_kbps


class DownloadStatus(enum.Enum):
    """Lifecycle states for a queued download item."""

    PENDING = "Pending"
    DOWNLOADING = "Downloading"
    COMPLETED = "Completed"
    FAILED = "Failed"
    CANCELED = "Canceled"

    @property
    def is_terminal(self) -> bool:
        """States from which the item will not progress on its own."""
        return self in (
            DownloadStatus.COMPLETED,
            DownloadStatus.FAILED,
            DownloadStatus.CANCELED,
        )


# A process-wide counter used to assign each queue item a stable unique id.
_id_counter = itertools.count(1)


@dataclass
class DownloadItem:
    """A single entry in the download queue.

    Attributes
    ----------
    url:
        The source video URL.
    output_format:
        Desired output format (MP4/MP3/...).
    video_quality:
        Preferred resolution; only meaningful for video formats.
    audio_quality:
        Preferred bitrate; only meaningful for audio formats.
    status:
        Current lifecycle state.
    progress:
        Download progress as a percentage in the range ``0.0``–``100.0``.
    save_path:
        Final save location of the produced file once known.
    error_message:
        User-friendly error text when the item has failed.
    title:
        Resolved media title (populated once metadata is available).
    """

    url: str
    output_format: OutputFormat = OutputFormat.MP4
    video_quality: VideoQuality = VideoQuality.BEST
    audio_quality: AudioQuality = AudioQuality.BEST
    status: DownloadStatus = DownloadStatus.PENDING
    progress: float = 0.0
    save_path: str = ""
    error_message: str = ""
    title: str = ""
    item_id: int = field(default_factory=lambda: next(_id_counter))

    @property
    def quality_label(self) -> str:
        """Return the resolution/quality label relevant to the chosen format."""
        if self.output_format.is_audio_only:
            return self.audio_quality.label
        return self.video_quality.label
