# Candidate validation codebook

Annotate the abstract without consulting `candidate_validation_system_key.csv`.
For the browser interface, run `python code/candidate_validation_app.py` from the repository root.

- `gold_any_candidate`: enter `yes` when the abstract mentions at least one physical dark-matter candidate, otherwise `no`.
- `gold_candidates`: enter each canonical candidate family mentioned in the abstract once, separated by semicolons. The unit is the paper--candidate-family pair, not the number of times a name appears.
- Select every applicable family. Generic and specific labels may both be recorded when both are explicit (for example, `Generic WIMP` and `Neutralino`); synonymous tags mapped to one family (for example, axion and ALP) still contribute only one family.
- Count explicit mentions made in comparison, criticism, constraint, or exclusion as well as candidates favored by the paper. The annotation records organized attention, not endorsement or viability.
- Use the candidate as written in context. Do not code portals, production mechanisms, interaction types, or generic `dark sector` language as candidates.
- Record ambiguity or a proposed new canonical label in `notes`.
- Development annotations may inform dictionary refinement. Freeze the dictionary before starting either holdout, and do not inspect the system key until both holdouts are complete.
