"""Download backend built on top of yt-dlp.

This module is deliberately free of any GUI code. It exposes a small, callback
driven API so it can be driven from a background thread (see ``gui.py``) or from
a script/test without a display.

The :class:`Downloader` translates a :class:`~app.models.DownloadItem` into a
yt-dlp configuration, runs the download, performs MP3 extraction/MP4 muxing via
ffmpeg, and reports progress and errors through callbacks.

ffmpeg resolution
-----------------
ffmpeg is looked up in two places, in order:

1. The system ``PATH`` (a user-managed install always wins).
2. The statically-built binary bundled with the ``imageio-ffmpeg`` pip package,
   which is installed automatically via ``requirements.txt``.

This means a plain ``pip install -r requirements.txt`` is enough to get a fully
working app — no separate ffmpeg install step is required.
"""

from __future__ import annotations

import functools
import glob
import os
import shutil
import threading
from typing import Callable, Optional, Tuple

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


# yt-dlp lets its own DownloadCancelled exception propagate cleanly out of
# extract_info(), whereas arbitrary exceptions raised from a progress hook can
# be wrapped in DownloadError (making a user cancel look like a failure). So
# the progress hook raises yt-dlp's class when available.
if yt_dlp is not None:
    _CANCEL_EXCEPTIONS: tuple = (DownloadCanceled, yt_dlp.utils.DownloadCancelled)
    _CANCEL_RAISE = yt_dlp.utils.DownloadCancelled
else:  # pragma: no cover - only hit when yt-dlp is missing entirely.
    _CANCEL_EXCEPTIONS = (DownloadCanceled,)
    _CANCEL_RAISE = DownloadCanceled


@functools.lru_cache(maxsize=1)
def find_ffmpeg() -> Optional[str]:
    """Return the path to an ffmpeg executable, or ``None`` if unavailable.

    A system-wide install on the ``PATH`` takes precedence; otherwise the
    binary bundled with the ``imageio-ffmpeg`` package is used.
    """
    path = shutil.which("ffmpeg")
    if path:
        return path
    try:
        import imageio_ffmpeg

        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:  # noqa: BLE001 - any failure just means "not available".
        return None


def ffmpeg_source() -> Tuple[str, Optional[str]]:
    """Describe where ffmpeg comes from: ``(source, path)``.

    ``source`` is ``"system"``, ``"bundled"`` or ``"missing"``.
    """
    if shutil.which("ffmpeg"):
        return "system", shutil.which("ffmpeg")
    path = find_ffmpeg()
    if path:
        return "bundled", path
    return "missing", None


def is_ffmpeg_available() -> bool:
    """Return ``True`` when an ffmpeg executable could be located."""
    return find_ffmpeg() is not None


def is_ytdlp_available() -> bool:
    """Return ``True`` when the yt-dlp library imported successfully."""
    return yt_dlp is not None


