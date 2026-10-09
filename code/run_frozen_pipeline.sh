#!/bin/zsh
set -euo pipefail

REPO_DIR="$(cd -- "$(dirname -- "$0")/.." && pwd)"
PYTHON_CMD="${PYTHON_BIN:-python3}"
ARCHIVE="$REPO_DIR/code/stage-outputs/001-collect-ads-records/ads_stage_001_snapshots.zip"
SNAPSHOT_DIR="$REPO_DIR/code/stage-outputs/001-collect-ads-records"

cd "$REPO_DIR"

if [[ ! -f "$ARCHIVE" ]]; then
  echo "Missing retained ADS archive: $ARCHIVE" >&2
  exit 1
fi

unzip -oq "$ARCHIVE" -d "$SNAPSHOT_DIR"
Rscript code/002-build-canonical-data.R
"$PYTHON_CMD" -m jupyter nbconvert --to notebook --execute --inplace \
  --ExecutePreprocessor.timeout=-1 code/003-extract-dm-candidates.ipynb
"$PYTHON_CMD" -m jupyter nbconvert --to notebook --execute --inplace \
  --ExecutePreprocessor.timeout=-1 code/004-build-lexical-data.ipynb
"$PYTHON_CMD" -m jupyter nbconvert --to notebook --execute --inplace \
  --ExecutePreprocessor.timeout=-1 code/005-robustness-validation.ipynb
Rscript code/006-build-paper-assets.R
"$PYTHON_CMD" -m unittest discover -s code/tests -p 'test_*.py' -v

echo "Frozen six-stage pipeline completed successfully."
