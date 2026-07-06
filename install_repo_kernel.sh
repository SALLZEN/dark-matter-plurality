#!/bin/zsh
set -euo pipefail

ROOT_DIR="$(cd -- "$(dirname -- "$0")" && pwd)"
PYTHON_BIN="$ROOT_DIR/.venv/bin/python"
KERNEL_NAME="dark-matter-plurality"
DISPLAY_NAME="dark-matter-plurality"

if [[ ! -x "$PYTHON_BIN" ]]; then
  echo "Missing interpreter: $PYTHON_BIN" >&2
  exit 1
fi

"$PYTHON_BIN" -m ipykernel install --user --name "$KERNEL_NAME" --display-name "$DISPLAY_NAME"
echo "Installed Jupyter kernel: $KERNEL_NAME"
