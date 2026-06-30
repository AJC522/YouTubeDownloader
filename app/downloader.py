"""Download backend built on top of yt-dlp.

This module is deliberately free of any GUI code. It exposes a small, callback
driven API so it can be driven from a background thread (see ``gui.py``) or from
a script/test without a display.

The :class:`Downloader` translates a :class:`~app.models.DownloadItem` into a
yt-dlp configuration, runs the download, performs MP3 extraction/MP4 muxing via
ffmpeg, and reports progress and errors through callbacks.
"""

from __future__ import annotations

import os
import shutil
from typing import Callable, Optional

from .logger import logger
from .models import (
    AudioQuality,
    DownloadItem,
    DownloadStatus,
    OutputFormat,
    VideoQuality,
)

try:
    import yt_dlp
except ImportError:  # pragma: no cover - surfaced to the user at runtime.
    yt_dlp = None  # type: ignore[assignment]


# Type aliases for the callbacks used to report state back to the caller.
ProgressCallback = Callable[[DownloadItem, float, str], None]
StatusCallback = Callable[[DownloadItem, DownloadStatus, str], None]


class DownloadCanceled(Exception):
    """Raised internally to unwind yt-dlp when a cancel is requested."""


class FFmpegNotFoundError(Exception):
    """Raised when ffmpeg is required but cannot be located."""


def is_ffmpeg_available() -> bool:
    """Return ``True`` when an ffmpeg executable is on the PATH."""
    return shutil.which("ffmpeg") is not None


def is_ytdlp_available() -> bool:
    """Return ``True`` when the yt-dlp library imported successfully."""
    return yt_dlp is not None


