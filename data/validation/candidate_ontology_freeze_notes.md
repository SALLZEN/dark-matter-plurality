# Candidate ontology freeze notes

The ontology was frozen after review of the 180-record candidate-enriched development sample. The development sample informed rules and regression cases; it is not used to estimate precision or recall. The 180-record system-positive and 480-record field-by-period population holdouts remained unannotated at freeze time.

## Measurement convention

The unit is one paper--candidate-family pair. Repeated occurrences of a family in one abstract collapse to one observation. Explicit generic and specific names may each produce an observation when both occur; synonymous tags assigned to one canonical family collapse. Mentions made in support, comparison, criticism, constraint, or exclusion count because the measure concerns organized attention rather than endorsement.

## Development-informed corrections

- Excluded `WIMP` and the expanded phrase `weakly interacting massive particle` when immediately negated by `non-` or `non `.
- Excluded `lightest supersymmetric particle` when it is the suffix of `next-to-lightest supersymmetric particle`, while retaining a later independent `LSP` mention.
- Recognized the attested hyphenated and spaced spellings `b-ino`, `b ino`, `w-ino`, and `w ino` as Bino and Wino.
- Extended the nearby-dark-matter context window only for ambiguous Glueball expressions, from the 60-character default to 160 characters.
- Left broad context restrictions for otherwise explicit family names unchanged. The dictionary counts explicit candidate discussion even when the paper compares, constrains, or rejects the candidate.

## Effect on canonical output

Relative to the pre-freeze extraction, the corrected table removes 11 Generic WIMP and 58 LSP paper--family rows and recovers 27 Bino, 17 Wino, and 10 Glueball rows. The canonical table changes from 28,454 to 28,439 rows. Recovering Bino moves it into the full-period union of the nine most-mentioned families per field, replacing Sneutrino in the 13-family primary composition analysis.

The primary mean annual Jensen--Shannon divergence changes from 0.332 to 0.326 for 1995--2004 and from 0.291 to 0.293 for 2016--2025; the late-minus-early contrast remains negative, changing from -0.041 to -0.033. The all-observed-ontology sensitivity likewise remains negative (-0.029 after correction). Thus, the corrected extraction changes exact values and one tracked-family membership but not the manuscript's bounded conclusion that the data do not support increasing candidate-composition divergence.

Run `python3 code/freeze_candidate_ontology.py` from the repository root to verify the annotation state, refresh the blinded system key from the canonical candidate table, and recreate `candidate_ontology_freeze.json` with source and output SHA-256 hashes.
