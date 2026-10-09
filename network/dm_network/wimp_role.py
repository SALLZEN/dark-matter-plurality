from __future__ import annotations

import hashlib
import json
import math
import platform
from dataclasses import dataclass
from datetime import datetime, timezone
from itertools import combinations
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

import networkx as nx
import numpy as np
import pandas as pd
import pyarrow

from .extraction import CandidateAdapter, slugify


ASTRO = "astrophysics"
HEP = "high-energy physics"


@dataclass(frozen=True)
class Window:
    kind: str
    label: str
    start: int
    end: int


@dataclass(frozen=True)
class WimpDefinition:
    name: str
    label: str
    node_id: str
    collapse_tags: frozenset[str]

    @property
    def focal_node_id(self) -> str:
        return "dm_model:generic_wimp" if self.name == "explicit_generic" else self.node_id


def read_config(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as handle:
        config = json.load(handle)
    required = {
        "analysis_years", "focal_fields", "rolling_window_years", "stable_periods",
        "primary_wimp_definition", "wimp_definitions", "gephi",
    }
    missing = sorted(required - set(config))
    if missing:
        raise ValueError(f"WIMP-role config is missing keys: {missing}")
    if config["focal_fields"] != [ASTRO, HEP]:
        raise ValueError(f"The canonical focal field order must be [{ASTRO!r}, {HEP!r}]")
    if config["primary_wimp_definition"] not in config["wimp_definitions"]:
        raise ValueError("primary_wimp_definition must name a configured WIMP definition")
    stable_periods = config["stable_periods"]
    if len(stable_periods) != 2:
        raise ValueError("The publication design requires exactly two comparison periods")
    for start, end, label in stable_periods:
        if int(end) - int(start) + 1 != 10 or str(label) != f"{start}-{end}":
            raise ValueError("Each comparison period must be a labelled ten-year interval")
    return config


def parse_definitions(config: Mapping[str, Any]) -> list[WimpDefinition]:
    definitions: list[WimpDefinition] = []
    for name, values in config["wimp_definitions"].items():
        definitions.append(
            WimpDefinition(
                name=name,
                label=str(values["label"]),
                node_id=str(values["node_id"]),
                collapse_tags=frozenset(map(str, values.get("collapse_tags", []))),
            )
        )
    names = {definition.name for definition in definitions}
    if names != {"explicit_generic", "published_umbrella", "canonical_core"}:
        raise ValueError("The three canonical WIMP definitions must be configured")
    return definitions


def build_windows(config: Mapping[str, Any]) -> list[Window]:
    start, end = map(int, config["analysis_years"])
    width = int(config["rolling_window_years"])
    if width < 2 or start > end:
        raise ValueError("Invalid analysis years or rolling-window width")
    windows = [Window("full", f"{start}-{end}", start, end)]
    for period_start, period_end, label in config["stable_periods"]:
        windows.append(Window("stable", str(label), int(period_start), int(period_end)))
    for rolling_start in range(start, end - width + 2):
        rolling_end = rolling_start + width - 1
        windows.append(
            Window("rolling", f"{rolling_start}-{rolling_end}", rolling_start, rolling_end)
        )
    return windows


def sha256_file(path: Path, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(chunk_size):
            digest.update(chunk)
    return digest.hexdigest()


def _as_python(value: Any) -> Any:
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, (np.ndarray, list, tuple, set, frozenset)):
        return "|".join(map(str, value))
    if pd.isna(value):
        return None
    return value


def _graphml_attrs(row: Mapping[str, Any], excluded: Iterable[str] = ()) -> dict[str, Any]:
    excluded_set = set(excluded)
    attrs: dict[str, Any] = {}
    for key, value in row.items():
        if key in excluded_set:
            continue
        converted = _as_python(value)
        if converted is not None:
            attrs[str(key)] = converted
    return attrs


def write_graphml(nodes: pd.DataFrame, edges: pd.DataFrame, path: Path) -> None:
    graph = nx.Graph()
    for row in nodes.to_dict(orient="records"):
        node_id = str(row["Id"])
        graph.add_node(node_id, **_graphml_attrs(row, excluded={"Id"}))
    for row in edges.to_dict(orient="records"):
        source, target = str(row["Source"]), str(row["Target"])
        if source not in graph or target not in graph:
            raise ValueError(f"GraphML edge endpoint is absent from node table: {source}, {target}")
        graph.add_edge(source, target, **_graphml_attrs(row, excluded={"Source", "Target"}))
    path.parent.mkdir(parents=True, exist_ok=True)
    nx.write_graphml(graph, path, infer_numeric_types=True)


def write_gephi_gexf(nodes: pd.DataFrame, edges: pd.DataFrame, path: Path) -> None:
    """Write a Gephi-native graph that applies the shared master coordinates."""
    graph = nx.Graph()
    for row in nodes.to_dict(orient="records"):
        node_id = str(row["Id"])
        attrs = _graphml_attrs(row, excluded={"Id", "layout_x", "layout_y"})
        x = pd.to_numeric(pd.Series([row.get("layout_x")]), errors="coerce").iloc[0]
        y = pd.to_numeric(pd.Series([row.get("layout_y")]), errors="coerce").iloc[0]
        if pd.notna(x) and pd.notna(y):
            attrs["viz"] = {
                "position": {"x": float(x), "y": float(y), "z": 0.0}
            }
        graph.add_node(node_id, **attrs)
    for row in edges.to_dict(orient="records"):
        source, target = str(row["Source"]), str(row["Target"])
        if source not in graph or target not in graph:
            raise ValueError(f"GEXF edge endpoint is absent from node table: {source}, {target}")
        graph.add_edge(
            source,
            target,
            **_graphml_attrs(row, excluded={"Source", "Target"}),
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    nx.write_gexf(graph, path, encoding="utf-8", prettyprint=True)


def minmax_scale(values: pd.Series, lower: float, upper: float, transform: str = "identity") -> pd.Series:
    numeric = pd.to_numeric(values, errors="coerce").fillna(0).clip(lower=0).astype(float)
    if transform == "sqrt":
        numeric = np.sqrt(numeric)
    elif transform == "log1p":
        numeric = np.log1p(numeric)
    elif transform != "identity":
        raise ValueError(f"Unknown scaling transform: {transform}")
    minimum, maximum = float(numeric.min()), float(numeric.max())
    if math.isclose(minimum, maximum):
        return pd.Series((lower + upper) / 2, index=values.index, dtype=float)
    return lower + (numeric - minimum) * (upper - lower) / (maximum - minimum)


def fixed_unit_scale(
    values: pd.Series, lower: float, upper: float, transform: str = "identity"
) -> pd.Series:
    """Map an already bounded 0--1 measure to a fixed visual range."""
    numeric = pd.to_numeric(values, errors="coerce").fillna(0).clip(0, 1).astype(float)
    if transform == "sqrt":
        numeric = np.sqrt(numeric)
    elif transform != "identity":
        raise ValueError(f"Unknown fixed-unit transform: {transform}")
    return lower + numeric * (upper - lower)


def common_reference_scale(
    values: pd.Series,
    lower: float,
    upper: float,
    reference_maximum: float,
    transform: str = "identity",
) -> pd.Series:
    """Scale against a shared cross-period maximum rather than a per-graph maximum."""
    numeric = pd.to_numeric(values, errors="coerce").fillna(0).clip(lower=0).astype(float)
    maximum = float(reference_maximum)
    maximum = max(maximum, 0.0) if math.isfinite(maximum) else 0.0
    if transform == "sqrt":
        numeric = np.sqrt(numeric)
        maximum = math.sqrt(maximum)
    elif transform == "log1p":
        numeric = np.log1p(numeric)
        maximum = math.log1p(maximum)
    elif transform != "identity":
        raise ValueError(f"Unknown common-reference transform: {transform}")
    if maximum <= 0:
        return pd.Series(lower, index=values.index, dtype=float)
    return lower + numeric.clip(upper=maximum) / maximum * (upper - lower)


def master_layout_positions(
    edge_frames: Sequence[pd.DataFrame],
    weight_column: str,
    seed: int,
    iterations: int,
) -> dict[str, tuple[float, float]]:
    """Compute one deterministic union-graph layout reused by both decade panels."""
    graph = nx.Graph()
    for edges in edge_frames:
        if edges.empty:
            continue
        for row in edges.itertuples(index=False):
            source, target = str(row.Source), str(row.Target)
            weight = float(getattr(row, weight_column))
            if not math.isfinite(weight) or weight <= 0:
                continue
            if graph.has_edge(source, target):
                graph[source][target]["weight"] += weight
            else:
                graph.add_edge(source, target, weight=weight)
    if graph.number_of_nodes() == 0:
        return {}
    positions = nx.spring_layout(
        graph,
        weight="weight",
        seed=int(seed),
        iterations=int(iterations),
        method="energy",
        gravity=1.0,
        scale=1000.0,
    )
    return {
        str(node): (float(coordinates[0]), float(coordinates[1]))
        for node, coordinates in positions.items()
    }


def attach_master_layout(
    nodes: pd.DataFrame, positions: Mapping[str, tuple[float, float]]
) -> pd.DataFrame:
    out = nodes.copy()
    out["layout_x"] = out["Id"].map(lambda node: positions.get(str(node), (math.nan, math.nan))[0])
    out["layout_y"] = out["Id"].map(lambda node: positions.get(str(node), (math.nan, math.nan))[1])
    return out


def apply_common_brokerage_scales(
    nodes: pd.DataFrame, definitions: Sequence[WimpDefinition], gephi_config: Mapping[str, Any]
) -> pd.DataFrame:
    """Give both comparison decades the same betweenness, removal, and label scales."""
    out = nodes.copy()
    size_lower, size_upper = map(float, gephi_config["node_size_range"])
    label_lower, label_upper = map(float, gephi_config["label_size_range"])
    for definition in definitions:
        definition_mask = out["wimp_definition"].eq(definition.name)
        reference = out[definition_mask & out["window_kind"].eq("stable")]
        betweenness_max = float(
            pd.to_numeric(
                reference["cross_field_betweenness_prevalence"], errors="coerce"
            ).max()
        )
        removal_max = float(
            pd.to_numeric(
                reference["removal_effect_efficiency_prevalence"], errors="coerce"
            ).max()
        )
        strength_max = float(
            pd.to_numeric(reference["strength_mean_field_prevalence"], errors="coerce").max()
        )
        out.loc[definition_mask, "node_size_sqrt_betweenness_common"] = common_reference_scale(
            out.loc[definition_mask, "cross_field_betweenness_prevalence"],
            size_lower,
            size_upper,
            betweenness_max,
            transform="sqrt",
        )
        out.loc[definition_mask, "node_size_sqrt_removal_effect_common"] = common_reference_scale(
            out.loc[definition_mask, "removal_effect_efficiency_prevalence"],
            size_lower,
            size_upper,
            removal_max,
            transform="sqrt",
        )
        out.loc[definition_mask, "label_size_log_prevalence_strength_common"] = common_reference_scale(
            out.loc[definition_mask, "strength_mean_field_prevalence"],
            label_lower,
            label_upper,
            strength_max,
            transform="log1p",
        )
    return out


def percentile_rank(values: pd.Series) -> pd.Series:
    return pd.to_numeric(values, errors="coerce").rank(method="average", pct=True).fillna(0)


def _normalize_list(value: Any) -> list[str]:
    if isinstance(value, np.ndarray):
        value = value.tolist()
    if not isinstance(value, (list, tuple, set)):
        return []
    return [str(item) for item in value if isinstance(item, str) and item.strip()]


def load_paper_metadata(path: Path, min_year: int, max_year: int) -> pd.DataFrame:
    columns = [
        "bibcode", "year", "arxiv_class", "primary_arxiv_class", "arxiv_category",
        "eligible_for_model_extraction", "abstract_clean", "dm_models_candidates",
    ]
    data = pd.read_parquet(path, columns=columns)
    if data["bibcode"].duplicated().any():
        raise ValueError("Candidate metadata contains duplicate bibcodes")
    data["year"] = pd.to_numeric(data["year"], errors="coerce").astype("Int64")
    data = data[
        data["year"].between(min_year, max_year, inclusive="both")
        & data["eligible_for_model_extraction"].fillna(False)
        & data["abstract_clean"].notna()
    ].copy()
    data["candidate_tags"] = data["dm_models_candidates"].map(_normalize_list)
    data["arxiv_classes"] = data["arxiv_class"].map(_normalize_list)
    return data.drop(columns=["dm_models_candidates", "arxiv_class", "abstract_clean"])


def build_paper_table(metadata: pd.DataFrame, candidate_adapter: CandidateAdapter) -> pd.DataFrame:
    categorize = candidate_adapter.dmtn.categorize_arxiv
    rows: list[dict[str, Any]] = []
    for row in metadata.itertuples(index=False):
        broad_fields = sorted({categorize(value) for value in row.arxiv_classes})
        rows.append(
            {
                "bibcode": str(row.bibcode),
                "year": int(row.year),
                "primary_arxiv_class": row.primary_arxiv_class,
                "primary_field": str(row.arxiv_category),
                "arxiv_classes": "|".join(row.arxiv_classes),
                "broad_fields": "|".join(broad_fields),
                "has_astrophysics": ASTRO in broad_fields,
                "has_high_energy_physics": HEP in broad_fields,
                "crosslisted_astrophysics_hep": ASTRO in broad_fields and HEP in broad_fields,
                "candidate_bearing": bool(row.candidate_tags),
            }
        )
    return pd.DataFrame(rows).sort_values(["year", "bibcode"], kind="mergesort")


def build_raw_candidate_papers(metadata: pd.DataFrame, candidate_adapter: CandidateAdapter) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for row in metadata.itertuples(index=False):
        for tag in row.candidate_tags:
            labels = candidate_adapter.dmtn.candidate_species_labels([tag])
            label = labels[0] if labels else str(tag)
            rows.append(
                {
                    "bibcode": str(row.bibcode),
                    "year": int(row.year),
                    "primary_field": str(row.arxiv_category),
                    "candidate_tag": str(tag),
                    "candidate_id": f"dm_model:{slugify(label)}",
                    "candidate_label": label,
                }
            )
    columns = ["bibcode", "year", "primary_field", "candidate_tag", "candidate_id", "candidate_label"]
    if not rows:
        return pd.DataFrame(columns=columns)
    return (
        pd.DataFrame(rows, columns=columns)
        .drop_duplicates(["bibcode", "candidate_id"])
        .sort_values(["year", "bibcode", "candidate_id"], kind="mergesort")
    )


def apply_wimp_definition_to_candidates(
    candidates: pd.DataFrame, definition: WimpDefinition
) -> pd.DataFrame:
    out = candidates.copy()
    if definition.name == "explicit_generic":
        generic = out["candidate_tag"].eq("wimp")
        out.loc[generic, "candidate_id"] = definition.focal_node_id
        out.loc[generic, "candidate_label"] = definition.label
    elif definition.collapse_tags:
        collapsed = out["candidate_tag"].isin(definition.collapse_tags)
        out.loc[collapsed, "candidate_id"] = definition.node_id
        out.loc[collapsed, "candidate_label"] = definition.label
        out.loc[collapsed, "candidate_tag"] = "|".join(sorted(definition.collapse_tags))
    out.insert(0, "wimp_definition", definition.name)
    return out.drop_duplicates(["wimp_definition", "bibcode", "candidate_id"])


def apply_wimp_definition_to_occurrences(
    occurrences: pd.DataFrame, definition: WimpDefinition
) -> pd.DataFrame:
    """Apply a WIMP specification to occurrence-level candidate nodes.

    The operation is deliberately paper-binary downstream: several named WIMP
    occurrences in one abstract collapse to one canonical WIMP node before
    concept pairs are generated.
    """
    out = occurrences.copy()
    candidate_rows = out["occurrence_kind"].eq("dm_model")
    tags = out["candidate_tag"].fillna("").astype(str).str.split("|")
    if definition.name == "explicit_generic":
        collapsed = candidate_rows & tags.map(lambda values: "wimp" in values)
        out.loc[collapsed, "node_id"] = definition.focal_node_id
        out.loc[collapsed, "label"] = definition.label
    elif definition.collapse_tags:
        collapsed = candidate_rows & tags.map(
            lambda values: bool(set(values).intersection(definition.collapse_tags))
        )
        out.loc[collapsed, "node_id"] = definition.node_id
        out.loc[collapsed, "label"] = definition.label
        out.loc[collapsed, "candidate_tag"] = "|".join(sorted(definition.collapse_tags))
    out.insert(0, "wimp_definition", definition.name)
    return out


def apply_wimp_definition_to_events(
    events: pd.DataFrame, definition: WimpDefinition
) -> pd.DataFrame:
    out = events.copy()
    tags = out["candidate_tag"].fillna("").astype(str).str.split("|")
    if definition.name == "explicit_generic":
        mask = tags.map(lambda values: "wimp" in values)
        out.loc[mask, "source"] = definition.focal_node_id
        out.loc[mask, "source_label"] = definition.label
    elif definition.collapse_tags:
        mask = tags.map(lambda values: bool(set(values).intersection(definition.collapse_tags)))
        out.loc[mask, "source"] = definition.node_id
        out.loc[mask, "source_label"] = definition.label
        out.loc[mask, "candidate_tag"] = "|".join(sorted(definition.collapse_tags))
    out.insert(0, "wimp_definition", definition.name)
    return out


def _select_window(data: pd.DataFrame, window: Window) -> pd.DataFrame:
    return data[data["year"].between(window.start, window.end, inclusive="both")]


def _npmi(joint: float, source: float, target: float, population: float) -> float:
    if min(joint, source, target, population) <= 0:
        return float("nan")
    p_xy, p_x, p_y = joint / population, source / population, target / population
    if p_xy >= 1:
        return 1.0
    denominator = -math.log(p_xy)
    return 1.0 if denominator == 0 else math.log(p_xy / (p_x * p_y)) / denominator


def _normalized_entropy(weights: Sequence[float], fixed_categories: int | None = None) -> float:
    values = np.asarray([value for value in weights if value > 0], dtype=float)
    if len(values) <= 1:
        return 0.0
    probabilities = values / values.sum()
    denominator_categories = fixed_categories or len(values)
    if denominator_categories <= 1:
        return 0.0
    return float(-(probabilities * np.log(probabilities)).sum() / math.log(denominator_categories))


def _participation(weights: Sequence[float], fixed_categories: int | None = None) -> float:
    values = np.asarray([value for value in weights if value > 0], dtype=float)
    if len(values) == 0:
        return 0.0
    probabilities = values / values.sum()
    raw = float(1 - np.square(probabilities).sum())
    categories = fixed_categories or len(values)
    return raw if categories <= 1 else raw * categories / (categories - 1)


def build_prominence_metrics(
    paper_table: pd.DataFrame,
    raw_candidate_papers: pd.DataFrame,
    definitions: Sequence[WimpDefinition],
    windows: Sequence[Window],
    focal_fields: Sequence[str],
) -> tuple[pd.DataFrame, pd.DataFrame]:
    metric_rows: list[dict[str, Any]] = []
    crosslisting_rows: list[dict[str, Any]] = []
    paper_lookup = paper_table.set_index("bibcode")

    for definition in definitions:
        candidates = apply_wimp_definition_to_candidates(raw_candidate_papers, definition)
        candidate_labels = candidates[["candidate_id", "candidate_label"]].drop_duplicates("candidate_id")
        for window in windows:
            window_papers = _select_window(paper_table, window)
            window_candidates = _select_window(candidates, window)
            candidate_bearing_ids = set(window_candidates["bibcode"])
            total_candidate_bearing = len(candidate_bearing_ids)

            for field in focal_fields:
                field_papers = window_papers[window_papers["primary_field"].eq(field)]
                field_candidates = window_candidates[window_candidates["primary_field"].eq(field)]
                all_dm_papers = int(field_papers["bibcode"].nunique())
                candidate_bearing_papers = int(field_candidates["bibcode"].nunique())
                total_mentions = int(len(field_candidates))
                counts = (
                    field_candidates.groupby("candidate_id", observed=True)
                    .agg(candidate_paper_count=("bibcode", "nunique"))
                    .reset_index()
                    .merge(candidate_labels, on="candidate_id", how="left")
                )
                for row in counts.itertuples(index=False):
                    metric_rows.append(
                        {
                            "wimp_definition": definition.name,
                            "window_kind": window.kind,
                            "window": window.label,
                            "start_year": window.start,
                            "end_year": window.end,
                            "field": field,
                            "candidate_id": row.candidate_id,
                            "candidate_label": row.candidate_label,
                            "candidate_paper_count": int(row.candidate_paper_count),
                            "all_dm_papers": all_dm_papers,
                            "candidate_bearing_papers": candidate_bearing_papers,
                            "paper_candidate_mentions": total_mentions,
                            "candidate_prevalence_all_dm": (
                                row.candidate_paper_count / all_dm_papers if all_dm_papers else math.nan
                            ),
                            "candidate_prevalence_candidate_papers": (
                                row.candidate_paper_count / candidate_bearing_papers
                                if candidate_bearing_papers
                                else math.nan
                            ),
                            "candidate_share_of_mentions": (
                                row.candidate_paper_count / total_mentions if total_mentions else math.nan
                            ),
                        }
                    )

            for candidate_id, group in window_candidates.groupby("candidate_id", observed=True):
                paper_ids = set(group["bibcode"])
                if not paper_ids:
                    continue
                candidate_paper_rows = paper_lookup.loc[sorted(paper_ids)]
                crosslisted = int(candidate_paper_rows["crosslisted_astrophysics_hep"].sum())
                other_ids = candidate_bearing_ids - paper_ids
                other_rows = paper_lookup.loc[sorted(other_ids)] if other_ids else paper_table.iloc[0:0]
                other_crosslisted = int(other_rows["crosslisted_astrophysics_hep"].sum()) if len(other_rows) else 0
                a, b = crosslisted, len(candidate_paper_rows) - crosslisted
                c, d = other_crosslisted, len(other_rows) - other_crosslisted
                odds_ratio = ((a + 0.5) * (d + 0.5)) / ((b + 0.5) * (c + 0.5))
                label = str(group["candidate_label"].iloc[0])
                crosslisting_rows.append(
                    {
                        "wimp_definition": definition.name,
                        "window_kind": window.kind,
                        "window": window.label,
                        "start_year": window.start,
                        "end_year": window.end,
                        "candidate_id": candidate_id,
                        "candidate_label": label,
                        "candidate_paper_count": len(candidate_paper_rows),
                        "crosslisted_paper_count": a,
                        "crosslisted_paper_share": a / len(candidate_paper_rows),
                        "other_candidate_bearing_paper_count": len(other_rows),
                        "other_crosslisted_paper_count": c,
                        "crosslisting_odds_ratio_vs_other_candidate_papers": odds_ratio,
                        "log2_crosslisting_odds_ratio": math.log2(odds_ratio),
                    }
                )

    metrics = pd.DataFrame(metric_rows)
    if metrics.empty:
        return metrics, pd.DataFrame(crosslisting_rows)
    denominator_keys = [
        "wimp_definition", "window_kind", "window", "start_year", "end_year", "field"
    ]
    denominator_lookup = (
        metrics.drop_duplicates(denominator_keys)
        .set_index(denominator_keys)[
            ["all_dm_papers", "candidate_bearing_papers", "paper_candidate_mentions"]
        ]
    )
    paired_rows: list[dict[str, Any]] = []
    group_columns = [
        "wimp_definition", "window_kind", "window", "start_year", "end_year",
        "candidate_id", "candidate_label",
    ]
    for keys, group in metrics.groupby(group_columns, observed=True, dropna=False):
        key_values = dict(zip(group_columns, keys))
        by_field = group.set_index("field")
        astro_count = float(by_field.loc[ASTRO, "candidate_paper_count"]) if ASTRO in by_field.index else 0.0
        hep_count = float(by_field.loc[HEP, "candidate_paper_count"]) if HEP in by_field.index else 0.0
        lookup_prefix = tuple(key_values[column] for column in group_columns[:5])
        astro_denominators = denominator_lookup.loc[lookup_prefix + (ASTRO,)]
        hep_denominators = denominator_lookup.loc[lookup_prefix + (HEP,)]
        astro_den = float(astro_denominators["all_dm_papers"])
        hep_den = float(hep_denominators["all_dm_papers"])
        astro_mentions = float(astro_denominators["paper_candidate_mentions"])
        hep_mentions = float(hep_denominators["paper_candidate_mentions"])
        astro_rate = (astro_count + 0.5) / (astro_den + 1.0)
        hep_rate = (hep_count + 0.5) / (hep_den + 1.0)
        log_ratio = math.log2(hep_rate / astro_rate)
        astro_share = astro_count / astro_mentions if astro_mentions else 0.0
        hep_share = hep_count / hep_mentions if hep_mentions else 0.0
        smoothed_astro_share = (astro_count + 0.5) / (astro_mentions + 1.0)
        smoothed_hep_share = (hep_count + 0.5) / (hep_mentions + 1.0)
        log10_share_ratio = math.log10(smoothed_astro_share / smoothed_hep_share)
        total_count = astro_count + hep_count
        astro_prevalence = astro_count / astro_den if astro_den else 0.0
        hep_prevalence = hep_count / hep_den if hep_den else 0.0
        field_participation = _participation(
            [astro_prevalence, hep_prevalence], fixed_categories=2
        )
        share_field_participation = _participation(
            [astro_share, hep_share], fixed_categories=2
        )
        paired_rows.append(
            {
                **key_values,
                "astrophysics_candidate_papers": int(astro_count),
                "hep_candidate_papers": int(hep_count),
                "astrophysics_all_dm_papers": int(astro_den),
                "hep_all_dm_papers": int(hep_den),
                "pooled_candidate_papers": int(total_count),
                "log2_hep_astro_prevalence_ratio": log_ratio,
                "astrophysics_candidate_share_of_mentions": astro_share,
                "hep_candidate_share_of_mentions": hep_share,
                "mean_field_candidate_share": 0.5 * (astro_share + hep_share),
                "log10_astro_hep_share_ratio": log10_share_ratio,
                "field_participation": field_participation,
                "share_field_participation": share_field_participation,
            }
        )
    paired = pd.DataFrame(paired_rows)
    metrics = metrics.merge(paired, on=group_columns, how="left", validate="many_to_one")
    metrics = metrics.sort_values(
        ["wimp_definition", "window_kind", "start_year", "field", "candidate_paper_count", "candidate_id"],
        ascending=[True, True, True, True, False, True],
        kind="mergesort",
    )
    crosslisting = pd.DataFrame(crosslisting_rows).sort_values(
        ["wimp_definition", "window_kind", "start_year", "candidate_paper_count", "candidate_id"],
        ascending=[True, True, True, False, True],
        kind="mergesort",
    )
    return metrics, crosslisting


def bootstrap_wimp_prominence(
    paper_table: pd.DataFrame,
    raw_candidate_papers: pd.DataFrame,
    definitions: Sequence[WimpDefinition],
    windows: Sequence[Window],
    focal_fields: Sequence[str],
    iterations: int,
    seed: int,
    confidence_level: float,
) -> pd.DataFrame:
    """Exact paper-bootstrap summaries for binary prevalence and grouped mention shares."""
    if iterations <= 0:
        return pd.DataFrame()
    if not 0 < confidence_level < 1:
        raise ValueError("confidence_level must lie between zero and one")
    rng = np.random.default_rng(seed)
    alpha = (1 - confidence_level) / 2
    rows: list[dict[str, Any]] = []
    for definition in definitions:
        candidates = apply_wimp_definition_to_candidates(raw_candidate_papers, definition)
        focal_id = definition.focal_node_id
        for window in windows:
            field_draws: dict[str, dict[str, np.ndarray]] = {}
            window_papers = _select_window(paper_table, window)
            window_candidates = _select_window(candidates, window)
            for field in focal_fields:
                field_papers = window_papers[window_papers["primary_field"].eq(field)][["bibcode"]]
                field_candidates = window_candidates[window_candidates["primary_field"].eq(field)]
                paper_features = (
                    field_candidates.assign(
                        focal=lambda d: d["candidate_id"].eq(focal_id).astype(int)
                    )
                    .groupby("bibcode", observed=True)
                    .agg(focal=("focal", "max"), candidate_mentions=("candidate_id", "nunique"))
                    .reset_index()
                )
                paper_features = field_papers.merge(
                    paper_features, on="bibcode", how="left", validate="one_to_one"
                ).fillna({"focal": 0, "candidate_mentions": 0})
                n_papers = len(paper_features)
                if n_papers == 0:
                    continue
                focal_count = int(paper_features["focal"].sum())
                prevalence_draws = rng.binomial(
                    n_papers, focal_count / n_papers, size=iterations
                ) / n_papers
                candidate_bearing = paper_features[paper_features["candidate_mentions"] > 0]
                if len(candidate_bearing):
                    focal_candidate_count = int(candidate_bearing["focal"].sum())
                    candidate_prevalence_draws = rng.binomial(
                        len(candidate_bearing), focal_candidate_count / len(candidate_bearing),
                        size=iterations,
                    ) / len(candidate_bearing)
                else:
                    candidate_prevalence_draws = np.full(iterations, np.nan)
                grouped = (
                    paper_features.groupby(["focal", "candidate_mentions"], observed=True)
                    .size()
                    .reset_index(name="paper_count")
                )
                probabilities = grouped["paper_count"].to_numpy(dtype=float) / n_papers
                multinomial = rng.multinomial(n_papers, probabilities, size=iterations)
                focal_values = grouped["focal"].to_numpy(dtype=float)
                mention_values = grouped["candidate_mentions"].to_numpy(dtype=float)
                numerators = multinomial @ focal_values
                denominators = multinomial @ mention_values
                share_draws = np.divide(
                    numerators, denominators,
                    out=np.full(iterations, np.nan), where=denominators > 0,
                )
                field_draws[field] = {
                    "candidate_count": rng.binomial(n_papers, focal_count / n_papers, size=iterations),
                    "paper_count": np.full(iterations, n_papers),
                    "mention_numerator": numerators,
                    "mention_denominator": denominators,
                }
                rows.append(
                    {
                        "wimp_definition": definition.name, "window_kind": window.kind,
                        "window": window.label, "start_year": window.start, "end_year": window.end,
                        "field": field, "candidate_id": focal_id,
                        "bootstrap_iterations": iterations, "confidence_level": confidence_level,
                        "candidate_prevalence_all_dm_low": float(np.nanquantile(prevalence_draws, alpha)),
                        "candidate_prevalence_all_dm_high": float(np.nanquantile(prevalence_draws, 1 - alpha)),
                        "candidate_prevalence_candidate_papers_low": float(np.nanquantile(candidate_prevalence_draws, alpha)),
                        "candidate_prevalence_candidate_papers_high": float(np.nanquantile(candidate_prevalence_draws, 1 - alpha)),
                        "candidate_share_of_mentions_low": float(np.nanquantile(share_draws, alpha)),
                        "candidate_share_of_mentions_high": float(np.nanquantile(share_draws, 1 - alpha)),
                    }
                )
            if ASTRO in field_draws and HEP in field_draws:
                astro = field_draws[ASTRO]
                hep = field_draws[HEP]
                astro_rate = (astro["candidate_count"] + 0.5) / (astro["paper_count"] + 1)
                hep_rate = (hep["candidate_count"] + 0.5) / (hep["paper_count"] + 1)
                ratios = np.log2(hep_rate / astro_rate)
                astro_share = (astro["mention_numerator"] + 0.5) / (
                    astro["mention_denominator"] + 1
                )
                hep_share = (hep["mention_numerator"] + 0.5) / (
                    hep["mention_denominator"] + 1
                )
                share_ratios = np.log10(astro_share / hep_share)
                for row in rows[-len(focal_fields):]:
                    if row["wimp_definition"] == definition.name and row["window"] == window.label:
                        row["log2_hep_astro_prevalence_ratio_low"] = float(np.quantile(ratios, alpha))
                        row["log2_hep_astro_prevalence_ratio_high"] = float(np.quantile(ratios, 1 - alpha))
                        row["log10_astro_hep_share_ratio_low"] = float(
                            np.quantile(share_ratios, alpha)
                        )
                        row["log10_astro_hep_share_ratio_high"] = float(
                            np.quantile(share_ratios, 1 - alpha)
                        )
    return pd.DataFrame(rows).sort_values(
        ["wimp_definition", "window_kind", "start_year", "field"], kind="mergesort"
    )


def build_prominence_graph(
    metrics: pd.DataFrame,
    definition: WimpDefinition,
    window: Window,
    gephi_config: Mapping[str, Any],
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    selected = metrics[
        metrics["wimp_definition"].eq(definition.name)
        & metrics["window_kind"].eq(window.kind)
        & metrics["window"].eq(window.label)
    ].copy()
    if selected.empty:
        raise ValueError(f"No prominence data for {definition.name}, {window.label}")
    candidate_metrics = selected.drop_duplicates("candidate_id").copy()
    size_lower, size_upper = map(float, gephi_config["node_size_range"])
    label_lower, label_upper = map(float, gephi_config["label_size_range"])
    clip = float(gephi_config["share_ratio_clip_log10"])
    candidate_metrics["node_size_sqrt_mean_field_share"] = fixed_unit_scale(
        candidate_metrics["mean_field_candidate_share"],
        size_lower,
        size_upper,
        transform="sqrt",
    )
    candidate_metrics["label_size_sqrt_mean_field_share"] = fixed_unit_scale(
        candidate_metrics["mean_field_candidate_share"],
        label_lower,
        label_upper,
        transform="sqrt",
    )
    candidate_metrics["astro_orientation_0_1"] = (
        candidate_metrics["log10_astro_hep_share_ratio"].clip(-clip, clip) + clip
    ) / (2 * clip)
    candidate_nodes = pd.DataFrame(
        {
            "Id": candidate_metrics["candidate_id"],
            "Label": candidate_metrics["candidate_label"],
            "node_type": "candidate",
            "wimp_definition": definition.name,
            "window_kind": window.kind,
            "window": window.label,
            "start_year": window.start,
            "end_year": window.end,
            "pooled_candidate_papers": candidate_metrics["pooled_candidate_papers"],
            "mean_field_candidate_share": candidate_metrics["mean_field_candidate_share"],
            "log10_astro_hep_share_ratio": candidate_metrics["log10_astro_hep_share_ratio"],
            "share_field_participation": candidate_metrics["share_field_participation"],
            "node_size_sqrt_mean_field_share": candidate_metrics["node_size_sqrt_mean_field_share"],
            "label_size_sqrt_mean_field_share": candidate_metrics["label_size_sqrt_mean_field_share"],
            "astro_orientation_0_1": candidate_metrics["astro_orientation_0_1"],
            "is_focal_wimp": candidate_metrics["candidate_id"].eq(definition.focal_node_id),
        }
    )
    field_nodes = pd.DataFrame(
        [
            {
                "Id": f"field:{slugify(field)}", "Label": field.title(), "node_type": "field",
                "wimp_definition": definition.name, "window_kind": window.kind,
                "window": window.label, "start_year": window.start, "end_year": window.end,
                "pooled_candidate_papers": 0, "mean_field_candidate_share": 0.0,
                "log10_astro_hep_share_ratio": clip if field == ASTRO else -clip,
                "share_field_participation": 0.0,
                "node_size_sqrt_mean_field_share": size_upper,
                "label_size_sqrt_mean_field_share": label_upper,
                "astro_orientation_0_1": 1.0 if field == ASTRO else 0.0,
                "is_focal_wimp": False,
            }
            for field in (ASTRO, HEP)
        ]
    )
    nodes = pd.concat([candidate_nodes, field_nodes], ignore_index=True)
    edges = selected.assign(
        Source=lambda d: d["candidate_id"],
        Target=lambda d: "field:" + d["field"].map(slugify),
        Type="Undirected",
        Weight=lambda d: d["candidate_share_of_mentions"],
        Label="candidate field-relative prominence",
    )[
        [
            "Source", "Target", "Type", "Weight", "Label", "wimp_definition", "field",
            "window_kind", "window", "start_year", "end_year",
            "candidate_paper_count", "all_dm_papers", "candidate_bearing_papers",
            "paper_candidate_mentions", "candidate_prevalence_all_dm",
            "candidate_prevalence_candidate_papers", "candidate_share_of_mentions",
        ]
    ]
    gephi_nodes = nodes[
        [
            "Id", "Label", "node_type", "is_focal_wimp", "node_size_sqrt_mean_field_share",
            "label_size_sqrt_mean_field_share", "astro_orientation_0_1",
            "share_field_participation",
        ]
    ].copy()
    gephi_edges = edges[
        ["Source", "Target", "Type", "Weight", "candidate_prevalence_all_dm"]
    ].rename(columns={"candidate_prevalence_all_dm": "AlternateWeightPaperPrevalence"})
    return nodes, edges, gephi_nodes, gephi_edges


def aggregate_importance_edges(
    events: pd.DataFrame,
    occurrences: pd.DataFrame,
    paper_table: pd.DataFrame,
    transformed_candidates: pd.DataFrame,
    definition: WimpDefinition,
    window: Window,
    field: str | Sequence[str],
    min_edge_papers: int,
    evidence_scope: str,
) -> pd.DataFrame:
    columns = [
        "wimp_definition", "window_kind", "window", "start_year", "end_year", "field",
        "evidence_scope", "Source", "Target", "Type", "Label", "paper_count",
        "equal_paper_weight", "source_paper_count", "target_paper_count",
        "all_dm_papers", "candidate_bearing_papers", "cooc_doc_prevalence_all_dm",
        "cooc_doc_prevalence_candidate_papers", "jaccard", "cosine", "npmi",
        "positive_npmi", "distance_prevalence", "distance_positive_npmi", "first_year",
        "last_year", "source_label", "target_label", "target_type", "target_subtype", "target_domain",
    ]
    scope_fields = [field] if isinstance(field, str) else list(map(str, field))
    field_label = scope_fields[0] if len(scope_fields) == 1 else "pooled focal fields"
    window_events = _select_window(events, window)
    window_events = window_events[window_events["arxiv_category"].isin(scope_fields)]
    if window_events.empty:
        return pd.DataFrame(columns=columns)
    transformed = apply_wimp_definition_to_events(window_events, definition)
    dedup = transformed.drop_duplicates(["bibcode", "source", "target"]).copy()
    pair_counts = dedup.groupby("bibcode", observed=True).size().rename("paper_pair_count")
    dedup = dedup.merge(pair_counts, on="bibcode", how="left", validate="many_to_one")
    dedup["equal_paper_pair_weight"] = 1.0 / dedup["paper_pair_count"]

    candidate_subset = _select_window(transformed_candidates, window)
    candidate_subset = candidate_subset[candidate_subset["primary_field"].isin(scope_fields)]
    source_counts = candidate_subset.groupby("candidate_id", observed=True)["bibcode"].nunique()
    occurrence_subset = _select_window(occurrences, window)
    occurrence_subset = occurrence_subset[
        occurrence_subset["arxiv_category"].isin(scope_fields)
        & occurrence_subset["occurrence_kind"].eq("entity")
    ]
    target_counts = occurrence_subset.groupby("node_id", observed=True)["bibcode"].nunique()
    all_dm = int(
        _select_window(paper_table, window)
        .loc[lambda d: d["primary_field"].isin(scope_fields), "bibcode"]
        .nunique()
    )
    candidate_population = int(candidate_subset["bibcode"].nunique())

    grouped = (
        dedup.groupby(["source", "target"], observed=True)
        .agg(
            paper_count=("bibcode", "nunique"),
            equal_paper_weight=("equal_paper_pair_weight", "sum"),
            first_year=("year", "min"),
            last_year=("year", "max"),
            source_label=("source_label", "first"),
            target_label=("target_label", "first"),
            target_type=("target_type", "first"),
            target_subtype=("target_subtype", "first"),
            target_domain=("target_domain", "first"),
        )
        .reset_index()
        .rename(columns={"source": "Source", "target": "Target"})
    )
    grouped = grouped[grouped["paper_count"] >= min_edge_papers].copy()
    if grouped.empty:
        return pd.DataFrame(columns=columns)
    grouped["source_paper_count"] = grouped["Source"].map(source_counts).fillna(0).astype(int)
    grouped["target_paper_count"] = grouped["Target"].map(target_counts).fillna(0).astype(int)
    grouped["all_dm_papers"] = all_dm
    grouped["candidate_bearing_papers"] = candidate_population
    grouped["cooc_doc_prevalence_all_dm"] = grouped["paper_count"] / max(all_dm, 1)
    grouped["cooc_doc_prevalence_candidate_papers"] = grouped["paper_count"] / max(candidate_population, 1)
    union = grouped["source_paper_count"] + grouped["target_paper_count"] - grouped["paper_count"]
    grouped["jaccard"] = np.where(union > 0, grouped["paper_count"] / union, np.nan)
    grouped["cosine"] = grouped["paper_count"] / np.sqrt(
        grouped["source_paper_count"] * grouped["target_paper_count"]
    ).replace(0, np.nan)
    grouped["npmi"] = grouped.apply(
        lambda row: _npmi(
            float(row.paper_count), float(row.source_paper_count),
            float(row.target_paper_count), float(candidate_population),
        ),
        axis=1,
    )
    grouped["positive_npmi"] = grouped["npmi"].clip(lower=0)
    grouped["distance_prevalence"] = 1.0 / grouped["cooc_doc_prevalence_candidate_papers"].clip(lower=1e-12)
    grouped["distance_positive_npmi"] = np.where(
        grouped["positive_npmi"] > 0, 1.0 / grouped["positive_npmi"], np.nan
    )
    grouped["wimp_definition"] = definition.name
    grouped["window_kind"] = window.kind
    grouped["window"] = window.label
    grouped["start_year"] = window.start
    grouped["end_year"] = window.end
    grouped["field"] = field_label
    grouped["evidence_scope"] = evidence_scope
    grouped["Type"] = "Undirected"
    grouped["Label"] = f"{evidence_scope} candidate-concept co-occurrence"
    return grouped[columns].sort_values(
        ["paper_count", "positive_npmi", "Source", "Target"],
        ascending=[False, False, True, True], kind="mergesort",
    )


def _spectral_scores(edges: pd.DataFrame, weight_column: str) -> tuple[dict[str, float], dict[str, float]]:
    if edges.empty:
        return {}, {}
    candidates = sorted(edges["Source"].unique())
    concepts = sorted(edges["Target"].unique())
    candidate_index = {value: index for index, value in enumerate(candidates)}
    concept_index = {value: index for index, value in enumerate(concepts)}
    matrix = np.zeros((len(candidates), len(concepts)), dtype=float)
    for row in edges.itertuples(index=False):
        matrix[candidate_index[row.Source], concept_index[row.Target]] = float(
            getattr(row, weight_column)
        )
    if not np.any(matrix):
        return {value: 0.0 for value in candidates}, {value: 0.0 for value in concepts}
    left, _, right = np.linalg.svd(matrix, full_matrices=False)
    candidate_values = np.abs(left[:, 0])
    concept_values = np.abs(right[0, :])
    if candidate_values.max() > 0:
        candidate_values /= candidate_values.max()
    if concept_values.max() > 0:
        concept_values /= concept_values.max()
    return dict(zip(candidates, candidate_values)), dict(zip(concepts, concept_values))


def _eigenvector_scores(graph: nx.Graph, weight: str) -> dict[str, float]:
    nodes = list(graph.nodes)
    if not nodes:
        return {}
    matrix = nx.to_numpy_array(graph, nodelist=nodes, weight=weight, dtype=float)
    eigenvalues, eigenvectors = np.linalg.eigh(matrix)
    values = np.abs(eigenvectors[:, int(np.argmax(eigenvalues))])
    if values.max() > 0:
        values /= values.max()
    return dict(zip(nodes, values))


def build_importance_nodes(
    edges: pd.DataFrame,
    candidate_papers: pd.DataFrame,
    occurrences: pd.DataFrame,
    definition: WimpDefinition,
    window: Window,
    field: str | Sequence[str],
    gephi_config: Mapping[str, Any],
) -> pd.DataFrame:
    columns = [
        "wimp_definition", "window_kind", "window", "start_year", "end_year", "field",
        "Id", "Label", "node_type", "subtype", "domain", "paper_count", "degree",
        "strength_prevalence", "strength_positive_npmi", "hits_score_prevalence",
        "eigenvector_centrality_prevalence", "core_number", "target_type_count",
        "type_participation", "normalized_type_entropy", "strength_candidate_percentile",
        "hits_candidate_percentile", "eigenvector_candidate_percentile", "core_candidate_percentile",
        "node_size_sqrt_strength", "label_size_log_paper_count", "spectral_role_score",
        "role_spectral_percentile", "node_size_role_spectral_percentile",
        "label_size_role_spectral_percentile",
        "is_focal_wimp",
    ]
    if edges.empty:
        return pd.DataFrame(columns=columns)
    graph = nx.Graph()
    for row in edges.itertuples(index=False):
        graph.add_edge(
            row.Source, row.Target,
            prevalence=float(row.cooc_doc_prevalence_candidate_papers),
            positive_npmi=float(row.positive_npmi),
        )
    candidate_spectral, concept_spectral = _spectral_scores(
        edges, "cooc_doc_prevalence_candidate_papers"
    )
    eigenvector = _eigenvector_scores(graph, weight="prevalence")
    core = nx.core_number(graph)
    scope_fields = [field] if isinstance(field, str) else list(map(str, field))
    field_label = scope_fields[0] if len(scope_fields) == 1 else "pooled focal fields"
    candidate_subset = _select_window(candidate_papers, window)
    candidate_subset = candidate_subset[candidate_subset["primary_field"].isin(scope_fields)]
    candidate_counts = candidate_subset.groupby("candidate_id", observed=True)["bibcode"].nunique()
    occurrence_subset = _select_window(occurrences, window)
    occurrence_subset = occurrence_subset[
        occurrence_subset["arxiv_category"].isin(scope_fields)
        & occurrence_subset["occurrence_kind"].eq("entity")
    ]
    concept_counts = occurrence_subset.groupby("node_id", observed=True)["bibcode"].nunique()
    candidate_labels = candidate_subset.drop_duplicates("candidate_id").set_index("candidate_id")["candidate_label"]
    concept_meta = (
        occurrence_subset.sort_values(["node_id", "year", "bibcode"], kind="mergesort")
        .drop_duplicates("node_id")
        .set_index("node_id")
    )
    rows: list[dict[str, Any]] = []
    for node_id in graph.nodes:
        is_candidate = node_id in set(edges["Source"])
        incident = edges[edges["Source"].eq(node_id)] if is_candidate else edges[edges["Target"].eq(node_id)]
        type_weights = (
            incident.groupby("target_type", observed=True)["cooc_doc_prevalence_candidate_papers"].sum()
            if is_candidate
            else pd.Series(dtype=float)
        )
        if is_candidate:
            label = str(candidate_labels.get(node_id, node_id))
            subtype, domain = "candidate", "candidate"
            paper_count = int(candidate_counts.get(node_id, 0))
            spectral_score = candidate_spectral.get(node_id, 0.0)
        else:
            meta = concept_meta.loc[node_id] if node_id in concept_meta.index else None
            label = str(meta["label"]) if meta is not None else node_id
            subtype = str(meta["subtype"]) if meta is not None else ""
            domain = str(meta["domain"]) if meta is not None else ""
            paper_count = int(concept_counts.get(node_id, 0))
            spectral_score = concept_spectral.get(node_id, 0.0)
        rows.append(
            {
                "wimp_definition": definition.name, "window_kind": window.kind,
                "window": window.label, "start_year": window.start, "end_year": window.end,
                "field": field_label, "Id": node_id, "Label": label,
                "node_type": "candidate" if is_candidate else str(incident["target_type"].iloc[0]),
                "subtype": subtype, "domain": domain, "paper_count": paper_count,
                "degree": int(graph.degree(node_id)),
                "strength_prevalence": float(incident["cooc_doc_prevalence_candidate_papers"].sum()),
                "strength_positive_npmi": float(incident["positive_npmi"].sum()),
                "hits_score_prevalence": float(spectral_score),
                "eigenvector_centrality_prevalence": float(eigenvector.get(node_id, 0.0)),
                "core_number": int(core.get(node_id, 0)),
                "target_type_count": int(incident["target_type"].nunique()) if is_candidate else 0,
                "type_participation": _participation(type_weights.tolist(), fixed_categories=6) if is_candidate else 0.0,
                "normalized_type_entropy": _normalized_entropy(type_weights.tolist(), fixed_categories=6) if is_candidate else 0.0,
                "spectral_role_score": float(spectral_score),
                "is_focal_wimp": node_id == definition.focal_node_id,
            }
        )
    nodes = pd.DataFrame(rows)
    candidate_mask = nodes["node_type"].eq("candidate")
    for source, target in (
        ("strength_prevalence", "strength_candidate_percentile"),
        ("hits_score_prevalence", "hits_candidate_percentile"),
        ("eigenvector_centrality_prevalence", "eigenvector_candidate_percentile"),
        ("core_number", "core_candidate_percentile"),
    ):
        nodes[target] = 0.0
        nodes.loc[candidate_mask, target] = percentile_rank(nodes.loc[candidate_mask, source])
    concept_mask = ~candidate_mask
    nodes["role_spectral_percentile"] = 0.0
    nodes.loc[candidate_mask, "role_spectral_percentile"] = percentile_rank(
        nodes.loc[candidate_mask, "spectral_role_score"]
    )
    nodes.loc[concept_mask, "role_spectral_percentile"] = percentile_rank(
        nodes.loc[concept_mask, "spectral_role_score"]
    )
    size_lower, size_upper = map(float, gephi_config["node_size_range"])
    label_lower, label_upper = map(float, gephi_config["label_size_range"])
    nodes["node_size_sqrt_strength"] = minmax_scale(
        nodes["strength_prevalence"], size_lower, size_upper, transform="sqrt"
    )
    nodes["label_size_log_paper_count"] = minmax_scale(
        nodes["paper_count"], label_lower, label_upper, transform="log1p"
    )
    nodes["node_size_role_spectral_percentile"] = fixed_unit_scale(
        nodes["role_spectral_percentile"], size_lower, size_upper
    )
    nodes["label_size_role_spectral_percentile"] = fixed_unit_scale(
        nodes["role_spectral_percentile"], label_lower, label_upper
    )
    return nodes[columns].sort_values(
        ["node_type", "strength_prevalence", "Id"], ascending=[True, False, True], kind="mergesort"
    )


def gephi_importance_tables(
    nodes: pd.DataFrame, edges: pd.DataFrame
) -> tuple[pd.DataFrame, pd.DataFrame]:
    node_columns = [
        "Id", "Label", "node_type", "is_focal_wimp",
        "node_size_role_spectral_percentile", "label_size_role_spectral_percentile",
        "role_spectral_percentile", "hits_candidate_percentile",
    ]
    node_columns.extend(column for column in ("layout_x", "layout_y") if column in nodes.columns)
    gephi_nodes = nodes[node_columns].copy()
    gephi_edges = edges[
        [
            "Source", "Target", "Type", "cooc_doc_prevalence_candidate_papers",
            "positive_npmi", "distance_prevalence", "distance_positive_npmi",
        ]
    ].rename(
        columns={
            "cooc_doc_prevalence_candidate_papers": "Weight",
            "positive_npmi": "AssociationWeight",
            "distance_prevalence": "DistancePrevalence",
            "distance_positive_npmi": "DistanceAssociation",
        }
    )
    return gephi_nodes, gephi_edges


def aggregate_brokerage_edges(
    occurrences: pd.DataFrame,
    paper_table: pd.DataFrame,
    definition: WimpDefinition,
    window: Window,
    min_edge_papers: int,
    gephi_config: Mapping[str, Any],
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Build one concept graph with field-specific co-occurrence attributes.

    Each unordered pair records paper-binary abstract co-occurrence separately
    in astrophysics and HEP. The graph has one canonical node per concept; field
    is an empirical prevalence/orientation attribute rather than a node layer.
    """
    edge_columns = [
        "wimp_definition", "window_kind", "window", "start_year", "end_year",
        "Source", "Target", "Type", "Label", "source_label", "target_label",
        "source_type", "target_type", "source_subtype", "target_subtype",
        "source_domain", "target_domain", "astrophysics_paper_count", "hep_paper_count",
        "pooled_paper_count", "astrophysics_all_dm_papers", "hep_all_dm_papers",
        "pooled_all_dm_papers", "astrophysics_source_paper_count",
        "hep_source_paper_count", "astrophysics_target_paper_count",
        "hep_target_paper_count", "pooled_source_paper_count", "pooled_target_paper_count",
        "astrophysics_cooc_doc_prevalence", "hep_cooc_doc_prevalence",
        "mean_field_cooc_prevalence", "pooled_cooc_doc_prevalence",
        "astrophysics_npmi", "hep_npmi", "pooled_npmi",
        "astrophysics_positive_npmi", "hep_positive_npmi", "pooled_positive_npmi",
        "shared_positive_npmi", "shared_cooc_doc_prevalence",
        "edge_log10_astro_hep_prevalence_ratio", "edge_astro_orientation_0_1",
        "edge_field_participation", "distance_mean_field_prevalence",
        "distance_pooled_prevalence", "distance_pooled_association", "first_year", "last_year",
        "edge_cross_field_betweenness_prevalence",
    ]
    node_columns = [
        "wimp_definition", "window_kind", "window", "start_year", "end_year",
        "Id", "Label", "node_type", "subtype", "domain",
        "astrophysics_paper_count", "hep_paper_count", "pooled_paper_count",
        "astrophysics_all_dm_papers", "hep_all_dm_papers", "pooled_all_dm_papers",
        "astrophysics_prevalence", "hep_prevalence", "pooled_prevalence",
        "log10_astro_hep_prevalence_ratio", "astro_orientation_0_1",
        "field_participation", "is_focal_wimp",
    ]
    papers = _select_window(paper_table, window)
    papers = papers[papers["primary_field"].isin([ASTRO, HEP])].copy()
    denominators = papers.groupby("primary_field", observed=True)["bibcode"].nunique()
    n_astro = int(denominators.get(ASTRO, 0))
    n_hep = int(denominators.get(HEP, 0))
    if n_astro == 0 or n_hep == 0:
        return pd.DataFrame(columns=edge_columns), pd.DataFrame(columns=node_columns)

    selected = apply_wimp_definition_to_occurrences(
        _select_window(occurrences, window), definition
    )
    selected = selected[selected["arxiv_category"].isin([ASTRO, HEP])].copy()
    selected = selected[selected["bibcode"].isin(papers["bibcode"])].copy()
    selected = selected[selected["node_id"].notna() & selected["label"].notna()].copy()
    selected["node_type"] = selected["node_type"].replace({"dm_model": "candidate"})
    node_docs = selected[
        ["bibcode", "year", "arxiv_category", "node_id", "label", "node_type", "subtype", "domain"]
    ].drop_duplicates(["bibcode", "node_id"])
    if node_docs.empty:
        return pd.DataFrame(columns=edge_columns), pd.DataFrame(columns=node_columns)

    metadata = (
        node_docs.sort_values(["node_id", "year"], kind="mergesort")
        .drop_duplicates("node_id")
        .set_index("node_id")
    )
    counts = (
        node_docs.groupby(["node_id", "arxiv_category"], observed=True)["bibcode"]
        .nunique().unstack(fill_value=0)
    )
    for field in (ASTRO, HEP):
        if field not in counts:
            counts[field] = 0
    counts = counts[[ASTRO, HEP]]
    node_stats = counts.reset_index().rename(
        columns={"node_id": "Id", ASTRO: "astrophysics_paper_count", HEP: "hep_paper_count"}
    )
    node_stats["Label"] = node_stats["Id"].map(metadata["label"])
    node_stats["node_type"] = node_stats["Id"].map(metadata["node_type"])
    node_stats["subtype"] = node_stats["Id"].map(metadata["subtype"])
    node_stats["domain"] = node_stats["Id"].map(metadata["domain"])
    node_stats["pooled_paper_count"] = (
        node_stats["astrophysics_paper_count"] + node_stats["hep_paper_count"]
    )
    node_stats["astrophysics_all_dm_papers"] = n_astro
    node_stats["hep_all_dm_papers"] = n_hep
    node_stats["pooled_all_dm_papers"] = n_astro + n_hep
    node_stats["astrophysics_prevalence"] = node_stats["astrophysics_paper_count"] / n_astro
    node_stats["hep_prevalence"] = node_stats["hep_paper_count"] / n_hep
    node_stats["pooled_prevalence"] = node_stats["pooled_paper_count"] / (n_astro + n_hep)
    astro_rate = (node_stats["astrophysics_paper_count"] + 0.5) / (n_astro + 1)
    hep_rate = (node_stats["hep_paper_count"] + 0.5) / (n_hep + 1)
    node_stats["log10_astro_hep_prevalence_ratio"] = np.log10(astro_rate / hep_rate)
    clip = float(gephi_config["share_ratio_clip_log10"])
    node_stats["astro_orientation_0_1"] = (
        node_stats["log10_astro_hep_prevalence_ratio"].clip(-clip, clip) + clip
    ) / (2 * clip)
    node_stats["field_participation"] = [
        _participation([astro, hep], fixed_categories=2)
        for astro, hep in zip(node_stats["astrophysics_prevalence"], node_stats["hep_prevalence"])
    ]
    node_stats["is_focal_wimp"] = node_stats["Id"].eq(definition.focal_node_id)
    for column, value in (
        ("wimp_definition", definition.name), ("window_kind", window.kind),
        ("window", window.label), ("start_year", window.start), ("end_year", window.end),
    ):
        node_stats.insert(len(node_stats.columns) if column not in node_stats else 0, column, value)

    pair_rows: list[tuple[str, str, str, str, int]] = []
    for (field, bibcode), group in node_docs.groupby(
        ["arxiv_category", "bibcode"], observed=True, sort=False
    ):
        node_ids = sorted(group["node_id"].astype(str).unique())
        year = int(group["year"].iloc[0])
        pair_rows.extend(
            (str(field), str(bibcode), source, target, year)
            for source, target in combinations(node_ids, 2)
        )
    if not pair_rows:
        return pd.DataFrame(columns=edge_columns), node_stats[node_columns]
    pair_docs = pd.DataFrame(
        pair_rows, columns=["field", "bibcode", "Source", "Target", "year"]
    ).drop_duplicates(["field", "bibcode", "Source", "Target"])
    pairs = pair_docs[["Source", "Target"]].drop_duplicates()
    for field, prefix in ((ASTRO, "astrophysics"), (HEP, "hep")):
        field_counts = (
            pair_docs[pair_docs["field"].eq(field)]
            .groupby(["Source", "Target"], observed=True)
            .agg(
                **{
                    f"{prefix}_paper_count": ("bibcode", "nunique"),
                    f"{prefix}_first_year": ("year", "min"),
                    f"{prefix}_last_year": ("year", "max"),
                }
            )
            .reset_index()
        )
        pairs = pairs.merge(field_counts, on=["Source", "Target"], how="left")
    count_columns = ["astrophysics_paper_count", "hep_paper_count"]
    pairs[count_columns] = pairs[count_columns].fillna(0).astype(int)
    pairs = pairs[pairs[count_columns].max(axis=1) >= min_edge_papers].copy()
    if pairs.empty:
        return pd.DataFrame(columns=edge_columns), node_stats.iloc[0:0][node_columns]

    node_lookup = node_stats.set_index("Id")
    for endpoint in ("source", "target"):
        id_column = endpoint.title()
        pairs[f"{endpoint}_label"] = pairs[id_column].map(node_lookup["Label"])
        pairs[f"{endpoint}_type"] = pairs[id_column].map(node_lookup["node_type"])
        pairs[f"{endpoint}_subtype"] = pairs[id_column].map(node_lookup["subtype"])
        pairs[f"{endpoint}_domain"] = pairs[id_column].map(node_lookup["domain"])
        for field, prefix in ((ASTRO, "astrophysics"), (HEP, "hep")):
            pairs[f"{prefix}_{endpoint}_paper_count"] = pairs[id_column].map(
                node_lookup[f"{prefix}_paper_count"]
            )
        pairs[f"pooled_{endpoint}_paper_count"] = pairs[id_column].map(
            node_lookup["pooled_paper_count"]
        )
    pairs["pooled_paper_count"] = pairs[count_columns].sum(axis=1)
    pairs["astrophysics_all_dm_papers"] = n_astro
    pairs["hep_all_dm_papers"] = n_hep
    pairs["pooled_all_dm_papers"] = n_astro + n_hep
    pairs["astrophysics_cooc_doc_prevalence"] = pairs["astrophysics_paper_count"] / n_astro
    pairs["hep_cooc_doc_prevalence"] = pairs["hep_paper_count"] / n_hep
    pairs["mean_field_cooc_prevalence"] = 0.5 * (
        pairs["astrophysics_cooc_doc_prevalence"]
        + pairs["hep_cooc_doc_prevalence"]
    )
    pairs["pooled_cooc_doc_prevalence"] = pairs["pooled_paper_count"] / (n_astro + n_hep)
    for prefix, population in (("astrophysics", n_astro), ("hep", n_hep)):
        pairs[f"{prefix}_npmi"] = pairs.apply(
            lambda row: _npmi(
                row[f"{prefix}_paper_count"], row[f"{prefix}_source_paper_count"],
                row[f"{prefix}_target_paper_count"], population,
            ), axis=1,
        )
        pairs[f"{prefix}_positive_npmi"] = pairs[f"{prefix}_npmi"].clip(lower=0).fillna(0)
    pairs["pooled_npmi"] = pairs.apply(
        lambda row: _npmi(
            row["pooled_paper_count"], row["pooled_source_paper_count"],
            row["pooled_target_paper_count"], n_astro + n_hep,
        ), axis=1,
    )
    pairs["pooled_positive_npmi"] = pairs["pooled_npmi"].clip(lower=0).fillna(0)
    association_sum = pairs["astrophysics_positive_npmi"] + pairs["hep_positive_npmi"]
    pairs["shared_positive_npmi"] = np.where(
        (pairs["astrophysics_positive_npmi"] > 0) & (pairs["hep_positive_npmi"] > 0),
        2 * pairs["astrophysics_positive_npmi"] * pairs["hep_positive_npmi"] / association_sum,
        0.0,
    )
    prevalence_sum = (
        pairs["astrophysics_cooc_doc_prevalence"] + pairs["hep_cooc_doc_prevalence"]
    )
    pairs["shared_cooc_doc_prevalence"] = np.where(
        (pairs["astrophysics_cooc_doc_prevalence"] > 0)
        & (pairs["hep_cooc_doc_prevalence"] > 0),
        2 * pairs["astrophysics_cooc_doc_prevalence"]
        * pairs["hep_cooc_doc_prevalence"] / prevalence_sum,
        0.0,
    )
    astro_pair_rate = (pairs["astrophysics_paper_count"] + 0.5) / (n_astro + 1)
    hep_pair_rate = (pairs["hep_paper_count"] + 0.5) / (n_hep + 1)
    pairs["edge_log10_astro_hep_prevalence_ratio"] = np.log10(astro_pair_rate / hep_pair_rate)
    pairs["edge_astro_orientation_0_1"] = (
        pairs["edge_log10_astro_hep_prevalence_ratio"].clip(-clip, clip) + clip
    ) / (2 * clip)
    pairs["edge_field_participation"] = [
        _participation([astro, hep], fixed_categories=2)
        for astro, hep in zip(
            pairs["astrophysics_cooc_doc_prevalence"], pairs["hep_cooc_doc_prevalence"]
        )
    ]
    pairs["distance_mean_field_prevalence"] = np.where(
        pairs["mean_field_cooc_prevalence"] > 0,
        1 / pairs["mean_field_cooc_prevalence"], np.nan,
    )
    pairs["distance_pooled_prevalence"] = np.where(
        pairs["pooled_cooc_doc_prevalence"] > 0,
        1 / pairs["pooled_cooc_doc_prevalence"], np.nan,
    )
    pairs["distance_pooled_association"] = np.where(
        pairs["pooled_positive_npmi"] > 0, 1 / pairs["pooled_positive_npmi"], np.nan,
    )
    pairs["first_year"] = pairs[["astrophysics_first_year", "hep_first_year"]].min(axis=1)
    pairs["last_year"] = pairs[["astrophysics_last_year", "hep_last_year"]].max(axis=1)
    pairs["Type"] = "Undirected"
    pairs["Label"] = "abstract concept co-occurrence"
    pairs["edge_cross_field_betweenness_prevalence"] = 0.0
    for column, value in (
        ("wimp_definition", definition.name), ("window_kind", window.kind),
        ("window", window.label), ("start_year", window.start), ("end_year", window.end),
    ):
        pairs[column] = value
    connected = set(pairs["Source"]) | set(pairs["Target"])
    node_stats = node_stats[node_stats["Id"].isin(connected)].copy()
    return (
        pairs[edge_columns].sort_values(
            ["mean_field_cooc_prevalence", "pooled_paper_count", "Source", "Target"],
            ascending=[False, False, True, True], kind="mergesort",
        ),
        node_stats[node_columns].sort_values("Id", kind="mergesort"),
    )


def _make_weighted_graph(
    edges: pd.DataFrame, weight_column: str, distance_column: str
) -> nx.Graph:
    graph = nx.Graph()
    selected = edges[pd.to_numeric(edges[weight_column], errors="coerce").fillna(0) > 0]
    for row in selected.itertuples(index=False):
        graph.add_edge(
            row.Source,
            row.Target,
            strength=float(getattr(row, weight_column)),
            distance=float(getattr(row, distance_column)),
        )
    return graph


def cross_field_efficiency(
    graph: nx.Graph, astro_nodes: Sequence[str], hep_nodes: Sequence[str]
) -> tuple[float, float, int, int]:
    sources = sorted(node for node in astro_nodes if node in graph)
    targets = sorted(node for node in hep_nodes if node in graph)
    total_pairs = len(sources) * len(targets)
    if total_pairs == 0:
        return math.nan, 0.0, 0, total_pairs
    reciprocal_sum = 0.0
    reachable = 0
    for source in sources:
        lengths = nx.single_source_dijkstra_path_length(graph, source, weight="distance")
        for target in targets:
            distance = lengths.get(target)
            if distance is not None and distance > 0:
                reciprocal_sum += 1.0 / distance
                reachable += 1
    return reciprocal_sum / total_pairs, reachable / total_pairs, reachable, total_pairs


def build_brokerage_nodes_and_metrics(
    edges: pd.DataFrame,
    node_stats: pd.DataFrame,
    definition: WimpDefinition,
    window: Window,
    gephi_config: Mapping[str, Any],
    brokerage_config: Mapping[str, Any],
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    node_columns = [
        "wimp_definition", "window_kind", "window", "start_year", "end_year", "Id", "Label",
        "node_type", "subtype", "domain", "astrophysics_paper_count", "hep_paper_count",
        "pooled_paper_count", "astrophysics_prevalence", "hep_prevalence", "pooled_prevalence",
        "log10_astro_hep_prevalence_ratio", "astro_orientation_0_1", "field_participation",
        "strength_mean_field_prevalence", "strength_pooled_association",
        "is_astro_anchor", "is_hep_anchor",
        "is_cross_field_anchor", "cross_field_betweenness_prevalence",
        "cross_field_betweenness_percentile", "candidate_relative_betweenness_percentile",
        "removal_effect_efficiency_prevalence", "removal_effect_percentile",
        "node_size_sqrt_betweenness", "label_size_log_prevalence_strength",
        "node_size_sqrt_betweenness_common",
        "node_size_sqrt_removal_effect_common", "label_size_log_prevalence_strength_common",
        "is_focal_wimp",
    ]
    removal_columns = [
        "wimp_definition", "window_kind", "window", "start_year", "end_year", "node_id",
        "node_label", "node_type", "baseline_efficiency", "removed_efficiency",
        "relative_efficiency_loss", "baseline_reachable_share", "removed_reachable_share",
        "reachable_share_loss", "node_strength_mean_field_prevalence",
        "removal_effect_percentile",
    ]
    edges = edges[
        pd.to_numeric(edges["mean_field_cooc_prevalence"], errors="coerce").fillna(0) > 0
    ].copy()
    if edges.empty or node_stats.empty:
        return (
            pd.DataFrame(columns=node_columns), pd.DataFrame(columns=edges.columns),
            pd.DataFrame(columns=removal_columns),
        )
    prevalence_graph = _make_weighted_graph(
        edges, "mean_field_cooc_prevalence", "distance_mean_field_prevalence"
    )
    nodes = node_stats[node_stats["Id"].isin(prevalence_graph.nodes)].copy()
    fold_ratio = float(brokerage_config.get("anchor_fold_ratio", 2.0))
    threshold = math.log10(fold_ratio)
    eligible = ~nodes["node_type"].eq("candidate")
    nodes["is_astro_anchor"] = eligible & (
        nodes["log10_astro_hep_prevalence_ratio"] >= threshold
    )
    nodes["is_hep_anchor"] = eligible & (
        nodes["log10_astro_hep_prevalence_ratio"] <= -threshold
    )
    eligible_nodes = nodes[eligible].copy()
    if not nodes["is_astro_anchor"].any() and not eligible_nodes.empty:
        nodes.loc[eligible_nodes.nlargest(1, "log10_astro_hep_prevalence_ratio").index,
                  "is_astro_anchor"] = True
    if not nodes["is_hep_anchor"].any() and not eligible_nodes.empty:
        nodes.loc[eligible_nodes.nsmallest(1, "log10_astro_hep_prevalence_ratio").index,
                  "is_hep_anchor"] = True
    nodes["is_cross_field_anchor"] = nodes["is_astro_anchor"] | nodes["is_hep_anchor"]
    astro_nodes = nodes.loc[nodes["is_astro_anchor"], "Id"].tolist()
    hep_nodes = nodes.loc[nodes["is_hep_anchor"], "Id"].tolist()
    betweenness = (
        nx.betweenness_centrality_subset(
            prevalence_graph, astro_nodes, hep_nodes, normalized=True, weight="distance"
        )
        if prevalence_graph.number_of_edges() and astro_nodes and hep_nodes else {}
    )
    edge_betweenness = (
        nx.edge_betweenness_centrality_subset(
            prevalence_graph, astro_nodes, hep_nodes, normalized=True, weight="distance"
        )
        if prevalence_graph.number_of_edges() and astro_nodes and hep_nodes else {}
    )
    nodes["cross_field_betweenness_prevalence"] = nodes["Id"].map(betweenness).fillna(0.0)
    nodes["cross_field_betweenness_percentile"] = percentile_rank(
        nodes["cross_field_betweenness_prevalence"]
    )
    candidate_mask = nodes["node_type"].eq("candidate")
    nodes["candidate_relative_betweenness_percentile"] = 0.0
    nodes.loc[candidate_mask, "candidate_relative_betweenness_percentile"] = percentile_rank(
        nodes.loc[candidate_mask, "cross_field_betweenness_prevalence"]
    )
    edges = edges.copy()
    edges["edge_cross_field_betweenness_prevalence"] = [
        float(edge_betweenness.get((source, target), edge_betweenness.get((target, source), 0.0)))
        for source, target in zip(edges["Source"], edges["Target"])
    ]
    incident_prevalence_strength = pd.concat(
        [
            edges[["Source", "mean_field_cooc_prevalence"]].rename(columns={"Source": "Id"}),
            edges[["Target", "mean_field_cooc_prevalence"]].rename(columns={"Target": "Id"}),
        ], ignore_index=True,
    ).groupby("Id", observed=True)["mean_field_cooc_prevalence"].sum()
    incident_association_strength = pd.concat(
        [
            edges[["Source", "pooled_positive_npmi"]].rename(columns={"Source": "Id"}),
            edges[["Target", "pooled_positive_npmi"]].rename(columns={"Target": "Id"}),
        ], ignore_index=True,
    ).groupby("Id", observed=True)["pooled_positive_npmi"].sum()
    nodes["strength_mean_field_prevalence"] = (
        nodes["Id"].map(incident_prevalence_strength).fillna(0.0)
    )
    nodes["strength_pooled_association"] = (
        nodes["Id"].map(incident_association_strength).fillna(0.0)
    )

    baseline_efficiency, baseline_reachable, _, _ = cross_field_efficiency(
        prevalence_graph, astro_nodes, hep_nodes
    )
    top_n = int(brokerage_config.get("removal_top_betweenness_nodes", 25))
    removable = nodes[~nodes["is_cross_field_anchor"]].copy()
    top_bridge_ids = set(
        removable.nlargest(top_n, "cross_field_betweenness_prevalence")["Id"]
    )
    if bool(brokerage_config.get("removal_include_all_candidates", True)):
        top_bridge_ids.update(removable.loc[removable["node_type"].eq("candidate"), "Id"])
    top_bridge_ids.add(definition.focal_node_id)
    removal_rows: list[dict[str, Any]] = []
    removal_lookup: dict[str, float] = {}
    node_lookup = nodes.set_index("Id")
    for node_id in sorted(top_bridge_ids & set(prevalence_graph.nodes)):
        reduced = prevalence_graph.copy()
        reduced.remove_node(node_id)
        removed_efficiency, removed_reachable, _, _ = cross_field_efficiency(
            reduced, astro_nodes, hep_nodes
        )
        relative_loss = (
            max(0.0, (baseline_efficiency - removed_efficiency) / baseline_efficiency)
            if baseline_efficiency and not math.isnan(baseline_efficiency) else math.nan
        )
        removal_lookup[node_id] = relative_loss
        removal_rows.append(
            {
                "wimp_definition": definition.name, "window_kind": window.kind,
                "window": window.label, "start_year": window.start, "end_year": window.end,
                "node_id": node_id, "node_label": node_lookup.loc[node_id, "Label"],
                "node_type": node_lookup.loc[node_id, "node_type"],
                "baseline_efficiency": baseline_efficiency,
                "removed_efficiency": removed_efficiency,
                "relative_efficiency_loss": relative_loss,
                "baseline_reachable_share": baseline_reachable,
                "removed_reachable_share": removed_reachable,
                "reachable_share_loss": baseline_reachable - removed_reachable,
                "node_strength_mean_field_prevalence": node_lookup.loc[
                    node_id, "strength_mean_field_prevalence"
                ],
            }
        )
    removal = pd.DataFrame(removal_rows)
    if not removal.empty:
        removal["removal_effect_percentile"] = percentile_rank(
            removal["relative_efficiency_loss"]
        )
    removal = removal.reindex(columns=removal_columns)
    nodes["removal_effect_efficiency_prevalence"] = nodes["Id"].map(removal_lookup)
    nodes["removal_effect_percentile"] = 0.0
    removal_mask = nodes["removal_effect_efficiency_prevalence"].notna()
    nodes.loc[removal_mask, "removal_effect_percentile"] = percentile_rank(
        nodes.loc[removal_mask, "removal_effect_efficiency_prevalence"]
    )
    size_lower, size_upper = map(float, gephi_config["node_size_range"])
    label_lower, label_upper = map(float, gephi_config["label_size_range"])
    nodes["node_size_sqrt_betweenness"] = minmax_scale(
        nodes["cross_field_betweenness_prevalence"], size_lower, size_upper, transform="sqrt"
    )
    nodes["node_size_sqrt_betweenness_common"] = nodes["node_size_sqrt_betweenness"]
    nodes["node_size_sqrt_removal_effect_common"] = fixed_unit_scale(
        nodes["removal_effect_efficiency_prevalence"].fillna(0).clip(0, 1),
        size_lower, size_upper, transform="sqrt",
    )
    nodes["label_size_log_prevalence_strength"] = minmax_scale(
        nodes["strength_mean_field_prevalence"],
        label_lower, label_upper, transform="log1p"
    )
    nodes["label_size_log_prevalence_strength_common"] = (
        nodes["label_size_log_prevalence_strength"]
    )
    return nodes[node_columns], edges, removal


def build_common_endpoint_sensitivity(
    nodes: pd.DataFrame,
    edges: pd.DataFrame,
    definition: WimpDefinition,
    comparison_windows: Sequence[Window],
) -> pd.DataFrame:
    """Recalculate cross-field metrics using endpoints shared by both periods."""
    if len(comparison_windows) != 2:
        raise ValueError("Common-endpoint sensitivity requires exactly two comparison periods")
    scoped_nodes = nodes[
        nodes["wimp_definition"].eq(definition.name)
        & nodes["window_kind"].eq("stable")
    ].copy()
    scoped_edges = edges[
        edges["wimp_definition"].eq(definition.name)
        & edges["window_kind"].eq("stable")
    ].copy()
    endpoint_sets: dict[str, tuple[set[str], set[str]]] = {}
    for window in comparison_windows:
        period_nodes = scoped_nodes[scoped_nodes["window"].eq(window.label)]
        endpoint_sets[window.label] = (
            set(period_nodes.loc[period_nodes["is_astro_anchor"], "Id"]),
            set(period_nodes.loc[period_nodes["is_hep_anchor"], "Id"]),
        )
    first, second = (window.label for window in comparison_windows)
    common_astro = endpoint_sets[first][0] & endpoint_sets[second][0]
    common_hep = endpoint_sets[first][1] & endpoint_sets[second][1]
    if not common_astro or not common_hep:
        raise ValueError("Comparison periods do not share both endpoint types")

    astro_union = endpoint_sets[first][0] | endpoint_sets[second][0]
    hep_union = endpoint_sets[first][1] | endpoint_sets[second][1]
    rows: list[dict[str, Any]] = []
    for window in comparison_windows:
        period_nodes = scoped_nodes[scoped_nodes["window"].eq(window.label)].copy()
        period_edges = scoped_edges[scoped_edges["window"].eq(window.label)].copy()
        graph = _make_weighted_graph(
            period_edges, "mean_field_cooc_prevalence", "distance_mean_field_prevalence"
        )
        graph_nodes = set(graph.nodes)
        astro_endpoints = sorted(common_astro & graph_nodes)
        hep_endpoints = sorted(common_hep & graph_nodes)
        betweenness = nx.betweenness_centrality_subset(
            graph,
            astro_endpoints,
            hep_endpoints,
            normalized=True,
            weight="distance",
        )
        focal_value = float(betweenness.get(definition.focal_node_id, 0.0))
        candidate_nodes = period_nodes[period_nodes["node_type"].eq("candidate")].copy()
        candidate_nodes["common_endpoint_betweenness"] = (
            candidate_nodes["Id"].map(betweenness).fillna(0.0)
        )
        candidate_nodes["common_endpoint_rank"] = candidate_nodes[
            "common_endpoint_betweenness"
        ].rank(method="min", ascending=False)
        focal_rank = candidate_nodes.loc[
            candidate_nodes["Id"].eq(definition.focal_node_id), "common_endpoint_rank"
        ]
        baseline_efficiency, baseline_reachable, _, _ = cross_field_efficiency(
            graph, astro_endpoints, hep_endpoints
        )
        reduced = graph.copy()
        if definition.focal_node_id in reduced:
            reduced.remove_node(definition.focal_node_id)
        removed_efficiency, removed_reachable, _, _ = cross_field_efficiency(
            reduced, astro_endpoints, hep_endpoints
        )
        removal_effect = (
            max(
                0.0,
                (baseline_efficiency - removed_efficiency) / baseline_efficiency,
            )
            if baseline_efficiency and not math.isnan(baseline_efficiency)
            else math.nan
        )
        focal_dynamic = period_nodes[
            period_nodes["Id"].eq(definition.focal_node_id)
        ].iloc[0]
        original_astro, original_hep = endpoint_sets[window.label]
        rows.append(
            {
                "wimp_definition": definition.name,
                "window": window.label,
                "start_year": window.start,
                "end_year": window.end,
                "original_astro_endpoint_count": len(original_astro),
                "original_hep_endpoint_count": len(original_hep),
                "common_astro_endpoint_count": len(astro_endpoints),
                "common_hep_endpoint_count": len(hep_endpoints),
                "astro_endpoint_overlap_count": len(common_astro),
                "hep_endpoint_overlap_count": len(common_hep),
                "astro_endpoint_jaccard": len(common_astro) / len(astro_union),
                "hep_endpoint_jaccard": len(common_hep) / len(hep_union),
                "dynamic_endpoint_betweenness": float(
                    focal_dynamic["cross_field_betweenness_prevalence"]
                ),
                "common_endpoint_betweenness": focal_value,
                "common_endpoint_candidate_rank": (
                    int(focal_rank.iloc[0]) if not focal_rank.empty else pd.NA
                ),
                "candidate_count": len(candidate_nodes),
                "dynamic_endpoint_removal_effect": float(
                    focal_dynamic["removal_effect_efficiency_prevalence"]
                ),
                "common_endpoint_baseline_efficiency": baseline_efficiency,
                "common_endpoint_removed_efficiency": removed_efficiency,
                "common_endpoint_removal_effect": removal_effect,
                "common_endpoint_baseline_reachable_share": baseline_reachable,
                "common_endpoint_removed_reachable_share": removed_reachable,
            }
        )
    return pd.DataFrame(rows)


def gephi_brokerage_tables(
    nodes: pd.DataFrame, edges: pd.DataFrame
) -> tuple[pd.DataFrame, pd.DataFrame]:
    node_columns = [
        "Id", "Label", "node_type", "subtype", "domain", "is_focal_wimp",
        "node_size_sqrt_betweenness_common", "node_size_sqrt_removal_effect_common",
        "label_size_log_prevalence_strength_common", "astro_orientation_0_1",
        "field_participation", "cross_field_betweenness_prevalence",
        "cross_field_betweenness_percentile",
        "candidate_relative_betweenness_percentile", "is_astro_anchor", "is_hep_anchor",
        "removal_effect_efficiency_prevalence", "removal_effect_percentile",
    ]
    node_columns.extend(column for column in ("layout_x", "layout_y") if column in nodes.columns)
    gephi_nodes = nodes[node_columns].copy()
    gephi_edges = edges[
        [
            "Source", "Target", "Type", "mean_field_cooc_prevalence",
            "pooled_positive_npmi", "shared_positive_npmi",
            "shared_cooc_doc_prevalence", "pooled_cooc_doc_prevalence",
            "distance_mean_field_prevalence", "distance_pooled_association",
            "edge_astro_orientation_0_1", "edge_field_participation",
            "edge_cross_field_betweenness_prevalence",
        ]
    ].rename(
        columns={
            "mean_field_cooc_prevalence": "Weight",
            "pooled_positive_npmi": "AssociationWeight",
            "shared_positive_npmi": "SharedAssociationWeight",
            "shared_cooc_doc_prevalence": "SharedPrevalenceWeight",
            "pooled_cooc_doc_prevalence": "PooledPrevalenceWeight",
            "distance_mean_field_prevalence": "Distance",
            "distance_pooled_association": "AssociationDistance",
            "edge_cross_field_betweenness_prevalence": "BridgeWeight",
        }
    )
    gephi_edges = gephi_edges[gephi_edges["Weight"] > 0].copy()
    connected = set(gephi_edges["Source"]) | set(gephi_edges["Target"])
    gephi_nodes = gephi_nodes[gephi_nodes["Id"].isin(connected)].copy()
    return gephi_nodes, gephi_edges


def validate_node_edge_tables(nodes: pd.DataFrame, edges: pd.DataFrame, name: str) -> None:
    if nodes["Id"].duplicated().any():
        raise ValueError(f"{name}: duplicate node IDs")
    unresolved = (set(edges["Source"]) | set(edges["Target"])) - set(nodes["Id"])
    if unresolved:
        raise ValueError(f"{name}: unresolved edge endpoints: {sorted(unresolved)[:10]}")
    if edges.duplicated(["Source", "Target"]).any():
        raise ValueError(f"{name}: duplicate endpoint pairs")


def _write_csv(frame: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(path, index=False)


def _instance_name(*parts: str) -> str:
    return "--".join(slugify(part) for part in parts)


def _file_inventory(root: Path) -> dict[str, dict[str, Any]]:
    inventory: dict[str, dict[str, Any]] = {}
    for path in sorted(root.rglob("*")):
        if not path.is_file() or path.name == "manifest.json":
            continue
        relative = str(path.relative_to(root))
        entry: dict[str, Any] = {"sha256": sha256_file(path), "bytes": path.stat().st_size}
        if path.suffix == ".csv":
            entry["rows"] = int(len(pd.read_csv(path)))
        inventory[relative] = entry
    return inventory


def _manifest(
    graph_name: str,
    question: str,
    graph_family: str,
    primary_weight: str,
    config: Mapping[str, Any],
    input_paths: Mapping[str, Path],
    output_root: Path,
    contracts: Mapping[str, Any],
) -> dict[str, Any]:
    return {
        "analysis": graph_name,
        "schema_version": "3.1.0",
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "question": question,
        "graph_family": graph_family,
        "primary_edge_weight": primary_weight,
        "layout_guidance": {
            "primary": "multilevel force-directed layout for an undirected relational graph",
            "fallback": "stress majorization or filtered ego/community views",
            "stability": "layout_x and layout_y come from one union graph and are reused unchanged in both decade panels",
            "routing": "straight low-opacity edges; use filtering rather than decorative edge bundling",
        },
        "parameters": config,
        "inputs": {
            name: {"path": str(path.resolve()), "sha256": sha256_file(path)}
            for name, path in input_paths.items()
        },
        "software": {
            "python": platform.python_version(),
            "pandas": pd.__version__,
            "numpy": np.__version__,
            "networkx": nx.__version__,
            "pyarrow": pyarrow.__version__,
            "platform": platform.platform(),
        },
        "contracts": contracts,
        "files": _file_inventory(output_root),
        "validation": {
            "edge_endpoints_resolve": True,
            "duplicate_node_ids_within_graph_instance": False,
            "duplicate_edge_pairs_within_graph_instance": False,
            "gephi_tables_contain_derived_parameter_values_only": True,
        },
    }


def write_manifest(path: Path, manifest: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(manifest, handle, indent=2, ensure_ascii=False)
        handle.write("\n")


def _write_graph_instance(
    canonical_nodes: pd.DataFrame,
    canonical_edges: pd.DataFrame,
    gephi_nodes: pd.DataFrame,
    gephi_edges: pd.DataFrame,
    graph_root: Path,
    instance: str,
) -> None:
    validate_node_edge_tables(canonical_nodes, canonical_edges, f"canonical {instance}")
    validate_node_edge_tables(gephi_nodes, gephi_edges, f"Gephi {instance}")
    canonical_graph = graph_root / "canonical" / "graphs" / f"{instance}.graphml"
    gephi_dir = graph_root / "gephi" / instance
    gephi_nodes_path = gephi_dir / "nodes.csv"
    gephi_edges_path = gephi_dir / "edges.csv"
    _write_csv(gephi_nodes, gephi_nodes_path)
    _write_csv(gephi_edges, gephi_edges_path)
    write_graphml(canonical_nodes, canonical_edges, canonical_graph)
    write_graphml(gephi_nodes, gephi_edges, gephi_dir / "network.graphml")
    write_gephi_gexf(gephi_nodes, gephi_edges, gephi_dir / "network.gexf")


def _write_canonical_only_instance(
    canonical_nodes: pd.DataFrame,
    canonical_edges: pd.DataFrame,
    graph_root: Path,
    instance: str,
) -> None:
    validate_node_edge_tables(canonical_nodes, canonical_edges, f"canonical {instance}")
    path = graph_root / "canonical" / "graphs" / "robustness" / f"{instance}.graphml"
    write_graphml(canonical_nodes, canonical_edges, path)


def build_wimp_role_outputs(
    paper_metadata_path: Path,
    occurrences_path: Path,
    sentence_events_path: Path,
    abstract_events_path: Path,
    candidate_code_dir: Path,
    config_path: Path,
    output_dir: Path,
) -> dict[str, Any]:
    config = read_config(config_path)
    definitions = parse_definitions(config)
    windows = build_windows(config)
    start_year, end_year = map(int, config["analysis_years"])
    focal_fields = list(map(str, config["focal_fields"]))
    adapter = CandidateAdapter(candidate_code_dir, dm_scope="candidate")
    metadata = load_paper_metadata(paper_metadata_path, start_year, end_year)
    paper_table = build_paper_table(metadata, adapter)
    raw_candidates = build_raw_candidate_papers(metadata, adapter)
    occurrences = pd.read_parquet(occurrences_path)
    sentence_events = pd.read_parquet(sentence_events_path)
    abstract_events = pd.read_parquet(abstract_events_path)
    occurrences = occurrences[occurrences["year"].between(start_year, end_year)].copy()
    sentence_events = sentence_events[sentence_events["year"].between(start_year, end_year)].copy()
    abstract_events = abstract_events[abstract_events["year"].between(start_year, end_year)].copy()
    input_paths = {
        "paper_metadata": paper_metadata_path,
        "occurrences": occurrences_path,
        "sentence_events": sentence_events_path,
        "abstract_events": abstract_events_path,
        "candidate_ontology": candidate_code_dir / "dm_term_normalization" / "candidate_ontology.py",
        "analysis_config": config_path,
        "analysis_code": Path(__file__),
        "analysis_entrypoint": Path(__file__).resolve().parents[1] / "build_wimp_role_graphs.py",
    }
    base_manifest = occurrences_path.parent / "manifest.json"
    if base_manifest.exists():
        input_paths["base_pipeline_manifest"] = base_manifest

    comparison_windows = [window for window in windows if window.kind == "stable"]
    primary_definition_name = str(config["primary_wimp_definition"])
    primary_definition = next(
        definition for definition in definitions if definition.name == primary_definition_name
    )
    layout_seed = int(config["gephi"].get("master_layout_seed", 20260815))
    layout_iterations = int(config["gephi"].get("master_layout_iterations", 150))

    graph1_root = output_dir / "01_field_relative_prominence"
    prominence, crosslisting = build_prominence_metrics(
        paper_table, raw_candidates, definitions, windows, focal_fields
    )
    uncertainty = config.get("uncertainty", {})
    prominence_bootstrap = bootstrap_wimp_prominence(
        paper_table,
        raw_candidates,
        definitions,
        windows,
        focal_fields,
        iterations=int(uncertainty.get("prominence_bootstrap_iterations", 0)),
        seed=int(uncertainty.get("random_seed", 20260815)),
        confidence_level=float(uncertainty.get("confidence_level", 0.95)),
    )
    focal_ids = {definition.name: definition.focal_node_id for definition in definitions}
    wimp_prominence = prominence[
        prominence.apply(
            lambda row: row["candidate_id"] == focal_ids[row["wimp_definition"]], axis=1
        )
    ].copy()
    if not prominence_bootstrap.empty:
        merge_keys = [
            "wimp_definition", "window_kind", "window", "start_year", "end_year",
            "field", "candidate_id",
        ]
        wimp_prominence = wimp_prominence.merge(
            prominence_bootstrap, on=merge_keys, how="left", validate="one_to_one"
        )
    wimp_crosslisting = crosslisting[
        crosslisting.apply(
            lambda row: row["candidate_id"] == focal_ids[row["wimp_definition"]], axis=1
        )
    ].copy()
    _write_csv(paper_table, graph1_root / "canonical" / "paper_field_membership.csv")
    _write_csv(prominence, graph1_root / "canonical" / "candidate_field_metrics_by_window.csv")
    _write_csv(crosslisting, graph1_root / "canonical" / "candidate_crosslisting_by_window.csv")
    _write_csv(prominence_bootstrap, graph1_root / "canonical" / "wimp_prominence_bootstrap.csv")
    _write_csv(wimp_prominence, graph1_root / "canonical" / "wimp_prominence_trajectory.csv")
    _write_csv(wimp_crosslisting, graph1_root / "canonical" / "wimp_crosslisting_trajectory.csv")
    prominence_nodes_all: list[pd.DataFrame] = []
    prominence_edges_all: list[pd.DataFrame] = []
    prominence_instances: dict[
        tuple[str, str], tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]
    ] = {}
    for definition in definitions:
        for window in comparison_windows:
            nodes, edges, gephi_nodes, gephi_edges = build_prominence_graph(
                prominence, definition, window, config["gephi"]
            )
            prominence_nodes_all.append(nodes)
            prominence_edges_all.append(edges)
            prominence_instances[(definition.name, window.label)] = (
                nodes, edges, gephi_nodes, gephi_edges
            )
    prominence_layout = master_layout_positions(
        [
            prominence_instances[(primary_definition_name, window.label)][1]
            for window in comparison_windows
        ],
        "Weight",
        layout_seed,
        layout_iterations,
    )
    for definition in definitions:
        for window in comparison_windows:
            nodes, edges, gephi_nodes, gephi_edges = prominence_instances[
                (definition.name, window.label)
            ]
            instance = _instance_name(definition.name, window.label)
            if definition.name == primary_definition_name:
                nodes = attach_master_layout(nodes, prominence_layout)
                gephi_nodes = attach_master_layout(gephi_nodes, prominence_layout)
                _write_graph_instance(
                    nodes, edges, gephi_nodes, gephi_edges, graph1_root, instance
                )
            else:
                _write_canonical_only_instance(nodes, edges, graph1_root, instance)
    _write_csv(pd.concat(prominence_nodes_all, ignore_index=True), graph1_root / "canonical" / "nodes.csv")
    _write_csv(pd.concat(prominence_edges_all, ignore_index=True), graph1_root / "canonical" / "edges.csv")

    graph2_root = output_dir / "02_area_wide_importance"
    importance_edges_all: list[pd.DataFrame] = []
    importance_nodes_all: list[pd.DataFrame] = []
    importance_instances: dict[tuple[str, str], tuple[pd.DataFrame, pd.DataFrame]] = {}
    transformed_by_definition = {
        definition.name: apply_wimp_definition_to_candidates(raw_candidates, definition)
        for definition in definitions
    }
    for definition in definitions:
        transformed_candidates = transformed_by_definition[definition.name]
        for window in windows:
            min_edge_papers = int(config["min_edge_papers"][window.kind])
            abstract_edges = aggregate_importance_edges(
                abstract_events, occurrences, paper_table, transformed_candidates,
                definition, window, focal_fields, min_edge_papers, "abstract",
            )
            sentence_edges = aggregate_importance_edges(
                sentence_events, occurrences, paper_table, transformed_candidates,
                definition, window, focal_fields, min_edge_papers, "sentence",
            )
            importance_edges_all.extend([abstract_edges, sentence_edges])
            if abstract_edges.empty:
                continue
            nodes = build_importance_nodes(
                abstract_edges, transformed_candidates, occurrences,
                definition, window, focal_fields, config["gephi"],
            )
            importance_nodes_all.append(nodes)
            if window.kind == "stable":
                importance_instances[(definition.name, window.label)] = (nodes, abstract_edges)
    importance_edges_frame = pd.concat(importance_edges_all, ignore_index=True)
    importance_nodes_frame = pd.concat(importance_nodes_all, ignore_index=True)
    importance_candidate_metrics = importance_nodes_frame[
        importance_nodes_frame["node_type"].eq("candidate")
    ].copy()
    importance_wimp = importance_candidate_metrics[
        importance_candidate_metrics.apply(
            lambda row: row["Id"] == focal_ids[row["wimp_definition"]], axis=1
        )
    ].copy()
    _write_csv(importance_edges_frame, graph2_root / "canonical" / "edges_by_window.csv")
    _write_csv(importance_nodes_frame, graph2_root / "canonical" / "nodes_by_window.csv")
    _write_csv(importance_candidate_metrics, graph2_root / "canonical" / "candidate_metrics_by_window.csv")
    _write_csv(importance_wimp, graph2_root / "canonical" / "wimp_importance_trajectory.csv")
    importance_layout = master_layout_positions(
        [
            importance_instances[(primary_definition_name, window.label)][1]
            for window in comparison_windows
        ],
        "cooc_doc_prevalence_candidate_papers",
        layout_seed,
        layout_iterations,
    )
    for definition in definitions:
        for window in comparison_windows:
            nodes, edges = importance_instances[(definition.name, window.label)]
            instance = _instance_name(definition.name, window.label)
            if definition.name == primary_definition_name:
                nodes = attach_master_layout(nodes, importance_layout)
                gephi_nodes, gephi_edges = gephi_importance_tables(nodes, edges)
                _write_graph_instance(
                    nodes, edges, gephi_nodes, gephi_edges, graph2_root, instance
                )
            else:
                _write_canonical_only_instance(nodes, edges, graph2_root, instance)

    graph3_root = output_dir / "03_cross_field_brokerage"
    brokerage_edges_all: list[pd.DataFrame] = []
    brokerage_nodes_all: list[pd.DataFrame] = []
    removal_all: list[pd.DataFrame] = []
    brokerage_instances: dict[tuple[str, str], pd.DataFrame] = {}
    for definition in definitions:
        for window in windows:
            min_edge_papers = int(config["min_edge_papers"][window.kind])
            broker_edges, broker_node_stats = aggregate_brokerage_edges(
                occurrences, paper_table, definition, window, min_edge_papers, config["gephi"]
            )
            if broker_edges.empty:
                continue
            broker_nodes, broker_edges, removal = build_brokerage_nodes_and_metrics(
                broker_edges, broker_node_stats, definition, window,
                config["gephi"], config["brokerage"]
            )
            brokerage_edges_all.append(broker_edges)
            brokerage_nodes_all.append(broker_nodes)
            removal_all.append(removal)
            if window.kind == "stable":
                brokerage_instances[(definition.name, window.label)] = broker_edges
    brokerage_edges_frame = pd.concat(brokerage_edges_all, ignore_index=True)
    brokerage_nodes_frame = apply_common_brokerage_scales(
        pd.concat(brokerage_nodes_all, ignore_index=True), definitions, config["gephi"]
    )
    removal_frame = pd.concat(removal_all, ignore_index=True)
    concept_brokerage = brokerage_nodes_frame.copy()
    wimp_brokerage = concept_brokerage[
        concept_brokerage.apply(
            lambda row: row["Id"] == focal_ids[row["wimp_definition"]], axis=1
        )
    ].copy()
    common_endpoint_sensitivity = build_common_endpoint_sensitivity(
        brokerage_nodes_frame,
        brokerage_edges_frame,
        primary_definition,
        comparison_windows,
    )
    _write_csv(brokerage_edges_frame, graph3_root / "canonical" / "edges_by_window.csv")
    _write_csv(brokerage_nodes_frame, graph3_root / "canonical" / "nodes_by_window.csv")
    _write_csv(removal_frame, graph3_root / "canonical" / "node_removal_metrics.csv")
    _write_csv(concept_brokerage, graph3_root / "canonical" / "concept_brokerage_metrics_by_window.csv")
    _write_csv(wimp_brokerage, graph3_root / "canonical" / "wimp_brokerage_trajectory.csv")
    _write_csv(
        common_endpoint_sensitivity,
        graph3_root / "canonical" / "common_endpoint_sensitivity.csv",
    )
    brokerage_layout = master_layout_positions(
        [
            brokerage_instances[(primary_definition_name, window.label)]
            for window in comparison_windows
        ],
        "mean_field_cooc_prevalence",
        layout_seed,
        layout_iterations,
    )
    for definition in definitions:
        for window in comparison_windows:
            edges = brokerage_instances[(definition.name, window.label)]
            nodes = brokerage_nodes_frame[
                brokerage_nodes_frame["wimp_definition"].eq(definition.name)
                & brokerage_nodes_frame["window_kind"].eq(window.kind)
                & brokerage_nodes_frame["window"].eq(window.label)
            ].copy()
            instance = _instance_name(definition.name, window.label)
            if definition.name == primary_definition_name:
                nodes = attach_master_layout(nodes, brokerage_layout)
                gephi_nodes, gephi_edges = gephi_brokerage_tables(nodes, edges)
                _write_graph_instance(
                    nodes, edges, gephi_nodes, gephi_edges, graph3_root, instance
                )
            else:
                _write_canonical_only_instance(nodes, edges, graph3_root, instance)

    manifests = {
        "01_field_relative_prominence": _manifest(
            "wimp-field-relative-prominence",
            "How prominent is each candidate, especially the WIMP, relative to astrophysics and HEP?",
            "candidate-field bipartite graph plus temporal prevalence tables",
            "candidate_share_of_mentions",
            config, input_paths, graph1_root,
            {
                "canonical": "lossless denominators, counts, field-specific shares, equal-field mean share, smoothed log10 astrophysics/HEP share ratio, participation, and cross-listing comparisons",
                "gephi_nodes": "fixed node/label size from mean field share; fixed colour from the clipped share ratio; focal flag, participation, and shared decade-layout coordinates",
                "gephi_edges": "Weight is candidate share of paper-candidate mentions; AlternateWeightPaperPrevalence is the paper-level alternative",
            },
        ),
        "02_area_wide_importance": _manifest(
            "wimp-area-wide-importance",
            "How structurally important is each candidate in pooled astrophysics and HEP dark-matter research?",
            "pooled focal-field candidate-concept bipartite graph",
            "cooc_doc_prevalence_candidate_papers",
            config, input_paths, graph2_root,
            {
                "canonical": "pooled abstract and sentence edges, full denominators, prevalence/association measures, role-specific HITS scores and percentiles, coreness, and ontology-type diversity",
                "gephi_nodes": "node size and label size are fixed mappings of role-specific HITS percentiles; node_type is the ontology colour category; layout coordinates are shared across decades",
                "gephi_edges": "Weight is pooled abstract co-occurrence prevalence among candidate-bearing papers; AssociationWeight is positive NPMI",
            },
        ),
        "03_cross_field_brokerage": _manifest(
            "wimp-cross-field-brokerage",
            "Which concepts, including the WIMP, hold together astrophysics- and HEP-oriented dark-matter discourse?",
            "single-node abstract concept co-occurrence graph with empirical field orientation",
            "mean_field_cooc_prevalence",
            config, input_paths, graph3_root,
            {
                "canonical": "one canonical node per concept; paper-binary abstract co-occurrence prevalence normalized within each field and averaged with equal field weight; empirical node and edge orientation; prevalence-weighted cross-field node/edge betweenness; targeted removal effects; a fixed common-endpoint period sensitivity; NPMI retained as a secondary association attribute",
                "gephi_nodes": "primary size uses common-scale prevalence-weighted cross-field betweenness; colour is empirical astrophysics orientation; alternative size uses common-scale removal effect; coordinates are shared across decades",
                "gephi_edges": "Weight is the equal-field mean co-occurrence prevalence and defines both layout attraction and shortest-path distance; BridgeWeight is derived prevalence-weighted cross-field edge betweenness; AssociationWeight is pooled positive NPMI retained only as a secondary attribute",
            },
        ),
    }
    for name, manifest in manifests.items():
        write_manifest(output_dir / name / "manifest.json", manifest)
    overall = {
        "analysis": "wimp-role-networks",
        "schema_version": "3.1.0",
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "graphs": {
            name: {
                "path": str((output_dir / name).resolve()),
                "manifest_sha256": sha256_file(output_dir / name / "manifest.json"),
            }
            for name in manifests
        },
        "wimp_definitions": config["wimp_definitions"],
        "primary_wimp_definition": primary_definition.name,
        "publication_periods": [window.label for window in comparison_windows],
        "publication_gephi_instances": 6,
        "validation": "passed",
    }
    write_manifest(output_dir / "manifest.json", overall)
    return overall
