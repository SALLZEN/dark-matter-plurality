# Dark-matter epistemic network

This directory contains a conservative, audit-first replacement for the legacy
string-matching and Gephi-export route. It complements the six-stage statistical pipeline in `../code/`.

The analysis asks whether dark-matter candidates connect heterogeneous parts of
research practice: theoretical frameworks, empirical and gravitational
phenomena, problems, methods, apparatus, and physical mechanisms. It can therefore be used to
explore the manuscript's **evidential-keystone** idea without treating abstract
co-occurrence as evidence of a substantive scientific relation.

## What the pipeline distinguishes

1. **Occurrence**: a canonical entity was matched in a particular sentence.
2. **Sentence co-occurrence**: a candidate and another entity occur in the same
   sentence. This is an association, not an inferred scientific relation.
3. **Abstract co-occurrence**: a candidate and another entity occur somewhere
   in the same abstract. The event records whether they also share a sentence
   and their minimum sentence distance.
4. **Heuristic relation event**: a candidate, another entity, and an explicit
   relation cue occur locally in the same sentence. These edges retain their
   evidence sentence, cue, distance, modality, negation, and confidence class.

The Gephi exports preserve this distinction. No edge is described simply as
"evidence".

## Improvements over the legacy route

- boundary-safe matching prevents substring errors such as `flux` becoming
  `LUX`, `lepton` becoming `LEP`, or words ending in `ps` becoming the CERN
  Proton Synchrotron;
- ambiguous acronyms are either case-sensitive or omitted;
- aliases resolve to stable canonical IDs;
- the expanded ontology resolves 549 concepts through 1,597 aliases while
  enforcing the six non-candidate vertex classes used by the graph;
- SUSY variants, modified-gravity families, inflationary theories, and other
  named frameworks remain separate vertices rather than one generic theory tag;
- the legacy stellar-object/context layer is replaced by gravitational and
  empirical phenomena;
- dark-matter candidate tags are paired with their own spans *before* portals,
  mechanisms, and other non-candidate tags are filtered;
- sentence, match span, matched surface text, paper identifier, year, and field
  are retained for audit;
- semantic relation candidates require an explicit cue and local proximity;
- co-occurrence weights include unique-paper count, fractional weight, Jaccard,
  cosine similarity, and normalized pointwise mutual information (NPMI);
- candidate bridge summaries use layer diversity and participation rather than
  raw degree alone;
- all configuration and input files are hashed in a run manifest;
- regression tests cover the known substring and tag/span failure modes.

## Inputs

Defaults point to the canonical files in the repository root:

- `../data/papers.parquet` for raw abstracts;
- `../data/papers_with_dm_models.parquet` for eligibility, field, and candidate
  metadata;
- `../code/` for the released candidate
  ontology and text normalizer.

The candidate ontology is reused rather than forked so the network and paper
analyses cannot silently drift apart. The new adapter repairs the old
mention-level pairing issue by filtering `(tag, span)` pairs together.
The default entity entry point is `config/entity_catalog.json`; its modular
sources and legacy-dictionary coverage are documented in
`config/ontology/README.md`. The source- and corpus-based coverage investigation
is recorded in `config/ontology/ONTOLOGY_GAP_AUDIT_2026-08-10.md`. Every
contributing ontology file is hashed in the run manifest.

## Run step by step

From this directory:

```bash
python3 -m unittest discover -s tests -v
python3 run_pipeline.py --validate-only
python3 run_pipeline.py --max-papers 500 --output-dir outputs/smoke-test
python3 run_pipeline.py --output-dir outputs/canonical
```

The default scope is papers containing at least one ontology entry whose
category is `candidate`. To include portals, mechanisms, interaction classes,
and umbrella models as focal nodes, add:

```bash
python3 run_pipeline.py \
  --dm-scope all \
  --output-dir outputs/canonical-all-dm-models
```

Useful filters include:

```bash
python3 run_pipeline.py \
  --min-year 1985 \
  --max-year 2025 \
  --fields astrophysics "high-energy physics" \
  --min-edge-papers 5 \
  --min-relation-papers 2 \
  --output-dir outputs/focal-fields
```

## Principal outputs