class Downloader:
    """Run downloads for individual :class:`DownloadItem` objects.

    Parameters
    ----------
    progress_callback:
        Invoked frequently with ``(item, percent, human_readable_status)``.
    status_callback:
        Invoked when an item transitions between lifecycle states with
        ``(item, new_status, message)``.
    """

    def __init__(
        self,
        progress_callback: Optional[ProgressCallback] = None,
        status_callback: Optional[StatusCallback] = None,
    ) -> None:
        self._progress_callback = progress_callback
        self._status_callback = status_callback
        # Set by request_cancel(); checked from the yt-dlp progress hook.
        self._cancel_requested = False

    # -- Public API --------------------------------------------------------

    def request_cancel(self) -> None:
        """Ask the in-flight download to stop at the next opportunity."""
        self._cancel_requested = True

    def reset_cancel(self) -> None:
        """Clear any pending cancel request before starting a new item."""
        self._cancel_requested = False

    def download(self, item: DownloadItem, destination_dir: str) -> None:
        """Download a single item into ``destination_dir``.

        Updates ``item`` in place (status, progress, save_path, error_message)
        and fires the configured callbacks. Exceptions are caught and converted
        into a ``FAILED``/``CANCELED`` status with a user-friendly message.
        """

        if not is_ytdlp_available():
            self._fail(
                item,
                "The yt-dlp library is not installed. Run "
                "'pip install -r requirements.txt'.",
            )
            return

        # MP3 extraction (and MP4 muxing of separate streams) needs ffmpeg.
        if not is_ffmpeg_available():
            self._fail(
                item,
                "ffmpeg was not found. Please install ffmpeg and ensure it is "
                "on your PATH. See the README for instructions.",
            )
            return

        self.reset_cancel()
        self._set_status(item, DownloadStatus.DOWNLOADING, "Starting…")

        options = self._build_ytdlp_options(item, destination_dir)
        logger.debug("yt-dlp options for %s: %s", item.url, options)

        try:
            with yt_dlp.YoutubeDL(options) as ydl:
                info = ydl.extract_info(item.url, download=True)
                # Resolve the final output filename after post-processing.
                item.title = info.get("title", item.title)
                item.save_path = self._resolve_output_path(
                    ydl, info, item, destination_dir
                )

            item.progress = 100.0
            self._set_status(
                item, DownloadStatus.COMPLETED, "Download complete."
            )
            logger.info("Completed download: %s -> %s", item.url, item.save_path)

        except DownloadCanceled:
            self._set_status(item, DownloadStatus.CANCELED, "Canceled by user.")
            logger.info("Download canceled by user: %s", item.url)

        except Exception as exc:  # noqa: BLE001 - convert to friendly message.
            message = self._friendly_error(exc)
            self._fail(item, message)
            logger.exception("Download failed for %s: %s", item.url, exc)

    # -- yt-dlp configuration ---------------------------------------------

    def _build_ytdlp_options(
        self, item: DownloadItem, destination_dir: str
    ) -> dict:
        """Construct the yt-dlp options dict for a given item."""

        outtmpl = os.path.join(destination_dir, "%(title)s.%(ext)s")
        options: dict = {
            "outtmpl": outtmpl,
            "progress_hooks": [self._make_progress_hook(item)],
            "noplaylist": True,  # Treat a single URL as a single video.
            "quiet": True,
            "no_warnings": True,
            "ignoreerrors": False,
            "retries": 3,
            "fragment_retries": 3,
        }

        if item.output_format is OutputFormat.MP3:
            options.update(self._audio_options(item.audio_quality))
        else:
            options.update(self._video_options(item.video_quality))

        return options

    @staticmethod
    def _video_options(quality: VideoQuality) -> dict:
        """Return format selection options for MP4 video downloads.

        yt-dlp's ``[height<=N]`` selector automatically falls back to the next
        lower available resolution when the requested one is unavailable, which
        satisfies the "closest available lower resolution" requirement.
        """

        if quality.max_height is None:
            fmt = "bestvideo+bestaudio/best"
        else:
            h = quality.max_height
            fmt = (
                f"bestvideo[height<={h}]+bestaudio/"
                f"best[height<={h}]/best"
            )

        return {
            "format": fmt,
            # Ensure the final container is mp4 (muxing via ffmpeg as needed).
            "merge_output_format": "mp4",
            "postprocessors": [
                {"key": "FFmpegVideoRemuxer", "preferedformat": "mp4"}
            ],
        }

    @staticmethod
    def _audio_options(quality: AudioQuality) -> dict:
        """Return options that extract audio to MP3 at the chosen bitrate."""

        # "0" tells yt-dlp/ffmpeg to use the best available quality.
        preferred = "0" if quality.bitrate_kbps is None else str(quality.bitrate_kbps)
        return {
            "format": "bestaudio/best",
            "postprocessors": [
                {
                    "key": "FFmpegExtractAudio",
                    "preferredcodec": "mp3",
                    "preferredquality": preferred,
                }
            ],
        }

    # -- Progress / status helpers ----------------------------------------

    def _make_progress_hook(self, item: DownloadItem) -> Callable[[dict], None]:
        """Build a yt-dlp progress hook bound to a specific item."""

        def hook(data: dict) -> None:
            # Honour cancellation requests by aborting the download.
            if self._cancel_requested:
                raise DownloadCanceled()

            status = data.get("status")
            if status == "downloading":
                downloaded = data.get("downloaded_bytes") or 0
                total = (
                    data.get("total_bytes")
                    or data.get("total_bytes_estimate")
                    or 0
                )
                percent = (downloaded / total * 100.0) if total else 0.0
                item.progress = percent
                speed = data.get("_speed_str", "").strip()
                eta = data.get("_eta_str", "").strip()
                detail = "Downloading"
                if speed:
                    detail += f" · {speed}"
                if eta:
                    detail += f" · ETA {eta}"
                self._report_progress(item, percent, detail)
            elif status == "finished":
                # Raw download done; ffmpeg post-processing may still run.
                item.progress = 100.0
                self._report_progress(item, 100.0, "Processing…")

        return hook

    @staticmethod
    def _resolve_output_path(
        ydl: "yt_dlp.YoutubeDL",
        info: dict,
        item: DownloadItem,
        destination_dir: str,
    ) -> str:
        """Determine the final file path after post-processing.

        Post-processors (audio extraction / remuxing) change the extension, so
        we rebuild the path from the resolved title and target extension.
        """

        try:
            base = ydl.prepare_filename(info)
        except Exception:  # noqa: BLE001 - fall back to a best-effort guess.
            title = info.get("title", "download")
            base = os.path.join(destination_dir, title)

        root, _ = os.path.splitext(base)
        candidate = f"{root}.{item.output_format.file_extension}"
        if os.path.exists(candidate):
            return candidate
        # If the predicted file is missing, return whatever we computed so the
        # user still gets a meaningful location in the GUI.
        return candidate

    def _report_progress(
        self, item: DownloadItem, percent: float, detail: str
    ) -> None:
        if self._progress_callback is not None:
            self._progress_callback(item, percent, detail)

    def _set_status(
        self, item: DownloadItem, status: DownloadStatus, message: str
    ) -> None:
        item.status = status
        if status == DownloadStatus.FAILED:
            item.error_message = message
        if self._status_callback is not None:
            self._status_callback(item, status, message)

    def _fail(self, item: DownloadItem, message: str) -> None:
        self._set_status(item, DownloadStatus.FAILED, message)

    # -- Error translation -------------------------------------------------

    @staticmethod
    def _friendly_error(exc: Exception) -> str:
        """Map low-level yt-dlp/network errors to user-friendly messages."""

        text = str(exc).lower()

        if "private" in text:
            return "This video is private and cannot be downloaded."
        if "age" in text and "restrict" in text:
            return "This video is age-restricted and cannot be downloaded."
        # Check format errors before the generic "unavailable" branch, since
        # yt-dlp phrases them as "requested format is not available".
        if "requested format" in text or "no video formats" in text:
            return (
                "The requested format/resolution is not available for this "
                "video. Try 'Best available' or a different quality."
            )
        if "copyright" in text:
            return "This video is unavailable due to a copyright claim."
        if "removed" in text or "unavailable" in text or "not available" in text:
            return "This video is unavailable or has been removed."
        if any(
            token in text
            for token in ("timed out", "timeout", "connection", "network", "resolve")
        ):
            return "A network error occurred. Check your connection and retry."
        if "unsupported url" in text or "is not a valid url" in text:
            return "This URL is not supported or is not a valid video link."

        # Generic fallback; the full traceback is in the log file.
        return f"Download failed: {exc}"
