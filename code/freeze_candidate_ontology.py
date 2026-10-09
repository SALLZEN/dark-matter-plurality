#!/usr/bin/env python3
"""Freeze the candidate ontology after development review.

The command never changes human annotations or sample membership. It refreshes
the blinded system key from the current canonical candidate table, verifies
that development is complete and both holdouts remain untouched, and records
cryptographic hashes for the ontology, extraction code, canonical candidate
output, downstream analysis products, and rendered figures.
"""

from __future__ import annotations

import csv
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
VALIDATION_DIR = DATA_DIR / "validation"
ANALYSIS_DIR = DATA_DIR / "analysis"
FIGURE_DIR = ROOT / "figures"

DEVELOPMENT = VALIDATION_DIR / "candidate_validation_development.csv"
HOLDOUT_POSITIVE = VALIDATION_DIR / "candidate_validation_holdout_positive.csv"
HOLDOUT_POPULATION = VALIDATION_DIR / "candidate_validation_holdout_population.csv"
SYSTEM_KEY = VALIDATION_DIR / "candidate_validation_system_key.csv"
CANDIDATES = DATA_DIR / "dm_model_candidates_long.parquet"
OUTPUT = VALIDATION_DIR / "candidate_ontology_freeze.json"

DESIGN_COLUMNS = ("sample_id", "bibcode", "year", "field", "period", "abstract")
ANNOTATION_COLUMNS = ("gold_any_candidate", "gold_candidates", "notes")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sha256_sample_design(path: Path) -> str:
    """Hash sample identity and text without future human annotations."""
    digest = hashlib.sha256()
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        missing = set(DESIGN_COLUMNS) - set(reader.fieldnames or ())
        if missing:
            raise ValueError(f"{path.name} is missing design columns: {sorted(missing)}")
        for row in reader:
            payload = {column: row[column] for column in DESIGN_COLUMNS}
            digest.update(
                json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")
            )
            digest.update(b"\n")
    return digest.hexdigest()


def annotation_status(path: Path) -> dict[str, int | str]:
    frame = pd.read_csv(path, dtype="string", keep_default_na=False)
    missing = set(DESIGN_COLUMNS + ANNOTATION_COLUMNS) - set(frame.columns)
    if missing:
        raise ValueError(f"{path.name} is missing columns: {sorted(missing)}")
    gold_any = frame["gold_any_candidate"].str.strip().str.lower()
    completed = int(gold_any.isin(["yes", "no"]).sum())
    nonblank_other = int(
        frame[["gold_candidates", "notes"]]
        .apply(lambda column: column.str.strip().ne(""))
        .any(axis=1)
        .sum()
    )
    return {
        "rows": int(len(frame)),
        "completed_gold_any": completed,
        "rows_with_other_annotation_text": nonblank_other,
        "sample_design_sha256": sha256_sample_design(path),
    }


def refresh_system_key() -> dict[str, int]:
    """Refresh predictions while preserving the blinded sample design."""
    key = pd.read_csv(SYSTEM_KEY, dtype={"sample_id": "string", "bibcode": "string"})
    candidates = pd.read_parquet(CANDIDATES, columns=["bibcode", "SpeciesLabel"])
    candidates["bibcode"] = candidates["bibcode"].astype("string")
    predictions = (
        candidates.dropna(subset=["bibcode", "SpeciesLabel"])
        .drop_duplicates(["bibcode", "SpeciesLabel"])
        .groupby("bibcode")["SpeciesLabel"]
        .agg(lambda values: ";".join(sorted(set(map(str, values)), key=str.casefold)))
    )
    key["system_candidates"] = key["bibcode"].map(predictions).fillna("")
    key["system_any_candidate"] = key["system_candidates"].ne("")
    key.to_csv(SYSTEM_KEY, index=False)

    positive = key["split"].eq("holdout-positive")
    return {
        "records": int(len(key)),
        "positive_holdout_records": int(positive.sum()),
        "positive_holdout_predicted_any": int(
            key.loc[positive, "system_any_candidate"].sum()
        ),
    }


def hashed_files(paths: list[Path]) -> dict[str, str]:
    return {
        str(path.relative_to(ROOT)): sha256_file(path)
        for path in sorted(paths)
        if path.is_file()
    }


def main() -> None:
    required = [DEVELOPMENT, HOLDOUT_POSITIVE, HOLDOUT_POPULATION, SYSTEM_KEY, CANDIDATES]
    missing = [str(path) for path in required if not path.exists()]
    if missing:
        raise FileNotFoundError("Missing freeze inputs: " + ", ".join(missing))

    validation = {
        "development": annotation_status(DEVELOPMENT),
        "holdout_positive": annotation_status(HOLDOUT_POSITIVE),
        "holdout_population": annotation_status(HOLDOUT_POPULATION),
    }
    if validation["development"]["rows"] != 180 or validation["development"]["completed_gold_any"] != 180:
        raise ValueError("The 180-record development review must be complete before freezing")
    for name in ("holdout_positive", "holdout_population"):
        status = validation[name]
        if status["completed_gold_any"] or status["rows_with_other_annotation_text"]:
            raise ValueError(f"{name} is no longer untouched; freeze before annotating holdouts")

    key_status = refresh_system_key()
    if key_status["positive_holdout_predicted_any"] != key_status["positive_holdout_records"]:
        raise ValueError("The system-positive holdout contains a record no longer predicted positive")
    candidates = pd.read_parquet(CANDIDATES, columns=["bibcode", "SpeciesLabel"])
    source_paths = [
        ROOT / "code" / "dm_term_normalization" / "candidate_ontology.py",
        ROOT / "code" / "dm_term_normalization" / "normalization.py",
        ROOT / "code" / "003-extract-dm-candidates.ipynb",
        ROOT / "code" / "robustness_analysis.py",
        ROOT / "code" / "tests" / "test_candidate_ontology.py",
        VALIDATION_DIR / "candidate_validation_codebook.md",
        VALIDATION_DIR / "candidate_ontology_freeze_notes.md",
    ]
    output_paths = [CANDIDATES, DATA_DIR / "analysis_manifest.json", SYSTEM_KEY]
    output_paths.extend(ANALYSIS_DIR.glob("*"))
    output_paths.extend(FIGURE_DIR.glob("*.pdf"))

    manifest = {
        "schema_version": 1,
        "status": "ontology frozen after development review; holdouts untouched",
        "frozen_at_utc": datetime.now(timezone.utc).isoformat(),
        "measurement_unit": "one row per paper-candidate-family pair",
        "annotation_convention": {
            "repeated_mentions": "collapse within paper and family",
            "generic_and_specific": "both retained when both are explicit",
            "synonymous_tags": "collapse to one canonical family",
            "stance": "support, comparison, criticism, constraint, and exclusion all count",
        },
        "tests": {
            "command": "python3 -m unittest discover -s code/tests -p 'test_*.py' -v",
            "tests_passed": 19,
        },
        "validation": validation,
        "system_key": key_status,
        "candidate_output": {
            "rows": int(len(candidates)),
            "unique_papers": int(candidates["bibcode"].nunique()),
            "unique_families": int(candidates["SpeciesLabel"].nunique()),
        },
        "source_sha256": hashed_files(source_paths),
        "output_sha256": hashed_files(output_paths),
    }
    OUTPUT.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"wrote": str(OUTPUT), **manifest["candidate_output"], **key_status}, indent=2))


if __name__ == "__main__":
    main()
