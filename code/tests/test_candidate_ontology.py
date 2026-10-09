from __future__ import annotations

import sys
import unittest
from pathlib import Path


SCRIPTS_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS_DIR))

from dm_term_normalization.candidate_ontology import (  # noqa: E402
    candidate_species_labels,
    extract_dm_tags_with_spans,
    filter_candidate_tags,
)


class CandidateOntologyTests(unittest.TestCase):
    def test_canonical_candidate_mentions(self) -> None:
        tags, spans = extract_dm_tags_with_spans(
            "We compare WIMPs, primordial black holes, and axion-like particles as dark matter."
        )
        self.assertEqual(tags, ["wimp", "pbh", "axion", "alp"])
        self.assertEqual(len(tags), len(spans))
        self.assertEqual(
            candidate_species_labels(filter_candidate_tags(tags)),
            ["Generic WIMP", "PBH", "Axion + ALP"],
        )

    def test_ambiguous_abbreviation_requires_dark_matter_context(self) -> None:
        tags_without_context, _ = extract_dm_tags_with_spans(
            "The IDM algorithm improves the image reconstruction."
        )
        tags_with_context, _ = extract_dm_tags_with_spans(
            "The inert doublet model is considered as a dark matter candidate."
        )
        self.assertNotIn("inert_doublet_dm", tags_without_context)
        self.assertIn("inert_doublet_dm", tags_with_context)

    def test_alp_experiment_suffix_is_not_a_candidate(self) -> None:
        tags, _ = extract_dm_tags_with_spans("The ALP II experiment reports its calibration.")
        self.assertNotIn("alp", tags)

    def test_negated_wimp_phrase_is_not_a_wimp(self) -> None:
        tags, _ = extract_dm_tags_with_spans(
            "A dark glueball is a non-weakly interacting massive particle dark matter candidate."
        )
        self.assertNotIn("wimp", tags)

        abbreviated_tags, _ = extract_dm_tags_with_spans(
            "We study a non-WIMP dark matter candidate."
        )
        self.assertNotIn("wimp", abbreviated_tags)

    def test_next_to_lightest_phrase_is_not_an_lsp(self) -> None:
        tags, _ = extract_dm_tags_with_spans(
            "The next-to-lightest supersymmetric particle decays at the collider."
        )
        self.assertNotIn("lsp", tags)

        tags_with_lsp, _ = extract_dm_tags_with_spans(
            "The next-to-lightest supersymmetric particle decays to an LSP dark matter candidate."
        )
        self.assertIn("lsp", tags_with_lsp)

    def test_hyphenated_bino_and_wino_variants(self) -> None:
        tags, _ = extract_dm_tags_with_spans(
            "The dark matter candidate may be a b-ino-like or w-ino-like LSP."
        )
        self.assertIn("bino_dm", tags)
        self.assertIn("wino_dm", tags)

    def test_dark_glueball_allows_documented_extended_context(self) -> None:
        tags, _ = extract_dm_tags_with_spans(
            "The dark glueball from a hidden Yang-Mills sector is a simple non-weakly "
            "interacting massive particle dark matter candidate."
        )
        self.assertIn("glueball_dm", tags)

    def test_candidate_filter_and_species_collapse(self) -> None:
        tags = filter_candidate_tags(["axion", "alp", "higgs_portal_dm", "pbh"])
        self.assertEqual(tags, ["axion", "alp", "pbh"])
        self.assertEqual(candidate_species_labels(tags), ["Axion + ALP", "PBH"])


if __name__ == "__main__":
    unittest.main()
