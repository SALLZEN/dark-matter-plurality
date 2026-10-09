"""Audit-first dark-matter epistemic network construction."""

from .extraction import CandidateAdapter, extract_corpus
from .graph import build_outputs
from .wimp_role import build_wimp_role_outputs
from .ontology import (
    EntityMatcher,
    RelationMatcher,
    entity_ontology_paths,
    load_entity_ontology,
    load_relation_ontology,
)

__all__ = [
    "CandidateAdapter",
    "EntityMatcher",
    "RelationMatcher",
    "build_outputs",
    "build_wimp_role_outputs",
    "extract_corpus",
    "entity_ontology_paths",
    "load_entity_ontology",
    "load_relation_ontology",
]
