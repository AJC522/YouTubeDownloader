# Video Download Manager

A clean, modern desktop GUI for downloading online videos and extracting audio,
built with **Python** and **PySide6 (Qt)** on top of **yt-dlp** and **ffmpeg**.

> ⚠️ **Legal disclaimer**
> This tool is intended **only** for downloading content that **you own, have
> explicit permission to download, or that is otherwise legally available for
> offline use** (for example, content released under a permissive licence or in
> the public domain). You are solely responsible for complying with the terms
> of service of any website and with all applicable copyright laws. The authors
> accept no liability for misuse.

---

## Features

- 🎛️ **Modern desktop GUI** — paste one or more URLs and manage everything from
  a single window.
- 📋 **Download queue** — queue multiple items, each showing its URL, format,
  resolution/quality, status, live progress, and final save location.
- 🎬 **MP4 video** downloads with selectable resolution
  (Best available / 1080p / 720p / 480p / 360p). Unavailable resolutions fall
  back automatically to the closest lower one.
- 🎵 **MP3 audio** extraction with selectable bitrate
  (Best available / 320 / 192 / 128 kbps).
- 🔁 **Sequential processing** by default, structured so parallel downloads can
  be added later.
- 🗂️ **Status tracking** — Pending, Downloading, Completed, Failed, Canceled,
  with colour cues and per-row progress bars.
- 📁 **Native folder picker** with a remembered last-used location.
- ⏸️ **Start** and **Pause/Cancel** controls, plus **Remove** and **Clear**.
- 🛡️ **Graceful error handling** for invalid URLs, private/age-restricted/
  removed videos, network failures, and unsupported formats — with friendly
  on-screen messages and a technical log file for troubleshooting.

---

## Project structure

```
YouTubeDownloader/
├── app/
│   ├── __init__.py
│   ├── main.py         # Application entry point
│   ├── gui.py          # PySide6 GUI (window, queue table, threading)
│   ├── downloader.py   # yt-dlp/ffmpeg backend (no GUI code)
│   ├── models.py       # Data models & enums (formats, quality, status)
│   ├── settings.py     # Persistent JSON settings
│   └── logger.py       # Rotating-file logging setup
├── assets/             # Icons / images
├── requirements.txt
└── README.md
```

The downloader logic is deliberately kept separate from the GUI, and downloads
run on a background thread so the interface never freezes.

---

## Requirements

- **Python 3.9+**
- **PySide6** and **yt-dlp** (installed via `requirements.txt`)
- **ffmpeg** (external system dependency, required for MP3 extraction and for
  muxing high-resolution MP4 streams)

---

## Installation

### 1. Clone and create a virtual environment

```bash
git clone https://github.com/ajc522/youtubedownloader.git
cd youtubedownloader

python -m venv .venv
# Windows:        .venv\Scripts\activate
# macOS / Linux:  source .venv/bin/activate
```

### 2. Install the Python dependencies

```bash
pip install -r requirements.txt
```

### 3. Install ffmpeg

ffmpeg is **not** a Python package and must be installed separately.

- **Windows**
  - With [winget](https://learn.microsoft.com/windows/package-manager/):
    `winget install Gyan.FFmpeg`
  - Or with [Chocolatey](https://chocolatey.org/): `choco install ffmpeg`
  - Or download a build from <https://www.gyan.dev/ffmpeg/builds/> and add its
    `bin` folder to your `PATH`.
- **macOS** (with [Homebrew](https://brew.sh/)): `brew install ffmpeg`
- **Linux**
  - Debian/Ubuntu: `sudo apt install ffmpeg`
  - Fedora: `sudo dnf install ffmpeg`
  - Arch: `sudo pacman -S ffmpeg`

Verify it is on your `PATH`:

```bash
ffmpeg -version
```

The application checks for ffmpeg on startup and before each download, and shows
a clear message if it is missing.

---

## Usage

From the project root (with your virtual environment active):

```bash
python -m app.main
```

Then:

1. **Paste one or more video URLs** into the text box (one per line).
2. Choose the **Format** (MP4 video or MP3 audio) and the
   **Resolution / Audio quality**.
3. Click **Add to Queue**. Invalid or empty URLs are skipped with a notice.
4. Click **Choose Folder** to pick where files are saved (remembered for next
   time).
5. Click **Start Downloads**. Watch progress and status update live in the
   queue.
6. Use **Pause / Cancel** to stop, **Remove Selected** to drop items, or
   **Clear Queue** to empty it.

---

## Configuration & logs

The application stores its settings and log file in a per-user directory (no
hardcoded paths):

- **Windows:** `%APPDATA%\VideoDownloadManager\`
- **macOS:** `~/Library/Application Support/VideoDownloadManager/`
- **Linux:** `~/.local/share/VideoDownloadManager/`

It contains:

- `settings.json` — last download folder and last format/quality choices.
- `video_download_manager.log` — rotating technical log for troubleshooting.

---

## Extending the app

The format system is enum-based (`OutputFormat` in `app/models.py`) and the
format-to-options logic lives in `app/downloader.py`, so adding a new output
format (e.g. WAV, MKV) is a matter of extending the enum and adding a matching
options branch. Sequential processing is handled by a single `DownloadWorker`;
a pool of workers could be introduced to enable parallel downloads.

---

## Troubleshooting

| Symptom | Likely cause / fix |
| --- | --- |
| "ffmpeg was not found" | Install ffmpeg and ensure it is on your `PATH`. |
| "yt-dlp is not installed" | Run `pip install -r requirements.txt`. |
| "requested format/resolution not available" | Try **Best available** or a lower resolution. |
| Downloads suddenly fail for a site | Update yt-dlp: `pip install -U yt-dlp`. |
| Need more detail | Check `video_download_manager.log` in the config directory. |

---

## License

Provided as-is for personal, lawful use. See the legal disclaimer above.
