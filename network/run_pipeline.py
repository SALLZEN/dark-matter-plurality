#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import platform
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import pyarrow

from dm_network import (
    CandidateAdapter,
    EntityMatcher,
    RelationMatcher,
    build_outputs,
    entity_ontology_paths,
    extract_corpus,
    load_entity_ontology,
    load_relation_ontology,
)


PROJECT_DIR = Path(__file__).resolve().parent
WORKSPACE_DIR = PROJECT_DIR.parent


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build an audit-first candidate-centred dark-matter epistemic network."
    )
    parser.add_argument("--papers", type=Path, default=WORKSPACE_DIR / "data" / "papers.parquet")
    parser.add_argument(
        "--candidate-metadata",
        type=Path,
        default=WORKSPACE_DIR / "data" / "papers_with_dm_models.parquet",
    )
    parser.add_argument(
        "--candidate-code-dir",
        type=Path,
        default=WORKSPACE_DIR / "code",
    )
    parser.add_argument(
        "--entity-ontology", type=Path, default=PROJECT_DIR / "config" / "entity_catalog.json"
    )
    parser.add_argument(
        "--relation-ontology", type=Path, default=PROJECT_DIR / "config" / "relations.json"
    )
    parser.add_argument("--output-dir", type=Path, default=PROJECT_DIR / "outputs" / "canonical")
    parser.add_argument("--dm-scope", choices=["candidate", "all"], default="candidate")
    parser.add_argument("--min-year", type=int, default=1950)
    parser.add_argument("--max-year", type=int, default=2025)
    parser.add_argument("--fields", nargs="*", default=None)
    parser.add_argument("--max-papers", type=int, default=None)
    parser.add_argument("--min-edge-papers", type=int, default=5)
    parser.add_argument("--min-relation-papers", type=int, default=2)
    parser.add_argument("--max-relation-distance", type=int, default=180)
    parser.add_argument("--progress-every", type=int, default=2500)
    parser.add_argument(
        "--validate-only",
        action="store_true",
        help="Validate ontologies and dependencies without reading the corpus.",
    )
    return parser.parse_args()


