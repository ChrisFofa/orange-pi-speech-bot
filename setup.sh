#!/usr/bin/env bash
# ============================================================
# Spring Demo — Setup Script
# ============================================================
#
# Runs on the Orange Pi after the package is downloaded and
# extracted into /opt/bigbang/events/Spring Demo/.
#
# Steps:
#   0. Spawn loading_screen.py on the framebuffer so the student sees
#      a loading screen during the (~3-5 min) first-run install.
#   1. Install OS audio + speech dependencies via apt.
#   2. Create a Python venv with --system-site-packages
#      (mandatory so PyQt5 / numpy from the OS are visible).
#   3. pip install requirements.txt inside the venv.
#   4. Download + unzip the Vosk small English model if missing.
#   5. Mark run.sh executable.
#
# Safe to re-run.
# ============================================================

set -Eeuo pipefail

EVENT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="${EVENT_DIR}/.venv"
VOSK_DIR="${EVENT_DIR}/vosk-model-small-en-us-0.15"
VOSK_ZIP_URL="https://alphacephei.com/vosk/models/vosk-model-small-en-us-0.15.zip"
LOADER_SCRIPT="${EVENT_DIR}/loading_screen.py"
LOADER_PID=""

# ------------------------------------------------------------
# 0. Loading screen
# ------------------------------------------------------------
# Spawn loading_screen.py in the background on the framebuffer so the
# student sees a "Setting up..." screen during the long install.
# A trap ensures the loader is killed on ANY exit (success,
# failure, signal) so it never leaves an orphaned window.
# ------------------------------------------------------------

stop_loader() {
  if [[ -n "${LOADER_PID}" ]] && kill -0 "${LOADER_PID}" 2>/dev/null; then
    kill "${LOADER_PID}" 2>/dev/null || true
    # Give it a moment to release the framebuffer cleanly
    for _ in 1 2 3; do
      kill -0 "${LOADER_PID}" 2>/dev/null || break
      sleep 1
    done
    kill -9 "${LOADER_PID}" 2>/dev/null || true
    wait "${LOADER_PID}" 2>/dev/null || true
  fi
  LOADER_PID=""
}

# Kill the loader no matter how setup.sh exits.
trap stop_loader EXIT INT TERM

if [[ -f "${LOADER_SCRIPT}" ]]; then
  echo "[setup] Launching loading_screen.py on framebuffer..."
  # Use system python (the venv doesn't exist yet at this point).
  # QT_QPA_PLATFORM tells PyQt5 to render to the Linux framebuffer.
  QT_QPA_PLATFORM="linuxfb:fb=/dev/fb0:tty=/dev/tty1" \
    python3 "${LOADER_SCRIPT}" >/dev/null 2>&1 &
  LOADER_PID=$!
  # Give the loader a moment to grab the framebuffer before any
  # heavy work pushes log spam into the foreground.
  sleep 1
  echo "[setup] loading_screen.py started (PID=${LOADER_PID})"
else
  echo "[setup] loading_screen.py not found at ${LOADER_SCRIPT} — skipping loading screen."
fi

echo "============================================================"
echo " Spring Demo setup"
echo "============================================================"
echo "Event dir : ${EVENT_DIR}"
echo "Venv dir  : ${VENV_DIR}"
echo "Vosk dir  : ${VOSK_DIR}"
echo "============================================================"

section() {
  echo
  echo "------------------------------------------------------------"
  echo "$1"
  echo "------------------------------------------------------------"
}

# ------------------------------------------------------------
# 1. OS dependencies
# ------------------------------------------------------------
section "Installing apt dependencies"

if command -v apt-get >/dev/null 2>&1; then
  if [[ "${SKIP_APT:-0}" == "1" ]]; then
    echo "SKIP_APT=1 — skipping apt install."
  else
    sudo apt-get update
    sudo apt-get install -y \
      ca-certificates curl unzip wget \
      python3 python3-pip python3-venv \
      python3-pyqt5 python3-numpy \
      alsa-utils mpg123 \
      libportaudio2 portaudio19-dev \
      libsndfile1
  fi
else
  echo "apt-get not found. Skipping OS install."
fi

# ------------------------------------------------------------
# 2. Python venv with system-site-packages
# ------------------------------------------------------------
section "Creating Python virtual environment"

cd "${EVENT_DIR}"

if [[ ! -d "${VENV_DIR}" ]]; then
  python3 -m venv --system-site-packages "${VENV_DIR}"
else
  echo "Reusing existing venv."
fi

# ------------------------------------------------------------
# 3. pip requirements
# ------------------------------------------------------------
section "Installing pip requirements"

# shellcheck source=/dev/null
source "${VENV_DIR}/bin/activate"

python -m pip install --no-cache-dir --upgrade pip setuptools wheel

if [[ -f "${EVENT_DIR}/requirements.txt" ]]; then
  python -m pip install --no-cache-dir -r "${EVENT_DIR}/requirements.txt"
else
  echo "WARNING: requirements.txt missing."
fi

# ------------------------------------------------------------
# 4. Vosk model
# ------------------------------------------------------------
section "Checking Vosk model"

if [[ -d "${VOSK_DIR}" ]]; then
  echo "Vosk model already present at ${VOSK_DIR}"
else
  echo "Downloading Vosk small English model..."
  TMPZIP="$(mktemp -t vosk-XXXXXX.zip)"
  if command -v curl >/dev/null 2>&1; then
    curl -L --fail --output "${TMPZIP}" "${VOSK_ZIP_URL}"
  else
    wget -O "${TMPZIP}" "${VOSK_ZIP_URL}"
  fi

  echo "Extracting..."
  unzip -q "${TMPZIP}" -d "${EVENT_DIR}"
  rm -f "${TMPZIP}"

  if [[ -d "${VOSK_DIR}" ]]; then
    echo "Vosk model installed at ${VOSK_DIR}"
  else
    echo "WARNING: Vosk extraction did not produce ${VOSK_DIR}"
    echo "Check vosk-model-small-en-us-0.15 folder name inside the zip."
  fi
fi

# ------------------------------------------------------------
# 5. Permissions
# ------------------------------------------------------------
section "Marking scripts executable"

chmod +x "${EVENT_DIR}/run.sh" || true
chmod +x "${EVENT_DIR}/setup.sh" || true

section "Setup complete"
echo "Run with:"
echo "  cd \"${EVENT_DIR}\""
echo "  ./run.sh"

# The EXIT trap will kill the loader now that setup is done.
# run.sh will then continue and exec main.py, which takes over
# the framebuffer with the bot's UI.
