from __future__ import annotations

import csv
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPTS_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS_DIR))

from candidate_validation_app import CANDIDATE_FAMILIES, DATASETS, ValidationStore  # noqa: E402


class CandidateValidationAppTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.validation_dir = Path(self.temporary.name)
        self.fieldnames = [
            "sample_id", "bibcode", "year", "field", "period", "abstract",
            "gold_any_candidate", "gold_candidates", "notes",
        ]
        for key, config in DATASETS.items():
            with (self.validation_dir / config["filename"]).open(
                "w", encoding="utf-8", newline=""
            ) as handle:
                writer = csv.DictWriter(handle, fieldnames=self.fieldnames)
                writer.writeheader()
                writer.writerow(
                    {
                        "sample_id": f"{key}-1",
                        "bibcode": f"bib-{key}",
                        "year": "2020",
                        "field": "astrophysics",
                        "period": "2015-2025",
                        "abstract": "An axion may constitute dark matter.",
                        "gold_any_candidate": "",
                        "gold_candidates": "",
                        "notes": "",
                    }
                )
        self.store = ValidationStore(self.validation_dir)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def test_status_and_atomic_annotation_save(self) -> None:
        initial = self.store.status()
        self.assertTrue(self.store.session_backup_dir.is_dir())
        self.assertEqual([item["completed"] for item in initial["datasets"]], [0, 0, 0])

        result = self.store.save_annotation(
            "development",
            "development-1",
            "yes",
            ["PBH", "Axion + ALP"],
            "clear context",
        )
        self.assertEqual(result["completed"], 1)
        self.assertEqual(result["record"]["gold_candidates"], "Axion + ALP;PBH")
        self.assertTrue(
            (self.validation_dir / "candidate_validation_development.csv.bak").is_file()
        )

    def test_no_answer_clears_candidate_families(self) -> None:
        result = self.store.save_annotation(
            "holdout_positive",
            "holdout_positive-1",
            "no",
            ["Axion + ALP"],
            "not a candidate use",
        )
        self.assertEqual(result["record"]["gold_candidates"], "")

    def test_unknown_family_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            self.store.save_annotation(
                "holdout_population",
                "holdout_population-1",
                "yes",
                ["Not in ontology"],
                "",
            )

    def test_candidate_choices_come_from_public_ontology(self) -> None:
        self.assertIn("Generic WIMP", CANDIDATE_FAMILIES)
        self.assertIn("Axion + ALP", CANDIDATE_FAMILIES)


if __name__ == "__main__":
    unittest.main()
