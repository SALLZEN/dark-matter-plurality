#!/bin/zsh
set -euo pipefail

ROOT_DIR="$(cd -- "$(dirname -- "$0")" && pwd)"
cd "$ROOT_DIR"

echo "==> Step 1/2: bootstrapping local Python environment"
./bootstrap_python_env.sh
echo ""

echo "==> Step 2/2: installing the repo-local Jupyter kernel"
./install_repo_kernel.sh
echo ""

echo "Repository configuration complete."
echo "Next: read README.md and run the canonical pipeline in order."
