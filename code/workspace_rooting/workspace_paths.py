from __future__ import annotations

from pathlib import Path


def canonical_workspace_paths(workspace_root: str | Path) -> dict[str, Path]:
    root = Path(workspace_root).resolve()
    code = root / "code"
    return {
        "workspace": root,
        "code": code,
        "config": root / "config",
        "data": root / "data",
        "outputs": root,
        "docs": root / "docs",
        "local": code / "stage-outputs",
        "paper_dir": root,
        "paper_outputs": root,
        "overleaf": root,
    }
