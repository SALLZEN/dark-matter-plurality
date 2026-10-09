# Entity ontology

`../entity_catalog.json` is the default ontology entry point. It combines the
retained high-precision parts of the conservative v1 ontology with the
following concept-resolved modules:

- `theories.json`
- `phenomena.json`
- `concepts.json` for problems, mechanisms, and methods
- `apparatus.json`
- `coverage_theories.json`
- `coverage_concepts.json`
- `coverage_apparatus.json`

The catalog currently contains 549 canonical entities and 1,597 literal or
regex aliases. Dark-matter models are supplied separately by the manuscript's
released candidate ontology, so the complete graph has exactly seven vertex classes:
`dm_model`, `theory`, `phenomenon`, `problem`, `method`, `apparatus`, and
`mechanism`.

## Coverage and provenance

The expansion was seeded from the legacy dictionaries in:

- `damadi/lib/python/003-a-collider-plots.ipynb`
- `damadi/lib/python/003-b-detector-plots.ipynb`
- `damadi/lib/python/003-c-theory-plots.ipynb`
- `damadi/lib/python/003-d-telescope-plot.ipynb`
- `damadi/lib/python/003-h-method-plots.ipynb`
- `damadi/lib/python/003-i-gravity-plots.ipynb`
- `damadi/lib/python/003-j-inferences-plot.ipynb`

It was subsequently checked against the Particle Data Group dark-matter review,
four Snowmass theory/facility reports, specialist reviews, and the complete
candidate-bearing abstract corpus. The sources, additions, exclusions, corpus
counts, and validation results are recorded in
`ONTOLOGY_GAP_AUDIT_2026-08-10.md`.

The theory module contains exact literal mappings for 50 of the 59 unique
legacy theory strings. Four more are covered by boundary-safe regexes: the
three Lambda-CDM spellings and the hyphen variants of tensor-vector-scalar
gravity. `Gravitino` remains in the candidate ontology because it denotes a
particle/candidate, not a theory. Bare `SM`, `GR`, `SR`, and `QM` were not
retained because they are materially ambiguous in this corpus; their full names
are covered. The module also adds separate nodes for SUSY variants, modified-
gravity families, inflationary models, portal frameworks, effective field
theory, quantum-gravity programs, and other central frameworks.

The phenomena module contains exact literal mappings for 88 of the 101 unique
legacy gravitational strings. The remaining forms are deliberately qualified:

- bare `lensing`, `microlensing`, and `time dilation` are replaced by explicit
  gravitational or event phrases;
- bare `redshift`, `anisotropy`, `mass distribution`, and `substructure` are
  replaced by cosmological or dark-matter-qualified phrases;
- bare `wave emission` and `wave emissivity` are excluded;
- bare `acoustic oscillation(s)` is replaced by baryon-acoustic or CMB-specific
  phrases;
- `collisionless dark matter` is not treated as an empirical phenomenon.

This is why the ontology is described as coverage-oriented rather than as a
verbatim union of the old string lists. Exhaustiveness is pursued at the level
of scientific concepts while known ambiguous surface forms remain excluded.

## Category rules

- A `theory` is a named theoretical framework, model family, or physical
  principle—not a particle candidate.
- A `phenomenon` is an observation, inferred structure, dynamical process, or
  relativistic effect. The old generic stellar-object layer is not loaded.
- A `problem` is an explicitly named anomaly, tension, or explanatory target.
- A `method` is a recognizable research or inferential procedure, not a generic
  verb such as “observe,” “fit,” or “measure.”
- An `apparatus` is a named detector, accelerator, observatory, mission, or
  survey.
- A `mechanism` is a physical production, interaction, conversion, or
  thermal-history process.

All IDs must begin with their node type, aliases must be unique across active
entities, short literal acronyms must be case-sensitive, and regexes must
compile. Catalog validation enforces these rules before corpus processing.
Entity-level `exclude_with_candidates` rules suppress known definitional pairs;
currently, generic black-hole mentions do not form sentence edges with PBH,
although a separate black-hole discussion elsewhere in the abstract can still
form an abstract-level association.

## Auditing coverage

Every run writes `ontology_inventory.csv`. It contains every configured alias,
including zero-match aliases, together with its canonical ID, category,
matching rule, source module, matched-paper count, and occurrence count. Pair
that file with `pattern_frequency.csv` and `quality_flags.csv` when evaluating
new aliases or looking for corpus-specific omissions.
