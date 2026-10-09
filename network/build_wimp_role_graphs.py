#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

from dm_network.wimp_role import build_wimp_role_outputs


PROJECT_DIR = Path(__file__).resolve().parent
WORKSPACE_DIR = PROJECT_DIR.parent


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build canonical and Gephi-adapted graphs of the WIMP's research role."
    )
    parser.add_argument(
        "--candidate-metadata",
        type=Path,
        default=WORKSPACE_DIR / "data" / "papers_with_dm_models.parquet",
    )
    parser.add_argument(
        "--base-output-dir",
        type=Path,
        default=PROJECT_DIR / "outputs" / "canonical",
        help="Base epistemic-network output containing occurrence and event parquet files.",
    )
    parser.add_argument(
        "--candidate-code-dir",
        type=Path,
        default=WORKSPACE_DIR / "code",
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=PROJECT_DIR / "config" / "wimp_role_analysis.json",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=PROJECT_DIR / "outputs" / "wimp-role-networks",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    required = {
        "candidate metadata": args.candidate_metadata,
        "candidate code": args.candidate_code_dir,
        "config": args.config,
        "occurrences": args.base_output_dir / "occurrences.parquet",
        "sentence events": args.base_output_dir / "cooccurrence_events.parquet",
        "abstract events": args.base_output_dir / "abstract_cooccurrence_events.parquet",
    }
    missing = [f"{name}: {path}" for name, path in required.items() if not path.exists()]
    if missing:
        raise FileNotFoundError("Missing required input paths:\n- " + "\n- ".join(missing))
    print("Building WIMP-role graph families")
    print(f"  base events: {args.base_output_dir.resolve()}")
    print(f"  output: {args.output_dir.resolve()}")
    result = build_wimp_role_outputs(
        paper_metadata_path=args.candidate_metadata,
        occurrences_path=args.base_output_dir / "occurrences.parquet",
        sentence_events_path=args.base_output_dir / "cooccurrence_events.parquet",
        abstract_events_path=args.base_output_dir / "abstract_cooccurrence_events.parquet",
        candidate_code_dir=args.candidate_code_dir,
        config_path=args.config,
        output_dir=args.output_dir,
    )
    print("Completed graph families:")
    for name in result["graphs"]:
        print(f"  {name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
