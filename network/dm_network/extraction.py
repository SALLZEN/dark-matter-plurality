from __future__ import annotations

import importlib
import math
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

import pandas as pd

from .ontology import EntityMatcher, RelationMatcher


ABBREVIATIONS = {
    "e.g.",
    "i.e.",
    "et al.",
    "fig.",
    "figs.",
    "eq.",
    "eqs.",
    "dr.",
    "prof.",
    "vs.",
    "approx.",
}

NEGATION_RE = re.compile(
    r"\b(?:not|no|never|cannot|can't|couldn't|doesn't|didn't|fails?\s+to|failed\s+to|without)\b",
    re.IGNORECASE,
)
MODAL_RE = re.compile(
    r"\b(?:may|might|could|can|possibly|potentially|suggests?|appears?\s+to)\b",
    re.IGNORECASE,
)


def slugify(value: str) -> str:
    value = value.casefold().replace("ν", "nu")
    value = re.sub(r"[^a-z0-9]+", "_", value).strip("_")
    return value or "unknown"


def sentence_spans(text: str) -> list[tuple[int, int, str]]:
    """Return conservative sentence spans while preserving the original text."""
    if not isinstance(text, str) or not text.strip():
        return []
    boundaries = [0]
    for match in re.finditer(r"[.!?]+\s+", text):
        punctuation_start = match.start()
        prefix = text[max(0, punctuation_start - 12) : match.end()].casefold().strip()
        if any(prefix.endswith(abbrev) for abbrev in ABBREVIATIONS):
            continue
        if punctuation_start > 0 and punctuation_start + 1 < len(text):
            if text[punctuation_start - 1].isdigit() and text[punctuation_start + 1].isdigit():
                continue
        boundaries.append(match.end())
    boundaries.append(len(text))

    spans: list[tuple[int, int, str]] = []
    for start, end in zip(boundaries[:-1], boundaries[1:]):
        raw = text[start:end]
        left_trim = len(raw) - len(raw.lstrip())
        right = len(raw.rstrip())
        clean_start = start + left_trim
        clean_end = start + right
        sentence = text[clean_start:clean_end]
        if sentence:
            spans.append((clean_start, clean_end, sentence))
    return spans


@dataclass
class CandidateAdapter:
    code_dir: Path
    dm_scope: str = "candidate"

    def __post_init__(self) -> None:
        code_dir = str(self.code_dir.resolve())
        if code_dir not in sys.path:
            sys.path.insert(0, code_dir)
        self.dmtn = importlib.import_module("dm_term_normalization")
        self.normalization = importlib.import_module("dm_term_normalization.normalization")
        if self.dm_scope not in {"candidate", "all"}:
            raise ValueError("dm_scope must be 'candidate' or 'all'")

    def normalize_sentence(self, sentence: str) -> str:
        return self.normalization.normalize_segment(sentence, mask_math=True)

    def find_in_normalized(self, text: str) -> list[dict[str, Any]]:
        tags, spans = self.dmtn.extract_dm_tags_with_spans(text)
        # Pair first; filter second. This is the key repair to the old snippet path.
        pairs = self._resolve_ambiguous_pairs(text, list(zip(tags, spans)))
        if self.dm_scope == "candidate":
            pairs = [(tag, span) for tag, span in pairs if tag in self.dmtn.CANDIDATE_TAGS]

        found: list[dict[str, Any]] = []
        for tag, span in pairs:
            info = self.dmtn.DM_TAGS_INFO.get(tag, {})
            category = info.get("category", "model")
            if tag in self.dmtn.CANDIDATE_TAGS:
                labels = self.dmtn.candidate_species_labels([tag])
                label = labels[0] if labels else info.get("full", tag)
            else:
                label = info.get("full", tag)
            start, end = int(span[0]), int(span[1])
            found.append(
                {
                    "node_id": f"dm_model:{slugify(label)}",
                    "label": label,
                    "node_type": "dm_model",
                    "subtype": category,
                    "domain": "candidate",
                    "ontology_source": "candidate_ontology.py",
                    "start": start,
                    "end": end,
                    "matched_text": text[start:end],
                    "matched_alias": tag,
                    "candidate_tag": tag,
                }
            )

        # Collapse axion/ALP and other shared species labels within a sentence.
        retained: dict[str, dict[str, Any]] = {}
        for row in sorted(found, key=lambda item: (item["start"], item["end"])):
            current = retained.get(row["node_id"])
            if current is None:
                retained[row["node_id"]] = {
                    **row,
                    "_all_spans": [(row["start"], row["end"])],
                }
            else:
                tags = sorted(set(str(current["candidate_tag"]).split("|") + [row["candidate_tag"]]))
                current["candidate_tag"] = "|".join(tags)
                current["_all_spans"].append((row["start"], row["end"]))
        return list(retained.values())

    @staticmethod
    def _resolve_ambiguous_pairs(
        text: str, pairs: list[tuple[str, tuple[int, int]]]
    ) -> list[tuple[str, tuple[int, int]]]:
        """Resolve ontology collisions that case-insensitive regex alone cannot."""
        resolved: list[tuple[str, tuple[int, int]]] = []
        for tag, span in pairs:
            start, end = int(span[0]), int(span[1])
            surface = text[start:end]
            if tag in {"inelastic_dm", "inert_doublet_dm"}:
                if surface == "iDM" and tag != "inelastic_dm":
                    continue
                if surface == "IDM" and tag != "inert_doublet_dm":
                    continue
                if surface.casefold() == "idm" and surface not in {"iDM", "IDM"}:
                    window = text[max(0, start - 80) : min(len(text), end + 80)].casefold()
                    if "inert doublet" in window and tag != "inert_doublet_dm":
                        continue
                    if "inelastic dark matter" in window and tag != "inelastic_dm":
                        continue
                    if "inert doublet" not in window and "inelastic dark matter" not in window:
                        continue
            resolved.append((tag, (start, end)))
        return resolved