def sha256_file(path: Path, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(chunk_size):
            digest.update(chunk)
    return digest.hexdigest()


def validate_paths(args: argparse.Namespace) -> None:
    required = [args.entity_ontology, args.relation_ontology, args.candidate_code_dir]
    if not args.validate_only:
        required.extend([args.papers, args.candidate_metadata])
    missing = [str(path) for path in required if not path.exists()]
    if missing:
        raise FileNotFoundError("Missing required paths:\n- " + "\n- ".join(missing))


def load_papers(args: argparse.Namespace) -> pd.DataFrame:
    paper_columns = ["bibcode", "abstract", "year", "doctype"]
    metadata_columns = [
        "bibcode",
        "arxiv_category",
        "eligible_for_model_extraction",
        "dm_models_count",
        "dm_models_candidates_count",
    ]
    papers = pd.read_parquet(args.papers, columns=paper_columns)
    metadata = pd.read_parquet(args.candidate_metadata, columns=metadata_columns)
    if papers["bibcode"].duplicated().any():
        raise ValueError("papers input contains duplicate bibcodes")
    if metadata["bibcode"].duplicated().any():
        raise ValueError("candidate metadata contains duplicate bibcodes")

    merged = papers.merge(metadata, on="bibcode", how="inner", validate="one_to_one")
    merged["year"] = pd.to_numeric(merged["year"], errors="coerce").astype("Int64")
    merged = merged[
        merged["year"].between(args.min_year, args.max_year, inclusive="both")
        & merged["eligible_for_model_extraction"].fillna(False)
        & merged["abstract"].notna()
    ].copy()
    count_column = "dm_models_candidates_count" if args.dm_scope == "candidate" else "dm_models_count"
    merged = merged[pd.to_numeric(merged[count_column], errors="coerce").fillna(0) > 0].copy()
    if args.fields:
        merged = merged[merged["arxiv_category"].isin(args.fields)].copy()
    merged = merged.sort_values(["year", "bibcode"], kind="mergesort").reset_index(drop=True)
    if args.max_papers is not None:
        if args.max_papers <= 0:
            raise ValueError("--max-papers must be positive")
        merged = merged.head(args.max_papers).copy()
    return merged[["bibcode", "year", "abstract", "doctype", "arxiv_category"]]


def write_table(frame: pd.DataFrame, path: Path) -> None:
    if path.suffix == ".parquet":
        frame.to_parquet(path, index=False)
    elif path.suffix == ".csv":
        frame.to_csv(path, index=False)
    else:
        raise ValueError(f"Unsupported output type: {path}")


def build_ontology_inventory(
    entities: list[Any], occurrences: pd.DataFrame
) -> pd.DataFrame:
    """Export every configured alias, including aliases with zero corpus matches."""
    columns = [
        "node_id",
        "label",
        "node_type",
        "subtype",
        "domain",
        "ontology_source",
        "match_type",
        "pattern",
        "case_sensitive",
        "matched_paper_count",
        "matched_occurrence_count",
    ]
    counts: dict[tuple[str, str], tuple[int, int]] = {}
    if not occurrences.empty:
        targets = occurrences[occurrences["occurrence_kind"] == "entity"]
        if not targets.empty:
            grouped = (
                targets.groupby(["node_id", "matched_alias"], observed=True)
                .agg(
                    matched_paper_count=("bibcode", "nunique"),
                    matched_occurrence_count=("matched_text", "size"),
                )
                .reset_index()
            )
            counts = {
                (str(row.node_id), str(row.matched_alias)): (
                    int(row.matched_paper_count),
                    int(row.matched_occurrence_count),
                )
                for row in grouped.itertuples(index=False)
            }
    rows: list[dict[str, Any]] = []
    for entity in entities:
        for alias in entity.aliases:
            match_type = "literal" if "text" in alias else "regex"
            pattern = str(alias.get("text", alias.get("regex", "")))
            paper_count, occurrence_count = counts.get((entity.id, pattern), (0, 0))
            rows.append(
                {
                    "node_id": entity.id,
                    "label": entity.label,
                    "node_type": entity.node_type,
                    "subtype": entity.subtype,
                    "domain": entity.domain,
                    "ontology_source": entity.ontology_source,
                    "match_type": match_type,
                    "pattern": pattern,
                    "case_sensitive": bool(alias.get("case_sensitive", False)),
                    "matched_paper_count": paper_count,
                    "matched_occurrence_count": occurrence_count,
                }
            )
    return pd.DataFrame(rows, columns=columns).sort_values(
        ["node_type", "node_id", "match_type", "pattern"], kind="mergesort"
    )


def validate_summary_outputs(summaries: dict[str, pd.DataFrame]) -> None:
    nodes = summaries["nodes"]
    co_edges = summaries["edges_cooccurrence"]
    abstract_edges = summaries["edges_abstract_cooccurrence"]
    relation_edges = summaries["edges_relations"]
    if nodes["Id"].duplicated().any():
        raise ValueError("Node export contains duplicate IDs")
    node_ids = set(nodes["Id"])
    for name, edges in (
        ("sentence co-occurrence", co_edges),
        ("abstract co-occurrence", abstract_edges),
        ("relation", relation_edges),
    ):
        unresolved = (set(edges["Source"]) | set(edges["Target"])) - node_ids
        if unresolved:
            raise ValueError(f"{name} edges contain unresolved node IDs: {sorted(unresolved)[:10]}")
    if co_edges.duplicated(subset=["Source", "Target"]).any():
        raise ValueError("Co-occurrence export contains duplicate endpoint pairs")
    if abstract_edges.duplicated(subset=["Source", "Target"]).any():
        raise ValueError("Abstract co-occurrence export contains duplicate endpoint pairs")
    if relation_edges["Id"].duplicated().any():
        raise ValueError("Relation export contains duplicate edge IDs")
    for scope, edges in (("sentence", co_edges), ("abstract", abstract_edges)):
        if not np.allclose(
            pd.to_numeric(edges["Weight"], errors="raise"),
            pd.to_numeric(edges["fractional_weight"], errors="raise"),
        ):
            raise ValueError(f"{scope} Gephi Weight differs from fractional_weight")
    if not np.allclose(
        pd.to_numeric(relation_edges["Weight"], errors="raise"),
        pd.to_numeric(relation_edges["paper_count"], errors="raise"),
    ):
        raise ValueError("Relation Gephi Weight differs from supporting paper_count")
    for raw_column, log_column in (
        ("weighted_degree", "weighted_degree_log1p"),
        ("weighted_degree_sentence", "weighted_degree_sentence_log1p"),
        ("weighted_degree_abstract", "weighted_degree_abstract_log1p"),
    ):
        raw = pd.to_numeric(nodes[raw_column], errors="raise")
        logged = pd.to_numeric(nodes[log_column], errors="raise")
        if not np.allclose(logged, np.log1p(raw)):
            raise ValueError(f"{log_column} differs from log1p({raw_column})")
    for column, lower, upper in (
        ("jaccard", 0.0, 1.0),
        ("cosine", 0.0, 1.0),
        ("npmi", -1.0, 1.0),
    ):
        for scope, edges in (("sentence", co_edges), ("abstract", abstract_edges)):
            values = pd.to_numeric(edges[column], errors="coerce").dropna()
            if not values.between(lower - 1e-12, upper + 1e-12).all():
                raise ValueError(
                    f"{scope} {column} contains values outside [{lower}, {upper}]"
                )
    same_sentence_share = pd.to_numeric(
        abstract_edges["same_sentence_share"], errors="coerce"
    ).dropna()
    if not same_sentence_share.between(0, 1).all():
        raise ValueError("Abstract same_sentence_share contains values outside [0, 1]")


def build_manifest(
    args: argparse.Namespace,
    papers: pd.DataFrame,
    occurrences: pd.DataFrame,
    cooccurrences: pd.DataFrame,
    abstract_cooccurrences: pd.DataFrame,
    relations: pd.DataFrame,
    summaries: dict[str, pd.DataFrame],
) -> dict[str, Any]:
    files = {
        "papers": args.papers,
        "candidate_metadata": args.candidate_metadata,
        "relation_ontology": args.relation_ontology,
        "candidate_ontology": args.candidate_code_dir
        / "dm_term_normalization"
        / "candidate_ontology.py",
        "normalization": args.candidate_code_dir
        / "dm_term_normalization"
        / "normalization.py",
        "pipeline_entrypoint": PROJECT_DIR / "run_pipeline.py",
        "pipeline_ontology_code": PROJECT_DIR / "dm_network" / "ontology.py",
        "pipeline_extraction_code": PROJECT_DIR / "dm_network" / "extraction.py",
        "pipeline_graph_code": PROJECT_DIR / "dm_network" / "graph.py",
    }
    for index, path in enumerate(entity_ontology_paths(args.entity_ontology)):
        key = "entity_ontology_catalog" if index == 0 else f"entity_ontology_{index:02d}_{path.stem}"
        files[key] = path
    return {
        "analysis": "dark-matter-epistemic-network",
        "schema_version": "2.1.0",
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "parameters": {
            "dm_scope": args.dm_scope,
            "min_year": args.min_year,
            "max_year": args.max_year,
            "fields": args.fields,
            "max_papers": args.max_papers,
            "min_edge_papers": args.min_edge_papers,
            "min_relation_papers": args.min_relation_papers,
            "max_relation_distance": args.max_relation_distance,
        },
        "inputs": {
            name: {"path": str(path.resolve()), "sha256": sha256_file(path)}
            for name, path in files.items()
        },
        "software": {
            "python": platform.python_version(),
            "pandas": pd.__version__,
            "numpy": np.__version__,
            "pyarrow": pyarrow.__version__,
            "platform": platform.platform(),
        },
        "row_counts": {
            "processed_papers": int(len(papers)),
            "occurrences": int(len(occurrences)),
            "cooccurrence_events": int(len(cooccurrences)),
            "abstract_cooccurrence_events": int(len(abstract_cooccurrences)),
            "relation_events": int(len(relations)),
            **{name: int(len(frame)) for name, frame in summaries.items()},
        },
        "semantic_contract": {
            "cooccurrence": "candidate and entity matched in the same sentence",
            "abstract_cooccurrence": "candidate and entity matched anywhere in the same abstract",
            "relation": "candidate, entity, and explicit relation cue matched locally in the same sentence",
            "edge_direction": "focal dark-matter model to associated entity; not grammatical direction",
        },
        "ontology": {
            "entity_count": int(summaries["ontology_inventory"]["node_id"].nunique()),
            "alias_count": int(len(summaries["ontology_inventory"])),
            "entity_node_types": sorted(
                summaries["ontology_inventory"]["node_type"].unique().tolist()
            ),
            "candidate_node_type": "dm_model",
        },
        "validation": {
            "summary_integrity_checks": "passed",
            "edge_endpoints_resolve": True,
            "association_measure_bounds": "passed"
        },
    }


def main() -> int:
    args = parse_args()
    validate_paths(args)
    entities = load_entity_ontology(args.entity_ontology)
    relations = load_relation_ontology(args.relation_ontology)
    candidate_adapter = CandidateAdapter(args.candidate_code_dir, dm_scope=args.dm_scope)
    entity_matcher = EntityMatcher(entities)
    relation_matcher = RelationMatcher(relations)
    print(f"Validated {len(entities)} entities and {len(relations)} relation classes")
    if args.validate_only:
        return 0

    papers = load_papers(args)
    if papers.empty:
        raise ValueError("No papers remain after applying filters")
    print(
        f"Processing {len(papers):,} candidate-bearing papers "
        f"from {int(papers.year.min())} to {int(papers.year.max())}"
    )
    occurrences, cooccurrences, abstract_cooccurrences, relation_events = extract_corpus(
        papers,
        candidate_adapter,
        entity_matcher,
        relation_matcher,
        max_relation_distance=args.max_relation_distance,
        progress_every=args.progress_every,
    )
    summaries = build_outputs(
        occurrences,
        cooccurrences,
        abstract_cooccurrences,
        relation_events,
        population_papers=len(papers),
        min_edge_papers=args.min_edge_papers,
        min_relation_papers=args.min_relation_papers,
    )
    summaries["ontology_inventory"] = build_ontology_inventory(entities, occurrences)
    validate_summary_outputs(summaries)

    args.output_dir.mkdir(parents=True, exist_ok=True)
    write_table(occurrences, args.output_dir / "occurrences.parquet")
    write_table(cooccurrences, args.output_dir / "cooccurrence_events.parquet")
    write_table(
        abstract_cooccurrences,
        args.output_dir / "abstract_cooccurrence_events.parquet",
    )
    write_table(relation_events, args.output_dir / "relation_events.parquet")
    for name, frame in summaries.items():
        write_table(frame, args.output_dir / f"{name}.csv")
    manifest = build_manifest(
        args,
        papers,
        occurrences,
        cooccurrences,
        abstract_cooccurrences,
        relation_events,
        summaries,
    )
    with (args.output_dir / "manifest.json").open("w", encoding="utf-8") as handle:
        json.dump(manifest, handle, ensure_ascii=False, indent=2)
        handle.write("\n")

    print(f"Wrote outputs to {args.output_dir.resolve()}")
    for name, count in manifest["row_counts"].items():
        print(f"  {name}: {count:,}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
