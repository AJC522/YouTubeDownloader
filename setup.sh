#!/usr/bin/env bash
#
# Video Download Manager — setup / startup script (macOS & Linux)
# -----------------------------------------------------------------
# Installs and updates everything the app needs in one step:
#   1. A Python virtual environment (.venv)
#   2. The Python dependencies from requirements.txt (upgraded to latest
#      allowed versions)
#   3. ffmpeg (external system dependency) via the platform package manager,
#      installing it if missing or updating it if already present
#
# Re-running this script is safe: it brings an existing setup up to date.
#
# Usage:
#   ./setup.sh            # set up / update, then exit
#   ./setup.sh --run      # set up / update, then launch the app
#
set -euo pipefail

# Resolve the project root (directory containing this script) so the script
# works regardless of where it is invoked from.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

VENV_DIR=".venv"

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
    err "Install Python 3.9 or newer and re-run this script."
    exit 1
fi
info "Using Python: $("$PYTHON" --version 2>&1) ($(command -v "$PYTHON"))"

# ---------------------------------------------------------------------------
# 2. Create / reuse the virtual environment and upgrade Python dependencies
# ---------------------------------------------------------------------------
if [ ! -d "$VENV_DIR" ]; then
    info "Creating virtual environment in $VENV_DIR"
    "$PYTHON" -m venv "$VENV_DIR"
else
    info "Reusing existing virtual environment in $VENV_DIR"
fi

# Use the venv's interpreter directly (avoids needing to 'activate').
VENV_PY="$VENV_DIR/bin/python"

info "Upgrading pip, setuptools and wheel"
"$VENV_PY" -m pip install --quiet --upgrade pip setuptools wheel

info "Installing / upgrading Python dependencies from requirements.txt"
# --upgrade pulls the newest versions permitted by requirements.txt so the
# install stays current on every run.
"$VENV_PY" -m pip install --upgrade -r requirements.txt

# ---------------------------------------------------------------------------
# 3. Install / update ffmpeg via the platform package manager
# ---------------------------------------------------------------------------
install_or_update_ffmpeg() {
    local os
    os="$(uname -s)"

    case "$os" in
        Darwin)
            if have brew; then
                if brew list ffmpeg >/dev/null 2>&1; then
                    info "Updating ffmpeg via Homebrew"
                    brew upgrade ffmpeg || info "ffmpeg is already up to date."
                else
                    info "Installing ffmpeg via Homebrew"
                    brew install ffmpeg
                fi
            else
                warn "Homebrew not found. Install it from https://brew.sh/ and then run:"
                warn "    brew install ffmpeg"
            fi
            ;;
        Linux)
            if have apt-get; then
                info "Installing / updating ffmpeg via apt"
                sudo apt-get update
                sudo apt-get install -y --only-upgrade ffmpeg || sudo apt-get install -y ffmpeg
            elif have dnf; then
                info "Installing / updating ffmpeg via dnf"
                sudo dnf install -y ffmpeg || sudo dnf upgrade -y ffmpeg
            elif have pacman; then
                info "Installing / updating ffmpeg via pacman"
                sudo pacman -S --noconfirm --needed ffmpeg
            elif have zypper; then
                info "Installing / updating ffmpeg via zypper"
                sudo zypper install -y ffmpeg || sudo zypper update -y ffmpeg
            elif have apk; then
                info "Installing / updating ffmpeg via apk"
                sudo apk add --upgrade ffmpeg
            else
                warn "No supported package manager found (apt, dnf, pacman, zypper, apk)."
                warn "Please install ffmpeg manually using your distribution's tools."
            fi
            ;;
        *)
            warn "Unsupported OS '$os'. Please install ffmpeg manually."
            ;;
    esac
}

install_or_update_ffmpeg

# Verify ffmpeg ended up on the PATH (mirrors the app's shutil.which check).
if have ffmpeg; then
    info "ffmpeg is available: $(ffmpeg -version 2>/dev/null | head -n1)"
else
    warn "ffmpeg still does not appear to be on your PATH."
    warn "MP3 extraction and high-resolution MP4 muxing will not work until it is."
fi

info "Setup complete."

# ---------------------------------------------------------------------------
# 4. Optionally launch the application
# ---------------------------------------------------------------------------
if [ "${1:-}" = "--run" ]; then
    info "Launching Video Download Manager"
    exec "$VENV_PY" -m app.main
else
    echo
    info "To run the app:"
    echo "    $VENV_PY -m app.main"
    info "Or re-run this script with --run to launch it now:"
    echo "    ./setup.sh --run"
fi
