from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np
import pandas as pd


SCRIPTS_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS_DIR))

from robustness_analysis import (  # noqa: E402
    arxiv_id_from_bibcode,
    build_candidate_family_selection_sensitivity,
    cosine_distance,
    equal_paper_candidate_weights,
    fractional_class_weights,
    jensen_shannon_divergence,
    score_candidate_validation,
    total_variation_distance,
    wilson_interval,
)


class RobustnessAnalysisTests(unittest.TestCase):
    def test_fractional_weights_sum_to_one_per_paper(self) -> None:
        classes = pd.DataFrame(
            {
                "bibcode": ["a", "a", "a", "b"],
                "arxiv_class": ["astro-ph.CO", "astro-ph.GA", "hep-ph", "hep-ex"],
                "arxiv_category": [
                    "astrophysics",
                    "astrophysics",
                    "high-energy physics",
                    "high-energy physics",
                ],
            }
        )
        weighted = fractional_class_weights(classes)
        sums = weighted.groupby("bibcode")["field_weight"].sum()
        self.assertTrue(np.allclose(sums.to_numpy(), 1.0))
        self.assertTrue(
            np.isclose(
                weighted.query("bibcode == 'a' and arxiv_category == 'astrophysics'")["field_weight"].iloc[0],
                2 / 3,
            )
        )

    def test_distance_invariants(self) -> None:
        p = np.array([4, 1, 0], dtype=float)
        q = np.array([0, 1, 4], dtype=float)
        self.assertTrue(np.isclose(jensen_shannon_divergence(p, p), 0))
        self.assertTrue(np.isclose(total_variation_distance(p, p), 0))
        self.assertTrue(np.isclose(cosine_distance(p, p), 0))
        self.assertLessEqual(float(jensen_shannon_divergence(p, q)), 1)
        self.assertLessEqual(float(total_variation_distance(p, q)), 1)
        self.assertLessEqual(float(cosine_distance(p, q)), 1)

    def test_equal_paper_candidate_weights_sum_to_one(self) -> None:
        candidates = pd.DataFrame(
            {
                "bibcode": ["a", "a", "a", "b"],
                "year": [2020, 2020, 2020, 2020],
                "arxiv_category": ["astrophysics"] * 4,
                "SpeciesLabel": ["Axion + ALP", "PBH", "PBH", "Generic WIMP"],
            }
        )
        weighted = equal_paper_candidate_weights(candidates)
        sums = weighted.groupby("bibcode")["candidate_weight"].sum()
        self.assertTrue(np.allclose(sums.to_numpy(), 1.0))
        self.assertEqual(len(weighted), 3)

    def test_candidate_family_selection_sensitivity_uses_fieldwise_union(self) -> None:
        candidates = pd.DataFrame(
            [
                {"bibcode": "a1", "year": 1995, "arxiv_category": "astrophysics", "SpeciesLabel": "A"},
                {"bibcode": "a2", "year": 1995, "arxiv_category": "astrophysics", "SpeciesLabel": "B"},
                {"bibcode": "h1", "year": 1995, "arxiv_category": "high-energy physics", "SpeciesLabel": "B"},
                {"bibcode": "h2", "year": 1995, "arxiv_category": "high-energy physics", "SpeciesLabel": "C"},
                {"bibcode": "a3", "year": 2016, "arxiv_category": "astrophysics", "SpeciesLabel": "A"},
                {"bibcode": "a4", "year": 2016, "arxiv_category": "astrophysics", "SpeciesLabel": "B"},
                {"bibcode": "h3", "year": 2016, "arxiv_category": "high-energy physics", "SpeciesLabel": "B"},
                {"bibcode": "h4", "year": 2016, "arxiv_category": "high-energy physics", "SpeciesLabel": "C"},
            ]
        )
        result = build_candidate_family_selection_sensitivity(candidates, top_k_values=(1, 2))
        top_one = result[result["top_k_per_field"].eq(1)].iloc[0]
        all_families = result[result["selection"].eq("all observed ontology families")].iloc[0]
        self.assertEqual(int(top_one["n_unique_families"]), 2)
        self.assertEqual(set(str(top_one["selected_families"]).split(";")), {"A", "B"})
        self.assertEqual(int(all_families["n_unique_families"]), 3)

    def test_wilson_interval_contains_observed_fraction(self) -> None:
        low, high = wilson_interval(90, 100)
        self.assertLess(low, 0.9)
        self.assertGreater(high, 0.9)

    def test_arxiv_identifier_from_bibcode(self) -> None:
        self.assertEqual(arxiv_id_from_bibcode("2010arXiv1001.0061R"), "1001.0061")
        self.assertIsNone(arxiv_id_from_bibcode("2015CoPhC.192..322B"))

    def test_candidate_validation_scores_holdouts_separately(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            validation_dir = Path(directory)
            key = pd.DataFrame(
                [
                    {"sample_id": "p1", "bibcode": "p1", "split": "holdout-positive", "target_family": "Axion + ALP", "system_any_candidate": True, "system_candidates": "Axion + ALP"},
                    {"sample_id": "p2", "bibcode": "p2", "split": "holdout-positive", "target_family": "Generic WIMP", "system_any_candidate": True, "system_candidates": "Generic WIMP"},
                    {"sample_id": "r1", "bibcode": "r1", "split": "holdout-population", "target_family": "population sample", "system_any_candidate": True, "system_candidates": "Axion + ALP"},
                    {"sample_id": "r2", "bibcode": "r2", "split": "holdout-population", "target_family": "population sample", "system_any_candidate": False, "system_candidates": ""},
                    {"sample_id": "r3", "bibcode": "r3", "split": "holdout-population", "target_family": "population sample", "system_any_candidate": True, "system_candidates": "Generic WIMP"},
                    {"sample_id": "r4", "bibcode": "r4", "split": "holdout-population", "target_family": "population sample", "system_any_candidate": False, "system_candidates": ""},
                ]
            )
            key.to_csv(validation_dir / "candidate_validation_system_key.csv", index=False)

            def annotations(rows: list[tuple[str, str, str, str, str, str]]) -> pd.DataFrame:
                return pd.DataFrame(
                    [
                        {
                            "sample_id": sample_id,
                            "bibcode": bibcode,
                            "year": 2020,
                            "field": field,
                            "period": period,
                            "abstract": "test",
                            "gold_any_candidate": any_candidate,
                            "gold_candidates": candidates,
                            "notes": "",
                        }
                        for sample_id, bibcode, field, any_candidate, candidates, period in rows
                    ]
                )

            annotations(
                [
                    ("p1", "p1", "astrophysics", "yes", "Axion + ALP", "2015-2025"),
                    ("p2", "p2", "high-energy physics", "no", "", "2015-2025"),
                ]
            ).to_csv(validation_dir / "candidate_validation_holdout_positive.csv", index=False)
            annotations(
                [
                    ("r1", "r1", "astrophysics", "yes", "Axion + ALP", "2015-2025"),
                    ("r2", "r2", "astrophysics", "yes", "PBH", "2015-2025"),
                    ("r3", "r3", "high-energy physics", "yes", "Generic WIMP", "2005-2014"),
                    ("r4", "r4", "high-energy physics", "no", "", "2005-2014"),
                ]
            ).to_csv(validation_dir / "candidate_validation_holdout_population.csv", index=False)

            result = score_candidate_validation(validation_dir)
            self.assertEqual(set(result["component"]), {"system-positive holdout", "population holdout"})
            population = result[result["component"].eq("population holdout")].iloc[0]
            self.assertAlmostEqual(float(population["micro_recall"]), 2 / 3)
            self.assertAlmostEqual(float(population["abstract_false_negative_rate"]), 1 / 3)
            breakdown = pd.read_csv(
                validation_dir / "candidate_validation_field_period_performance.csv"
            )
            self.assertIn("field-period", set(breakdown["breakdown"]))


if __name__ == "__main__":
    unittest.main()
