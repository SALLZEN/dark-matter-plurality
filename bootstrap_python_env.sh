#!/bin/zsh
set -euo pipefail

ROOT_DIR="$(cd -- "$(dirname -- "$0")" && pwd)"
VENV_DIR="$ROOT_DIR/.venv"

if [[ -f "$ROOT_DIR/code/requirements.lock.txt" ]]; then
  REQ_FILE="$ROOT_DIR/code/requirements.lock.txt"
else
  REQ_FILE="$ROOT_DIR/code/requirements.txt"
fi

if [[ -z "${PYTHON_BIN:-}" ]]; then
  if command -v python3.11 >/dev/null 2>&1; then
    PYTHON_BIN="python3.11"
  else
    PYTHON_BIN="python3"
  fi
fi

PYTHON_VERSION="$("$PYTHON_BIN" -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')"
case "$PYTHON_VERSION" in
  3.11|3.12|3.13) ;;
  *)
    echo "Unsupported Python version: $PYTHON_VERSION" >&2
    echo "This repo expects Python 3.11 or newer." >&2
    echo "Retry with, for example:" >&2
    echo "  PYTHON_BIN=python3.11 ./bootstrap_python_env.sh" >&2
    exit 1
    ;;
esac

if [[ ! -d "$VENV_DIR" ]]; then
  "$PYTHON_BIN" -m venv "$VENV_DIR"
fi

"$VENV_DIR/bin/python" -m pip install --upgrade pip setuptools wheel
"$VENV_DIR/bin/python" -m pip install -r "$REQ_FILE"

echo "Repository environment ready at $VENV_DIR"
echo "Launch notebooks with: $VENV_DIR/bin/python -m jupyter lab"
