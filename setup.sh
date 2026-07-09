#!/usr/bin/env bash
#
# Video Download Manager — one-step setup & launch (macOS & Linux)
# -----------------------------------------------------------------
# Run this once and you're done:
#
#   ./setup.sh
#
# It creates a private Python environment (.venv), installs/updates all
# dependencies — including a bundled ffmpeg, so there is nothing else to
# install — and then launches the app.
#
# Re-running it is always safe: it updates an existing install (useful when
# downloads stop working because a site changed and yt-dlp needs updating).
#
# Options:
#   ./setup.sh                # set up / update, then launch the app
#   ./setup.sh --setup-only   # set up / update, but don't launch
#
set -euo pipefail

# Resolve the project root (directory containing this script) so the script
# works regardless of where it is invoked from.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

VENV_DIR=".venv"
LAUNCH=1
case "${1:-}" in
    --setup-only|--no-run) LAUNCH=0 ;;
    --run|"") ;;  # --run kept for backwards compatibility; launching is now the default.
    *) echo "Unknown option: $1 (use --setup-only to skip launching)"; exit 1 ;;
esac

info()  { printf '\033[1;34m==>\033[0m %s\n' "$*"; }
warn()  { printf '\033[1;33m[!]\033[0m %s\n' "$*"; }
err()   { printf '\033[1;31m[x]\033[0m %s\n' "$*" >&2; }

have() { command -v "$1" >/dev/null 2>&1; }

# ---------------------------------------------------------------------------
# 1. Locate a usable Python interpreter (3.9+)
# ---------------------------------------------------------------------------
PYTHON=""
for candidate in python3 python; do
    if have "$candidate"; then
        if "$candidate" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 9) else 1)' 2>/dev/null; then
            PYTHON="$candidate"
            break
        fi
    fi
done

if [ -z "$PYTHON" ]; then
    err "Python 3.9+ is required but was not found on your PATH."
    err "Install Python from https://www.python.org/downloads/ and re-run this script."
    exit 1
fi
info "Using Python: $("$PYTHON" --version 2>&1) ($(command -v "$PYTHON"))"

# ---------------------------------------------------------------------------
# 2. Create / reuse the virtual environment and install dependencies
# ---------------------------------------------------------------------------
if [ ! -d "$VENV_DIR" ]; then
    info "Creating virtual environment in $VENV_DIR"
    "$PYTHON" -m venv "$VENV_DIR"
else
    info "Reusing existing virtual environment in $VENV_DIR"
fi

# Use the venv's interpreter directly (avoids needing to 'activate').
VENV_PY="$VENV_DIR/bin/python"

info "Upgrading pip"
"$VENV_PY" -m pip install --quiet --upgrade pip

info "Installing / updating dependencies (GUI, yt-dlp and bundled ffmpeg)"
# --upgrade pulls the newest versions permitted by requirements.txt so the
# install stays current on every run.
"$VENV_PY" -m pip install --upgrade -r requirements.txt

# ---------------------------------------------------------------------------
# 3. Verify everything the app needs is in place
# ---------------------------------------------------------------------------
info "Checking the installation"
if "$VENV_PY" - <<'EOF'
import sys
sys.path.insert(0, ".")
from app.downloader import ffmpeg_source, ytdlp_version

version = ytdlp_version()
source, path = ffmpeg_source()
print(f"    yt-dlp {version}")
print(f"    ffmpeg: {source}" + (f" ({path})" if path else ""))
sys.exit(0 if version and source != "missing" else 1)
EOF
then
    info "Everything is ready."
else
    warn "Something is missing — see the lines above. Try re-running this script."
fi

# ---------------------------------------------------------------------------
# 4. Launch the application
# ---------------------------------------------------------------------------
if [ "$LAUNCH" = 1 ]; then
    info "Launching Video Download Manager"
    exec "$VENV_PY" -m app.main
else
    echo
    info "Setup complete. To run the app later:"
    echo "    ./setup.sh"
fi
