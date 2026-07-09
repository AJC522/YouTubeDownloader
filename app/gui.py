"""PySide6 GUI for the Video Download Manager.

The GUI is kept strictly separate from the download backend (``downloader.py``).
Downloads run on a background ``QThread`` so the interface never freezes, and
progress/status updates flow back to the widgets via Qt signals.
"""

from __future__ import annotations

import os
from typing import Dict, List

from PySide6.QtCore import QObject, Qt, QThread, QUrl, Signal, Slot
from PySide6.QtGui import QColor, QDesktopServices
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QFileDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QProgressBar,
    QPlainTextEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from .downloader import (
    Downloader,
    ffmpeg_source,
    is_ffmpeg_available,
    is_ytdlp_available,
    ytdlp_version,
)
from .logger import get_log_file_path, logger
from .models import (
    AudioQuality,
    DownloadItem,
    DownloadStatus,
    OutputFormat,
    VideoQuality,
)
from .settings import Settings

# Column layout for the queue table.
COL_URL = 0
COL_FORMAT = 1
COL_QUALITY = 2
COL_STATUS = 3
COL_PROGRESS = 4
COL_LOCATION = 5
COLUMN_HEADERS = ["URL", "Format", "Quality", "Status", "Progress", "Save Location"]

# Colour cues for each status, keyed by status value.
STATUS_COLORS: Dict[DownloadStatus, str] = {
    DownloadStatus.PENDING: "#6c757d",
    DownloadStatus.DOWNLOADING: "#0d6efd",
    DownloadStatus.COMPLETED: "#198754",
    DownloadStatus.FAILED: "#dc3545",
    DownloadStatus.CANCELED: "#fd7e14",
}
# Used when a status has no explicit colour assigned above.
DEFAULT_STATUS_COLOR = "#000000"


class DownloadWorker(QObject):
    """Processes the download queue sequentially on a background thread.

    The worker owns a :class:`Downloader` and walks the shared list of items,
    downloading every ``PENDING`` entry in order. Updates are relayed to the GUI
    through Qt signals (which marshal safely across the thread boundary).

    Sequential processing is intentional, but the structure — a single worker
    iterating a list — makes it straightforward to add a pool of workers later
    for parallel downloads.
    """

    progress = Signal(int, float, str)  # item_id, percent, detail
    item_status = Signal(int, str, str)  # item_id, status value, message
    finished = Signal()  # the whole queue has been processed/stopped

    def __init__(self, items: List[DownloadItem], destination_dir: str) -> None:
        super().__init__()
        self._items = items
        self._destination_dir = destination_dir
        self._stop_requested = False
        self._downloader = Downloader(
            progress_callback=self._on_progress,
            status_callback=self._on_status,
        )

    @Slot()
    def run(self) -> None:
        """Entry point executed on the worker thread."""
        logger.info("Download worker started for %d item(s).", len(self._items))
        for item in self._items:
            if self._stop_requested:
                break
            # Only process items still waiting; skip completed/failed ones.
            if item.status is not DownloadStatus.PENDING:
                continue
            self._downloader.download(item, self._destination_dir)
        logger.info("Download worker finished.")
        self.finished.emit()

    def stop(self) -> None:
        """Request that the queue halt after cancelling the current item."""
        self._stop_requested = True
        self._downloader.request_cancel()

    # Callbacks invoked by the Downloader (already on the worker thread).
    def _on_progress(self, item: DownloadItem, percent: float, detail: str) -> None:
        self.progress.emit(item.item_id, percent, detail)

    def _on_status(
        self, item: DownloadItem, status: DownloadStatus, message: str
    ) -> None:
        self.item_status.emit(item.item_id, status.value, message)


