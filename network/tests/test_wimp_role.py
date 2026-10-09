from __future__ import annotations

import math
import sys
import unittest
from pathlib import Path

import networkx as nx
import pandas as pd


PROJECT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_DIR))

from dm_network.wimp_role import (
    ASTRO,
    HEP,
    Window,
    WimpDefinition,
    aggregate_importance_edges,
    aggregate_brokerage_edges,
    apply_wimp_definition_to_candidates,
    build_brokerage_nodes_and_metrics,
    build_common_endpoint_sensitivity,
    bootstrap_wimp_prominence,
    build_importance_nodes,
    build_prominence_graph,
    build_prominence_metrics,
    cross_field_efficiency,
    gephi_brokerage_tables,
    gephi_importance_tables,
    validate_node_edge_tables,
)


class WimpRoleTests(unittest.TestCase):
    def setUp(self) -> None:
        self.definition = WimpDefinition(
            name="published_umbrella",
            label="WIMP-related",
            node_id="dm_model:wimp_related",
            collapse_tags=frozenset(
                {"wimp", "neutralino", "lsp", "higgsino_dm", "gravitino_dm", "sneutrino_dm"}
            ),
        )
        self.window = Window("full", "1995-2025", 1995, 2025)
        self.gephi = {
            "node_size_range": [8.0, 40.0],
            "label_size_range": [8.0, 24.0],
            "share_ratio_clip_log10": 1.0,
        }
        self.paper_table = pd.DataFrame(
            [
                {"bibcode": "a", "year": 2000, "primary_field": ASTRO, "crosslisted_astrophysics_hep": True},
                {"bibcode": "b", "year": 2000, "primary_field": HEP, "crosslisted_astrophysics_hep": True},
                {"bibcode": "c", "year": 2000, "primary_field": ASTRO, "crosslisted_astrophysics_hep": False},
                {"bibcode": "d", "year": 2000, "primary_field": HEP, "crosslisted_astrophysics_hep": False},
            ]
        )
        self.raw_candidates = pd.DataFrame(
            [
                {"bibcode": "a", "year": 2000, "primary_field": ASTRO, "candidate_tag": "wimp", "candidate_id": "dm_model:generic_wimp", "candidate_label": "Generic WIMP"},
                {"bibcode": "a", "year": 2000, "primary_field": ASTRO, "candidate_tag": "neutralino", "candidate_id": "dm_model:neutralino", "candidate_label": "Neutralino"},
                {"bibcode": "b", "year": 2000, "primary_field": HEP, "candidate_tag": "wimp", "candidate_id": "dm_model:generic_wimp", "candidate_label": "Generic WIMP"},
                {"bibcode": "c", "year": 2000, "primary_field": ASTRO, "candidate_tag": "axion", "candidate_id": "dm_model:axion_alp", "candidate_label": "Axion + ALP"},
                {"bibcode": "d", "year": 2000, "primary_field": HEP, "candidate_tag": "neutralino", "candidate_id": "dm_model:neutralino", "candidate_label": "Neutralino"},
            ]
        )

    def test_wimp_umbrella_collapses_at_paper_level(self) -> None:
        collapsed = apply_wimp_definition_to_candidates(self.raw_candidates, self.definition)
        wimp = collapsed[collapsed["candidate_id"].eq(self.definition.node_id)]
        self.assertEqual(set(wimp["bibcode"]), {"a", "b", "d"})
        self.assertEqual(len(wimp), 3)

    def test_cross_field_efficiency_is_order_invariant(self) -> None:
        graph = nx.Graph()
        graph.add_edge("astro-a", "middle", distance=0.1)
        graph.add_edge("astro-b", "middle", distance=0.2)
        graph.add_edge("middle", "hep-a", distance=0.3)
        graph.add_edge("middle", "hep-b", distance=0.4)
        forward = cross_field_efficiency(
            graph, ["astro-a", "astro-b"], ["hep-a", "hep-b"]
        )
        reversed_order = cross_field_efficiency(
            graph, ["astro-b", "astro-a"], ["hep-b", "hep-a"]
        )
        self.assertEqual(forward, reversed_order)

    def test_prominence_uses_field_denominators_and_smoothed_ratio(self) -> None:
        metrics, _ = build_prominence_metrics(
            self.paper_table,
            self.raw_candidates,
            [self.definition],
            [self.window],
            [ASTRO, HEP],
        )
        wimp = metrics[metrics["candidate_id"].eq(self.definition.node_id)]
        astro = wimp[wimp["field"].eq(ASTRO)].iloc[0]
        hep = wimp[wimp["field"].eq(HEP)].iloc[0]
        self.assertEqual(int(astro["candidate_paper_count"]), 1)
        self.assertEqual(int(hep["candidate_paper_count"]), 2)
        self.assertAlmostEqual(float(astro["candidate_prevalence_all_dm"]), 0.5)
        expected = math.log2(((2 + 0.5) / (2 + 1)) / ((1 + 0.5) / (2 + 1)))
        self.assertAlmostEqual(float(astro["log2_hep_astro_prevalence_ratio"]), expected)
        expected_participation = 2 * (1 - ((0.5 / 1.5) ** 2 + (1.0 / 1.5) ** 2))
        self.assertAlmostEqual(float(astro["field_participation"]), expected_participation)
        self.assertAlmostEqual(float(astro["mean_field_candidate_share"]), 0.75)
        expected_share_ratio = math.log10(((1 + 0.5) / (2 + 1)) / ((2 + 0.5) / (2 + 1)))
        self.assertAlmostEqual(float(astro["log10_astro_hep_share_ratio"]), expected_share_ratio)
        nodes, edges, gephi_nodes, gephi_edges = build_prominence_graph(
            metrics, self.definition, self.window, self.gephi
        )
        validate_node_edge_tables(nodes, edges, "prominence")
        validate_node_edge_tables(gephi_nodes, gephi_edges, "prominence gephi")
        self.assertNotIn("all_dm_papers", gephi_edges.columns)
        self.assertIn("astro_orientation_0_1", gephi_nodes.columns)
        self.assertIn("node_size_sqrt_mean_field_share", gephi_nodes.columns)
        bootstrap = bootstrap_wimp_prominence(
            self.paper_table, self.raw_candidates, [self.definition], [self.window],
            [ASTRO, HEP], iterations=100, seed=7, confidence_level=0.95,
        )
        self.assertEqual(len(bootstrap), 2)
        self.assertTrue(
            (bootstrap["candidate_prevalence_all_dm_low"]
             <= bootstrap["candidate_prevalence_all_dm_high"]).all()
        )

    def _importance_fixture(self) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
        events = pd.DataFrame(
            [
                {"bibcode": "a", "year": 2000, "arxiv_category": ASTRO, "candidate_tag": "wimp", "source": "dm_model:generic_wimp", "source_label": "Generic WIMP", "target": "phenomenon:rotation", "target_label": "Rotation curves", "target_type": "phenomenon", "target_subtype": "dynamics", "target_domain": "macrophysical"},
                {"bibcode": "a", "year": 2000, "arxiv_category": ASTRO, "candidate_tag": "neutralino", "source": "dm_model:neutralino", "source_label": "Neutralino", "target": "phenomenon:rotation", "target_label": "Rotation curves", "target_type": "phenomenon", "target_subtype": "dynamics", "target_domain": "macrophysical"},
                {"bibcode": "b", "year": 2000, "arxiv_category": HEP, "candidate_tag": "wimp", "source": "dm_model:generic_wimp", "source_label": "Generic WIMP", "target": "theory:susy", "target_label": "Supersymmetry", "target_type": "theory", "target_subtype": "bsm", "target_domain": "microphysical"},
                {"bibcode": "d", "year": 2000, "arxiv_category": HEP, "candidate_tag": "neutralino", "source": "dm_model:neutralino", "source_label": "Neutralino", "target": "theory:susy", "target_label": "Supersymmetry", "target_type": "theory", "target_subtype": "bsm", "target_domain": "microphysical"},
            ]
        )
        occurrences = pd.DataFrame(
            [
                {"bibcode": "a", "year": 2000, "arxiv_category": ASTRO, "occurrence_kind": "entity", "node_id": "phenomenon:rotation", "label": "Rotation curves", "node_type": "phenomenon", "subtype": "dynamics", "domain": "macrophysical"},
                {"bibcode": "b", "year": 2000, "arxiv_category": HEP, "occurrence_kind": "entity", "node_id": "theory:susy", "label": "Supersymmetry", "node_type": "theory", "subtype": "bsm", "domain": "microphysical"},
                {"bibcode": "d", "year": 2000, "arxiv_category": HEP, "occurrence_kind": "entity", "node_id": "theory:susy", "label": "Supersymmetry", "node_type": "theory", "subtype": "bsm", "domain": "microphysical"},
            ]
        )
        transformed = apply_wimp_definition_to_candidates(self.raw_candidates, self.definition)
        return events, occurrences, transformed

    def test_area_importance_is_pooled_and_paper_binary_after_umbrella_collapse(self) -> None:
        events, occurrences, transformed = self._importance_fixture()
        pooled_edges = aggregate_importance_edges(
            events, occurrences, self.paper_table, transformed, self.definition,
            self.window, [ASTRO, HEP], 1, "abstract",
        )
        self.assertEqual(len(pooled_edges), 2)
        self.assertEqual(set(pooled_edges["field"]), {"pooled focal fields"})
        self.assertEqual(int(pooled_edges["paper_count"].sum()), 3)
        nodes = build_importance_nodes(
            pooled_edges, transformed, occurrences, self.definition,
            self.window, [ASTRO, HEP], self.gephi,
        )
        gephi_nodes, gephi_edges = gephi_importance_tables(nodes, pooled_edges)
        validate_node_edge_tables(gephi_nodes, gephi_edges, "importance gephi")
        focal = nodes[nodes["Id"].eq(self.definition.focal_node_id)].iloc[0]
        self.assertAlmostEqual(float(focal["hits_candidate_percentile"]), 1.0)
        self.assertIn("node_size_role_spectral_percentile", gephi_nodes.columns)
        self.assertIn("Weight", gephi_edges.columns)
        self.assertNotIn("paper_count", gephi_edges.columns)
        self.assertNotIn("source_paper_count", gephi_edges.columns)

    def test_brokerage_graph_uses_one_empirically_oriented_node_per_concept(self) -> None:
        paper_table = pd.DataFrame(
            [
                {"bibcode": "a", "year": 2000, "primary_field": ASTRO},
                {"bibcode": "c", "year": 2000, "primary_field": ASTRO},
                {"bibcode": "e", "year": 2000, "primary_field": ASTRO},
                {"bibcode": "b", "year": 2000, "primary_field": HEP},
                {"bibcode": "d", "year": 2000, "primary_field": HEP},
                {"bibcode": "f", "year": 2000, "primary_field": HEP},
            ]
        )
        paper_nodes = {
            "a": [("wimp", "dm_model:generic_wimp", "Generic WIMP", "dm_model"),
                  (None, "phenomenon:rotation", "Rotation curves", "phenomenon"),
                  (None, "method:shared", "Shared method", "method")],
            "c": [("axion", "dm_model:axion_alp", "Axion + ALP", "dm_model"),
                  (None, "phenomenon:rotation", "Rotation curves", "phenomenon"),
                  (None, "method:shared", "Shared method", "method")],
            "e": [(None, "phenomenon:rotation", "Rotation curves", "phenomenon"),
                  (None, "phenomenon:stellar", "Stellar dynamics", "phenomenon")],
            "b": [("wimp", "dm_model:generic_wimp", "Generic WIMP", "dm_model"),
                  (None, "theory:susy", "Supersymmetry", "theory"),
                  (None, "method:shared", "Shared method", "method")],
            "d": [("neutralino", "dm_model:neutralino", "Neutralino", "dm_model"),
                  (None, "theory:susy", "Supersymmetry", "theory")],
            "f": [(None, "theory:susy", "Supersymmetry", "theory"),
                  (None, "apparatus:collider", "Collider", "apparatus")],
        }
        field_lookup = dict(zip(paper_table["bibcode"], paper_table["primary_field"]))
        rows = []
        for bibcode, values in paper_nodes.items():
            for tag, node_id, label, node_type in values:
                rows.append(
                    {
                        "bibcode": bibcode, "year": 2000,
                        "arxiv_category": field_lookup[bibcode],
                        "occurrence_kind": "dm_model" if node_type == "dm_model" else "entity",
                        "node_id": node_id, "label": label, "node_type": node_type,
                        "subtype": "candidate" if node_type == "dm_model" else "test",
                        "domain": "candidate" if node_type == "dm_model" else "test",
                        "candidate_tag": tag,
                    }
                )
        occurrences = pd.DataFrame(rows)
        brokerage_edges, node_stats = aggregate_brokerage_edges(
            occurrences, paper_table, self.definition, self.window, 1, self.gephi
        )
        self.assertFalse(any("::" in value for value in node_stats["Id"]))
        self.assertEqual(int(node_stats["Id"].eq("theory:susy").sum()), 1)
        susy = node_stats[node_stats["Id"].eq("theory:susy")].iloc[0]
        self.assertLess(float(susy["astro_orientation_0_1"]), 0.5)
        expected_weight = 0.5 * (
            brokerage_edges["astrophysics_cooc_doc_prevalence"]
            + brokerage_edges["hep_cooc_doc_prevalence"]
        )
        self.assertTrue(
            brokerage_edges["mean_field_cooc_prevalence"].equals(expected_weight)
        )
        nodes, brokerage_edges, removal = build_brokerage_nodes_and_metrics(
            brokerage_edges, node_stats,
            self.definition,
            self.window,
            self.gephi,
            {
                "anchor_fold_ratio": 2.0,
                "removal_top_betweenness_nodes": 5,
                "removal_include_all_candidates": True,
            },
        )
        focal = nodes[nodes["Id"].eq(self.definition.node_id)].iloc[0]
        self.assertGreater(float(focal["cross_field_betweenness_prevalence"]), 0.0)
        self.assertTrue((removal["relative_efficiency_loss"].dropna() >= 0).all())
        self.assertIn("removal_effect_percentile", removal.columns)
        self.assertIn("edge_cross_field_betweenness_prevalence", brokerage_edges.columns)
        gephi_nodes, gephi_edges = gephi_brokerage_tables(nodes, brokerage_edges)
        validate_node_edge_tables(gephi_nodes, gephi_edges, "brokerage gephi")
        self.assertIn("Weight", gephi_edges.columns)
        self.assertIn("BridgeWeight", gephi_edges.columns)
        self.assertIn("AssociationWeight", gephi_edges.columns)
        self.assertTrue(
            gephi_edges["Weight"].equals(
                brokerage_edges.loc[brokerage_edges["mean_field_cooc_prevalence"] > 0,
                                     "mean_field_cooc_prevalence"]
            )
        )

    def test_common_endpoint_sensitivity_reuses_shared_period_endpoints(self) -> None:
        windows = [
            Window("stable", "2006-2015", 2006, 2015),
            Window("stable", "2016-2025", 2016, 2025),
        ]
        node_rows = []
        edge_rows = []
        for window, late in zip(windows, (False, True)):
            for node_id, node_type, astro_anchor, hep_anchor in (
                ("phenomenon:astro", "phenomenon", True, False),
                (self.definition.focal_node_id, "candidate", False, False),
                ("method:alternate", "method", False, False),
                ("theory:hep", "theory", False, True),
            ):
                node_rows.append(
                    {
                        "wimp_definition": self.definition.name,
                        "window_kind": "stable",
                        "window": window.label,
                        "Id": node_id,
                        "node_type": node_type,
                        "is_astro_anchor": astro_anchor,
                        "is_hep_anchor": hep_anchor,
                        "cross_field_betweenness_prevalence": 0.1,
                        "removal_effect_efficiency_prevalence": 0.2,
                    }
                )
            connections = [
                ("phenomenon:astro", self.definition.focal_node_id, 0.5),
                (self.definition.focal_node_id, "theory:hep", 0.5),
            ]
            if late:
                connections.extend(
                    [
                        ("phenomenon:astro", "method:alternate", 0.5),
                        ("method:alternate", "theory:hep", 0.5),
                    ]
                )
            for source, target, weight in connections:
                edge_rows.append(
                    {
                        "wimp_definition": self.definition.name,
                        "window_kind": "stable",
                        "window": window.label,
                        "Source": source,
                        "Target": target,
                        "mean_field_cooc_prevalence": weight,
                        "distance_mean_field_prevalence": 1 / weight,
                    }
                )
        result = build_common_endpoint_sensitivity(
            pd.DataFrame(node_rows),
            pd.DataFrame(edge_rows),
            self.definition,
            windows,
        )
        self.assertEqual(len(result), 2)
        self.assertTrue((result["common_astro_endpoint_count"] == 1).all())
        self.assertTrue((result["common_hep_endpoint_count"] == 1).all())
        early, late = result.sort_values("start_year").itertuples(index=False)
        self.assertGreater(
            early.common_endpoint_removal_effect,
            late.common_endpoint_removal_effect,
        )


if __name__ == "__main__":
    unittest.main()
