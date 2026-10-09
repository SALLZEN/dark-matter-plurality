# Data products

Large upstream parquet files are rebuilt locally from the retained stage-001 ADS archive:

- papers.parquet
- paper_arxiv_classes.parquet
- paper_metrics_long.parquet
- papers_with_dm_models.parquet

These are inputs to the full pipeline and are intentionally not committed.

Compact frozen inputs committed for direct figure reproduction:

- dm_model_candidates_long.parquet
- unigram_yearly.parquet

Other small versioned products committed for auditability:

- analysis_manifest.json — hashes, counts, cutoff, exclusions, versions, and seeds
- analysis/ — yearly classifications, class mappings and coverage, candidate divergence, rarefaction, permutation and weighting sensitivities, document sensitivity, lexical divergence, and figure source data
- validation/ — completed primary-order audit, completed candidate-ontology development review, untouched optional holdouts, freeze notes, and `candidate_ontology_freeze.json` with source and output SHA-256 hashes

All products exclude records after 2025.