| File | Unit |
|---|---|
| `occurrences.parquet` | one matched entity occurrence |
| `cooccurrence_events.parquet` | one candidate--entity sentence event |
| `abstract_cooccurrence_events.parquet` | one candidate--entity abstract event |
| `relation_events.parquet` | one cue-qualified heuristic relation event |
| `nodes.csv` | shared Gephi node table, including raw and `log1p` weighted degree |
| `edges_cooccurrence.csv` | primary undirected sentence-level Gephi edges |
| `edges_abstract_cooccurrence.csv` | complementary undirected abstract-level Gephi edges |
| `edges_relations.csv` | high-confidence directed focal-candidate relation edges |
| `edges_relations_all.csv` | high- and medium-confidence diagnostic relation edges |
| `edges_cooccurrence_by_period.csv` | period-specific co-occurrence edges |
| `edges_abstract_cooccurrence_by_period.csv` | period-specific abstract edges |
| `candidate_metrics.csv` | full-period candidate bridge summaries |
| `candidate_metrics_by_period.csv` | candidate bridge summaries by period |
| `candidate_metrics_abstract.csv` | abstract-scope candidate bridge summaries |
| `candidate_metrics_abstract_by_period.csv` | abstract summaries by period |
| `pattern_frequency.csv` | matched surface forms for extraction audit |
| `quality_flags.csv` | automated warnings for suspicious prevalence |
| `ontology_inventory.csv` | every configured entity alias, including zero-match aliases and corpus counts |
| `relation_audit_sample.csv` | deterministic sample stratified by relation and confidence |
| `manifest.json` | inputs, hashes, parameters, versions, and row counts |

For Gephi, import `nodes.csv` through the Nodes table. Pair it with
`edges_cooccurrence.csv` for the primary, higher-specificity sentence network,
or `edges_abstract_cooccurrence.csv` for the broader complementary network.
The co-occurrence exports duplicate the analytical `fractional_weight` as the
case-sensitive Gephi-standard `Weight` column, so layouts and weighted network
statistics use the intended edge strength without manual remapping. Relation
exports use the number of distinct supporting papers as `Weight`.

For node-size ranking, `weighted_degree_log1p` is the natural logarithm of one
plus the primary sentence-level weighted degree. It is safe for zero-degree
nodes and prevents a few highly connected nodes from compressing the rest of
the size scale. The corresponding scope-specific columns are
`weighted_degree_sentence_log1p` and `weighted_degree_abstract_log1p`.
The abstract table reports `same_sentence_share`, making it possible to see
which broad edges are mostly local and which depend on cross-sentence context.
`edges_relations.csv` is directed and includes only the
pipeline's high-confidence local relation structures. Broader medium-confidence
associations remain available in `edges_relations_all.csv` and the event table
for audit. The source-to-target
direction always means *focal dark-matter model to associated entity*; it is not
a claim about grammatical subject and object.

## Interpretation limits

- A sentence co-occurrence edge means only that two canonical terms appear in
  the same sentence. An abstract edge is broader still and may connect terms
  from different sentences.
- A relation edge is a transparent rule-based candidate, not a dependency parse
  or human adjudication. Use its evidence sentence and confidence fields.
- The ontology is coverage-oriented but remains a controlled dictionary.
  Absence of an edge is not evidence that a scientific connection does not
  exist; use the exported zero-match inventory to audit omissions.
- Candidate metrics describe the textual organization of this corpus, not the
  truth, existence, or evidential adequacy of a dark-matter candidate.
- Raw degree remains sensitive to publication volume. Prefer participation,
  normalized layer entropy, Jaccard, cosine, NPMI, and temporal comparisons.

Before a graph becomes a manuscript result, inspect the most frequent matched
surface forms, the highest-weight edges, and a small stratified sample of
relation evidence sentences. This is a targeted audit of a new analysis—not a
requirement to manually recode the corpus paper by paper.

## WIMP-role graph families

`build_wimp_role_graphs.py` builds three linked analyses on top of the canonical
paper-level occurrence and event tables. The base ontology extraction does not
need to be repeated when only a temporal window, WIMP definition, weight, or
Gephi presentation parameter changes.

```bash
python3 build_wimp_role_graphs.py
```