def ytdlp_version() -> Optional[str]:
    """Return the installed yt-dlp version string, or ``None``."""
    if yt_dlp is None:
        return None
    return getattr(yt_dlp.version, "__version__", "unknown")


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
        # Set by request_cancel(); checked from the yt-dlp progress hook. An
        # Event is used so the flag is safely shared between the GUI thread
        # (which requests cancellation) and the worker thread (which polls it).
        self._cancel_requested = threading.Event()

    # -- Public API --------------------------------------------------------

    def request_cancel(self) -> None:
        """Ask the in-flight download to stop at the next opportunity."""
        self._cancel_requested.set()

    def reset_cancel(self) -> None:
        """Clear any pending cancel request before starting a new item."""
        self._cancel_requested.clear()

    def download(self, item: DownloadItem, destination_dir: str) -> None:
        """Download a single item into ``destination_dir``.

        Updates ``item`` in place (status, progress, save_path, error_message)
        and fires the configured callbacks. Exceptions are caught and converted
        into a ``FAILED``/``CANCELED`` status with a user-friendly message.
        """

        if not is_ytdlp_available():
            self._fail(
                item,
                "The yt-dlp library is not installed. Re-run the setup script "
                "(setup.sh / setup.bat) or run 'pip install -r requirements.txt'.",
            )
            return

        ffmpeg_path = find_ffmpeg()
        # ffmpeg ships with the app's Python dependencies, so this only
        # happens if imageio-ffmpeg failed to install. MP3 extraction cannot
        # work without it; MP4 falls back to single-file (progressive) formats.
        if ffmpeg_path is None and item.output_format.is_audio_only:
            self._fail(
                item,
                "MP3 conversion needs ffmpeg, which could not be found. "
                "Re-run the setup script (setup.sh / setup.bat) or run "
                "'pip install -r requirements.txt' to restore it.",
            )
            return

        self.reset_cancel()
        self._set_status(item, DownloadStatus.DOWNLOADING, "Starting…")

        options = self._build_ytdlp_options(item, destination_dir, ffmpeg_path)
        logger.debug("yt-dlp options for %s: %s", item.url, options)

        for attempt in (1, 2):
            try:
                self._run_ytdlp(item, options, destination_dir)
            except _CANCEL_EXCEPTIONS:
                self._set_status(
                    item, DownloadStatus.CANCELED, "Canceled by user."
                )
                logger.info("Download canceled by user: %s", item.url)
            except Exception as exc:  # noqa: BLE001 - convert to friendly text.
                # A cancel can surface as a wrapped DownloadError; check the
                # flag before treating the exception as a real failure.
                if self._cancel_requested.is_set():
                    self._set_status(
                        item, DownloadStatus.CANCELED, "Canceled by user."
                    )
                    logger.info("Download canceled by user: %s", item.url)
                    return
                if attempt == 1 and self._is_format_error(exc):
                    # The preferred format combination isn't offered for this
                    # video; retry once with the most compatible selector.
                    logger.warning(
                        "Preferred format unavailable for %s; retrying with "
                        "fallback format. Original error: %s",
                        item.url,
                        exc,
                    )
                    self._report_progress(
                        item, 0.0, "Retrying with a compatible format…"
                    )
                    options = self._build_ytdlp_options(
                        item, destination_dir, ffmpeg_path, fallback=True
                    )
                    continue
                self._fail(item, self._friendly_error(exc))
                logger.exception("Download failed for %s: %s", item.url, exc)
            else:
                item.progress = 100.0
                self._set_status(
                    item, DownloadStatus.COMPLETED, "Download complete."
                )
                logger.info(
                    "Completed download: %s -> %s", item.url, item.save_path
                )
            return

    def _run_ytdlp(
        self, item: DownloadItem, options: dict, destination_dir: str
    ) -> None:
        """Execute a single yt-dlp download pass and resolve the output path."""
        with yt_dlp.YoutubeDL(options) as ydl:
            info = ydl.extract_info(item.url, download=True)
            if info is None:
                raise RuntimeError("yt-dlp returned no metadata for this URL.")
            item.title = info.get("title", item.title)
            item.save_path = self._resolve_output_path(
                ydl, info, item, destination_dir
            )

    # -- yt-dlp configuration ---------------------------------------------

    def _build_ytdlp_options(
        self,
        item: DownloadItem,
        destination_dir: str,
        ffmpeg_path: Optional[str] = None,
        fallback: bool = False,
    ) -> dict:
        """Construct the yt-dlp options dict for a given item.

        ``fallback=True`` selects the most broadly available format ("best
        single file") instead of the preferred quality-specific selector; it is
        used for an automatic retry when the preferred formats don't exist.
        """

        outtmpl = os.path.join(destination_dir, "%(title)s.%(ext)s")
        options: dict = {
            "outtmpl": outtmpl,
            "progress_hooks": [self._make_progress_hook(item)],
            "noplaylist": True,  # Treat a single URL as a single video.
            "quiet": True,
            "noprogress": True,  # Progress is rendered by the GUI, not stdout.
            "no_warnings": True,
            "ignoreerrors": False,
            "retries": 3,
            "fragment_retries": 3,
        }
        if ffmpeg_path is not None:
            options["ffmpeg_location"] = ffmpeg_path

        have_ffmpeg = ffmpeg_path is not None
        if item.output_format is OutputFormat.MP3:
            options.update(self._audio_options(item.audio_quality, fallback))
        else:
            options.update(
                self._video_options(item.video_quality, have_ffmpeg, fallback)
            )

        return options

    @staticmethod
    def _video_options(
        quality: VideoQuality, have_ffmpeg: bool = True, fallback: bool = False
    ) -> dict:
        """Return format selection options for MP4 video downloads.

        MP4-native codecs (H.264 video / AAC audio) are preferred so the
        resulting file plays everywhere without transcoding; other codecs are
        accepted as fallbacks. yt-dlp's ``[height<=N]`` selector automatically
        falls back to the next lower available resolution when the requested
        one is unavailable.

        Without ffmpeg, separate video+audio streams can't be merged, so only
        single-file (progressive) formats are requested.
        """

        h = quality.max_height

        if not have_ffmpeg:
            # Progressive-only: a single file that already contains audio.
            if h is None:
                fmt = "b[ext=mp4]/b"
            else:
                fmt = f"b[ext=mp4][height<={h}]/b[height<={h}]/b"
            return {"format": fmt}

        if fallback:
            fmt = "b"  # Best single file of any kind — maximally compatible.
        elif h is None:
            fmt = "bv*[ext=mp4]+ba[ext=m4a]/bv*+ba/b"
        else:
            fmt = (
                f"bv*[ext=mp4][height<={h}]+ba[ext=m4a]/"
                f"bv*[height<={h}]+ba/"
                f"b[height<={h}]/b"
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
    def _audio_options(quality: AudioQuality, fallback: bool = False) -> dict:
        """Return options that extract audio to MP3 at the chosen bitrate."""

        # "0" tells yt-dlp/ffmpeg to use the best available quality.
        preferred = "0" if quality.bitrate_kbps is None else str(quality.bitrate_kbps)
        return {
            # On fallback, accept any single file and extract its audio track.
            "format": "b" if fallback else "bestaudio/best",
            "postprocessors": [
                {
                    "key": "FFmpegExtractAudio",
                    "preferredcodec": "mp3",
                    "preferredquality": preferred,
                }
            ],
        }

    @staticmethod
    def _is_format_error(exc: Exception) -> bool:
        """Return ``True`` when the error means "this format doesn't exist"."""
        text = str(exc).lower()
        return "requested format is not available" in text or (
            "no video formats" in text
        )

    # -- Progress / status helpers ----------------------------------------

    def _make_progress_hook(self, item: DownloadItem) -> Callable[[dict], None]:
        """Build a yt-dlp progress hook bound to a specific item."""

        def hook(data: dict) -> None:
            # Honour cancellation requests by aborting the download.
            if self._cancel_requested.is_set():
                raise _CANCEL_RAISE("Canceled by user")

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
        we rebuild the path from the resolved title and target extension. The
        returned path is the *predicted* location: it normally exists, but if
        the prediction misses (unusual post-processor output) we fall back to
        any sibling file that shares the same stem before returning the guess.
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

        # Predicted file is missing: look for a sibling produced from the same
        # stem (e.g. a different extension chosen by the post-processor).
        for path in glob.glob(f"{glob.escape(root)}.*"):
            if os.path.isfile(path):
                return path

        # Nothing on disk matched; return the predicted path so the GUI still
        # shows a meaningful location.
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
        # Sites (YouTube in particular) change frequently; an out-of-date
        # yt-dlp is the usual cause of extraction/signature/403 errors.
        if (
            "sign in to confirm" in text
            or "not a bot" in text
            or "nsig" in text
            or "unable to extract" in text
            or "http error 403" in text
            or "forbidden" in text
        ):
            return (
                "The site rejected the download. This usually means yt-dlp "
                "needs updating — re-run the setup script (setup.sh / "
                "setup.bat), or run 'pip install -U yt-dlp', then try again."
            )
        # Check format errors before the generic "unavailable" branch, since
        # yt-dlp phrases them as "requested format is not available".
        if "requested format" in text or "no video formats" in text:
            return (
                "The requested format/resolution is not available for this "
                "video. Try 'Best available' or a different quality."
            )
        if "copyright" in text:
            return "This video is unavailable due to a copyright claim."
        if "http error 404" in text or "not found" in text:
            return "This video could not be found. Check that the URL is correct."
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
