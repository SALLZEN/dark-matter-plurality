from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable


ALNUM_LEFT = r"(?<![A-Za-z0-9])"
ALNUM_RIGHT = r"(?![A-Za-z0-9])"
ALLOWED_ENTITY_NODE_TYPES = {
    "theory",
    "phenomenon",
    "problem",
    "method",
    "apparatus",
    "mechanism",
}


@dataclass(frozen=True)
class Entity:
    id: str
    label: str
    node_type: str
    subtype: str
    domain: str
    aliases: tuple[dict[str, Any], ...]
    ontology_source: str
    exclude_with_candidates: tuple[str, ...]


@dataclass(frozen=True)
class Relation:
    id: str
    label: str
    base_polarity: str
    allowed_target_types: tuple[str, ...]
    patterns: tuple[str, ...]


def _read_json(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def _literal_pattern(text: str) -> str:
    escaped = re.escape(text.strip())
    escaped = escaped.replace(r"\ ", r"\s+")
    return f"{ALNUM_LEFT}{escaped}{ALNUM_RIGHT}"


def entity_ontology_paths(path: str | Path) -> list[Path]:
    """Return every file contributing to an ontology catalog."""
    root = Path(path).resolve()
    collected: list[Path] = []
    active: set[Path] = set()

    def visit(current: Path) -> None:
        current = current.resolve()
        if current in active:
            raise ValueError(f"Circular entity-ontology include: {current}")
        if current in collected:
            return
        active.add(current)
        payload = _read_json(current)
        collected.append(current)
        for include in payload.get("includes", []):
            include_path = include if isinstance(include, str) else include["path"]
            visit(current.parent / str(include_path))
        active.remove(current)

    visit(root)
    return collected


def _entity_rows(
    path: Path,
    excluded_types: set[str] | None = None,
    active: set[Path] | None = None,
) -> list[tuple[dict[str, Any], Path]]:
    path = path.resolve()
    active = set(active or ())
    if path in active:
        raise ValueError(f"Circular entity-ontology include: {path}")
    active.add(path)
    payload = _read_json(path)
    excluded_types = set(excluded_types or ())
    rows: list[tuple[dict[str, Any], Path]] = [
        (row, path)
        for row in payload.get("entities", [])
        if str(row.get("node_type", "")) not in excluded_types
    ]
    for include in payload.get("includes", []):
        if isinstance(include, str):
            include_path = include
            include_excluded: set[str] = set()
        else:
            include_path = str(include["path"])
            include_excluded = set(map(str, include.get("exclude_node_types", [])))
        rows.extend(_entity_rows(path.parent / include_path, include_excluded, active))
    return rows


def load_entity_ontology(path: str | Path) -> list[Entity]:
    entities = [
        Entity(
            id=str(row["id"]),
            label=str(row["label"]),
            node_type=str(row["node_type"]),
            subtype=str(row.get("subtype", "")),
            domain=str(row.get("domain", "")),
            aliases=tuple(row.get("aliases", [])),
            ontology_source=source.name,
            exclude_with_candidates=tuple(row.get("exclude_with_candidates", [])),
        )
        for row, source in _entity_rows(Path(path))
    ]
    validate_entities(entities)
    return entities


def load_relation_ontology(path: str | Path) -> list[Relation]:
    payload = _read_json(Path(path))
    relations = [
        Relation(
            id=str(row["id"]),
            label=str(row["label"]),
            base_polarity=str(row.get("base_polarity", "neutral")),
            allowed_target_types=tuple(row.get("allowed_target_types", [])),
            patterns=tuple(row.get("patterns", [])),
        )
        for row in payload.get("relations", [])
    ]
    validate_relations(relations)
    return relations


def validate_entities(entities: Iterable[Entity]) -> None:
    entities = list(entities)
    ids = [entity.id for entity in entities]
    duplicate_ids = sorted({value for value in ids if ids.count(value) > 1})
    if duplicate_ids:
        raise ValueError(f"Duplicate entity IDs: {duplicate_ids}")

    if not entities:
        raise ValueError("Entity ontology is empty")

    seen_aliases: dict[tuple[str, bool], str] = {}
    for entity in entities:
        if entity.node_type not in ALLOWED_ENTITY_NODE_TYPES:
            raise ValueError(
                f"Unsupported entity node type {entity.node_type!r}: {entity.id}"
            )
        expected_prefix = f"{entity.node_type}:"
        if not entity.id.startswith(expected_prefix):
            raise ValueError(
                f"Entity ID must begin with {expected_prefix!r}: {entity.id}"
            )
        if not entity.aliases:
            raise ValueError(f"Entity has no aliases: {entity.id}")
        invalid_candidate_ids = [
            value
            for value in entity.exclude_with_candidates
            if not value.startswith("dm_model:")
        ]
        if invalid_candidate_ids:
            raise ValueError(
                f"Entity exclusions must use dm_model IDs: {entity.id} {invalid_candidate_ids}"
            )
        for alias in entity.aliases:
            if ("text" in alias) == ("regex" in alias):
                raise ValueError(
                    f"Alias must contain exactly one of text or regex: {entity.id} {alias}"
                )
            case_sensitive = bool(alias.get("case_sensitive", False))
            if "text" in alias:
                text = str(alias["text"]).strip()
                if len(text) <= 3 and not case_sensitive:
                    raise ValueError(
                        f"Short literal aliases must be case-sensitive: {entity.id} {text!r}"
                    )
                key_text = text if case_sensitive else text.casefold()
                key = (key_text, case_sensitive)
                owner = seen_aliases.get(key)
                if owner and owner != entity.id:
                    raise ValueError(
                        f"Alias {text!r} is shared by {owner} and {entity.id}"
                    )
                seen_aliases[key] = entity.id
                pattern = _literal_pattern(text)
            else:
                pattern = str(alias["regex"])
            re.compile(pattern, 0 if case_sensitive else re.IGNORECASE)


def validate_relations(relations: Iterable[Relation]) -> None:
    relations = list(relations)
    ids = [relation.id for relation in relations]
    duplicate_ids = sorted({value for value in ids if ids.count(value) > 1})
    if duplicate_ids:
        raise ValueError(f"Duplicate relation IDs: {duplicate_ids}")
    if not relations:
        raise ValueError("Relation ontology is empty")
    for relation in relations:
        invalid_types = sorted(
            set(relation.allowed_target_types) - ALLOWED_ENTITY_NODE_TYPES
        )
        if invalid_types:
            raise ValueError(
                f"Relation {relation.id} has unsupported target types: {invalid_types}"
            )
        if not relation.allowed_target_types:
            raise ValueError(f"Relation has no allowed target types: {relation.id}")
        if not relation.patterns:
            raise ValueError(f"Relation has no patterns: {relation.id}")
        for pattern in relation.patterns:
            re.compile(pattern, re.IGNORECASE)


class EntityMatcher:
    """Boundary-safe matcher that resolves overlapping aliases longest-first."""

    def __init__(self, entities: Iterable[Entity]):
        self.entities = list(entities)
        self.by_id = {entity.id: entity for entity in self.entities}
        self._patterns: list[tuple[Entity, str, re.Pattern[str]]] = []
        for entity in self.entities:
            for alias in entity.aliases:
                case_sensitive = bool(alias.get("case_sensitive", False))
                pattern_text = (
                    _literal_pattern(str(alias["text"]))
                    if "text" in alias
                    else str(alias["regex"])
                )
                label = str(alias.get("text", alias.get("regex", "")))
                flags = 0 if case_sensitive else re.IGNORECASE
                self._patterns.append((entity, label, re.compile(pattern_text, flags)))

    def find(self, text: str) -> list[dict[str, Any]]:
        if not isinstance(text, str) or not text:
            return []
        candidates: list[dict[str, Any]] = []
        for entity, alias, pattern in self._patterns:
            for match in pattern.finditer(text):
                candidates.append(
                    {
                        "node_id": entity.id,
                        "label": entity.label,
                        "node_type": entity.node_type,
                        "subtype": entity.subtype,
                        "domain": entity.domain,
                        "ontology_source": entity.ontology_source,
                        "_exclude_with_candidates": entity.exclude_with_candidates,
                        "start": match.start(),
                        "end": match.end(),
                        "matched_text": match.group(0),
                        "matched_alias": alias,
                    }
                )

        # Prefer the longest match at a given position and suppress nested aliases.
        candidates.sort(key=lambda row: (row["start"], -(row["end"] - row["start"]), row["node_id"]))
        retained: list[dict[str, Any]] = []
        for candidate in candidates:
            overlaps = any(
                candidate["start"] < prior["end"] and prior["start"] < candidate["end"]
                for prior in retained
            )
            if not overlaps:
                retained.append(candidate)
        return retained


class RelationMatcher:
    def __init__(self, relations: Iterable[Relation]):
        self.relations = list(relations)
        self._patterns = [
            (relation, re.compile(pattern, re.IGNORECASE))
            for relation in self.relations
            for pattern in relation.patterns
        ]

    def find(self, text: str) -> list[dict[str, Any]]:
        if not isinstance(text, str) or not text:
            return []
        found: list[dict[str, Any]] = []
        for relation, pattern in self._patterns:
            for match in pattern.finditer(text):
                found.append(
                    {
                        "relation": relation.id,
                        "relation_label": relation.label,
                        "base_polarity": relation.base_polarity,
                        "allowed_target_types": relation.allowed_target_types,
                        "cue": match.group(0),
                        "cue_start": match.start(),
                        "cue_end": match.end(),
                    }
                )
        found.sort(key=lambda row: (row["cue_start"], row["cue_end"], row["relation"]))
        return found
