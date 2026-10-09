from __future__ import annotations

import math
import sys
import unittest
from pathlib import Path

import pandas as pd


PROJECT_DIR = Path(__file__).resolve().parents[1]
WORKSPACE_DIR = PROJECT_DIR.parent
sys.path.insert(0, str(PROJECT_DIR))

from dm_network.extraction import CandidateAdapter, extract_corpus, sentence_spans
from dm_network.graph import build_outputs
from dm_network.ontology import (
    EntityMatcher,
    RelationMatcher,
    load_entity_ontology,
    load_relation_ontology,
)


class PipelineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.entities = load_entity_ontology(PROJECT_DIR / "config" / "entity_catalog.json")
        cls.relations = load_relation_ontology(PROJECT_DIR / "config" / "relations.json")
        cls.entity_matcher = EntityMatcher(cls.entities)
        cls.relation_matcher = RelationMatcher(cls.relations)
        cls.candidate_adapter = CandidateAdapter(
            WORKSPACE_DIR / "code"
        )

    def test_substring_false_positives_are_blocked(self) -> None:
        text = "The flux calculation uses lepton groups and a technical prescription."
        ids = {match["node_id"] for match in self.entity_matcher.find(text)}
        self.assertNotIn("apparatus:lux", ids)
        self.assertNotIn("apparatus:lep", ids)

    def test_case_sensitive_acronyms_and_full_names_match(self) -> None:
        text = "LUX and the Large Electron-Positron Collider constrain the model."
        ids = {match["node_id"] for match in self.entity_matcher.find(text)}
        self.assertIn("apparatus:lux", ids)
        self.assertIn("apparatus:lep", ids)

    def test_requested_vertex_classes_are_exhaustive_and_context_is_absent(self) -> None:
        self.assertEqual(
            {entity.node_type for entity in self.entities},
            {"theory", "phenomenon", "problem", "method", "apparatus", "mechanism"},
        )
        self.assertFalse(any(entity.id.startswith("context:") for entity in self.entities))

    def test_susy_modified_gravity_and_inflation_families_resolve_separately(self) -> None:
        text = (
            "We compare MSSM, NMSSM, split supersymmetry, TeVeS, f(R) gravity, "
            "Horndeski theory, slow-roll inflation, and Starobinsky inflation."
        )
        ids = {match["node_id"] for match in self.entity_matcher.find(text)}
        expected = {
            "theory:mssm",
            "theory:nmssm",
            "theory:split_supersymmetry",
            "theory:teves",
            "theory:f_r_gravity",
            "theory:horndeski",
            "theory:slow_roll_inflation",
            "theory:starobinsky_inflation",
        }
        self.assertTrue(expected.issubset(ids), expected - ids)

    def test_coverage_audit_entities_resolve_across_all_six_layers(self) -> None:
        text = (
            "The CMSSM predicts a nuclear recoil above the neutrino fog through "
            "kinetic mixing; nested sampling compares ATLAS and LISA results."
        )
        ids = {match["node_id"] for match in self.entity_matcher.find(text)}
        expected = {
            "theory:cmssm",
            "phenomenon:nuclear_recoil",
            "problem:neutrino_floor",
            "mechanism:kinetic_mixing",
            "method:nested_sampling",
            "apparatus:atlas",
            "apparatus:lisa",
        }
        self.assertTrue(expected.issubset(ids), expected - ids)

    def test_new_lexical_apparatus_names_require_case_or_qualification(self) -> None:
        ordinary = "The atlas has gaps, while a genius studies a warp in the model."
        ordinary_ids = {match["node_id"] for match in self.entity_matcher.find(ordinary)}
        self.assertFalse(
            {
                "apparatus:atlas",
                "apparatus:gaps",
                "apparatus:genius",
                "apparatus:warp",
            }
            & ordinary_ids
        )
        scientific = "ATLAS, GAPS, GENIUS, and WARP constrain dark matter."
        scientific_ids = {
            match["node_id"] for match in self.entity_matcher.find(scientific)
        }
        self.assertTrue(
            {
                "apparatus:atlas",
                "apparatus:gaps",
                "apparatus:genius",
                "apparatus:warp",
            }.issubset(scientific_ids)
        )

    def test_cmb_facility_alias_survives_shared_text_normalization(self) -> None:
        normalized = self.candidate_adapter.normalize_sentence(
            "CMB-S4 can constrain axion dark matter."
        )
        ids = {match["node_id"] for match in self.entity_matcher.find(normalized)}
        self.assertIn("apparatus:cmb_s4", ids)

    def test_early_universe_residual_gaps_resolve_separately(self) -> None:
        text = (
            "Higgs inflation is followed by reheating, while leptogenesis and "
            "dark-visible cogenesis generate asymmetries during an early "
            "matter-dominated era."
        )
        ids = {match["node_id"] for match in self.entity_matcher.find(text)}
        expected = {
            "theory:higgs_inflation",
            "mechanism:reheating",
            "mechanism:leptogenesis",
            "mechanism:dark_visible_cogenesis",
            "phenomenon:early_matter_dominated_era",
        }
        self.assertTrue(expected.issubset(ids), expected - ids)

    def test_gravitational_phenomena_replace_stellar_object_contexts(self) -> None:
        text = (
            "Strong gravitational lensing, frame dragging, gravitational waves, "
            "rotation curves, the Sachs-Wolfe effect, and halo substructure are compared."
        )
        ids = {match["node_id"] for match in self.entity_matcher.find(text)}
        expected = {
            "phenomenon:strong_lensing",
            "phenomenon:frame_dragging",
            "phenomenon:gravitational_waves",
            "phenomenon:rotation_curves",
            "phenomenon:sachs_wolfe_effect",
            "phenomenon:halo_substructure",
        }
        self.assertTrue(expected.issubset(ids), expected - ids)

    def test_candidate_embedded_entity_does_not_create_tautological_edge(self) -> None:
        papers = pd.DataFrame(
            [
                {
                    "bibcode": "PBH",
                    "year": 2020,
                    "arxiv_category": "astrophysics",
                    "abstract": "Primordial black holes are dark matter candidates.",
                }
            ]
        )
        occurrences, sentence_events, abstract_events, _ = extract_corpus(
            papers,
            self.candidate_adapter,
            self.entity_matcher,
            self.relation_matcher,
            progress_every=0,
        )
        self.assertNotIn("phenomenon:black_holes", set(occurrences["node_id"]))
        self.assertTrue(sentence_events.empty)
        self.assertTrue(abstract_events.empty)

    def test_repeated_candidate_mentions_do_not_leak_embedded_entities(self) -> None:
        papers = pd.DataFrame(
            [
                {
                    "bibcode": "PBH2",
                    "year": 2021,
                    "arxiv_category": "astrophysics",
                    "abstract": (
                        "Primordial black holes may cluster, while primordial black holes "
                        "may also evaporate."
                    ),
                }
            ]
        )
        occurrences, sentence_events, abstract_events, _ = extract_corpus(
            papers,
            self.candidate_adapter,
            self.entity_matcher,
            self.relation_matcher,
            progress_every=0,
        )
        self.assertNotIn("phenomenon:black_holes", set(occurrences["node_id"]))
        self.assertTrue(sentence_events.empty)
        self.assertTrue(abstract_events.empty)

    def test_ambiguous_telescope_words_are_not_standalone_entities(self) -> None:
        text = "A fast calculation estimates heat transport and the Planck mass."
        ids = {match["node_id"] for match in self.entity_matcher.find(text)}
        self.assertNotIn("apparatus:planck", ids)
        text_with_context = "We use Planck data to constrain the relic abundance."
        ids_with_context = {
            match["node_id"] for match in self.entity_matcher.find(text_with_context)
        }
        self.assertIn("apparatus:planck", ids_with_context)

    def test_candidate_tag_span_pairing_survives_non_candidate_first(self) -> None:
        sentence = self.candidate_adapter.normalize_sentence(
            "The Higgs portal is compared with WIMPs as a dark matter candidate."
        )
        candidates = self.candidate_adapter.find_in_normalized(sentence)
        wimp = next(item for item in candidates if item["candidate_tag"] == "wimp")
        self.assertIn("massive particle", wimp["matched_text"].casefold())
        self.assertNotIn("higgs", wimp["matched_text"].casefold())

    def test_idm_case_resolves_inelastic_vs_inert_doublet(self) -> None:
        all_adapter = CandidateAdapter(
            WORKSPACE_DIR / "code",
            dm_scope="all",
        )
        inelastic_sentence = all_adapter.normalize_sentence(
            "We study iDM as an inelastic dark matter scenario."
        )
        inert_sentence = all_adapter.normalize_sentence(
            "We study IDM as an inert doublet model dark matter candidate."
        )
        inelastic_tags = {
            row["candidate_tag"] for row in all_adapter.find_in_normalized(inelastic_sentence)
        }
        inert_tags = {row["candidate_tag"] for row in all_adapter.find_in_normalized(inert_sentence)}
        self.assertIn("inelastic_dm", inelastic_tags)
        self.assertNotIn("inert_doublet_dm", inelastic_tags)
        self.assertIn("inert_doublet_dm", inert_tags)
        self.assertNotIn("inelastic_dm", inert_tags)

    def test_sentence_splitter_does_not_split_decimal_or_common_abbreviation(self) -> None:
        text = "We find a 3.5 keV line, e.g. in clusters. WIMPs do not explain it."
        sentences = sentence_spans(text)
        self.assertEqual(len(sentences), 2)

    def test_relation_requires_candidate_entity_and_cue(self) -> None:
        papers = pd.DataFrame(
            [
                {
                    "bibcode": "A",
                    "year": 2000,
                    "arxiv_category": "astrophysics",
                    "abstract": "WIMPs explain flat galaxy rotation curves.",
                },
                {
                    "bibcode": "B",
                    "year": 2001,
                    "arxiv_category": "high-energy physics",
                    "abstract": "WIMPs and flat galaxy rotation curves are discussed.",
                },
            ]
        )
        occurrences, cooccurrences, abstract_cooccurrences, relations = extract_corpus(
            papers,
            self.candidate_adapter,
            self.entity_matcher,
            self.relation_matcher,
            progress_every=0,
        )
        self.assertEqual(len(cooccurrences), 2)
        self.assertEqual(len(abstract_cooccurrences), 2)
        self.assertEqual(len(relations), 1)
        self.assertEqual(relations.iloc[0]["relation"], "explanation_claim")
        self.assertEqual(relations.iloc[0]["confidence"], "high")
        outputs = build_outputs(
            occurrences,
            cooccurrences,
            abstract_cooccurrences,
            relations,
            population_papers=2,
            min_edge_papers=1,
            min_relation_papers=1,
        )
        self.assertEqual(int(outputs["edges_cooccurrence"].iloc[0]["paper_count"]), 2)
        self.assertAlmostEqual(
            float(outputs["edges_cooccurrence"].iloc[0]["Weight"]),
            float(outputs["edges_cooccurrence"].iloc[0]["fractional_weight"]),
        )
        self.assertEqual(
            int(outputs["edges_abstract_cooccurrence"].iloc[0]["paper_count"]), 2
        )
        self.assertAlmostEqual(
            float(outputs["edges_abstract_cooccurrence"].iloc[0]["Weight"]),
            float(outputs["edges_abstract_cooccurrence"].iloc[0]["fractional_weight"]),
        )
        self.assertEqual(int(outputs["edges_relations"].iloc[0]["paper_count"]), 1)
        self.assertEqual(float(outputs["edges_relations"].iloc[0]["Weight"]), 1.0)
        wimp_node = outputs["nodes"].loc[
            outputs["nodes"]["Label"] == "Generic WIMP"
        ].iloc[0]
        self.assertAlmostEqual(
            float(wimp_node["weighted_degree_log1p"]),
            math.log1p(float(wimp_node["weighted_degree"])),
        )

    def test_abstract_scope_retains_cross_sentence_association(self) -> None:
        papers = pd.DataFrame(
            [
                {
                    "bibcode": "D",
                    "year": 2003,
                    "arxiv_category": "astrophysics",
                    "abstract": (
                        "We investigate WIMPs as dark matter candidates. "
                        "Galaxy rotation curves motivate the analysis."
                    ),
                }
            ]
        )
        occurrences, sentence_events, abstract_events, relations = extract_corpus(
            papers,
            self.candidate_adapter,
            self.entity_matcher,
            self.relation_matcher,
            progress_every=0,
        )
        self.assertEqual(len(sentence_events), 0)
        self.assertEqual(len(abstract_events), 1)
        self.assertFalse(bool(abstract_events.iloc[0]["same_sentence"]))
        self.assertEqual(int(abstract_events.iloc[0]["minimum_sentence_distance"]), 1)
        self.assertIn("phenomenon:rotation_curves", set(occurrences["node_id"]))
        outputs = build_outputs(
            occurrences,
            sentence_events,
            abstract_events,
            relations,
            population_papers=1,
            min_edge_papers=1,
            min_relation_papers=1,
        )
        self.assertTrue(outputs["edges_cooccurrence"].empty)
        abstract_edge = outputs["edges_abstract_cooccurrence"].iloc[0]
        self.assertEqual(int(abstract_edge["paper_count"]), 1)
        self.assertEqual(int(abstract_edge["cross_sentence_only_paper_count"]), 1)
        self.assertIn(abstract_edge["Target"], set(outputs["nodes"]["Id"]))

    def test_negation_is_preserved(self) -> None:
        papers = pd.DataFrame(
            [
                {
                    "bibcode": "C",
                    "year": 2002,
                    "arxiv_category": "astrophysics",
                    "abstract": "WIMPs do not explain flat galaxy rotation curves.",
                }
            ]
        )
        _, _, _, relations = extract_corpus(
            papers,
            self.candidate_adapter,
            self.entity_matcher,
            self.relation_matcher,
            progress_every=0,
        )
        self.assertEqual(len(relations), 1)
        self.assertTrue(bool(relations.iloc[0]["negated"]))


if __name__ == "__main__":
    unittest.main()
