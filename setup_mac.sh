#!/usr/bin/env bash
# setup_mac.sh — One-command setup and launch for Warrior IPTV Player on macOS.
#
# Usage:
#   chmod +x setup_mac.sh
#   ./setup_mac.sh          # set up and launch
#   ./setup_mac.sh --run    # skip setup, just launch (after first run)
set -euo pipefail

REPO_DIR="$(cd "$(dirname "$0")" && pwd)"
VENV="$REPO_DIR/.venv"
PYTHON="$VENV/bin/python"

# ── colour helpers ───────────────────────────────────────────────────────────
green()  { printf '\033[0;32m%s\033[0m\n' "$*"; }
yellow() { printf '\033[0;33m%s\033[0m\n' "$*"; }
red()    { printf '\033[0;31m%s\033[0m\n' "$*"; }
step()   { printf '\n\033[1;34m▶  %s\033[0m\n' "$*"; }

# ── skip setup if --run was passed ───────────────────────────────────────────
if [[ "${1:-}" == "--run" ]]; then
    if [[ ! -f "$PYTHON" ]]; then
        red "Virtual environment not found. Run ./setup_mac.sh first."
        exit 1
    fi
    exec "$PYTHON" "$REPO_DIR/src/main.py" "${@:2}"
fi

# ── 1. Check macOS ───────────────────────────────────────────────────────────
if [[ "$(uname)" != "Darwin" ]]; then
    red "This script is for macOS only."
    exit 1
fi
green "macOS detected."

# ── 2. Homebrew ──────────────────────────────────────────────────────────────
step "Checking Homebrew"
if ! command -v brew &>/dev/null; then
    yellow "Homebrew not found. Installing..."
    /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
    # Add Homebrew to PATH for Apple Silicon
    if [[ -f /opt/homebrew/bin/brew ]]; then
        eval "$(/opt/homebrew/bin/brew shellenv)"
    fi
else
    green "Homebrew found: $(brew --version | head -1)"
fi

# ── 3. Python 3.10+ ──────────────────────────────────────────────────────────
step "Checking Python"
PYTHON3=""
for candidate in python3.12 python3.11 python3.10 python3; do
    if command -v "$candidate" &>/dev/null; then
        ver=$("$candidate" -c "import sys; print('%d.%d' % sys.version_info[:2])")
        major=${ver%%.*}
        minor=${ver##*.}
        if (( major >= 3 && minor >= 10 )); then
            PYTHON3=$(command -v "$candidate")
            green "Using Python $ver at $PYTHON3"
            break
        fi
    fi
done

if [[ -z "$PYTHON3" ]]; then
    yellow "Python 3.10+ not found. Installing python@3.12 via Homebrew..."
    brew install python@3.12
    PYTHON3=$(brew --prefix)/bin/python3.12
fi

# ── 4. mpv (provides libmpv.dylib) ───────────────────────────────────────────
step "Checking mpv"
if brew list mpv &>/dev/null; then
    green "mpv already installed."
else
    yellow "Installing mpv via Homebrew..."
    brew install mpv
fi

# ── 5. Virtual environment ───────────────────────────────────────────────────
step "Setting up Python virtual environment"
if [[ ! -f "$VENV/bin/activate" ]]; then
    "$PYTHON3" -m venv "$VENV"
    green "Virtual environment created at $VENV"
else
    green "Virtual environment already exists."
fi

# ── 6. Install Python dependencies ───────────────────────────────────────────
step "Installing Python dependencies"
"$PYTHON" -m pip install --upgrade pip --quiet
"$PYTHON" -m pip install -r "$REPO_DIR/requirements.txt" --quiet
green "Dependencies installed."

# ── 7. Sanity check — can we import mpv? ─────────────────────────────────────
step "Verifying mpv Python bindings"
if "$PYTHON" -c "import mpv" 2>/dev/null; then
    green "python-mpv OK."
else
    # python-mpv needs to find libmpv.dylib; help it via DYLD_LIBRARY_PATH
    MPV_LIB_DIR=""
    for candidate in /opt/homebrew/lib /usr/local/lib; do
        if [[ -f "$candidate/libmpv.dylib" ]]; then
            MPV_LIB_DIR="$candidate"
            break
        fi
    done
    if [[ -n "$MPV_LIB_DIR" ]]; then
        export DYLD_LIBRARY_PATH="$MPV_LIB_DIR${DYLD_LIBRARY_PATH:+:$DYLD_LIBRARY_PATH}"
        if "$PYTHON" -c "import mpv" 2>/dev/null; then
            green "python-mpv OK (DYLD_LIBRARY_PATH=$MPV_LIB_DIR)."
            # Persist the hint for future --run invocations via a small wrapper
            yellow "Note: DYLD_LIBRARY_PATH=$MPV_LIB_DIR will be set automatically on launch."
        else
            red "python-mpv import failed even with DYLD_LIBRARY_PATH set."
            red "Try: brew reinstall mpv"
            exit 1
        fi
    else
        red "libmpv.dylib not found. Try: brew install mpv"
        exit 1
    fi
fi

# ── 8. Launch ────────────────────────────────────────────────────────────────
step "Launching Warrior IPTV Player"
# Set DYLD_LIBRARY_PATH so libmpv is found at runtime (harmless if not needed)
for candidate in /opt/homebrew/lib /usr/local/lib; do
    if [[ -d "$candidate" ]]; then
        export DYLD_LIBRARY_PATH="$candidate${DYLD_LIBRARY_PATH:+:$DYLD_LIBRARY_PATH}"
        break
    fi
done

exec "$PYTHON" "$REPO_DIR/src/main.py" "$@"