The default destination is `outputs/wimp-role-networks/`. Each graph family has
its own directory, manifest, lossless canonical tables, reduced Gephi tables,
and GraphML files:

1. `01_field_relative_prominence`: candidate--field mention share, equal-field
   mean share, smoothed astrophysics/HEP log share ratio, field-normalized
   participation, cross-listing, and deterministic paper-bootstrap intervals.
2. `02_area_wide_importance`: one pooled astrophysics-and-HEP
   candidate--concept bipartite network with abstract-level primary edges,
   sentence-level sensitivity edges, role-specific HITS scores and percentiles,
   strength, coreness, and ontology-type diversity.
3. `03_cross_field_brokerage`: one canonical node per candidate or concept in
   an abstract-level co-occurrence graph. Node and edge field orientation are
   estimated from their relative prevalence in astrophysics and HEP. Concepts
   at least twice as prevalent in one field define the two endpoint sets;
   cross-field node and edge betweenness then identify the concepts that hold
   those oriented regions together. Targeted node-removal effects provide a
   stricter alternative check for the WIMP and the strongest bridge nodes.

The analysis is generated under three non-overlapping graph specifications:

- `explicit_generic`: literal generic-WIMP mentions remain separate from named
  candidates;
- `published_umbrella`: the manuscript's Generic WIMP, Neutralino, LSP,
  Higgsino, Gravitino, and Sneutrino grouping is collapsed at paper level;
- `canonical_core`: the same collapsed grouping without the Gravitino.

The canonical CSV files retain counts, denominators, component measures, all
three WIMP definitions, and five-year rolling results. The main Gephi directory
contains only the manuscript's `published_umbrella` definition for the two
equal comparison periods, 2006--2015 and 2016--2025: six import-ready graph
instances in total. The alternative WIMP definitions remain as canonical
robustness GraphML files rather than duplicating the publication workspace.

Every Gephi node table contains only identifiers, labels/types, focal flags,
directly assignable node/label/colour values, and `layout_x`/`layout_y`.
The coordinates are computed once from the union of both decades and reused in
both panels. Node sizes and colour ranges are likewise fixed across decades.
Open `network.gexf` to apply the shared coordinates automatically in Gephi.
Alternatively, import `network.graphml` or import `nodes.csv` before
`edges.csv`; the manifest names the primary and alternative edge weights.

For Graph 3, use `node_size_sqrt_betweenness_common` for node size and
`astro_orientation_0_1` for the astrophysics--HEP colour scale. `Weight` is the
equal-field mean of paper-level co-occurrence prevalence: field-specific joint
prevalence is calculated separately in astrophysics and HEP, then the two
values are averaged so that corpus size does not give either field greater
influence. This is both the layout weight and the basis of the inverse distance
used for cross-field betweenness. `BridgeWeight` is the resulting cross-field
edge betweenness and is suitable for edge width or filtering.

`AssociationWeight` retains pooled positive NPMI as a secondary diagnostic; it
does not determine the primary layout or brokerage calculation.
`SharedPrevalenceWeight` is the harmonic mean of the two field prevalences and
is available as a stricter sensitivity value for connections observed in both
fields, but is not the primary graph weight.

## Released frozen outputs

From the repository root, extract `network/canonical-frozen.zip` and `network/wimp-role-networks-frozen.zip` into `network/` to restore `network/outputs/canonical/` and `network/outputs/wimp-role-networks/`. The archives retain event tables, metrics, graph exports, manifests, and saved Gephi projects. Large intermediate image exports and editor scratch files are omitted; the final figure assets are in `../figures/`. Archive and member hashes are recorded in `../release_manifest.json`. Compact manuscript-cited tables are also available in `summaries/`.

The packaged command defaults use `../data/` and `../code/`. Original frozen manifests preserve their historical development paths and input hashes. Rebuilding extraction requires the large canonical parquet inputs regenerated by stages 002–005; inspecting the frozen graph analyses does not.

## Historical archive and current code

The network archives preserve the results and saved presentations used in the paper. Their historical manifests record earlier candidate-dictionary and network-code versions. The current code includes later revisions, so rerunning it is not guaranteed to reproduce those archived network results exactly. The archived tables, graphs, and figure assets remain available for inspection.
