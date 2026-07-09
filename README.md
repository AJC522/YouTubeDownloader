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

## Get started in one step

The only thing you need installed beforehand is
**[Python 3.9+](https://www.python.org/downloads/)** (on Windows, tick
*"Add Python to PATH"* during install). Everything else — the GUI toolkit,
the yt-dlp download engine, and even **ffmpeg** — is installed automatically.

- **Windows:** double-click **`setup.bat`**
- **macOS / Linux:** open a terminal in the project folder and run:

  ```bash
  ./setup.sh
  ```

That's it. The script sets up a private Python environment, installs/updates
all dependencies, and launches the app. **Run the same script any time you want
to open the app again** — it also keeps everything up to date, which matters
because video sites change frequently and an out-of-date downloader is the most
common cause of failing downloads.

> No separate ffmpeg install is needed: a static ffmpeg binary ships with the
> Python dependencies (via `imageio-ffmpeg`). If you already have ffmpeg on
> your PATH, the app uses that instead.

### Using the app

1. **Paste one or more video links** into the box at the top (one per line).
2. Pick **MP4 video** or **MP3 audio**, and a resolution/quality.
3. Click **Start Downloads** — links still in the box are queued automatically.

Files are saved to your **Downloads** folder by default; use **Choose Folder**
to change that (remembered for next time) and **Open Folder** to jump straight
to your downloaded files. A short welcome guide appears the first time you open
the app.

---

## Features

- 🎛️ **Modern desktop GUI** — paste one or more URLs and manage everything from
  a single window.
- 🚀 **Zero-config setup** — one script installs everything, including a
  bundled ffmpeg; sensible defaults mean you can download immediately.
- 📋 **Download queue** — queue multiple items, each showing its URL, format,
  resolution/quality, status, live progress, and final save location.
- 🎬 **MP4 video** downloads with selectable resolution
  (Best available / 1080p / 720p / 480p / 360p). Unavailable resolutions fall
  back automatically to the closest lower one, and widely-compatible
  H.264/AAC streams are preferred so files play everywhere.
- 🎵 **MP3 audio** extraction with selectable bitrate
  (Best available / 320 / 192 / 128 kbps).
- 🔁 **Automatic retry** with a more compatible format when the preferred one
  isn't offered for a video.
- 🗂️ **Status tracking** — Pending, Downloading, Completed, Failed, Canceled,
  with colour cues, per-row progress bars, and live speed/ETA in the status
  bar.
- 📁 **Native folder picker** with a remembered last-used location and an
  **Open Folder** shortcut.
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
├── setup.sh            # One-step setup & launch (macOS / Linux)
├── setup.ps1           # One-step setup & launch (Windows PowerShell)
├── setup.bat           # Double-clickable wrapper for setup.ps1 (Windows)
├── requirements.txt
└── README.md
```

The downloader logic is deliberately kept separate from the GUI, and downloads
run on a background thread so the interface never freezes.

---

## Manual setup (optional)

Prefer to manage the environment yourself? All the setup script really does is:

```bash
git clone https://github.com/ajc522/youtubedownloader.git
cd youtubedownloader

python -m venv .venv
# Windows:        .venv\Scripts\activate
# macOS / Linux:  source .venv/bin/activate

pip install -r requirements.txt
python -m app.main
```

`requirements.txt` pulls in **PySide6** (GUI), **yt-dlp** (download engine) and
**imageio-ffmpeg** (bundled ffmpeg binary). A system-wide ffmpeg on your `PATH`
is used in preference to the bundled one when present, but is not required.

---

## Configuration & logs

The application stores its settings and log file in a per-user directory (no
hardcoded paths):

- **Windows:** `%APPDATA%\VideoDownloadManager\`
- **macOS:** `~/Library/Application Support/VideoDownloadManager/`
- **Linux:** `~/.local/share/VideoDownloadManager/`

It contains:

- `settings.json` — last download folder, last format/quality choices, and the
  first-run flag.
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
| Downloads suddenly fail / "the site rejected the download" | The site changed and yt-dlp needs updating. Re-run the setup script (`./setup.sh` / `setup.bat`) — it updates everything. |
| "Setup is incomplete" warning on startup | A dependency didn't install. Re-run the setup script, or `pip install -r requirements.txt`. |
| "requested format/resolution not available" | The app already retries with a compatible format automatically; if it still fails, try **Best available**. |
| MP3 conversion fails | ffmpeg is missing — re-run the setup script to restore the bundled copy. |
| Nothing happens on double-clicking `setup.bat` | Install Python from <https://www.python.org/downloads/> and tick *"Add Python to PATH"*, then try again. |
| Need more detail | Check `video_download_manager.log` in the config directory (paths above). |

---

## License

Provided as-is for personal, lawful use. See the legal disclaimer above.