def _span_distance(a_start: int, a_end: int, b_start: int, b_end: int) -> int:
    if a_end < b_start:
        return b_start - a_end
    if b_end < a_start:
        return a_start - b_end
    return 0


def _cue_between(candidate: dict[str, Any], target: dict[str, Any], cue: dict[str, Any]) -> bool:
    left_end = min(candidate["end"], target["end"])
    right_start = max(candidate["start"], target["start"])
    return cue["cue_start"] >= left_end and cue["cue_end"] <= right_start


def _relation_context_flags(text: str, cue_start: int, cue_end: int) -> tuple[bool, bool]:
    before = text[max(0, cue_start - 55) : cue_start]
    around = text[max(0, cue_start - 55) : min(len(text), cue_end + 25)]
    return bool(NEGATION_RE.search(before)), bool(MODAL_RE.search(around))


def _best_relation(
    candidate: dict[str, Any],
    target: dict[str, Any],
    cues: Iterable[dict[str, Any]],
    max_relation_distance: int,
) -> dict[str, Any] | None:
    eligible: list[dict[str, Any]] = []
    for cue in cues:
        if target["node_type"] not in cue["allowed_target_types"]:
            continue
        total_distance = _span_distance(
            candidate["start"], candidate["end"], cue["cue_start"], cue["cue_end"]
        ) + _span_distance(target["start"], target["end"], cue["cue_start"], cue["cue_end"])
        between = _cue_between(candidate, target, cue)
        if total_distance <= max_relation_distance:
            eligible.append({**cue, "cue_distance": total_distance, "cue_between": between})
    if not eligible:
        return None
    eligible.sort(
        key=lambda row: (
            not row["cue_between"],
            row["cue_distance"],
            row["cue_start"],
            row["relation"],
        )
    )
    return eligible[0]


