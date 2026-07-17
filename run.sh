#!/usr/bin/env bash
# All output (stdout+stderr) goes to BOTH the parent's pipe AND the log file
exec > >(tee -a /tmp/spring5_launch.log) 2>&1

echo
echo "============================================================"
echo "[run.sh] STARTED at $(date -u +"%Y-%m-%dT%H:%M:%SZ")"
echo "  PWD=$(pwd)  USER=$(id -un)  PID=$$"
echo "============================================================"

set -Eeuo pipefail

EVENT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="${EVENT_DIR}/.venv"
SETUP_SCRIPT="${EVENT_DIR}/setup.sh"
SETUP_MARKER="${EVENT_DIR}/.setup_complete"

trap 'echo "[run.sh] EXITING at line $LINENO with code $?"' EXIT
trap 'echo "[run.sh] ERROR at line $LINENO (exit $?)"' ERR

cd "${EVENT_DIR}"
echo "[run.sh] EVENT_DIR=${EVENT_DIR}"
echo "[run.sh] VENV exists? $([[ -d "$VENV_DIR" ]] && echo yes || echo no)"
echo "[run.sh] SETUP_MARKER exists? $([[ -f "$SETUP_MARKER" ]] && echo yes || echo no)"

needs_setup=0
[[ ! -d "${VENV_DIR}" ]] && needs_setup=1
[[ ! -f "${SETUP_MARKER}" ]] && needs_setup=1
echo "[run.sh] needs_setup=${needs_setup}"

if [[ "${needs_setup}" == "1" ]]; then
  if [[ ! -f "${SETUP_SCRIPT}" ]]; then
    echo "[run.sh] FATAL: setup.sh missing"
    exit 2
  fi
  echo "[run.sh] Running setup.sh ..."
  chmod +x "${SETUP_SCRIPT}" || true
  set +e
  bash -x "${SETUP_SCRIPT}"
  setup_rc=$?
  set -e
  echo "[run.sh] setup.sh exited with code ${setup_rc}"
  if [[ ${setup_rc} -ne 0 ]]; then
    echo "[run.sh] FATAL: setup.sh failed"
    exit ${setup_rc}
  fi
  date -u +"%Y-%m-%dT%H:%M:%SZ" > "${SETUP_MARKER}"
fi

if [[ ! -d "${VENV_DIR}" ]]; then
  echo "[run.sh] FATAL: venv still missing after setup"
  exit 3
fi

echo "[run.sh] Activating venv and launching main.py"
source "${VENV_DIR}/bin/activate"
export PYTHONUNBUFFERED=1
exec python "${EVENT_DIR}/main.py" "$@"