class MainWindow(QWidget):
    """The application's main window."""

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Video Download Manager")
        self.resize(960, 640)

        self._settings = Settings()
        self._items: List[DownloadItem] = []
        # Maps keyed by the stable item id for fast lookups when signals arrive.
        self._row_by_id: Dict[int, int] = {}
        self._item_by_id: Dict[int, DownloadItem] = {}
        self._progress_bars: Dict[int, QProgressBar] = {}

        self._thread: QThread | None = None
        self._worker: DownloadWorker | None = None

        self._download_dir: str = self._settings.get("download_directory", "")

        self._build_ui()
        self._restore_last_choices()
        self._check_dependencies()
        self._show_welcome_if_first_run()

    # -- UI construction ---------------------------------------------------

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)

        root.addWidget(self._build_input_section())
        root.addWidget(self._build_queue_table(), stretch=1)
        root.addLayout(self._build_queue_buttons())
        root.addLayout(self._build_location_row())
        root.addLayout(self._build_action_row())

        self._status_label = QLabel("Ready.")
        self._status_label.setStyleSheet("color: #495057; padding: 4px;")
        root.addWidget(self._status_label)

    def _build_input_section(self) -> QWidget:
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)

        layout.addWidget(QLabel("Paste one or more video URLs (one per line):"))
        self._url_input = QPlainTextEdit()
        self._url_input.setPlaceholderText(
            "https://example.com/watch?v=...\nhttps://example.com/watch?v=..."
        )
        self._url_input.setFixedHeight(80)
        layout.addWidget(self._url_input)

        controls = QHBoxLayout()

        controls.addWidget(QLabel("Format:"))
        self._format_combo = QComboBox()
        for fmt in OutputFormat:
            self._format_combo.addItem(fmt.value, fmt)
        self._format_combo.currentIndexChanged.connect(self._on_format_changed)
        controls.addWidget(self._format_combo)

        self._quality_label = QLabel("Resolution:")
        controls.addWidget(self._quality_label)

        # Video resolution options.
        self._video_quality_combo = QComboBox()
        for quality in VideoQuality:
            self._video_quality_combo.addItem(quality.label, quality)
        controls.addWidget(self._video_quality_combo)

        # Audio bitrate options (shown only for MP3).
        self._audio_quality_combo = QComboBox()
        for quality in AudioQuality:
            self._audio_quality_combo.addItem(quality.label, quality)
        controls.addWidget(self._audio_quality_combo)

        controls.addStretch(1)

        self._add_button = QPushButton("Add to Queue")
        self._add_button.clicked.connect(self._on_add_to_queue)
        controls.addWidget(self._add_button)

        layout.addLayout(controls)
        return container

    def _build_queue_table(self) -> QTableWidget:
        self._table = QTableWidget(0, len(COLUMN_HEADERS))
        self._table.setHorizontalHeaderLabels(COLUMN_HEADERS)
        self._table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self._table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self._table.verticalHeader().setVisible(False)

        header = self._table.horizontalHeader()
        header.setSectionResizeMode(COL_URL, QHeaderView.Stretch)
        header.setSectionResizeMode(COL_FORMAT, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(COL_QUALITY, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(COL_STATUS, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(COL_PROGRESS, QHeaderView.Fixed)
        header.setSectionResizeMode(COL_LOCATION, QHeaderView.Stretch)
        self._table.setColumnWidth(COL_PROGRESS, 160)
        return self._table

    def _build_queue_buttons(self) -> QHBoxLayout:
        layout = QHBoxLayout()
        self._remove_button = QPushButton("Remove Selected")
        self._remove_button.clicked.connect(self._on_remove_selected)
        self._clear_button = QPushButton("Clear Queue")
        self._clear_button.clicked.connect(self._on_clear_queue)
        layout.addWidget(self._remove_button)
        layout.addWidget(self._clear_button)
        layout.addStretch(1)
        return layout

    def _build_location_row(self) -> QHBoxLayout:
        layout = QHBoxLayout()
        layout.addWidget(QLabel("Save to:"))
        self._location_label = QLabel(self._download_dir)
        self._location_label.setStyleSheet(
            "border: 1px solid #ced4da; padding: 4px; border-radius: 4px;"
        )
        self._location_label.setTextInteractionFlags(
            Qt.TextSelectableByMouse
        )
        layout.addWidget(self._location_label, stretch=1)
        self._choose_folder_button = QPushButton("Choose Folder")
        self._choose_folder_button.clicked.connect(self._on_choose_folder)
        layout.addWidget(self._choose_folder_button)
        self._open_folder_button = QPushButton("Open Folder")
        self._open_folder_button.setToolTip(
            "Open the download folder in your file manager."
        )
        self._open_folder_button.clicked.connect(self._on_open_folder)
        layout.addWidget(self._open_folder_button)
        return layout

    def _build_action_row(self) -> QHBoxLayout:
        layout = QHBoxLayout()
        self._start_button = QPushButton("Start Downloads")
        self._start_button.clicked.connect(self._on_start)
        self._cancel_button = QPushButton("Pause / Cancel")
        self._cancel_button.clicked.connect(self._on_cancel)
        self._cancel_button.setEnabled(False)
        layout.addStretch(1)
        layout.addWidget(self._start_button)
        layout.addWidget(self._cancel_button)
        return layout

    # -- Startup helpers ---------------------------------------------------

    def _restore_last_choices(self) -> None:
        """Re-apply the format/quality selections from the previous session."""
        fmt_label = self._settings.get("last_output_format")
        idx = self._format_combo.findText(fmt_label)
        if idx >= 0:
            self._format_combo.setCurrentIndex(idx)

        vq_label = self._settings.get("last_video_quality")
        vq_idx = self._video_quality_combo.findText(vq_label)
        if vq_idx >= 0:
            self._video_quality_combo.setCurrentIndex(vq_idx)

        aq_label = self._settings.get("last_audio_quality")
        aq_idx = self._audio_quality_combo.findText(aq_label)
        if aq_idx >= 0:
            self._audio_quality_combo.setCurrentIndex(aq_idx)

        self._on_format_changed()

    def _check_dependencies(self) -> None:
        """Warn the user up-front if yt-dlp or ffmpeg are missing.

        Both normally install automatically with the app's Python
        dependencies (ffmpeg ships inside the imageio-ffmpeg package), so a
        warning here means the install is incomplete — the fix is always to
        re-run the setup script.
        """
        problems = []
        if not is_ytdlp_available():
            problems.append("• yt-dlp (the download engine) is not installed.")
        if not is_ffmpeg_available():
            problems.append(
                "• ffmpeg could not be found, so MP3 conversion is disabled "
                "and MP4 downloads are limited to lower resolutions."
            )
        if problems:
            QMessageBox.warning(
                self,
                "Setup is incomplete",
                "Some parts of the app are missing:\n\n"
                + "\n".join(problems)
                + "\n\nTo fix this, re-run the setup script that came with "
                "the app (setup.sh on macOS/Linux, setup.bat on Windows), "
                "or run 'pip install -r requirements.txt'.",
            )
            self._set_status("Warning: setup incomplete (see log).")
        else:
            source, _ = ffmpeg_source()
            logger.info(
                "Dependencies OK: yt-dlp %s, ffmpeg (%s).",
                ytdlp_version(),
                source,
            )

    def _show_welcome_if_first_run(self) -> None:
        """Show a short one-time guide the first time the app is opened."""
        if self._settings.get("first_run_done"):
            return
        QMessageBox.information(
            self,
            "Welcome!",
            "<b>Welcome to Video Download Manager!</b><br><br>"
            "Downloading is three steps:<br>"
            "1. <b>Paste</b> one or more video links into the box at the top.<br>"
            "2. Pick <b>MP4 video</b> or <b>MP3 audio</b> (and a quality).<br>"
            "3. Click <b>Start Downloads</b>.<br><br>"
            f"Files are saved to <b>{self._download_dir}</b> — use "
            "<i>Choose Folder</i> to change that anytime.<br><br>"
            "Everything the app needs is already included. Happy downloading!",
        )
        self._settings.set("first_run_done", True)

    # -- Format/quality interaction ---------------------------------------

    def _on_format_changed(self) -> None:
        """Show the quality control relevant to the selected output format."""
        fmt: OutputFormat = self._format_combo.currentData()
        is_audio = fmt.is_audio_only
        self._video_quality_combo.setVisible(not is_audio)
        self._audio_quality_combo.setVisible(is_audio)
        self._quality_label.setText("Audio quality:" if is_audio else "Resolution:")

    # -- Queue management --------------------------------------------------

    def _on_add_to_queue(self) -> None:
        """Validate the URL input and append items to the queue."""
        self._add_urls_from_input(interactive=True)

    def _add_urls_from_input(self, interactive: bool) -> int:
        """Queue every URL currently in the input box; return the count added.

        ``interactive`` controls whether an empty/invalid input pops a warning
        dialog. ``_on_start`` also calls this silently so users can paste
        links and click "Start Downloads" directly, without needing to know
        about "Add to Queue" first.
        """
        raw = self._url_input.toPlainText().strip()
        if not raw:
            if interactive:
                self._warn("Please enter at least one video URL.")
            return 0

        fmt: OutputFormat = self._format_combo.currentData()
        video_quality: VideoQuality = self._video_quality_combo.currentData()
        audio_quality: AudioQuality = self._audio_quality_combo.currentData()

        added = 0
        skipped = 0
        for line in raw.splitlines():
            url = line.strip()
            if not url:
                continue
            if not self._looks_like_url(url):
                skipped += 1
                logger.warning("Skipping invalid URL: %s", url)
                continue
            item = DownloadItem(
                url=url,
                output_format=fmt,
                video_quality=video_quality,
                audio_quality=audio_quality,
            )
            self._items.append(item)
            self._append_row(item)
            added += 1

        # Persist the chosen format/quality for next time (single disk write).
        self._settings.update(
            {
                "last_output_format": fmt.value,
                "last_video_quality": video_quality.label,
                "last_audio_quality": audio_quality.label,
            }
        )

        self._url_input.clear()

        if added and skipped:
            self._set_status(
                f"Added {added} URL(s); skipped {skipped} invalid URL(s)."
            )
        elif added:
            self._set_status(f"Added {added} URL(s) to the queue.")
        elif interactive:
            self._warn(
                "None of the entered lines looked like valid URLs. "
                "URLs should start with http:// or https://."
            )
        return added

    @staticmethod
    def _looks_like_url(text: str) -> bool:
        """Lightweight URL sanity check before queuing."""
        lowered = text.lower()
        return lowered.startswith("http://") or lowered.startswith("https://")

    def _append_row(self, item: DownloadItem) -> None:
        row = self._table.rowCount()
        self._table.insertRow(row)
        self._row_by_id[item.item_id] = row
        self._item_by_id[item.item_id] = item

        url_item = QTableWidgetItem(item.url)
        # Stash the stable item id on the row so we can recover it after rows
        # are reordered or removed, even when URLs are duplicated.
        url_item.setData(Qt.UserRole, item.item_id)
        self._table.setItem(row, COL_URL, url_item)
        self._table.setItem(
            row, COL_FORMAT, QTableWidgetItem(item.output_format.value)
        )
        self._table.setItem(
            row, COL_QUALITY, QTableWidgetItem(item.quality_label)
        )

        status_item = QTableWidgetItem(item.status.value)
        status_item.setForeground(
            QColor(STATUS_COLORS.get(item.status, DEFAULT_STATUS_COLOR))
        )
        self._table.setItem(row, COL_STATUS, status_item)

        progress = QProgressBar()
        progress.setRange(0, 100)
        progress.setValue(0)
        progress.setTextVisible(True)
        self._table.setCellWidget(row, COL_PROGRESS, progress)
        self._progress_bars[item.item_id] = progress

        self._table.setItem(row, COL_LOCATION, QTableWidgetItem(""))

    def _on_remove_selected(self) -> None:
        """Remove the selected queue rows (only when not downloading)."""
        if self._is_running():
            self._warn("Cannot modify the queue while downloads are running.")
            return

        selected_rows = sorted(
            {index.row() for index in self._table.selectedIndexes()}, reverse=True
        )
        if not selected_rows:
            self._warn("Select one or more rows to remove.")
            return

        for row in selected_rows:
            self._remove_row(row)
        self._rebuild_row_index()
        self._set_status(f"Removed {len(selected_rows)} item(s).")

    def _remove_row(self, row: int) -> None:
        # Find the item id associated with this row to keep maps in sync.
        item_id = self._item_id_for_row(row)
        if item_id is not None:
            self._items = [i for i in self._items if i.item_id != item_id]
            self._progress_bars.pop(item_id, None)
            self._item_by_id.pop(item_id, None)
        self._table.removeRow(row)

    def _on_clear_queue(self) -> None:
        if self._is_running():
            self._warn("Cannot clear the queue while downloads are running.")
            return
        self._table.setRowCount(0)
        self._items.clear()
        self._row_by_id.clear()
        self._item_by_id.clear()
        self._progress_bars.clear()
        self._set_status("Queue cleared.")

    # -- Save location -----------------------------------------------------

    def _on_choose_folder(self) -> None:
        """Open the native folder picker and remember the choice."""
        directory = QFileDialog.getExistingDirectory(
            self, "Choose download folder", self._download_dir or ""
        )
        if directory:
            self._download_dir = directory
            self._location_label.setText(directory)
            self._settings.set("download_directory", directory)
            self._set_status(f"Save location set to: {directory}")

    def _on_open_folder(self) -> None:
        """Open the current download folder in the system file manager."""
        if not self._download_dir or not os.path.isdir(self._download_dir):
            self._warn("The download folder does not exist yet. Choose one first.")
            return
        QDesktopServices.openUrl(QUrl.fromLocalFile(self._download_dir))

    # -- Start / cancel ----------------------------------------------------

    def _on_start(self) -> None:
        """Begin processing the queue on a background thread."""
        if self._is_running():
            return
        # Convenience: URLs still sitting in the input box are queued
        # automatically, so pasting a link and hitting Start "just works".
        self._add_urls_from_input(interactive=False)
        if not self._items:
            self._warn(
                "Paste at least one video URL into the box at the top, "
                "then click Start Downloads."
            )
            return
        if not self._download_dir:
            self._warn("Please choose a save location first.")
            return
        if not os.path.isdir(self._download_dir):
            self._warn(
                "The save location no longer exists. Please choose a folder "
                "again."
            )
            return
        if not os.access(self._download_dir, os.W_OK):
            self._warn(
                "The save location is not writable. Please choose a different "
                "folder."
            )
            return

        pending = [i for i in self._items if i.status is DownloadStatus.PENDING]
        if not pending:
            self._warn("There are no pending items to download.")
            return

        # Spin up the worker on a dedicated QThread.
        self._thread = QThread()
        self._worker = DownloadWorker(self._items, self._download_dir)
        self._worker.moveToThread(self._thread)

        self._thread.started.connect(self._worker.run)
        self._worker.progress.connect(self._on_worker_progress)
        self._worker.item_status.connect(self._on_worker_status)
        # Canonical Qt teardown: when the worker is done it stops the thread's
        # event loop and schedules its own deletion (while its event loop is
        # still alive to process the deferred delete). GUI tidy-up and thread
        # deletion run off the thread's ``finished`` signal, by which point the
        # thread has actually stopped — so we never block the GUI on wait().
        self._worker.finished.connect(self._thread.quit)
        self._worker.finished.connect(self._worker.deleteLater)
        self._thread.finished.connect(self._on_queue_finished)
        self._thread.finished.connect(self._thread.deleteLater)

        self._set_running_ui(True)
        self._set_status("Downloading…")
        self._thread.start()

    def _on_cancel(self) -> None:
        """Cancel the in-flight download and stop processing the queue."""
        if self._worker is not None:
            self._worker.stop()
            self._set_status("Cancelling… finishing the current item.")
            self._cancel_button.setEnabled(False)

    # -- Worker signal handlers (run on the GUI thread) -------------------

    @Slot(int, float, str)
    def _on_worker_progress(
        self, item_id: int, percent: float, detail: str
    ) -> None:
        bar = self._progress_bars.get(item_id)
        if bar is not None:
            bar.setValue(int(percent))
        row = self._row_by_id.get(item_id)
        if row is not None:
            status_cell = self._table.item(row, COL_STATUS)
            if status_cell is not None and detail:
                status_cell.setToolTip(detail)
        # Mirror the live speed/ETA detail in the status bar so progress is
        # visible without hovering over the table.
        if detail:
            item = self._item_by_id.get(item_id)
            title = (item.title or item.url) if item is not None else ""
            self._set_status(f"{detail} — {title}" if title else detail)

    @Slot(int, str, str)
    def _on_worker_status(
        self, item_id: int, status_value: str, message: str
    ) -> None:
        status = DownloadStatus(status_value)
        row = self._row_by_id.get(item_id)
        item = self._find_item(item_id)
        if row is None or item is None:
            return

        self._update_status_cell(row, status, message)

        if status is DownloadStatus.COMPLETED:
            self._apply_completed(row, item_id, item)
        elif status is DownloadStatus.FAILED:
            self._apply_failed(row, message)

    def _update_status_cell(
        self, row: int, status: DownloadStatus, message: str
    ) -> None:
        """Set the text, colour and tooltip of a row's status cell."""
        status_cell = self._table.item(row, COL_STATUS)
        if status_cell is not None:
            status_cell.setText(status.value)
            status_cell.setForeground(
                QColor(STATUS_COLORS.get(status, DEFAULT_STATUS_COLOR))
            )
            status_cell.setToolTip(message)

    def _apply_completed(
        self, row: int, item_id: int, item: DownloadItem
    ) -> None:
        """Reflect a successful download: show the save path and fill the bar."""
        location_cell = self._table.item(row, COL_LOCATION)
        if location_cell is not None:
            location_cell.setText(item.save_path)
            location_cell.setToolTip(item.save_path)
        bar = self._progress_bars.get(item_id)
        if bar is not None:
            bar.setValue(100)

    def _apply_failed(self, row: int, message: str) -> None:
        """Reflect a failed download.

        The error text lives on the status cell's tooltip (set by
        :meth:`_update_status_cell`); the Save Location column is left empty so
        it never conflates an error message with a real file path.
        """
        location_cell = self._table.item(row, COL_LOCATION)
        if location_cell is not None:
            location_cell.setText("")

    @Slot()
    def _on_queue_finished(self) -> None:
        """Tidy up after the worker thread has finished.

        Connected to ``QThread.finished``, so the thread has already stopped;
        the worker and thread objects delete themselves via ``deleteLater``.
        """
        self._thread = None
        self._worker = None
        self._set_running_ui(False)

        summary = self._build_summary()
        self._set_status(summary)
        logger.info(summary)

    # -- Small helpers -----------------------------------------------------

    def _build_summary(self) -> str:
        counts: Dict[DownloadStatus, int] = {}
        for item in self._items:
            counts[item.status] = counts.get(item.status, 0) + 1
        parts = [
            f"{count} {status.value}"
            for status, count in counts.items()
            if count
        ]
        return "Finished. " + ", ".join(parts) if parts else "Finished."

    def _set_running_ui(self, running: bool) -> None:
        """Enable/disable controls based on whether a run is in progress."""
        self._start_button.setEnabled(not running)
        self._cancel_button.setEnabled(running)
        self._add_button.setEnabled(not running)
        self._remove_button.setEnabled(not running)
        self._clear_button.setEnabled(not running)
        self._choose_folder_button.setEnabled(not running)

    def _is_running(self) -> bool:
        return self._thread is not None and self._thread.isRunning()

    def _item_id_for_row(self, row: int) -> int | None:
        url_item = self._table.item(row, COL_URL)
        if url_item is None:
            return None
        return url_item.data(Qt.UserRole)

    def _rebuild_row_index(self) -> None:
        """Recompute the id->row map after rows have been removed."""
        self._row_by_id.clear()
        for row in range(self._table.rowCount()):
            item_id = self._item_id_for_row(row)
            if item_id is not None:
                self._row_by_id[item_id] = row

    def _find_item(self, item_id: int) -> DownloadItem | None:
        return self._item_by_id.get(item_id)

    def _set_status(self, text: str) -> None:
        self._status_label.setText(text)

    def _warn(self, message: str) -> None:
        QMessageBox.warning(self, "Video Download Manager", message)
        self._set_status(message)

    # -- Window lifecycle --------------------------------------------------

    def closeEvent(self, event) -> None:  # noqa: N802 - Qt naming.
        """Ensure any running download is stopped cleanly on exit."""
        if self._is_running():
            confirm = QMessageBox.question(
                self,
                "Quit",
                "A download is in progress. Stop it and quit?",
                QMessageBox.Yes | QMessageBox.No,
            )
            if confirm != QMessageBox.Yes:
                event.ignore()
                return
            if self._worker is not None:
                self._worker.stop()
            if self._thread is not None:
                self._thread.quit()
                self._thread.wait(5000)
        logger.info("Application closing. Log file at %s", get_log_file_path())
        event.accept()