def extract_corpus(
    papers: pd.DataFrame,
    candidate_adapter: CandidateAdapter,
    entity_matcher: EntityMatcher,
    relation_matcher: RelationMatcher,
    max_relation_distance: int = 180,
    progress_every: int = 2500,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    required = {"bibcode", "year", "abstract", "arxiv_category"}
    missing = sorted(required - set(papers.columns))
    if missing:
        raise ValueError(f"Paper input is missing columns: {missing}")

    occurrence_rows: list[dict[str, Any]] = []
    cooccurrence_rows: list[dict[str, Any]] = []
    abstract_cooccurrence_rows: list[dict[str, Any]] = []
    relation_rows: list[dict[str, Any]] = []

    for paper_index, row in enumerate(papers.itertuples(index=False), start=1):
        abstract = row.abstract if isinstance(row.abstract, str) else ""
        if not abstract:
            continue
        paper_candidates: dict[str, dict[str, Any]] = {}
        paper_targets: dict[str, dict[str, Any]] = {}
        candidate_sentence_ids: dict[str, set[int]] = {}
        target_sentence_ids: dict[str, set[int]] = {}
        for sentence_id, (global_start, global_end, raw_sentence) in enumerate(
            sentence_spans(abstract), start=1
        ):
            sentence = candidate_adapter.normalize_sentence(raw_sentence)
            candidates = candidate_adapter.find_in_normalized(sentence)
            targets = entity_matcher.find(sentence)
            # Do not manufacture a candidate--entity edge when an entity alias is
            # embedded in the candidate mention itself (for example, the words
            # "black hole" inside "primordial black hole").
            targets = [
                target
                for target in targets
                if not (
                    any(
                        candidate["node_id"]
                        in target.get("_exclude_with_candidates", ())
                        for candidate in candidates
                    )
                    or any(
                        target["start"] < candidate_end
                        and candidate_start < target["end"]
                        for candidate in candidates
                        for candidate_start, candidate_end in candidate.get(
                            "_all_spans", [(candidate["start"], candidate["end"])]
                        )
                    )
                )
            ]
            cues = relation_matcher.find(sentence) if candidates and targets else []
            candidate_bearing_sentence = bool(candidates)

            base = {
                "bibcode": row.bibcode,
                "year": int(row.year) if not pd.isna(row.year) else pd.NA,
                "arxiv_category": row.arxiv_category,
                "sentence_id": sentence_id,
                "sentence_global_start": global_start,
                "sentence_global_end": global_end,
                "sentence": sentence,
                "sentence_raw": raw_sentence,
            }
            for occurrence_kind, matches in (("dm_model", candidates), ("entity", targets)):
                for match in matches:
                    public_match = {
                        key: value for key, value in match.items() if not key.startswith("_")
                    }
                    occurrence_rows.append(
                        {
                            **base,
                            "candidate_bearing_sentence": candidate_bearing_sentence,
                            "occurrence_kind": occurrence_kind,
                            **public_match,
                        }
                    )

            unique_candidates = {item["node_id"]: item for item in candidates}
            unique_targets = {item["node_id"]: item for item in targets}
            for candidate in unique_candidates.values():
                existing = paper_candidates.get(candidate["node_id"])
                if existing is None:
                    paper_candidates[candidate["node_id"]] = candidate.copy()
                else:
                    tags = sorted(
                        set(str(existing.get("candidate_tag", "")).split("|"))
                        | set(str(candidate.get("candidate_tag", "")).split("|"))
                    )
                    existing["candidate_tag"] = "|".join(tag for tag in tags if tag)
                candidate_sentence_ids.setdefault(candidate["node_id"], set()).add(sentence_id)
            for target in unique_targets.values():
                paper_targets.setdefault(target["node_id"], target.copy())
                target_sentence_ids.setdefault(target["node_id"], set()).add(sentence_id)

            pair_count = len(unique_candidates) * len(unique_targets)
            if pair_count == 0:
                continue
            fractional_weight = 1.0 / pair_count

            for candidate in unique_candidates.values():
                for target in unique_targets.values():
                    event = {
                        **base,
                        "source": candidate["node_id"],
                        "source_label": candidate["label"],
                        "source_subtype": candidate["subtype"],
                        "candidate_tag": candidate.get("candidate_tag", ""),
                        "target": target["node_id"],
                        "target_label": target["label"],
                        "target_type": target["node_type"],
                        "target_subtype": target["subtype"],
                        "target_domain": target["domain"],
                        "fractional_weight": fractional_weight,
                    }
                    cooccurrence_rows.append(event)

                    relation = _best_relation(
                        candidate, target, cues, max_relation_distance=max_relation_distance
                    )
                    if relation is None:
                        continue
                    negated, modal = _relation_context_flags(
                        sentence, relation["cue_start"], relation["cue_end"]
                    )
                    confidence = (
                        "high"
                        if relation["cue_distance"] <= 80
                        or (relation["cue_between"] and relation["cue_distance"] <= 120)
                        else "medium"
                    )
                    relation_rows.append(
                        {
                            **event,
                            "relation": relation["relation"],
                            "relation_label": relation["relation_label"],
                            "base_polarity": relation["base_polarity"],
                            "cue": relation["cue"],
                            "cue_start": relation["cue_start"],
                            "cue_end": relation["cue_end"],
                            "cue_distance": relation["cue_distance"],
                            "cue_between": relation["cue_between"],
                            "negated": negated,
                            "modal": modal,
                            "confidence": confidence,
                            "evidence_scope": "same_sentence_rule",
                        }
                    )

        abstract_pair_count = len(paper_candidates) * len(paper_targets)
        if abstract_pair_count:
            abstract_fractional_weight = 1.0 / abstract_pair_count
            abstract_base = {
                "bibcode": row.bibcode,
                "year": int(row.year) if not pd.isna(row.year) else pd.NA,
                "arxiv_category": row.arxiv_category,
                "fractional_weight": abstract_fractional_weight,
                "evidence_scope": "same_abstract",
            }
            for candidate in paper_candidates.values():
                source_sentences = candidate_sentence_ids[candidate["node_id"]]
                for target in paper_targets.values():
                    target_sentences = target_sentence_ids[target["node_id"]]
                    same_sentence = bool(source_sentences & target_sentences)
                    minimum_sentence_distance = min(
                        abs(source_id - target_id)
                        for source_id in source_sentences
                        for target_id in target_sentences
                    )
                    abstract_cooccurrence_rows.append(
                        {
                            **abstract_base,
                            "source": candidate["node_id"],
                            "source_label": candidate["label"],
                            "source_subtype": candidate["subtype"],
                            "candidate_tag": candidate.get("candidate_tag", ""),
                            "target": target["node_id"],
                            "target_label": target["label"],
                            "target_type": target["node_type"],
                            "target_subtype": target["subtype"],
                            "target_domain": target["domain"],
                            "candidate_sentence_ids": "|".join(
                                map(str, sorted(source_sentences))
                            ),
                            "target_sentence_ids": "|".join(map(str, sorted(target_sentences))),
                            "same_sentence": same_sentence,
                            "minimum_sentence_distance": minimum_sentence_distance,
                        }
                    )

        if progress_every and paper_index % progress_every == 0:
            print(f"Processed {paper_index:,}/{len(papers):,} papers")

    occurrences = pd.DataFrame(occurrence_rows)
    cooccurrences = pd.DataFrame(cooccurrence_rows)
    abstract_cooccurrences = pd.DataFrame(abstract_cooccurrence_rows)
    relations = pd.DataFrame(relation_rows)
    return occurrences, cooccurrences, abstract_cooccurrences, relations
