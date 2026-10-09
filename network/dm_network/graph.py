from __future__ import annotations

import math
from typing import Any

import numpy as np
import pandas as pd


PERIODS = (
    (1985, 1994, "1985-1994"),
    (1995, 2004, "1995-2004"),
    (2005, 2015, "2005-2015"),
    (2016, 2025, "2016-2025"),
)


def add_period(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    if out.empty:
        out["period"] = pd.Series(dtype="string")
        return out
    conditions = [out["year"].between(start, end) for start, end, _ in PERIODS]
    labels = [label for _, _, label in PERIODS]
    out["period"] = np.select(conditions, labels, default="outside_focal_periods")
    return out


def _npmi(joint: float, source: float, target: float, population: float) -> float:
    if min(joint, source, target, population) <= 0:
        return float("nan")
    p_xy = joint / population
    p_x = source / population
    p_y = target / population
    if p_xy >= 1:
        return 1.0
    denominator = -math.log(p_xy)
    if denominator == 0:
        return 1.0
    return math.log(p_xy / (p_x * p_y)) / denominator


def aggregate_cooccurrences(
    events: pd.DataFrame,
    occurrences: pd.DataFrame,
    population_papers: int,
    min_edge_papers: int,
) -> pd.DataFrame:
    columns = [
        "Source", "Target", "Type", "Weight", "Label", "relation", "paper_count",
        "sentence_count", "fractional_weight", "source_paper_count",
        "target_paper_count", "jaccard", "cosine", "npmi", "first_year",
        "last_year", "fields", "target_type", "target_domain",
    ]
    if events.empty:
        return pd.DataFrame(columns=columns)

    node_papers = (
        occurrences[["node_id", "bibcode"]]
        .drop_duplicates()
        .groupby("node_id", observed=True)["bibcode"]
        .nunique()
        .to_dict()
    )
    dedup = events.drop_duplicates(
        subset=["bibcode", "sentence_id", "source", "target"]
    ).copy()
    grouped = (
        dedup.groupby(["source", "target"], observed=True)
        .agg(
            paper_count=("bibcode", "nunique"),
            sentence_count=("sentence_id", "size"),
            fractional_weight=("fractional_weight", "sum"),
            first_year=("year", "min"),
            last_year=("year", "max"),
            fields=("arxiv_category", lambda x: "|".join(sorted(set(map(str, x))))),
            target_type=("target_type", "first"),
            target_domain=("target_domain", "first"),
        )
        .reset_index()
        .rename(columns={"source": "Source", "target": "Target"})
    )
    grouped = grouped[grouped["paper_count"] >= min_edge_papers].copy()
    grouped["source_paper_count"] = grouped["Source"].map(node_papers).fillna(0).astype(int)
    grouped["target_paper_count"] = grouped["Target"].map(node_papers).fillna(0).astype(int)
    denominator = (
        grouped["source_paper_count"] + grouped["target_paper_count"] - grouped["paper_count"]
    )
    grouped["jaccard"] = np.where(denominator > 0, grouped["paper_count"] / denominator, np.nan)
    grouped["cosine"] = grouped["paper_count"] / np.sqrt(
        grouped["source_paper_count"] * grouped["target_paper_count"]
    )
    grouped["npmi"] = grouped.apply(
        lambda row: _npmi(
            row.paper_count,
            row.source_paper_count,
            row.target_paper_count,
            population_papers,
        ),
        axis=1,
    )
    grouped["Type"] = "Undirected"
    # Gephi recognizes the case-sensitive `Weight` column as the edge weight.
    # Keep the analytically named source column alongside it for auditability.
    grouped["Weight"] = grouped["fractional_weight"]
    grouped["Label"] = "sentence co-occurrence"
    grouped["relation"] = "co_mentioned_in_sentence"
    return grouped[columns].sort_values(
        ["paper_count", "fractional_weight", "Source", "Target"],
        ascending=[False, False, True, True],
        kind="mergesort",
    )


def aggregate_abstract_cooccurrences(
    events: pd.DataFrame,
    occurrences: pd.DataFrame,
    population_papers: int,
    min_edge_papers: int,
) -> pd.DataFrame:
    columns = [
        "Source", "Target", "Type", "Weight", "Label", "relation", "paper_count",
        "same_sentence_paper_count", "cross_sentence_only_paper_count",
        "same_sentence_share", "mean_minimum_sentence_distance", "fractional_weight",
        "source_paper_count", "target_paper_count", "jaccard", "cosine", "npmi",
        "first_year", "last_year", "fields", "target_type", "target_domain",
    ]
    if events.empty:
        return pd.DataFrame(columns=columns)

    node_papers = (
        occurrences[["node_id", "bibcode"]]
        .drop_duplicates()
        .groupby("node_id", observed=True)["bibcode"]
        .nunique()
        .to_dict()
    )
    dedup = events.drop_duplicates(subset=["bibcode", "source", "target"]).copy()
    grouped = (
        dedup.groupby(["source", "target"], observed=True)
        .agg(
            paper_count=("bibcode", "nunique"),
            same_sentence_paper_count=("same_sentence", "sum"),
            mean_minimum_sentence_distance=("minimum_sentence_distance", "mean"),
            fractional_weight=("fractional_weight", "sum"),
            first_year=("year", "min"),
            last_year=("year", "max"),
            fields=("arxiv_category", lambda x: "|".join(sorted(set(map(str, x))))),
            target_type=("target_type", "first"),
            target_domain=("target_domain", "first"),
        )
        .reset_index()
        .rename(columns={"source": "Source", "target": "Target"})
    )
    grouped = grouped[grouped["paper_count"] >= min_edge_papers].copy()
    grouped["same_sentence_paper_count"] = grouped["same_sentence_paper_count"].astype(int)
    grouped["cross_sentence_only_paper_count"] = (
        grouped["paper_count"] - grouped["same_sentence_paper_count"]
    )
    grouped["same_sentence_share"] = (
        grouped["same_sentence_paper_count"] / grouped["paper_count"]
    )
    grouped["source_paper_count"] = grouped["Source"].map(node_papers).fillna(0).astype(int)
    grouped["target_paper_count"] = grouped["Target"].map(node_papers).fillna(0).astype(int)
    denominator = (
        grouped["source_paper_count"] + grouped["target_paper_count"] - grouped["paper_count"]
    )
    grouped["jaccard"] = np.where(denominator > 0, grouped["paper_count"] / denominator, np.nan)
    grouped["cosine"] = grouped["paper_count"] / np.sqrt(
        grouped["source_paper_count"] * grouped["target_paper_count"]
    )
    grouped["npmi"] = grouped.apply(
        lambda row: _npmi(
            row.paper_count,
            row.source_paper_count,
            row.target_paper_count,
            population_papers,
        ),
        axis=1,
    )
    grouped["Type"] = "Undirected"
    grouped["Weight"] = grouped["fractional_weight"]
    grouped["Label"] = "abstract co-occurrence"
    grouped["relation"] = "co_mentioned_in_abstract"
    return grouped[columns].sort_values(
        ["paper_count", "fractional_weight", "Source", "Target"],
        ascending=[False, False, True, True],
        kind="mergesort",
    )


def aggregate_relations(
    events: pd.DataFrame,
    min_relation_papers: int,
    confidence: str | None = None,
) -> pd.DataFrame:
    columns = [
        "Id", "Source", "Target", "Type", "Weight", "Label", "relation", "base_polarity",
        "paper_count", "event_count", "high_confidence_events", "negated_share",
        "modal_share", "mean_cue_distance", "first_year", "last_year", "fields",
        "target_type", "target_domain", "evidence_scope",
    ]
    if events.empty:
        return pd.DataFrame(columns=columns)
    selected = events if confidence is None else events[events["confidence"] == confidence]
    if selected.empty:
        return pd.DataFrame(columns=columns)
    dedup = selected.drop_duplicates(
        subset=["bibcode", "sentence_id", "source", "target", "relation"]
    ).copy()
    grouped = (
        dedup.groupby(["source", "target", "relation"], observed=True)
        .agg(
            Label=("relation_label", "first"),
            base_polarity=("base_polarity", "first"),
            paper_count=("bibcode", "nunique"),
            event_count=("bibcode", "size"),
            high_confidence_events=("confidence", lambda x: int((x == "high").sum())),
            negated_share=("negated", "mean"),
            modal_share=("modal", "mean"),
            mean_cue_distance=("cue_distance", "mean"),
            first_year=("year", "min"),
            last_year=("year", "max"),
            fields=("arxiv_category", lambda x: "|".join(sorted(set(map(str, x))))),
            target_type=("target_type", "first"),
            target_domain=("target_domain", "first"),
            evidence_scope=("evidence_scope", "first"),
        )
        .reset_index()
        .rename(columns={"source": "Source", "target": "Target"})
    )
    grouped = grouped[grouped["paper_count"] >= min_relation_papers].copy()
    grouped["Type"] = "Directed"
    # Relation events are not fractionally weighted; distinct supporting papers
    # provide the most conservative Gephi edge strength for this export.
    grouped["Weight"] = grouped["paper_count"].astype(float)
    grouped["Id"] = grouped["Source"] + "|" + grouped["relation"] + "|" + grouped["Target"]
    return grouped[columns].sort_values(
        ["paper_count", "event_count", "Source", "relation", "Target"],
        ascending=[False, False, True, True, True],
        kind="mergesort",
    )


def build_nodes(
    occurrences: pd.DataFrame,
    co_edges: pd.DataFrame,
    abstract_edges: pd.DataFrame,
) -> pd.DataFrame:
    columns = [
        "Id", "Label", "node_type", "subtype", "domain", "ontology_source", "paper_count",
        "sentence_count", "occurrence_count", "weighted_degree", "weighted_degree_log1p",
        "weighted_degree_sentence", "weighted_degree_sentence_log1p",
        "weighted_degree_abstract", "weighted_degree_abstract_log1p",
    ]
    if occurrences.empty:
        return pd.DataFrame(columns=columns)
    counted = occurrences.copy()
    counted["sentence_key"] = counted["bibcode"].astype(str) + "::" + counted["sentence_id"].astype(str)
    nodes = (
        counted.groupby("node_id", observed=True)
        .agg(
            Label=("label", "first"),
            node_type=("node_type", "first"),
            subtype=("subtype", "first"),
            domain=("domain", "first"),
            ontology_source=("ontology_source", "first"),
            paper_count=("bibcode", "nunique"),
            sentence_count=("sentence_key", "nunique"),
            occurrence_count=("matched_text", "size"),
        )
        .reset_index()
        .rename(columns={"node_id": "Id"})
    )
    def strength(edges: pd.DataFrame) -> pd.Series:
        if edges.empty:
            return pd.Series(dtype=float)
        source_strength = edges.groupby("Source")["fractional_weight"].sum()
        target_strength = edges.groupby("Target")["fractional_weight"].sum()
        return source_strength.add(target_strength, fill_value=0)

    nodes["weighted_degree_sentence"] = nodes["Id"].map(strength(co_edges)).fillna(0)
    nodes["weighted_degree_abstract"] = nodes["Id"].map(strength(abstract_edges)).fillna(0)
    nodes["weighted_degree"] = nodes["weighted_degree_sentence"]
    nodes["weighted_degree_log1p"] = np.log1p(nodes["weighted_degree"])
    nodes["weighted_degree_sentence_log1p"] = np.log1p(
        nodes["weighted_degree_sentence"]
    )
    nodes["weighted_degree_abstract_log1p"] = np.log1p(
        nodes["weighted_degree_abstract"]
    )
    return nodes[columns].sort_values(
        ["node_type", "paper_count", "Label"], ascending=[True, False, True], kind="mergesort"
    )


def _normalized_entropy(weights: pd.Series) -> float:
    weights = weights[weights > 0].astype(float)
    if len(weights) <= 1:
        return 0.0
    probabilities = weights / weights.sum()
    entropy = -(probabilities * np.log(probabilities)).sum()
    return float(entropy / math.log(len(weights)))


def candidate_metrics(co_edges: pd.DataFrame, relation_edges: pd.DataFrame) -> pd.DataFrame:
    columns = [
        "candidate_id", "paper_count", "target_count", "target_type_count",
        "target_domain_count", "weighted_degree", "mean_jaccard", "mean_cosine",
        "mean_npmi", "participation_coefficient", "normalized_layer_entropy",
        "relation_type_count", "relation_paper_count",
    ]
    if co_edges.empty:
        return pd.DataFrame(columns=columns)
    rows: list[dict[str, Any]] = []
    for source, group in co_edges.groupby("Source", observed=True):
        layer_weights = group.groupby("target_domain")["fractional_weight"].sum()
        probabilities = layer_weights / layer_weights.sum()
        relation_subset = relation_edges[relation_edges["Source"] == source]
        rows.append(
            {
                "candidate_id": source,
                "paper_count": int(group["source_paper_count"].max()),
                "target_count": int(group["Target"].nunique()),
                "target_type_count": int(group["target_type"].nunique()),
                "target_domain_count": int(group["target_domain"].nunique()),
                "weighted_degree": float(group["fractional_weight"].sum()),
                "mean_jaccard": float(group["jaccard"].mean()),
                "mean_cosine": float(group["cosine"].mean()),
                "mean_npmi": float(group["npmi"].mean()),
                "participation_coefficient": float(1 - (probabilities**2).sum()),
                "normalized_layer_entropy": _normalized_entropy(layer_weights),
                "relation_type_count": int(relation_subset["relation"].nunique()),
                "relation_paper_count": int(relation_subset["paper_count"].sum()),
            }
        )
    return pd.DataFrame(rows, columns=columns).sort_values(
        ["participation_coefficient", "target_domain_count", "weighted_degree"],
        ascending=[False, False, False],
        kind="mergesort",
    )


def pattern_frequency(occurrences: pd.DataFrame, population_papers: int) -> pd.DataFrame:
    columns = [
        "node_id", "label", "node_type", "matched_text", "paper_count",
        "sentence_count", "paper_share",
    ]
    if occurrences.empty:
        return pd.DataFrame(columns=columns)
    counted = occurrences.copy()
    counted["sentence_key"] = counted["bibcode"].astype(str) + "::" + counted["sentence_id"].astype(str)
    result = (
        counted.groupby(["node_id", "label", "node_type", "matched_text"], observed=True)
        .agg(paper_count=("bibcode", "nunique"), sentence_count=("sentence_key", "nunique"))
        .reset_index()
    )
    result["paper_share"] = result["paper_count"] / max(population_papers, 1)
    return result[columns].sort_values(
        ["paper_count", "node_id", "matched_text"], ascending=[False, True, True], kind="mergesort"
    )


def quality_flags(patterns: pd.DataFrame) -> pd.DataFrame:
    columns = ["severity", "node_id", "matched_text", "paper_count", "paper_share", "reason"]
    if patterns.empty:
        return pd.DataFrame(columns=columns)
    flags: list[dict[str, Any]] = []
    for row in patterns.itertuples(index=False):
        compact = "".join(ch for ch in str(row.matched_text) if ch.isalnum())
        formula_node = row.node_id in {"theory:f_r_gravity", "theory:f_r_t_gravity"}
        if (
            len(compact) <= 3
            and str(row.matched_text) != str(row.matched_text).upper()
            and not formula_node
        ):
            flags.append(
                {
                    "severity": "warning",
                    "node_id": row.node_id,
                    "matched_text": row.matched_text,
                    "paper_count": row.paper_count,
                    "paper_share": row.paper_share,
                    "reason": "short matched form is not uppercase",
                }
            )
        if row.paper_share >= 0.25 and row.node_type in {"apparatus", "theory"}:
            flags.append(
                {
                    "severity": "warning",
                    "node_id": row.node_id,
                    "matched_text": row.matched_text,
                    "paper_count": row.paper_count,
                    "paper_share": row.paper_share,
                    "reason": "unusually prevalent apparatus/theory match",
                }
            )
    return pd.DataFrame(flags, columns=columns).sort_values(
        ["severity", "paper_share"], ascending=[True, False], kind="mergesort"
    )


def relation_audit_sample(events: pd.DataFrame, per_stratum: int = 10) -> pd.DataFrame:
    columns = [
        "relation", "confidence", "bibcode", "year", "arxiv_category", "source",
        "source_label", "target", "target_label", "cue", "cue_distance",
        "cue_between", "negated", "modal", "sentence",
    ]
    if events.empty:
        return pd.DataFrame(columns=columns)
    selected = events.drop_duplicates(
        subset=["bibcode", "sentence_id", "source", "target", "relation"]
    ).copy()
    selected["audit_order"] = pd.util.hash_pandas_object(
        selected[["bibcode", "sentence_id", "source", "target", "relation"]],
        index=False,
    ).astype("uint64")
    selected = (
        selected.sort_values(["relation", "confidence", "audit_order"], kind="mergesort")
        .groupby(["relation", "confidence"], observed=True, sort=True)
        .head(per_stratum)
    )
    return selected[columns].sort_values(
        ["relation", "confidence", "year", "bibcode"], kind="mergesort"
    )


def build_outputs(
    occurrences: pd.DataFrame,
    cooccurrence_events: pd.DataFrame,
    abstract_cooccurrence_events: pd.DataFrame,
    relation_events: pd.DataFrame,
    population_papers: int,
    min_edge_papers: int = 5,
    min_relation_papers: int = 2,
) -> dict[str, pd.DataFrame]:
    sentence_occurrences = occurrences[
        occurrences["candidate_bearing_sentence"].fillna(False)
    ].copy()
    co_edges = aggregate_cooccurrences(
        cooccurrence_events,
        sentence_occurrences,
        population_papers=population_papers,
        min_edge_papers=min_edge_papers,
    )
    abstract_edges = aggregate_abstract_cooccurrences(
        abstract_cooccurrence_events,
        occurrences,
        population_papers=population_papers,
        min_edge_papers=min_edge_papers,
    )
    relation_edges_all = aggregate_relations(
        relation_events,
        min_relation_papers=min_relation_papers,
        confidence=None,
    )
    relation_edges = aggregate_relations(
        relation_events,
        min_relation_papers=min_relation_papers,
        confidence="high",
    )
    nodes = build_nodes(occurrences, co_edges, abstract_edges)
    metrics = candidate_metrics(co_edges, relation_edges)
    abstract_metrics = candidate_metrics(abstract_edges, relation_edges)
    patterns = pattern_frequency(occurrences, population_papers)
    flags = quality_flags(patterns)
    audit_sample = relation_audit_sample(relation_events)

    period_co_edges: list[pd.DataFrame] = []
    period_abstract_edges: list[pd.DataFrame] = []
    period_metrics: list[pd.DataFrame] = []
    period_abstract_metrics: list[pd.DataFrame] = []
    co_by_period = add_period(cooccurrence_events)
    abstract_co_by_period = add_period(abstract_cooccurrence_events)
    rel_by_period = add_period(relation_events)
    occ_by_period = add_period(occurrences)
    for _, _, period in PERIODS:
        co_subset = co_by_period[co_by_period["period"] == period].drop(columns="period")
        abstract_co_subset = abstract_co_by_period[
            abstract_co_by_period["period"] == period
        ].drop(columns="period")
        rel_subset = rel_by_period[rel_by_period["period"] == period].drop(columns="period")
        occ_subset = occ_by_period[occ_by_period["period"] == period].drop(columns="period")
        sentence_occ_subset = occ_subset[
            occ_subset["candidate_bearing_sentence"].fillna(False)
        ].copy()
        period_population = int(occ_subset["bibcode"].nunique()) if not occ_subset.empty else 0
        edges_subset = aggregate_cooccurrences(
            co_subset,
            sentence_occ_subset,
            population_papers=period_population,
            min_edge_papers=min_edge_papers,
        )
        if not edges_subset.empty:
            edges_subset.insert(0, "period", period)
            period_co_edges.append(edges_subset)
        abstract_edges_subset = aggregate_abstract_cooccurrences(
            abstract_co_subset,
            occ_subset,
            population_papers=period_population,
            min_edge_papers=min_edge_papers,
        )
        if not abstract_edges_subset.empty:
            abstract_edges_subset.insert(0, "period", period)
            period_abstract_edges.append(abstract_edges_subset)
        relation_subset = aggregate_relations(
            rel_subset,
            min_relation_papers=min_relation_papers,
            confidence="high",
        )
        metrics_subset = candidate_metrics(edges_subset.drop(columns="period", errors="ignore"), relation_subset)
        if not metrics_subset.empty:
            metrics_subset.insert(0, "period", period)
            period_metrics.append(metrics_subset)
        abstract_metrics_subset = candidate_metrics(
            abstract_edges_subset.drop(columns="period", errors="ignore"),
            relation_subset,
        )
        if not abstract_metrics_subset.empty:
            abstract_metrics_subset.insert(0, "period", period)
            period_abstract_metrics.append(abstract_metrics_subset)

    empty_period_edges = pd.DataFrame(columns=["period", *co_edges.columns])
    empty_period_abstract_edges = pd.DataFrame(columns=["period", *abstract_edges.columns])
    empty_period_metrics = pd.DataFrame(columns=["period", *metrics.columns])
    empty_period_abstract_metrics = pd.DataFrame(columns=["period", *abstract_metrics.columns])
    return {
        "nodes": nodes,
        "edges_cooccurrence": co_edges,
        "edges_abstract_cooccurrence": abstract_edges,
        "edges_relations": relation_edges,
        "edges_relations_all": relation_edges_all,
        "edges_cooccurrence_by_period": (
            pd.concat(period_co_edges, ignore_index=True) if period_co_edges else empty_period_edges
        ),
        "edges_abstract_cooccurrence_by_period": (
            pd.concat(period_abstract_edges, ignore_index=True)
            if period_abstract_edges
            else empty_period_abstract_edges
        ),
        "candidate_metrics": metrics,
        "candidate_metrics_abstract": abstract_metrics,
        "candidate_metrics_by_period": (
            pd.concat(period_metrics, ignore_index=True) if period_metrics else empty_period_metrics
        ),
        "candidate_metrics_abstract_by_period": (
            pd.concat(period_abstract_metrics, ignore_index=True)
            if period_abstract_metrics
            else empty_period_abstract_metrics
        ),
        "pattern_frequency": patterns,
        "quality_flags": flags,
        "relation_audit_sample": audit_sample,
    }
