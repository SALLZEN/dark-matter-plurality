#!/usr/bin/env python3
"""Build robustness, validation, and divergence products for the manuscript.

The module is deliberately usable both from the development workspace and from
the self-contained public reproduction bundle.  The analysis never includes
records after ``END_YEAR`` and records every canonical input hash in a manifest.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import platform
import re
import shutil
import sys
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Sequence

import numpy as np
import pandas as pd


END_YEAR = 2025
START_YEAR = 1995
SEED = 20250801
N_BOOTSTRAP = 2_000
N_SENSITIVITY = 1_000
VALIDATION_TOP_FAMILIES = 6

ASTRO = "astrophysics"
HEP = "high-energy physics"
FOCAL_FIELDS = (ASTRO, HEP)

EXCLUDED_DOCTYPES = {
    "pressrelease",
    "mastersthesis",
    "misc",
    "techreport",
    "dataset",
    "proposal",
    "proceedings",
    "abstract",
    "newsletter",
    "obituary",
    "talk",
    "circular",
    "bookreview",
    "software",
    "editorial",
    "erratum",
    "phdthesis",
}

BIOLOGY_FILTER_TERMS = {
    "bacteria",
    "bacterial",
    "eukaryotic",
    "genome",
    "genomes",
    "genomic",
    "mags",
    "metabolites",
    "metagenomics",
    "microbes",
    "microbial",
    "microorganisms",
    "phyla",
}

CANDIDATE_UNIGRAMS = {
    "adm",
    "alp",
    "axion",
    "axino",
    "bino",
    "gravitino",
    "higgsino",
    "macho",
    "neutralino",
    "pbh",
    "sneutrino",
    "sterile",
    "superwimp",
    "ula",
    "wimp",
    "wino",
}


@dataclass(frozen=True)
class Paths:
    project_root: Path
    data_dir: Path
    analysis_dir: Path
    validation_dir: Path
    papers: Path
    classes: Path
    metrics: Path | None
    candidates: Path
    enriched_papers: Path
    unigrams: Path
    archive: Path | None


def _find_project_root(start: Path) -> Path:
    for candidate in (start, *start.parents):
        if (candidate / "config" / "workspace.json").exists():
            return candidate
        if (candidate / ".zenodo.json").exists() and (candidate / "code").exists():
            return candidate
    raise FileNotFoundError("Could not identify the development workspace or public repository root")


def resolve_paths(project_root: str | Path | None = None) -> Paths:
    root = Path(project_root).resolve() if project_root else _find_project_root(Path(__file__).resolve())
    data_dir = root / "data"
    analysis_dir = data_dir / "analysis"
    validation_dir = data_dir / "validation"

    canonical_root = Path(os.environ.get("DM_CANONICAL_ROOT", data_dir)).resolve()
    archive_candidates = [
        root / "code" / "stage-outputs" / "001-collect-ads-records" / "ads_stage_001_snapshots.zip",
        root / "data" / "raw" / "ads_stage_001_snapshots.zip",
    ]

    papers = Path(os.environ.get("DM_PAPERS_PATH", canonical_root / "papers.parquet")).resolve()
    classes = Path(os.environ.get("DM_CLASSES_PATH", canonical_root / "paper_arxiv_classes.parquet")).resolve()
    metrics_candidate = Path(os.environ.get("DM_METRICS_PATH", canonical_root / "paper_metrics_long.parquet")).resolve()
    metrics = metrics_candidate if metrics_candidate.exists() else None
    candidates = Path(os.environ.get("DM_CANDIDATES_PATH", data_dir / "dm_model_candidates_long.parquet")).resolve()
    enriched = Path(os.environ.get("DM_ENRICHED_PAPERS_PATH", data_dir / "papers_with_dm_models.parquet")).resolve()
    unigrams = Path(os.environ.get("DM_UNIGRAM_PATH", data_dir / "unigram_yearly.parquet")).resolve()
    archive = next((p.resolve() for p in archive_candidates if p.exists()), None)

    required = [papers, classes, candidates, enriched, unigrams]
    missing = [str(p) for p in required if not p.exists()]
    if missing:
        raise FileNotFoundError("Missing canonical analysis inputs:\n- " + "\n- ".join(missing))

    return Paths(
        project_root=root,
        data_dir=data_dir,
        analysis_dir=analysis_dir,
        validation_dir=validation_dir,
        papers=papers,
        classes=classes,
        metrics=metrics,
        candidates=candidates,
        enriched_papers=enriched,
        unigrams=unigrams,
        archive=archive,
    )


def sha256_file(path: Path, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(chunk_size), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _write_json(payload: dict, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _python_versions() -> dict[str, str]:
    versions = {
        "python": platform.python_version(),
        "numpy": np.__version__,
        "pandas": pd.__version__,
    }
    try:
        import pyarrow

        versions["pyarrow"] = pyarrow.__version__
    except ImportError:
        versions["pyarrow"] = "unavailable"
    return versions


def _coerce_year(data: pd.DataFrame) -> pd.DataFrame:
    result = data.copy()
    result["year"] = pd.to_numeric(result["year"], errors="coerce").astype("Int64")
    return result


def load_inputs(paths: Paths) -> dict[str, pd.DataFrame]:
    papers = _coerce_year(pd.read_parquet(paths.papers))
    classes = pd.read_parquet(paths.classes).copy()
    candidates = _coerce_year(pd.read_parquet(paths.candidates))
    enriched = _coerce_year(pd.read_parquet(paths.enriched_papers))
    unigrams = _coerce_year(pd.read_parquet(paths.unigrams))

    papers = papers[papers["year"].le(END_YEAR)].copy()
    candidates = candidates[candidates["year"].between(START_YEAR, END_YEAR)].copy()
    enriched = enriched[enriched["year"].le(END_YEAR)].copy()
    unigrams = unigrams[unigrams["year"].le(END_YEAR)].copy()

    keep_bibcodes = set(papers["bibcode"])
    classes = classes[classes["bibcode"].isin(keep_bibcodes)].copy()
    return {
        "papers": papers,
        "classes": classes,
        "candidates": candidates,
        "enriched": enriched,
        "unigrams": unigrams,
    }


def build_manifest(paths: Paths, frames: dict[str, pd.DataFrame]) -> dict:
    inputs = {
        "papers": paths.papers,
        "paper_arxiv_classes": paths.classes,
        "dm_model_candidates_long": paths.candidates,
        "papers_with_dm_models": paths.enriched_papers,
        "unigram_yearly": paths.unigrams,
    }
    if paths.metrics:
        inputs["paper_metrics_long"] = paths.metrics
    if paths.archive:
        inputs["retained_ads_snapshot"] = paths.archive

    def portable_path(path: Path) -> str:
        try:
            return str(path.relative_to(paths.project_root))
        except ValueError:
            return str(path)

    input_manifest = {
        name: {
            "path": portable_path(path),
            "bytes": path.stat().st_size,
            "sha256": sha256_file(path),
        }
        for name, path in inputs.items()
    }

    papers = frames["papers"]
    classes = frames["classes"]
    manifest = {
        "schema_version": 1,
        "analysis_name": "PNAS Nexus Research Report robustness analysis",
        "query": 'full:"dark matter"',
        "indexing_snapshot_utc": "2026-05-21T22:17:06Z",
        "analysis_cutoff_year": END_YEAR,
        "analysis_start_year_for_candidate_trends": START_YEAR,
        "random_seed": SEED,
        "bootstrap_replicates": N_BOOTSTRAP,
        "2025_status": "complete",
        "inputs": input_manifest,
        "row_counts_after_cutoff": {
            "papers": int(len(papers)),
            "papers_with_abstracts": int(papers["abstract"].notna().sum()),
            "classified_papers": int(classes["bibcode"].nunique()),
            "arxiv_class_rows": int(len(classes)),
            "candidate_rows": int(len(frames["candidates"])),
            "candidate_papers": int(frames["candidates"]["bibcode"].nunique()),
            "lexical_rows": int(len(frames["unigrams"])),
        },
        "exclusions": {
            "years_after": END_YEAR,
            "candidate_excluded_doctypes": sorted(EXCLUDED_DOCTYPES),
            "biology_filter_terms": sorted(BIOLOGY_FILTER_TERMS),
            "records_without_abstracts_excluded_from_text_analyses": True,
        },
        "software": _python_versions(),
    }
    _write_json(manifest, paths.data_dir / "analysis_manifest.json")
    return manifest


def wilson_interval(successes: int, total: int, z: float = 1.959963984540054) -> tuple[float, float]:
    if total <= 0:
        return (math.nan, math.nan)
    p = successes / total
    denominator = 1 + z * z / total
    center = (p + z * z / (2 * total)) / denominator
    half = z * math.sqrt((p * (1 - p) + z * z / (4 * total)) / total) / denominator
    return center - half, center + half


def fractional_class_weights(classes: pd.DataFrame) -> pd.DataFrame:
    required = {"bibcode", "arxiv_class", "arxiv_category"}
    if not required.issubset(classes.columns):
        raise ValueError(f"classes must contain {sorted(required)}")
    result = classes.drop_duplicates(["bibcode", "arxiv_class"]).copy()
    result["n_classes"] = result.groupby("bibcode")["arxiv_class"].transform("size")
    result["class_weight"] = 1.0 / result["n_classes"]
    result["field_weight"] = result.groupby(["bibcode", "arxiv_category"])["class_weight"].transform("sum")
    return result.drop_duplicates(["bibcode", "arxiv_category"])[
        ["bibcode", "arxiv_category", "field_weight"]
    ]


def build_classification_outputs(
    papers: pd.DataFrame, classes: pd.DataFrame, output_dir: Path
) -> dict[str, pd.DataFrame]:
    output_dir.mkdir(parents=True, exist_ok=True)
    years = papers[["bibcode", "year", "abstract", "doctype"]].drop_duplicates("bibcode")
    class_year = classes.merge(years[["bibcode", "year"]], on="bibcode", how="inner")
    primary = class_year[class_year["class_pos"].eq(1)].copy()
    if primary["bibcode"].duplicated().any():
        raise AssertionError("Primary arXiv assignment is not unique per paper")

    denominators = primary.groupby("year")["bibcode"].nunique().rename("n_classified")
    individual = (
        primary.groupby(["year", "arxiv_class", "arxiv_category"])["bibcode"]
        .nunique()
        .rename("n_papers")
        .reset_index()
        .merge(denominators, on="year")
    )
    individual["share"] = individual["n_papers"] / individual["n_classified"]

    primary_agg = (
        primary.groupby(["year", "arxiv_category"])["bibcode"]
        .nunique()
        .rename("value")
        .reset_index()
        .merge(denominators, on="year")
    )
    primary_agg["share"] = primary_agg["value"] / primary_agg["n_classified"]
    primary_agg["assignment"] = "primary"

    any_class = class_year.drop_duplicates(["year", "bibcode", "arxiv_category"])
    any_agg = (
        any_class.groupby(["year", "arxiv_category"])["bibcode"]
        .nunique()
        .rename("value")
        .reset_index()
        .merge(denominators, on="year")
    )
    any_agg["share"] = any_agg["value"] / any_agg["n_classified"]
    any_agg["assignment"] = "any class"

    fractional = fractional_class_weights(class_year)
    fractional = fractional.merge(years[["bibcode", "year"]], on="bibcode", how="inner")
    frac_agg = (
        fractional.groupby(["year", "arxiv_category"])["field_weight"]
        .sum()
        .rename("value")
        .reset_index()
        .merge(denominators, on="year")
    )
    frac_agg["share"] = frac_agg["value"] / frac_agg["n_classified"]
    frac_agg["assignment"] = "fractional"

    aggregate = pd.concat([primary_agg, any_agg, frac_agg], ignore_index=True)
    aggregate = aggregate[
        ["year", "arxiv_category", "assignment", "value", "n_classified", "share"]
    ]

    flags = (
        class_year.assign(
            astro=lambda d: d["arxiv_category"].eq(ASTRO),
            hep=lambda d: d["arxiv_category"].eq(HEP),
        )
        .groupby(["year", "bibcode"])
        .agg(n_classes=("arxiv_class", "nunique"), astro=("astro", "max"), hep=("hep", "max"))
        .reset_index()
    )
    cross = (
        flags.assign(both=lambda d: d["astro"] & d["hep"], multi=lambda d: d["n_classes"].gt(1))
        .groupby("year")
        .agg(
            n_classified=("bibcode", "nunique"),
            n_multiclass=("multi", "sum"),
            n_astro=("astro", "sum"),
            n_hep=("hep", "sum"),
            n_astro_hep=("both", "sum"),
        )
        .reset_index()
    )
    cross["crosslisting_rate"] = cross["n_astro_hep"] / cross["n_classified"]
    intervals = [wilson_interval(int(k), int(n)) for k, n in zip(cross.n_astro_hep, cross.n_classified)]
    cross[["crosslisting_low", "crosslisting_high"]] = pd.DataFrame(intervals, index=cross.index)

    coverage = primary[["bibcode", "year", "arxiv_category"]].merge(years, on=["bibcode", "year"])
    coverage = (
        coverage.assign(has_abstract=lambda d: d["abstract"].notna())
        .groupby(["year", "arxiv_category"])
        .agg(n_papers=("bibcode", "nunique"), n_abstracts=("has_abstract", "sum"))
        .reset_index()
    )
    coverage["abstract_coverage"] = coverage["n_abstracts"] / coverage["n_papers"]

    volume = (
        papers.groupby("year")
        .agg(
            n_papers=("bibcode", "nunique"),
            n_abstracts=("abstract", lambda values: values.notna().sum()),
        )
        .reset_index()
    )
    volume["abstract_coverage"] = volume["n_abstracts"] / volume["n_papers"]

    classified_bibcodes = set(primary["bibcode"])
    classification_coverage = (
        years.assign(classified=lambda d: d["bibcode"].isin(classified_bibcodes))
        .groupby("year")
        .agg(n_papers=("bibcode", "nunique"), n_classified=("classified", "sum"))
        .reset_index()
    )
    classification_coverage["n_unclassified"] = (
        classification_coverage["n_papers"] - classification_coverage["n_classified"]
    )
    classification_coverage["classification_coverage"] = (
        classification_coverage["n_classified"] / classification_coverage["n_papers"]
    )

    classification_coverage_doctype = (
        years.assign(
            doctype=lambda d: d["doctype"].fillna("missing"),
            classified=lambda d: d["bibcode"].isin(classified_bibcodes),
        )
        .groupby("doctype")
        .agg(n_papers=("bibcode", "nunique"), n_classified=("classified", "sum"))
        .reset_index()
    )
    classification_coverage_doctype["n_unclassified"] = (
        classification_coverage_doctype["n_papers"]
        - classification_coverage_doctype["n_classified"]
    )
    classification_coverage_doctype["classification_coverage"] = (
        classification_coverage_doctype["n_classified"]
        / classification_coverage_doctype["n_papers"]
    )

    arxiv_class_mapping = (
        classes.drop_duplicates(["bibcode", "arxiv_class", "arxiv_category"])
        .groupby(["arxiv_class", "arxiv_category"])["bibcode"]
        .nunique()
        .rename("n_papers")
        .reset_index()
        .sort_values(["arxiv_category", "arxiv_class"])
    )

    outputs = {
        "classification_primary_yearly": individual,
        "classification_assignment_yearly": aggregate,
        "classification_crosslisting_yearly": cross,
        "abstract_coverage_yearly": coverage,
        "paper_volume_yearly": volume,
        "classification_coverage_yearly": classification_coverage,
        "classification_coverage_doctype": classification_coverage_doctype,
        "arxiv_class_mapping": arxiv_class_mapping,
    }
    for name, data in outputs.items():
        data.to_parquet(output_dir / f"{name}.parquet", index=False)
        data.to_csv(output_dir / f"{name}.csv", index=False)
    return outputs


def _period(year: int) -> str:
    if year <= 2004:
        return "1995-2004"
    if year <= 2014:
        return "2005-2014"
    return "2015-2025"


def _allocate_strata(sizes: pd.Series, total: int, minimum: int = 0) -> pd.Series:
    sizes = sizes[sizes.gt(0)].astype(int)
    if total > int(sizes.sum()):
        raise ValueError("Requested sample exceeds available population")
    raw = sizes / sizes.sum() * total
    allocation = np.floor(raw).astype(int)
    if minimum:
        allocation = allocation.clip(lower=np.minimum(minimum, sizes))
    allocation = np.minimum(allocation, sizes)
    while int(allocation.sum()) < total:
        candidates = sizes[allocation.lt(sizes)]
        residual = (raw - allocation).loc[candidates.index]
        idx = residual.idxmax()
        allocation.loc[idx] += 1
    while int(allocation.sum()) > total:
        candidates = allocation[allocation.gt(minimum)]
        idx = (allocation - raw).loc[candidates.index].idxmax()
        allocation.loc[idx] -= 1
    return allocation


def _sample_by_strata(
    frame: pd.DataFrame,
    strata: Sequence[str],
    total: int,
    rng: np.random.Generator,
    minimum: int = 0,
) -> pd.DataFrame:
    grouped = frame.groupby(list(strata), dropna=False)
    sizes = grouped.size()
    allocation = _allocate_strata(sizes, total, minimum=minimum)
    parts: list[pd.DataFrame] = []
    for key, count in allocation.items():
        key_tuple = key if isinstance(key, tuple) else (key,)
        mask = pd.Series(True, index=frame.index)
        for column, value in zip(strata, key_tuple):
            mask &= frame[column].eq(value)
        choices = frame.loc[mask]
        selected = rng.choice(choices.index.to_numpy(), size=int(count), replace=False)
        parts.append(frame.loc[selected])
    return pd.concat(parts, ignore_index=True)


ARXIV_BIBCODE_RE = re.compile(r"^\d{4}arXiv(?P<identifier>\d{4}\.\d{4,5})[A-Z]$")


def arxiv_id_from_bibcode(bibcode: str) -> str | None:
    match = ARXIV_BIBCODE_RE.match(str(bibcode))
    return match.group("identifier") if match else None


def prepare_primary_validation_sample(
    papers: pd.DataFrame, classes: pd.DataFrame, validation_dir: Path, size: int = 500
) -> pd.DataFrame:
    validation_dir.mkdir(parents=True, exist_ok=True)
    path = validation_dir / "primary_category_validation.csv"
    if path.exists():
        existing = pd.read_csv(path)
        if len(existing) == size:
            return existing
    ordered = classes.sort_values(["bibcode", "class_pos"])
    grouped = (
        ordered.groupby("bibcode")
        .agg(
            n_classes=("arxiv_class", "nunique"),
            ads_primary=("arxiv_class", "first"),
            ads_primary_field=("arxiv_category", "first"),
            ads_classes=("arxiv_class", lambda s: ";".join(map(str, s))),
        )
        .reset_index()
        .merge(papers[["bibcode", "year"]], on="bibcode", how="inner")
    )
    eligible = grouped[
        grouped["n_classes"].gt(1) & grouped["year"].between(2010, END_YEAR)
    ].copy()
    eligible["arxiv_id"] = eligible["bibcode"].map(arxiv_id_from_bibcode)
    eligible = eligible.dropna(subset=["arxiv_id"])
    eligible["period"] = pd.cut(
        eligible["year"], bins=[2009, 2013, 2017, 2021, END_YEAR], labels=["2010-2013", "2014-2017", "2018-2021", "2022-2025"]
    ).astype("string")
    eligible["field_stratum"] = eligible["ads_primary_field"].where(
        eligible["ads_primary_field"].isin(FOCAL_FIELDS), "other"
    )
    rng = np.random.default_rng(SEED)
    sample = _sample_by_strata(
        eligible, ["period", "field_stratum"], size, rng, minimum=5
    ).sort_values(["year", "arxiv_id"])
    sample["arxiv_primary"] = ""
    sample["agreement"] = pd.NA
    sample["validation_status"] = "pending arXiv metadata fetch"
    sample.to_csv(path, index=False)
    return sample


def fetch_arxiv_primary_categories(
    validation_csv: Path, batch_size: int = 100, delay_seconds: float = 3.0
) -> pd.DataFrame:
    sample = pd.read_csv(validation_csv, dtype={"arxiv_id": "string"})
    ids = sample["arxiv_id"].dropna().astype(str).tolist()
    found: dict[str, str] = {}
    namespaces = {
        "atom": "http://www.w3.org/2005/Atom",
        "arxiv": "http://arxiv.org/schemas/atom",
    }
    for start in range(0, len(ids), batch_size):
        batch = ids[start : start + batch_size]
        query = urllib.parse.urlencode({"id_list": ",".join(batch), "max_results": len(batch)})
        request = urllib.request.Request(
            f"https://export.arxiv.org/api/query?{query}",
            headers={"User-Agent": "dark-matter-reproduction/3.0 (research validation)"},
        )
        with urllib.request.urlopen(request, timeout=90) as response:
            root = ET.fromstring(response.read())
        for entry in root.findall("atom:entry", namespaces):
            identifier = entry.findtext("atom:id", default="", namespaces=namespaces).rsplit("/", 1)[-1]
            identifier = identifier.split("v", 1)[0]
            primary = entry.find("arxiv:primary_category", namespaces)
            if identifier and primary is not None:
                found[identifier] = primary.attrib.get("term", "")
        if start + batch_size < len(ids):
            time.sleep(delay_seconds)

    sample["arxiv_primary"] = sample["arxiv_id"].map(found).fillna("")
    sample["agreement"] = sample["ads_primary"].eq(sample["arxiv_primary"]).where(sample["arxiv_primary"].ne(""))
    sample["validation_status"] = np.where(
        sample["arxiv_primary"].ne(""), "validated", "arXiv record not returned"
    )
    sample.to_csv(validation_csv, index=False)

    validated = sample[sample["validation_status"].eq("validated")]
    successes = int(validated["agreement"].sum())
    total = int(len(validated))
    low, high = wilson_interval(successes, total)
    summary = pd.DataFrame(
        [{
            "n_sampled": len(sample),
            "n_validated": total,
            "n_agree": successes,
            "agreement_rate": successes / total if total else math.nan,
            "agreement_low": low,
            "agreement_high": high,
        }]
    )
    summary.to_csv(validation_csv.with_name("primary_category_validation_summary.csv"), index=False)
    return sample


def _listify(value: object) -> list[str]:
    if isinstance(value, np.ndarray):
        return [str(x) for x in value.tolist()]
    if isinstance(value, (list, tuple)):
        return [str(x) for x in value]
    return []


def _validation_annotation_frame(sample: pd.DataFrame) -> pd.DataFrame:
    return sample[
        ["sample_id", "bibcode", "year", "arxiv_category", "period", "abstract_clean"]
    ].rename(columns={"arxiv_category": "field", "abstract_clean": "abstract"}).assign(
        gold_any_candidate="",
        gold_candidates="",
        notes="",
    )


def prepare_candidate_validation_samples(
    enriched: pd.DataFrame, validation_dir: Path
) -> dict[str, pd.DataFrame]:
    validation_dir.mkdir(parents=True, exist_ok=True)
    eligible = enriched[
        enriched["eligible_for_model_extraction"].fillna(False)
        & enriched["year"].between(START_YEAR, END_YEAR)
        & enriched["arxiv_category"].isin(FOCAL_FIELDS)
        & enriched["abstract_clean"].notna()
    ].copy()
    eligible["system_candidates"] = eligible["dm_candidate_species"].map(_listify)
    eligible["system_any_candidate"] = eligible["system_candidates"].map(bool)
    eligible["period"] = eligible["year"].astype(int).map(_period)
    eligible = eligible.drop_duplicates("bibcode")
    paper_system_candidates = eligible.set_index("bibcode")["system_candidates"].to_dict()

    exploded = eligible[eligible["system_any_candidate"]].explode("system_candidates")
    top_families = exploded["system_candidates"].value_counts().head(VALIDATION_TOP_FAMILIES).index.tolist()
    rng = np.random.default_rng(SEED)
    used: set[str] = set()

    def family_sample(per_family: int, split: str) -> pd.DataFrame:
        parts: list[pd.DataFrame] = []
        for family in top_families:
            pool = exploded[
                exploded["system_candidates"].eq(family) & ~exploded["bibcode"].isin(used)
            ].drop_duplicates("bibcode")
            if len(pool) < per_family:
                raise ValueError(f"Insufficient validation examples for {family}")
            selected_idx = rng.choice(pool.index.to_numpy(), size=per_family, replace=False)
            selected = pool.loc[selected_idx].copy()
            selected["target_family"] = family
            selected["split"] = split
            used.update(selected["bibcode"].astype(str))
            parts.append(selected)
        return pd.concat(parts, ignore_index=True)

    development = family_sample(30, "development")
    positive_holdout = family_sample(30, "holdout-positive")

    population_pool = eligible[~eligible["bibcode"].isin(used)].copy()
    population = _sample_by_strata(
        population_pool,
        ["arxiv_category", "period"],
        480,
        rng,
        minimum=30,
    )
    population["target_family"] = "population sample"
    population["split"] = "holdout-population"

    samples = {
        "candidate_validation_development": development,
        "candidate_validation_holdout_population": population,
        "candidate_validation_holdout_positive": positive_holdout,
    }
    key_parts: list[pd.DataFrame] = []
    for name, frame in samples.items():
        frame = frame.copy()
        frame["sample_id"] = [f"{name}-{i + 1:04d}" for i in range(len(frame))]
        annotation_path = validation_dir / f"{name}.csv"
        if not annotation_path.exists():
            _validation_annotation_frame(frame).to_csv(annotation_path, index=False)
        key_parts.append(
            frame[["sample_id", "bibcode", "split", "target_family"]].assign(
                system_candidates=lambda d: d["bibcode"].map(paper_system_candidates).map(
                    lambda x: ";".join(_listify(x))
                ),
                system_any_candidate=lambda d: d["system_candidates"].ne(""),
            )
        )
        samples[name] = frame

    key = pd.concat(key_parts, ignore_index=True)
    key.to_csv(validation_dir / "candidate_validation_system_key.csv", index=False)
    codebook = validation_dir / "candidate_validation_codebook.md"
    if not codebook.exists():
        codebook.write_text(
            "# Candidate validation codebook\n\n"
            "Annotate the abstract without consulting `candidate_validation_system_key.csv`.\n\n"
            "- `gold_any_candidate`: enter `yes` when the abstract mentions at least one physical dark-matter candidate, otherwise `no`.\n"
            "- `gold_candidates`: enter each canonical candidate family mentioned in the abstract once, separated by semicolons. The unit is the paper--candidate-family pair, not the number of times a name appears.\n"
            "- Select every applicable family. Generic and specific labels may both be recorded when both are explicit; synonymous tags mapped to one family still contribute only one family.\n"
            "- Count explicit mentions made in comparison, criticism, constraint, or exclusion as well as candidates favored by the paper. The annotation records organized attention, not endorsement or viability.\n"
            "- Use the candidate as written in context. Do not code portals, production mechanisms, interaction types, or generic `dark sector` language as candidates.\n"
            "- Record ambiguity or a proposed new canonical label in `notes`.\n"
            "- Development annotations may inform dictionary refinement. Holdout annotations must remain unopened until the dictionary is frozen.\n",
            encoding="utf-8",
        )
    return samples


def _parse_gold(value: object) -> set[str]:
    if not isinstance(value, str) or not value.strip():
        return set()
    return {part.strip() for part in value.split(";") if part.strip()}


def _safe_ratio(numerator: int | float, denominator: int | float) -> float:
    return float(numerator / denominator) if denominator else math.nan


def _validation_metrics(scored: pd.DataFrame) -> dict[str, float | int]:
    """Return family-mention and abstract-level classification metrics."""
    tp = sum(len(predicted & gold) for predicted, gold in zip(scored.predicted, scored.gold))
    fp = sum(len(predicted - gold) for predicted, gold in zip(scored.predicted, scored.gold))
    fn = sum(len(gold - predicted) for predicted, gold in zip(scored.predicted, scored.gold))
    precision = _safe_ratio(tp, tp + fp)
    recall = _safe_ratio(tp, tp + fn)
    f1 = _safe_ratio(2 * precision * recall, precision + recall)

    predicted_any = scored["predicted"].map(bool).to_numpy(dtype=bool)
    gold_any = scored["gold_any_candidate"].astype("string").str.lower().eq("yes").to_numpy(dtype=bool)
    abstract_tp = int(np.sum(predicted_any & gold_any))
    abstract_fp = int(np.sum(predicted_any & ~gold_any))
    abstract_tn = int(np.sum(~predicted_any & ~gold_any))
    abstract_fn = int(np.sum(~predicted_any & gold_any))
    abstract_precision = _safe_ratio(abstract_tp, abstract_tp + abstract_fp)
    abstract_recall = _safe_ratio(abstract_tp, abstract_tp + abstract_fn)
    abstract_f1 = _safe_ratio(
        2 * abstract_precision * abstract_recall,
        abstract_precision + abstract_recall,
    )
    return {
        "family_tp": tp,
        "family_fp": fp,
        "family_fn": fn,
        "micro_precision": precision,
        "micro_recall": recall,
        "micro_f1": f1,
        "abstract_tp": abstract_tp,
        "abstract_fp": abstract_fp,
        "abstract_tn": abstract_tn,
        "abstract_fn": abstract_fn,
        "abstract_precision": abstract_precision,
        "abstract_recall": abstract_recall,
        "abstract_f1": abstract_f1,
        "abstract_accuracy": _safe_ratio(abstract_tp + abstract_tn, len(scored)),
        "abstract_false_positive_rate": _safe_ratio(abstract_fp, abstract_fp + abstract_tn),
        "abstract_false_negative_rate": _safe_ratio(abstract_fn, abstract_fn + abstract_tp),
    }


def _validation_predictions(validation_dir: Path, key: pd.DataFrame) -> pd.DataFrame:
    """Recover predictions from canonical candidate data, with key fallback.

    The canonical table avoids relying on legacy positive-holdout keys in which
    an exploded sampling frame could erase the full paper-level prediction set.
    """
    candidates_path = validation_dir.parent / "dm_model_candidates_long.parquet"
    if candidates_path.exists():
        candidates = pd.read_parquet(candidates_path, columns=["bibcode", "SpeciesLabel"])
        predictions = (
            candidates.dropna(subset=["bibcode", "SpeciesLabel"])
            .drop_duplicates(["bibcode", "SpeciesLabel"])
            .groupby("bibcode")["SpeciesLabel"]
            .agg(lambda values: ";".join(sorted(set(map(str, values)), key=str.casefold)))
        )
        key = key.copy()
        key["system_candidates"] = key["bibcode"].map(predictions).fillna("")
        key["system_any_candidate"] = key["system_candidates"].ne("")
    return key


def _blank_validation_summary(
    component: str,
    estimand: str,
    required: int,
    completed: int,
) -> dict[str, object]:
    row: dict[str, object] = {
        "component": component,
        "estimand": estimand,
        "status": "complete" if completed == required else "pending manual annotation",
        "n_required": required,
        "n_completed": completed,
    }
    for column in (
        "family_tp", "family_fp", "family_fn", "micro_precision", "precision_low",
        "precision_high", "micro_recall", "recall_low", "recall_high", "micro_f1",
        "f1_low", "f1_high", "abstract_tp", "abstract_fp", "abstract_tn", "abstract_fn",
        "abstract_precision", "abstract_recall", "abstract_f1", "abstract_accuracy",
        "abstract_false_positive_rate", "abstract_false_negative_rate",
    ):
        row[column] = math.nan
    return row


def _bootstrap_validation_metrics(scored: pd.DataFrame) -> dict[str, float]:
    rng = np.random.default_rng(SEED)
    boot = []
    for _ in range(N_BOOTSTRAP):
        draw = scored.iloc[rng.integers(0, len(scored), len(scored))]
        metrics = _validation_metrics(draw)
        boot.append(
            (metrics["micro_precision"], metrics["micro_recall"], metrics["micro_f1"])
        )
    values = np.asarray(boot, dtype=float)
    return {
        "precision_low": float(np.nanpercentile(values[:, 0], 2.5)),
        "precision_high": float(np.nanpercentile(values[:, 0], 97.5)),
        "recall_low": float(np.nanpercentile(values[:, 1], 2.5)),
        "recall_high": float(np.nanpercentile(values[:, 1], 97.5)),
        "f1_low": float(np.nanpercentile(values[:, 2], 2.5)),
        "f1_high": float(np.nanpercentile(values[:, 2], 97.5)),
    }


def score_candidate_validation(validation_dir: Path) -> pd.DataFrame:
    key = _validation_predictions(
        validation_dir,
        pd.read_csv(validation_dir / "candidate_validation_system_key.csv"),
    )
    component_config = {
        "holdout-positive": {
            "filename": "candidate_validation_holdout_positive.csv",
            "label": "system-positive holdout",
            "estimand": "candidate-enriched precision and family-level performance; not population prevalence",
        },
        "holdout-population": {
            "filename": "candidate_validation_holdout_population.csv",
            "label": "population holdout",
            "estimand": "unweighted performance in the stratified field-by-period population sample",
        },
    }
    summary_rows: list[dict[str, object]] = []
    complete_components: dict[str, pd.DataFrame] = {}

    for split, config in component_config.items():
        annotations = pd.read_csv(validation_dir / str(config["filename"]))
        component_key = key[key["split"].eq(split)]
        scored = annotations.merge(
            component_key,
            on=["sample_id", "bibcode"],
            how="left",
            validate="one_to_one",
        )
        completed_mask = scored["gold_any_candidate"].astype("string").str.lower().isin(["yes", "no"])
        row = _blank_validation_summary(
            str(config["label"]), str(config["estimand"]), len(scored), int(completed_mask.sum())
        )
        if completed_mask.all():
            scored["predicted"] = scored["system_candidates"].map(_parse_gold)
            scored["gold"] = scored["gold_candidates"].map(_parse_gold)
            row.update(_validation_metrics(scored))
            row.update(_bootstrap_validation_metrics(scored))
            complete_components[split] = scored
        summary_rows.append(row)

    summary = pd.DataFrame(summary_rows)
    summary.to_csv(validation_dir / "candidate_validation_summary.csv", index=False)

    breakdown_columns = [
        "component", "breakdown", "field", "period", "n_records",
        "family_tp", "family_fp", "family_fn", "micro_precision", "micro_recall", "micro_f1",
        "abstract_tp", "abstract_fp", "abstract_tn", "abstract_fn", "abstract_precision",
        "abstract_recall", "abstract_f1", "abstract_accuracy", "abstract_false_positive_rate",
        "abstract_false_negative_rate",
    ]
    breakdown_rows: list[dict[str, object]] = []
    population = complete_components.get("holdout-population")
    if population is not None:
        group_specs = [
            ("overall", []),
            ("field", ["field"]),
            ("period", ["period"]),
            ("field-period", ["field", "period"]),
        ]
        for label, columns in group_specs:
            groups = [((), population)] if not columns else population.groupby(columns, dropna=False)
            for key_values, group in groups:
                values = key_values if isinstance(key_values, tuple) else (key_values,)
                identifiers = dict(zip(columns, values))
                breakdown_rows.append(
                    {
                        "component": "population holdout",
                        "breakdown": label,
                        "field": identifiers.get("field", "all"),
                        "period": identifiers.get("period", "all"),
                        "n_records": len(group),
                        **_validation_metrics(group),
                    }
                )
    pd.DataFrame(breakdown_rows, columns=breakdown_columns).to_csv(
        validation_dir / "candidate_validation_field_period_performance.csv", index=False
    )

    family_columns = [
        "component", "candidate_family", "n_records", "n_predicted", "n_gold",
        "true_positive", "false_positive", "false_negative", "precision", "recall", "f1",
    ]
    family_rows: list[dict[str, object]] = []
    for split, scored in complete_components.items():
        families = sorted(set().union(*scored.predicted, *scored.gold), key=str.casefold)
        for family in families:
            family_tp = sum(
                family in predicted and family in gold
                for predicted, gold in zip(scored.predicted, scored.gold)
            )
            family_fp = sum(
                family in predicted and family not in gold
                for predicted, gold in zip(scored.predicted, scored.gold)
            )
            family_fn = sum(
                family not in predicted and family in gold
                for predicted, gold in zip(scored.predicted, scored.gold)
            )
            precision = _safe_ratio(family_tp, family_tp + family_fp)
            recall = _safe_ratio(family_tp, family_tp + family_fn)
            family_rows.append(
                {
                    "component": component_config[split]["label"],
                    "candidate_family": family,
                    "n_records": len(scored),
                    "n_predicted": family_tp + family_fp,
                    "n_gold": family_tp + family_fn,
                    "true_positive": family_tp,
                    "false_positive": family_fp,
                    "false_negative": family_fn,
                    "precision": precision,
                    "recall": recall,
                    "f1": _safe_ratio(2 * precision * recall, precision + recall),
                }
            )
    family_performance = pd.DataFrame(family_rows, columns=family_columns)
    family_performance.to_csv(
        validation_dir / "candidate_validation_family_performance.csv", index=False
    )
    positive_precision = family_performance[
        family_performance["component"].eq("system-positive holdout")
    ].copy()
    positive_precision.to_csv(
        validation_dir / "candidate_validation_family_precision.csv", index=False
    )
    return summary


def _normalize_counts(counts: np.ndarray, pseudocount: float = 0.0) -> np.ndarray:
    values = np.asarray(counts, dtype=float) + pseudocount
    total = values.sum(axis=-1, keepdims=True)
    return np.divide(values, total, out=np.zeros_like(values), where=total > 0)


def jensen_shannon_divergence(p: np.ndarray, q: np.ndarray) -> np.ndarray:
    p = _normalize_counts(np.asarray(p, dtype=float))
    q = _normalize_counts(np.asarray(q, dtype=float))
    m = 0.5 * (p + q)

    def kl(a: np.ndarray, b: np.ndarray) -> np.ndarray:
        terms = np.zeros_like(a, dtype=float)
        mask = a > 0
        terms[mask] = a[mask] * np.log2(a[mask] / b[mask])
        return terms.sum(axis=-1)

    return 0.5 * kl(p, m) + 0.5 * kl(q, m)


def total_variation_distance(p: np.ndarray, q: np.ndarray) -> np.ndarray:
    p = _normalize_counts(np.asarray(p, dtype=float))
    q = _normalize_counts(np.asarray(q, dtype=float))
    return 0.5 * np.abs(p - q).sum(axis=-1)


def cosine_distance(p: np.ndarray, q: np.ndarray) -> np.ndarray:
    p = np.asarray(p, dtype=float)
    q = np.asarray(q, dtype=float)
    numerator = (p * q).sum(axis=-1)
    denominator = np.linalg.norm(p, axis=-1) * np.linalg.norm(q, axis=-1)
    similarity = np.divide(numerator, denominator, out=np.zeros_like(numerator, dtype=float), where=denominator > 0)
    return 1 - similarity


def _paper_species_matrix(data: pd.DataFrame, species: list[str]) -> tuple[np.ndarray, np.ndarray]:
    matrix = (
        data.assign(value=1)
        .pivot_table(index="bibcode", columns="SpeciesLabel", values="value", aggfunc="max", fill_value=0)
        .reindex(columns=species, fill_value=0)
    )
    return matrix.index.to_numpy(), matrix.to_numpy(dtype=np.int16)


def equal_paper_candidate_weights(data: pd.DataFrame) -> pd.DataFrame:
    """Give every paper total weight one across the families it mentions."""
    required = {"bibcode", "year", "arxiv_category", "SpeciesLabel"}
    if not required.issubset(data.columns):
        raise ValueError(f"candidate data must contain {sorted(required)}")
    result = data.drop_duplicates(list(required)).copy()
    result["n_families_in_paper"] = result.groupby(
        ["bibcode", "year", "arxiv_category"]
    )["SpeciesLabel"].transform("nunique")
    result["candidate_weight"] = 1.0 / result["n_families_in_paper"]
    return result


def _candidate_js_for_year(
    data: pd.DataFrame,
    species: list[str],
    weight_column: str | None = None,
) -> float:
    if data.empty:
        return math.nan
    if weight_column:
        counts = (
            data.groupby(["arxiv_category", "SpeciesLabel"])[weight_column]
            .sum()
            .unstack(0, fill_value=0)
            .reindex(species, fill_value=0)
        )
    else:
        counts = (
            data.groupby(["arxiv_category", "SpeciesLabel"])["bibcode"]
            .nunique()
            .unstack(0, fill_value=0)
            .reindex(species, fill_value=0)
        )
    if ASTRO not in counts or HEP not in counts:
        return math.nan
    return float(
        jensen_shannon_divergence(
            counts[ASTRO].to_numpy(dtype=float), counts[HEP].to_numpy(dtype=float)
        )
    )


def _candidate_js_yearly(
    data: pd.DataFrame,
    species: list[str],
    weight_column: str | None = None,
) -> pd.DataFrame:
    rows = [
        {
            "year": int(year),
            "js_divergence": _candidate_js_for_year(year_data, species, weight_column),
        }
        for year, year_data in data.groupby("year")
    ]
    return pd.DataFrame(rows).sort_values("year").reset_index(drop=True)


def _contrast_row(
    yearly: pd.DataFrame,
    specification: str,
    early_period: tuple[int, int] = (1995, 2004),
    late_period: tuple[int, int] = (2016, 2025),
) -> dict[str, object]:
    early = yearly["year"].between(*early_period)
    late = yearly["year"].between(*late_period)
    early_mean = float(yearly.loc[early, "js_divergence"].mean())
    late_mean = float(yearly.loc[late, "js_divergence"].mean())
    return {
        "specification": specification,
        "early_period": f"{early_period[0]}-{early_period[1]}",
        "late_period": f"{late_period[0]}-{late_period[1]}",
        "early_mean_js": early_mean,
        "late_mean_js": late_mean,
        "late_minus_early": late_mean - early_mean,
    }


def build_candidate_family_selection_sensitivity(
    candidate_data: pd.DataFrame,
    top_k_values: Sequence[int] = tuple(range(3, 21)),
) -> pd.DataFrame:
    """Compare annual JSD across frequency-ranked candidate-family scopes.

    For each ``top_k``, families are selected independently by document
    frequency in astrophysics and HEP over the full analysis period, after
    which the union of the two lists defines the common yearly vocabulary.
    The final row retains every observed ontology family.
    """
    required = {"bibcode", "year", "arxiv_category", "SpeciesLabel"}
    if not required.issubset(candidate_data.columns):
        raise ValueError(f"candidate data must contain {sorted(required)}")
    data = candidate_data[
        candidate_data["year"].between(START_YEAR, END_YEAR)
        & candidate_data["arxiv_category"].isin(FOCAL_FIELDS)
    ].drop_duplicates(["bibcode", "year", "arxiv_category", "SpeciesLabel"])
    ranked = (
        data.groupby(["arxiv_category", "SpeciesLabel"])["bibcode"]
        .nunique()
        .rename("n")
        .reset_index()
        .sort_values(["arxiv_category", "n", "SpeciesLabel"], ascending=[True, False, True])
    )
    rows: list[dict[str, object]] = []
    for top_k in sorted({int(value) for value in top_k_values if int(value) > 0}):
        selected = ranked.groupby("arxiv_category", sort=False).head(top_k)
        species = sorted(selected["SpeciesLabel"].unique().tolist())
        contrast = _contrast_row(
            _candidate_js_yearly(data[data["SpeciesLabel"].isin(species)], species),
            f"union of top {top_k} families per field",
        )
        rows.append(
            {
                "selection": "frequency-ranked union",
                "top_k_per_field": top_k,
                "n_unique_families": len(species),
                "selected_families": ";".join(species),
                **contrast,
            }
        )

    all_species = sorted(data["SpeciesLabel"].unique().tolist())
    all_contrast = _contrast_row(
        _candidate_js_yearly(data, all_species),
        "all observed ontology families",
    )
    rows.append(
        {
            "selection": "all observed ontology families",
            "top_k_per_field": pd.NA,
            "n_unique_families": len(all_species),
            "selected_families": ";".join(all_species),
            **all_contrast,
        }
    )
    return pd.DataFrame(rows)


def build_candidate_sensitivities(
    tracked: pd.DataFrame,
    species: list[str],
    output_dir: Path,
    n_iterations: int = N_SENSITIVITY,
) -> dict[str, pd.DataFrame]:
    """Build small-sample, weighting, hierarchy, and cutoff checks."""
    tracked = tracked.drop_duplicates(
        ["bibcode", "year", "arxiv_category", "SpeciesLabel"]
    ).copy()
    primary_yearly = _candidate_js_yearly(tracked, species)

    equal_weighted = equal_paper_candidate_weights(tracked)
    equal_yearly = _candidate_js_yearly(
        equal_weighted, species, weight_column="candidate_weight"
    )

    tracked_wimp_labels = set(species).intersection(
        {"Generic WIMP", "Neutralino", "LSP", "Higgsino", "Gravitino", "Sneutrino"}
    )
    specific_wimp_labels = tracked_wimp_labels - {"Generic WIMP"}
    paper_wimp_flags = (
        tracked.groupby("bibcode")["SpeciesLabel"]
        .agg(
            generic_wimp=lambda values: "Generic WIMP" in set(values),
            specific_wimp=lambda values: bool(set(values).intersection(specific_wimp_labels)),
        )
        .reset_index()
    )
    generic_papers = int(paper_wimp_flags["generic_wimp"].sum())
    generic_overlap = int(
        (paper_wimp_flags["generic_wimp"] & paper_wimp_flags["specific_wimp"]).sum()
    )

    overlap_bibcodes = set(
        paper_wimp_flags.loc[
            paper_wimp_flags["generic_wimp"] & paper_wimp_flags["specific_wimp"],
            "bibcode",
        ]
    )
    generic_suppressed = tracked[
        ~(
            tracked["bibcode"].isin(overlap_bibcodes)
            & tracked["SpeciesLabel"].eq("Generic WIMP")
        )
    ].copy()
    suppressed_yearly = _candidate_js_yearly(generic_suppressed, species)

    collapsed = tracked.assign(
        SpeciesLabel=lambda d: d["SpeciesLabel"].where(
            ~d["SpeciesLabel"].isin(tracked_wimp_labels), "WIMP-related"
        )
    ).drop_duplicates(["bibcode", "year", "arxiv_category", "SpeciesLabel"])
    collapsed_species = sorted((set(species) - tracked_wimp_labels) | {"WIMP-related"})
    collapsed_yearly = _candidate_js_yearly(collapsed, collapsed_species)

    specification_rows = [
        _contrast_row(primary_yearly, "paper-family mentions (primary)"),
        _contrast_row(equal_yearly, "equal total weight per paper"),
        _contrast_row(suppressed_yearly, "overlapping generic WIMP suppressed"),
        _contrast_row(collapsed_yearly, "tracked WIMP families collapsed"),
        _contrast_row(
            primary_yearly,
            "paper-family mentions; 2024 cutoff",
            late_period=(2015, 2024),
        ),
    ]
    specification = pd.DataFrame(specification_rows)
    specification["generic_wimp_papers"] = generic_papers
    specification["generic_specific_overlap_papers"] = generic_overlap
    specification["generic_specific_overlap_share"] = (
        generic_overlap / generic_papers if generic_papers else math.nan
    )

    matrices: dict[int, tuple[np.ndarray, np.ndarray]] = {}
    for year, year_data in tracked.groupby("year"):
        astro = year_data[year_data["arxiv_category"].eq(ASTRO)]
        hep = year_data[year_data["arxiv_category"].eq(HEP)]
        if astro.empty or hep.empty:
            continue
        matrices[int(year)] = (
            _paper_species_matrix(astro, species)[1],
            _paper_species_matrix(hep, species)[1],
        )

    target_astro = min(len(pair[0]) for pair in matrices.values())
    target_hep = min(len(pair[1]) for pair in matrices.values())
    rare_rng = np.random.default_rng(SEED + 1)
    permutation_rng = np.random.default_rng(SEED + 2)
    rare_by_year: dict[int, np.ndarray] = {}
    null_by_year: dict[int, np.ndarray] = {}
    rarefaction_rows: list[dict[str, object]] = []
    permutation_rows: list[dict[str, object]] = []

    for year, (astro_matrix, hep_matrix) in sorted(matrices.items()):
        rare_values = np.empty(n_iterations, dtype=float)
        null_values = np.empty(n_iterations, dtype=float)
        combined = np.vstack([astro_matrix, hep_matrix])
        n_astro = len(astro_matrix)
        n_hep = len(hep_matrix)
        observed = float(
            jensen_shannon_divergence(
                astro_matrix.sum(axis=0), hep_matrix.sum(axis=0)
            )
        )
        for iteration in range(n_iterations):
            astro_idx = rare_rng.choice(n_astro, size=target_astro, replace=False)
            hep_idx = rare_rng.choice(n_hep, size=target_hep, replace=False)
            rare_values[iteration] = jensen_shannon_divergence(
                astro_matrix[astro_idx].sum(axis=0),
                hep_matrix[hep_idx].sum(axis=0),
            )

            permuted = permutation_rng.permutation(len(combined))
            null_values[iteration] = jensen_shannon_divergence(
                combined[permuted[:n_astro]].sum(axis=0),
                combined[permuted[n_astro:]].sum(axis=0),
            )

        rare_by_year[year] = rare_values
        null_by_year[year] = null_values
        rarefaction_rows.append(
            {
                "year": year,
                "target_astro_papers": target_astro,
                "target_hep_papers": target_hep,
                "rarefied_js_mean": float(rare_values.mean()),
                "rarefied_js_low": float(np.percentile(rare_values, 2.5)),
                "rarefied_js_high": float(np.percentile(rare_values, 97.5)),
            }
        )
        null_low, null_high = np.percentile(null_values, [2.5, 97.5])
        permutation_rows.append(
            {
                "year": year,
                "observed_js": observed,
                "permutation_js_mean": float(null_values.mean()),
                "permutation_js_low": float(null_low),
                "permutation_js_high": float(null_high),
                "observed_minus_null_mean": observed - float(null_values.mean()),
                "observed_above_null_95": observed > float(null_high),
            }
        )

    early_years = [year for year in range(1995, 2005) if year in matrices]
    late_years = [year for year in range(2016, 2026) if year in matrices]
    rare_early = np.vstack([rare_by_year[year] for year in early_years]).mean(axis=0)
    rare_late = np.vstack([rare_by_year[year] for year in late_years]).mean(axis=0)
    rare_contrast = rare_late - rare_early

    observed_by_year = {
        int(row["year"]): float(row["observed_js"]) for row in permutation_rows
    }
    excess_by_year = {
        year: observed_by_year[year] - null_by_year[year] for year in matrices
    }
    excess_early = np.vstack([excess_by_year[year] for year in early_years]).mean(axis=0)
    excess_late = np.vstack([excess_by_year[year] for year in late_years]).mean(axis=0)
    excess_contrast = excess_late - excess_early

    bias_summary = pd.DataFrame(
        [
            {
                "sensitivity": "rarefaction to minimum annual field support",
                "early_mean": float(rare_early.mean()),
                "late_mean": float(rare_late.mean()),
                "late_minus_early": float(rare_contrast.mean()),
                "contrast_low": float(np.percentile(rare_contrast, 2.5)),
                "contrast_high": float(np.percentile(rare_contrast, 97.5)),
                "iterations": n_iterations,
            },
            {
                "sensitivity": "observed divergence above within-year permutation null",
                "early_mean": float(excess_early.mean()),
                "late_mean": float(excess_late.mean()),
                "late_minus_early": float(excess_contrast.mean()),
                "contrast_low": float(np.percentile(excess_contrast, 2.5)),
                "contrast_high": float(np.percentile(excess_contrast, 97.5)),
                "iterations": n_iterations,
            },
        ]
    )

    outputs = {
        "candidate_specification_sensitivity": specification,
        "candidate_rarefaction_yearly": pd.DataFrame(rarefaction_rows),
        "candidate_permutation_yearly": pd.DataFrame(permutation_rows),
        "candidate_bias_sensitivity_summary": bias_summary,
    }
    for name, data in outputs.items():
        data.to_parquet(output_dir / f"{name}.parquet", index=False)
        data.to_csv(output_dir / f"{name}.csv", index=False)
    return outputs


def _bootstrap_candidate_year(
    astro: pd.DataFrame,
    hep: pd.DataFrame,
    species: list[str],
    rng: np.random.Generator,
    n_bootstrap: int,
) -> tuple[dict, np.ndarray, dict[str, tuple[float, float]]]:
    _, astro_matrix = _paper_species_matrix(astro, species)
    _, hep_matrix = _paper_species_matrix(hep, species)
    astro_counts = astro_matrix.sum(axis=0)
    hep_counts = hep_matrix.sum(axis=0)
    point = {
        "js_divergence": float(jensen_shannon_divergence(astro_counts, hep_counts)),
        "total_variation": float(total_variation_distance(astro_counts, hep_counts)),
        "cosine_distance": float(cosine_distance(astro_counts, hep_counts)),
        "n_astro_papers": int(len(astro_matrix)),
        "n_hep_papers": int(len(hep_matrix)),
    }

    boot_js = np.empty(n_bootstrap, dtype=float)
    log_ratios = np.empty((n_bootstrap, len(species)), dtype=float)
    chunk_size = 100
    for start in range(0, n_bootstrap, chunk_size):
        size = min(chunk_size, n_bootstrap - start)
        astro_idx = rng.integers(0, len(astro_matrix), size=(size, len(astro_matrix)))
        hep_idx = rng.integers(0, len(hep_matrix), size=(size, len(hep_matrix)))
        astro_boot = astro_matrix[astro_idx].sum(axis=1)
        hep_boot = hep_matrix[hep_idx].sum(axis=1)
        boot_js[start : start + size] = jensen_shannon_divergence(astro_boot, hep_boot)
        astro_share = _normalize_counts(astro_boot, pseudocount=0.5)
        hep_share = _normalize_counts(hep_boot, pseudocount=0.5)
        log_ratios[start : start + size] = np.log2(hep_share / astro_share)

    point["js_low"] = float(np.percentile(boot_js, 2.5))
    point["js_high"] = float(np.percentile(boot_js, 97.5))
    intervals = {
        label: (float(np.percentile(log_ratios[:, i], 2.5)), float(np.percentile(log_ratios[:, i], 97.5)))
        for i, label in enumerate(species)
    }
    return point, boot_js, intervals


def build_candidate_divergence(
    candidates: pd.DataFrame,
    papers: pd.DataFrame,
    output_dir: Path,
    n_bootstrap: int = N_BOOTSTRAP,
) -> dict[str, pd.DataFrame]:
    output_dir.mkdir(parents=True, exist_ok=True)
    candidate_data = candidates[
        candidates["year"].between(START_YEAR, END_YEAR)
        & candidates["arxiv_category"].isin(FOCAL_FIELDS)
    ].drop_duplicates(["bibcode", "year", "arxiv_category", "SpeciesLabel"])

    top = (
        candidate_data.groupby(["arxiv_category", "SpeciesLabel"])["bibcode"]
        .nunique()
        .rename("n")
        .reset_index()
        .sort_values(["arxiv_category", "n"], ascending=[True, False])
        .groupby("arxiv_category")
        .head(9)
    )
    species = sorted(top["SpeciesLabel"].unique().tolist())
    tracked = candidate_data[candidate_data["SpeciesLabel"].isin(species)].copy()
    rng = np.random.default_rng(SEED)
    divergence_rows: list[dict] = []
    field_rows: list[dict] = []
    boot_by_year: dict[int, np.ndarray] = {}

    for year in range(START_YEAR, END_YEAR + 1):
        year_data = tracked[tracked["year"].eq(year)]
        astro = year_data[year_data["arxiv_category"].eq(ASTRO)]
        hep = year_data[year_data["arxiv_category"].eq(HEP)]
        if astro.empty or hep.empty:
            continue
        point, boot_js, intervals = _bootstrap_candidate_year(
            astro, hep, species, rng, n_bootstrap
        )
        boot_by_year[year] = boot_js
        divergence_rows.append({"year": year, **point})

        counts = (
            year_data.groupby(["arxiv_category", "SpeciesLabel"])["bibcode"]
            .nunique()
            .unstack(0, fill_value=0)
            .reindex(species, fill_value=0)
        )
        for field in FOCAL_FIELDS:
            if field not in counts:
                counts[field] = 0
        astro_counts = counts[ASTRO].to_numpy(dtype=float)
        hep_counts = counts[HEP].to_numpy(dtype=float)
        astro_share = _normalize_counts(astro_counts, pseudocount=0.5)
        hep_share = _normalize_counts(hep_counts, pseudocount=0.5)
        log_ratio = np.log2(hep_share / astro_share)
        for i, label in enumerate(species):
            low, high = intervals[label]
            total_mentions = int(astro_counts[i] + hep_counts[i])
            field_rows.append(
                {
                    "year": year,
                    "SpeciesLabel": label,
                    "astro_mentions": int(astro_counts[i]),
                    "hep_mentions": int(hep_counts[i]),
                    "astro_share": float(astro_share[i]),
                    "hep_share": float(hep_share[i]),
                    "log2_hep_astro_ratio": float(log_ratio[i]),
                    "log_ratio_low": low,
                    "log_ratio_high": high,
                    "total_mentions": total_mentions,
                    "meets_minimum_count": total_mentions >= 20,
                    "interval_excludes_parity": low > 0 or high < 0,
                }
            )

    divergence = pd.DataFrame(divergence_rows)
    field_year = pd.DataFrame(field_rows)
    early_years = [year for year in range(1995, 2005) if year in boot_by_year]
    late_years = [year for year in range(2016, 2026) if year in boot_by_year]
    early_boot = np.vstack([boot_by_year[year] for year in early_years]).mean(axis=0)
    late_boot = np.vstack([boot_by_year[year] for year in late_years]).mean(axis=0)
    contrast_boot = late_boot - early_boot
    point_contrast = (
        divergence[divergence["year"].isin(late_years)]["js_divergence"].mean()
        - divergence[divergence["year"].isin(early_years)]["js_divergence"].mean()
    )
    contrast = pd.DataFrame(
        [{
            "early_period": "1995-2004",
            "late_period": "2016-2025",
            "early_mean_js": divergence[divergence["year"].isin(early_years)]["js_divergence"].mean(),
            "late_mean_js": divergence[divergence["year"].isin(late_years)]["js_divergence"].mean(),
            "late_minus_early": point_contrast,
            "contrast_low": np.percentile(contrast_boot, 2.5),
            "contrast_high": np.percentile(contrast_boot, 97.5),
            "supports_increasing_divergence": np.percentile(contrast_boot, 2.5) > 0,
        }]
    )

    # Articles/eprints-only sensitivity. Each paper still counts once per candidate.
    sensitivity_source = tracked.merge(
        papers[["bibcode", "doctype"]].drop_duplicates("bibcode"), on="bibcode", how="left"
    )
    sensitivity_rows: list[dict] = []
    for label, subset in {
        "all eligible document types": sensitivity_source,
        "articles and eprints only": sensitivity_source[
            sensitivity_source["doctype"].isin(["article", "eprint"])
        ],
    }.items():
        for year, year_data in subset.groupby("year"):
            counts = (
                year_data.groupby(["arxiv_category", "SpeciesLabel"])["bibcode"]
                .nunique()
                .unstack(0, fill_value=0)
                .reindex(species, fill_value=0)
            )
            if ASTRO not in counts or HEP not in counts:
                continue
            sensitivity_rows.append(
                {
                    "year": int(year),
                    "document_scope": label,
                    "js_divergence": float(
                        jensen_shannon_divergence(counts[ASTRO].to_numpy(), counts[HEP].to_numpy())
                    ),
                }
            )
    sensitivity = pd.DataFrame(sensitivity_rows)

    candidate_bibcodes = set(candidates["bibcode"])
    document_type_flow = (
        papers.assign(
            doctype=lambda d: d["doctype"].fillna("missing"),
            included_document_type=lambda d: ~d["doctype"].fillna("missing").isin(
                EXCLUDED_DOCTYPES
            ),
            candidate_paper=lambda d: d["bibcode"].isin(candidate_bibcodes),
        )
        .groupby(["doctype", "included_document_type"])
        .agg(
            n_corpus_papers=("bibcode", "nunique"),
            n_candidate_papers=("candidate_paper", "sum"),
        )
        .reset_index()
        .sort_values(["included_document_type", "n_corpus_papers"], ascending=[False, False])
    )

    outputs = {
        "candidate_divergence_yearly": divergence,
        "candidate_field_yearly": field_year,
        "candidate_divergence_contrast": contrast,
        "candidate_divergence_document_sensitivity": sensitivity,
        "candidate_family_selection_sensitivity": (
            build_candidate_family_selection_sensitivity(candidate_data)
        ),
        "candidate_document_type_flow": document_type_flow,
    }
    outputs.update(build_candidate_sensitivities(tracked, species, output_dir))
    for name, data in outputs.items():
        data.to_parquet(output_dir / f"{name}.parquet", index=False)
        data.to_csv(output_dir / f"{name}.csv", index=False)
    (output_dir / "tracked_candidate_species.txt").write_text("\n".join(species) + "\n", encoding="utf-8")
    return outputs


def build_lexical_divergence(unigrams: pd.DataFrame, output_dir: Path) -> pd.DataFrame:
    output_dir.mkdir(parents=True, exist_ok=True)
    data = unigrams.copy()
    data["field_norm"] = data["field"].astype(str).str.lower()
    data = data[data["field_norm"].isin(FOCAL_FIELDS)]
    rows: list[dict] = []
    for year, year_data in data.groupby("year"):
        table = year_data.pivot_table(index="term", columns="field_norm", values="n_kw", aggfunc="sum", fill_value=0)
        if ASTRO not in table or HEP not in table:
            continue
        for scope, scoped in {
            "all unigrams": table,
            "candidate terms removed": table[~table.index.astype(str).str.lower().isin(CANDIDATE_UNIGRAMS)],
        }.items():
            rows.append(
                {
                    "year": int(year),
                    "vocabulary_scope": scope,
                    "js_divergence": float(
                        jensen_shannon_divergence(scoped[ASTRO].to_numpy(), scoped[HEP].to_numpy())
                    ),
                    "total_astro_term_documents": int(scoped[ASTRO].sum()),
                    "total_hep_term_documents": int(scoped[HEP].sum()),
                    "n_terms": int(len(scoped)),
                }
            )
    result = pd.DataFrame(rows)
    result.to_parquet(output_dir / "lexical_divergence_yearly.parquet", index=False)
    result.to_csv(output_dir / "lexical_divergence_yearly.csv", index=False)
    return result


def build_analysis_summary(
    manifest: dict,
    classification: dict[str, pd.DataFrame],
    candidate: dict[str, pd.DataFrame],
    validation: pd.DataFrame | None,
    validation_dir: Path,
    output_dir: Path,
) -> dict:
    contrast = candidate["candidate_divergence_contrast"].iloc[0].to_dict()
    primary = classification["classification_primary_yearly"]
    crossover = primary[
        primary["arxiv_class"].isin(["hep-ph", "astro-ph.CO"])
        & primary["year"].between(2010, END_YEAR)
    ].pivot_table(index="year", columns="arxiv_class", values="share", fill_value=0)
    crossover_years = crossover.index[crossover.get("hep-ph", 0) > crossover.get("astro-ph.CO", 0)].tolist()
    primary_validation_path = validation_dir / "primary_category_validation_summary.csv"
    primary_validation = (
        pd.read_csv(primary_validation_path).iloc[0].replace({np.nan: None}).to_dict()
        if primary_validation_path.exists()
        else {"status": "pending arXiv metadata fetch"}
    )
    summary = {
        "analysis_cutoff_year": END_YEAR,
        "corpus_papers": manifest["row_counts_after_cutoff"]["papers"],
        "classified_papers": manifest["row_counts_after_cutoff"]["classified_papers"],
        "first_hep_ph_above_astro_ph_co_year": int(min(crossover_years)) if crossover_years else None,
        "candidate_divergence": {
            key: (bool(value) if isinstance(value, (np.bool_, bool)) else float(value) if isinstance(value, (np.floating, float)) else value)
            for key, value in contrast.items()
        },
        "candidate_validation": (
            validation.iloc[0].replace({np.nan: None}).to_dict()
            if validation is not None and not validation.empty
            else {
                "status": "optional audit not run",
                "scope": "paper-level dictionary mentions; no performance claim",
            }
        ),
        "primary_category_validation": primary_validation,
        "claim_language": (
            "increasingly dissimilar"
            if bool(contrast["supports_increasing_divergence"])
            else "persistently different"
        ),
    }
    _write_json(summary, output_dir / "analysis_summary.json")
    return summary


def build_all(
    project_root: str | Path | None = None,
    n_bootstrap: int = N_BOOTSTRAP,
    fetch_arxiv: bool = False,
    prepare_candidate_validation: bool = False,
) -> dict:
    paths = resolve_paths(project_root)
    paths.analysis_dir.mkdir(parents=True, exist_ok=True)
    paths.validation_dir.mkdir(parents=True, exist_ok=True)
    lexical_output_dir = (
        paths.project_root / "code" / "stage-outputs" / "004-build-lexical-data"
    )
    for filename in (
        "field_unigram_rankings.csv",
        "field_bigram_rankings.csv",
        "keyness_unigrams.csv",
        "keyness_bigrams.csv",
    ):
        source = lexical_output_dir / filename
        target = paths.analysis_dir / filename
        if source.exists():
            shutil.copyfile(source, target)
        elif not target.exists():
            raise FileNotFoundError(
                f"Missing stage-004 lexical ranking required for release: {source}"
            )
    frames = load_inputs(paths)
    manifest = build_manifest(paths, frames)
    classification = build_classification_outputs(
        frames["papers"], frames["classes"], paths.analysis_dir
    )
    validation_path = paths.validation_dir / "primary_category_validation.csv"
    prepare_primary_validation_sample(frames["papers"], frames["classes"], paths.validation_dir)
    if fetch_arxiv:
        fetch_arxiv_primary_categories(validation_path)
    validation = None
    if prepare_candidate_validation:
        prepare_candidate_validation_samples(frames["enriched"], paths.validation_dir)
        validation = score_candidate_validation(paths.validation_dir)
    candidate = build_candidate_divergence(
        frames["candidates"], frames["papers"], paths.analysis_dir, n_bootstrap=n_bootstrap
    )
    lexical = build_lexical_divergence(frames["unigrams"], paths.analysis_dir)
    summary = build_analysis_summary(
        manifest, classification, candidate, validation, paths.validation_dir, paths.analysis_dir
    )
    return {
        "paths": paths,
        "manifest": manifest,
        "classification": classification,
        "candidate": candidate,
        "lexical": lexical,
        "validation": validation,
        "summary": summary,
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-root", type=Path)
    parser.add_argument("--bootstrap", type=int, default=N_BOOTSTRAP)
    parser.add_argument("--fetch-arxiv", action="store_true")
    parser.add_argument(
        "--prepare-candidate-validation",
        action="store_true",
        help="prepare and score the optional manual dictionary-audit scaffold",
    )
    parser.add_argument(
        "--score-candidate-validation-only",
        action="store_true",
        help="score existing blinded holdouts without rebuilding the analysis pipeline",
    )
    args = parser.parse_args(argv)
    if args.score_candidate_validation_only:
        root = (
            args.project_root.resolve()
            if args.project_root
            else _find_project_root(Path(__file__).resolve())
        )
        summary = score_candidate_validation(root / "data" / "validation")
        print(summary.to_json(orient="records", indent=2))
        return 0
    result = build_all(
        args.project_root,
        n_bootstrap=args.bootstrap,
        fetch_arxiv=args.fetch_arxiv,
        prepare_candidate_validation=args.prepare_candidate_validation,
    )
    print(json.dumps(result["summary"], indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
