# Reproduction Bundle for “Diverging paths to dark-matter discovery”

[![DOI](https://zenodo.org/badge/1240854446.svg)](https://doi.org/10.5281/zenodo.20241725)

This repository is the code and data bundle for the preprint *Diverging paths to dark-matter discovery*. It preserves the frozen ADS retrieval, rebuilds the canonical analysis tables, performs robustness and validation analyses, and includes the network analyses and all five main and five supplementary figure assets. The manuscript source and compiled preprint are maintained separately.

Version 3.0.0 accompanies the arXiv preprint. The Zenodo badge intentionally uses the concept DOI, [10.5281/zenodo.20241725](https://doi.org/10.5281/zenodo.20241725), which resolves across versions. The archived v3.0.0 release is identified by the version DOI [10.5281/zenodo.23263996](https://doi.org/10.5281/zenodo.23263996).

## Frozen analysis contract

- ADS query: full:"dark matter"
- indexing snapshot: 2026-05-21
- analysis cutoff: 2025 inclusive
- 2026 records: excluded everywhere
- canonical corpus through 2025: 201,627 records
- papers with arXiv classifications: 143,390
- random seed: 20250801
- candidate-divergence bootstrap: 2,000 paper-level resamples per field-year

The machine-readable statistical analysis contract is [data/analysis_manifest.json](data/analysis_manifest.json). It records the canonical inputs and their hashes. The network archives have separate historical manifests and the scope described below.

## Six-stage pipeline

1. code/001-collect-ads-records.ipynb — retained ADS retrieval and provenance
2. code/002-build-canonical-data.R — canonical papers, classes, and metrics
3. code/003-extract-dm-candidates.ipynb — candidate mentions
4. code/004-build-lexical-data.ipynb — lexical data and rankings
5. code/005-robustness-validation.ipynb — classification sensitivity, validation, divergence, and robustness
6. code/006-build-paper-assets.R — Figures 1–3 and S1–S4, an auxiliary closure schematic, and a candidate-ranking table

`code/006a-build-paper-assets-stepwise.R` is the readable, stepwise renderer for Figures 1–3. `code/006b-build-si-assets-stepwise.R` provides the corresponding route for Figures S1–S4. Stage 006 invokes both companions, using the same frozen inputs, so the interactive and noninteractive routes share the final rendering code.

code/001a-update-ads-records.ipynb is retained only as an optional future maintenance route. It is not used for v3.0.0 because the frozen ADS snapshot covers records through the 2025 analysis cutoff.

## Reproduce from the retained archive

Set up the pinned Python environment:

    ./configure_repo.sh

Restore the pinned R environment:

    Rscript -e 'renv::restore()'

Stage 006 requires the open-source STIX Two Text font to be installed on the system. The renderer resolves the installed regular and italic faces and stops with an explicit error if the font is unavailable.

### Regenerate the current main figures only

The compact frozen inputs needed for Figures 1–3 are included, so the revised main figures can be regenerated without rebuilding the large canonical corpus:

    Rscript code/006a-build-paper-assets-stepwise.R

This writes `figures/primary_dominant.pdf`, `figures/log_ratio.pdf`, and `figures/norm.pdf`. Figure 2 excludes candidate-year cells with fewer than 20 paper mentions.

### Regenerate the SI figures step by step

Open `code/006b-build-si-assets-stepwise.R` in RStudio and run its numbered sections to inspect the source tables, transformations, selected lexical terms, and plot objects for Figures S1–S4. To run the same route noninteractively:

    Rscript code/006b-build-si-assets-stepwise.R

Set `SAVE_OUTPUTS <- FALSE` before running in RStudio to inspect the objects without overwriting the released PDFs.

To regenerate these seven statistical figures, the auxiliary schematic, and the candidate-ranking table from the included frozen analysis products:

    Rscript code/006-build-paper-assets.R

Extract the retained archive:

    unzip code/stage-outputs/001-collect-ads-records/ads_stage_001_snapshots.zip -d code/stage-outputs/001-collect-ads-records/

Run stages 002–006 in order. The notebook stages can be run interactively or executed noninteractively with the pinned environment:

    PYTHON_BIN=.venv/bin/python code/run_frozen_pipeline.sh

The equivalent individual commands are:

    Rscript code/002-build-canonical-data.R
    .venv/bin/jupyter nbconvert --to notebook --execute --inplace code/003-extract-dm-candidates.ipynb
    .venv/bin/jupyter nbconvert --to notebook --execute --inplace code/004-build-lexical-data.ipynb
    .venv/bin/jupyter nbconvert --to notebook --execute --inplace code/005-robustness-validation.ipynb
    Rscript code/006-build-paper-assets.R

The noninteractive stage-005 analysis core and automated checks are also available directly:

    python code/robustness_analysis.py --bootstrap 2000
    Rscript code/006-build-paper-assets.R
    python -m unittest discover -s code/tests -p 'test_*.py' -v

No ADS token or new network retrieval is required. Network access is needed only to rebuild the independent arXiv primary-category audit from scratch; the fixed 500-record output is included.

## Inspect the archived network analyses

The network code reuses the candidate ontology in `code/`.

The network archives preserve the results and saved presentations used in the paper. Their historical manifests record earlier candidate-dictionary and network-code versions. The current code includes later revisions, so rerunning it is not guaranteed to reproduce those archived network results exactly. The archived tables, graphs, and figure assets remain available for inspection. Its frozen event tables, metric tables, graph exports, and saved Gephi layouts are included in `network/canonical-frozen.zip` and `network/wimp-role-networks-frozen.zip`:

    unzip network/canonical-frozen.zip -d network/
    unzip network/wimp-role-networks-frozen.zip -d network/
    python -m unittest discover -s network/tests -p 'test_*.py' -v
    python network/run_pipeline.py --validate-only

After rebuilding the canonical upstream data with stages 002–005, run the current extraction and WIMP-role code with:

    python network/run_pipeline.py
    python network/build_wimp_role_graphs.py

The saved graph exports and Gephi projects preserve the layouts used in Figure 4 (`graph-01.pdf`) and Figure S5 (`graph_removal.pdf`). Rendering those panels uses the saved Gephi presentation; it is not performed by stage 006. Figure 5 (`fig_table.png`) is the conceptual assessment supplied with the paper. See [network/README.md](network/README.md) for the graph definitions, weights, sensitivity analyses, and interpretation limits.

## Released material

- data/analysis/: yearly classifications, mappings and coverage, candidate divergence, weighting, rarefaction, permutation, document sensitivities, and lexical divergence
- data/validation/: completed primary-order audit and optional candidate-dictionary audit materials
- figures/: source-data manifest, alt text, five main figures, and five SI figures
- tables/: generated candidate-family ranking
- code/tests/: deterministic weighting, distance, identifier, and candidate-ontology checks
- network/: ontology extraction, WIMP-role analyses, tests, compact summaries, and a frozen archive of events, metrics, graph exports, and saved Gephi layouts
- release_manifest.json: release assembly provenance and SHA-256 hashes of the frozen network archives and their members

Two compact figure inputs, `data/dm_model_candidates_long.parquet` and `data/unigram_yearly.parquet`, are included so the paper assets can be regenerated directly. Four large upstream intermediates—`papers.parquet`, `paper_arxiv_classes.parquet`, `paper_metrics_long.parquet`, and `papers_with_dm_models.parquet`—are intentionally omitted and rebuild from the retained 76-MB compressed ADS archive.

## Audit status

The 500-paper ADS/arXiv primary-category audit is complete: agreement is 1.000 with a Wilson 95% interval of 0.992–1.000.

The candidate dictionary measures explicit paper--candidate-family mentions, not endorsements. Repeated occurrences of one family in an abstract count once; explicitly named generic and specific families may each count once when they co-occur, while synonymous tags mapped to one family are collapsed. Its full patterns, context rules, canonical-family mappings, and deterministic regression tests are released with the pipeline. A completed 180-record candidate-enriched development review informed a small set of boundary corrections and is not used to estimate precision or recall. The untouched holdout scaffold is retained in `data/validation/`; it does not affect release status, and no precision or recall value is claimed.

The frozen ontology and regenerated outputs are recorded in `data/validation/candidate_ontology_freeze.json`. Recreate and verify that manifest from the repository root with:

    python code/freeze_candidate_ontology.py

## Citation and archive lineage

- Citation metadata: [CITATION.cff](CITATION.cff)
- Zenodo metadata: [.zenodo.json](.zenodo.json)
- GitHub: [SALLZEN/dark-matter-plurality](https://github.com/SALLZEN/dark-matter-plurality)
- Zenodo v3.0.0 DOI: [10.5281/zenodo.23263996](https://doi.org/10.5281/zenodo.23263996)
- Zenodo concept DOI: [10.5281/zenodo.20241725](https://doi.org/10.5281/zenodo.20241725)
- License: [MIT](LICENSE)

The earlier version DOI 10.5281/zenodo.20241726 identifies an older archive and is not the revised v3.0.0 release.
