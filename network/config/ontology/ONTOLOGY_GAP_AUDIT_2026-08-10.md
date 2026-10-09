# Ontology gap audit, 2026-08-10

## Purpose and scope

This audit tested whether the controlled entity ontology omitted named theories,
empirical or gravitational phenomena, scientific problems, mechanisms, methods,
or apparatus that are materially relevant to dark-matter research. Dark-matter
candidate families remain governed by the separate released candidate ontology;
they were not duplicated as entity vertices here.

The audit combined two forms of evidence:

1. comparison with broad, field-level reviews and facility surveys; and
2. case-sensitive and phrase-qualified searches in the 22,882 candidate-bearing
   abstracts processed by the canonical network pipeline.

The aim was concept-level breadth without admitting every observable noun or
ambiguous acronym. An item was added when it denotes a recognizable scientific
framework, signal, explanatory target, procedure, physical process, or named
research facility and can be matched with a reasonably precise surface form.

## Verified reference inventories

| Reference | Principal use in the audit |
|---|---|
| [Particle Data Group, *Dark Matter* review (2024)](https://pdg.lbl.gov/2024/reviews/rpp2024-rev-dark-matter.pdf) | Candidate frameworks, direct and indirect searches, anomalous signals, precision sensors, and named experiments |
| [Snowmass, *Cosmic Probes of Dark Matter*](https://arxiv.org/abs/2209.08215) | Strong lensing, stellar streams, small-scale structure, CMB, 21-cm, and survey facilities |
| [Snowmass, *Low-threshold direct detection of dark matter*](https://arxiv.org/abs/2203.08297) | Nuclear and electron recoil, the neutrino fog, low-threshold methods, Oscura, and TESSERACT |
| [Snowmass, *Observational Facilities to Study Dark Matter*](https://arxiv.org/abs/2203.06200) | CMB, optical, radio, x-ray, gravitational-wave, and pulsar-timing facilities |
| [Snowmass, *Accelerator-based Dark Matter Facilities*](https://arxiv.org/abs/2206.04220) | Collider, beam-dump, missing-momentum, and long-lived-particle experiments |
| [Fabbrichesi, Gabrielli, and Lanfranchi, *The Dark Photon*](https://arxiv.org/abs/2005.01515) | Hidden-sector theory, kinetic mixing, and accelerator experiments |
| [Adams et al., *Axion Dark Matter*](https://arxiv.org/abs/2203.14923) | Axion theory variants, production and conversion mechanisms, and experimental programs |
| [McGaugh, Lelli, and Schombert, radial acceleration relation](https://arxiv.org/abs/1609.05917) | Galaxy-scale acceleration and mass-discrepancy relations |
| [Particle Data Group, *Inflation* review (2024)](https://pdg.lbl.gov/2024/reviews/rpp2024-rev-inflation.pdf) | Named inflationary frameworks and their empirical status |
| [Cline, *TASI Lectures on Early Universe Cosmology*](https://arxiv.org/abs/1807.08749) | Inflation, baryogenesis, leptogenesis, phase transitions, and dark-matter genesis |
| [Petraki and Volkas, *Review of asymmetric dark matter*](https://arxiv.org/abs/1305.4939) | Linked dark-visible asymmetries and cogenesis mechanisms |

Specialized source checks were also made for the [constrained MSSM and
non-universal Higgs models](https://arxiv.org/abs/1405.4289), [mimetic dark
matter/gravity](https://arxiv.org/abs/1308.5410), the [axion-quality
problem](https://arxiv.org/abs/2009.03917), and the [axion domain-wall
problem](https://arxiv.org/abs/2307.04710). A residual corpus-led check used
primary or specialist sources for [D-term inflation](https://arxiv.org/abs/hep-ph/9606342),
[quintessential inflation](https://arxiv.org/abs/1410.6100), [asymptotic safety
with matter](https://arxiv.org/abs/2212.07456), and the [running-vacuum
model](https://arxiv.org/abs/2306.08064).

## Additions

The audit added **251 canonical entities** in three machine-readable modules:

| Module | Added entities | Added aliases | Contents |
|---|---:|---:|---|
| `coverage_theories.json` | 59 | 187 | Theory and model-family gaps |
| `coverage_concepts.json` | 103 | 390 | 39 phenomena, 19 problems, 30 mechanisms, and 15 methods |
| `coverage_apparatus.json` | 89 | 203 | Collider, direct-detection, indirect-detection, cosmological, gravitational-wave, survey, neutrino, and axion facilities |

Nine aliases were also added to established nodes: `Primakoff effect`,
`Primakoff process`, and `Primakoff production` for axion-photon conversion;
`GLAST` and its long form for Fermi-LAT; `FASER2` for FASER; and `BOSS`,
`eBOSS`, and the BOSS long form for SDSS. The complete active ontology therefore
grew from 298 entities and 808 aliases to **549 entities and 1,597 aliases**.

### Theory gaps

- Supersymmetric variants: CMSSM, mSUGRA, NUHM, R-parity-violating SUSY,
  BLSSM, MRSSM, GNMSSM, and E6SSM.
- Electroweak and compositeness frameworks: Little Higgs, composite Higgs,
  technicolor, and the two-Higgs-doublet model.
- Gauge and unification frameworks: left-right symmetry, Pati-Salam, SO(10),
  SU(5), and U(1) B-L.
- Extra-dimensional and hidden-sector frameworks: Randall-Sundrum,
  braneworlds, DGP, Hidden Valley, dark QCD, ETHOS, and dark-matter simplified
  models.
- Halo models: Standard Halo Model and the NFW, Einasto, Burkert, and
  isothermal profiles.
- Gravity and cosmology: f(Q), mimetic gravity, Galileons, early and
  interacting dark energy, and the Chaplygin-gas model.
- Early-universe and axion frameworks: axion, thermal, ultra-slow-roll,
  multifield, and fibre inflation; the curvaton scenario; KSVZ, DFSZ, and
  Peccei-Quinn; SMASH; KKLT; and the Large Volume Scenario.
- The residual corpus pass added Higgs, hilltop, D-brane, alpha-attractor,
  power-law, D-term, F-term, and quintessential inflation; the running-vacuum
  and holographic-dark-energy models; asymptotic safety; and the axion portal.

### Phenomenon, problem, mechanism, and method gaps

- New phenomena include stellar-stream perturbations, strong-lensing
  flux-ratio anomalies, RAR/MDAR, the baryonic Tully-Fisher relation, dark
  acoustic oscillations, the 21-cm signal, cosmic dawn and reionization,
  dark-matter spikes and caustics, gravothermal collapse and solitonic cores,
  black-hole shadows, stochastic gravitational waves, antimatter and gamma-ray
  anomalies, DAMA and XENON1T excesses, recoil and modulation signatures,
  local-halo quantities, dwarf-satellite populations, CMB birefringence and
  spectral distortions, the Sunyaev-Zeldovich effect, isocurvature modes, extra
  radiation density, early matter domination, wide-binary survival, and
  stellar and dynamical heating.
- New problems include the neutrino floor/fog; little-hierarchy, gravitino,
  domain-wall, axion-quality, axion-isocurvature, moduli, lithium, and monopole
  problems; muon g-2, flavour, W-mass, and short-baseline neutrino anomalies;
  the neutrino-mass and solar-neutrino problems; and disk-halo and mass-sheet
  degeneracies.
- New mechanisms include generic and typed seesaws, kinetic mixing, Sommerfeld
  enhancement, bound-state formation, Affleck-Dine generation, thermal and
  non-thermal production, resonant production, cascade decay, dark showers and
  hadronization, the Primakoff and axioelectric effects, and fifth forces.
- The residual mechanism pass added baryogenesis, electroweak baryogenesis,
  leptogenesis, dark-visible cogenesis, first-order cosmological phase
  transitions, bubble nucleation, spontaneous symmetry breaking, the
  Stueckelberg mechanism, dark recombination, reheating, preheating,
  forbidden-channel annihilation, and co-scattering.
- New methods include beam-dump and missing-momentum searches,
  light-shining-through-walls experiments, atom interferometry, atomic clocks,
  comagnetometry, torsion balances, halo-independent inference, nested
  sampling, machine learning, mono-X searches, 21-cm tomography, and CMB
  spectral-distortion measurements, plus Press-Schechter and spherical-collapse
  calculations.

### Apparatus gaps

- Collider, accelerator, and neutrino programs: ATLAS, CMS, LHCb, Belle II,
  BaBar, NA62, NA64, LDMX, SHiP, MATHUSLA, MoEDAL, MESA, MiniBooNE,
  MicroBooNE, LSND, DUNE, JUNO, Hyper-Kamiokande, Borexino, SNO/SNO+,
  COHERENT, and KATRIN.
- Direct and low-threshold detection: CoGeNT, GENIUS, EURECA, KIMS, MIMAC,
  ROSEBUD, DMTPC, NEWAGE, WARP, CUORE/CUORICINO, PVLAS, TEXONO, TREX-DM,
  Oscura, TESSERACT, COSINUS, CYGNUS, CYGNO, PTOLEMY, and DELight.
- Indirect and multimessenger facilities: AMS-02, PAMELA, EGRET, HAWC,
  LHAASO, INTEGRAL, NuSTAR, COMPTEL, GAPS, ANTARES, KM3NeT, AMANDA,
  DeepCore, and PINGU.
- Cosmology and gravitational waves: CMB-S4, BICEP/Keck, ACT, SPT, Simons
  Observatory, LiteBIRD, PIXIE, CMB-HD, LISA, Einstein Telescope, Cosmic
  Explorer, DECIGO, BBO, NANOGrav, IPTA, EPTA, and PPTA.
- Surveys and axion programs: OGLE, EROS, Subaru/HSC, Roman, eROSITA, XRISM,
  BabyIAXO, BREAD, CAPP/CULTASK, RADES, KLASH, DALI, TASEH, ARIADNE, OSQAR,
  and ORPHEUS.

## Corpus cross-check

The rebuilt canonical run processed 22,882 candidate-bearing papers from
1982--2025. Of the new nodes, 59/59 theories, 38/39 phenomena, 18/19 problems,
29/30 mechanisms, 12/15 methods, and 84/89 apparatus matched at least one
paper. The largest previously absent nodes included ATLAS (403 papers),
reheating (398), nuclear recoil (348), leptogenesis (344), CMS (339),
baryogenesis (331), Peccei-Quinn (242), kinetic mixing (236), mSUGRA (216),
extra radiation density (209), and LISA (200).

Eleven source-supported nodes had zero matches in the current candidate-bearing
corpus and were retained for explicit future coverage: DELight, MESA, Oscura,
TESSERACT, TREX-DM, forbidden-channel annihilation, atomic-clock searches, CMB
spectral-distortion measurements, torsion-balance searches, gamma-ray spectral
lines, and the disk-halo degeneracy. Their zero-match status is preserved in
`outputs/canonical/ontology_inventory.csv` rather than being silently dropped.

## Precision decisions and exclusions

- Candidate families already represented by the released candidate ontology,
  including hidden-sector dark matter, warm dark matter, self-interacting dark
  matter, co-decaying dark matter, and semi-annihilating dark matter, were not
  duplicated as entity nodes.
- Bare `SM`, `GR`, `SR`, `QM`, `ACT`, `SPT`, `ET`, and `CE` were omitted as
  aliases because they are materially ambiguous. Full names or qualified forms
  are used instead.
- Potentially lexical experiment names are case-sensitive or qualified:
  `GENIUS`, `GAPS`, `SIMPLE`, `WARP`, `NEWS-G`, and related acronyms never
  match their lowercase ordinary-language counterparts.
- Facility stages are collapsed only when they belong to the same program and
  retaining them separately would create artificial vertices; examples include
  SNO/SNO+, CUORE/CUORICINO, CAPP/CULTASK, and SDSS/BOSS/eBOSS.
- The sole new automated warning concerned short lowercase surfaces for f(Q)
  gravity. Every flagged occurrence was inspected and referred to the named
  symmetric-teleparallel gravity framework, so the guarded expression was
  retained. The remaining warnings concern pre-existing candidate aliases.

## Verification record

- JSON parsing: passed for all modules.
- Ontology validation: 549 entities and seven relation classes passed ID,
  category, alias-uniqueness, short-acronym, and regex-compilation checks.
- Regression suite: all 18 tests passed, including new cross-layer coverage,
  lexical-acronym, CMB-normalization, and early-universe checks.
- Full canonical rebuild: 22,882 papers; 139,971 occurrences; 34,646 sentence
  co-occurrence events; 75,948 abstract co-occurrence events; and a complete
  1,597-row alias inventory.

This remains a controlled dictionary rather than a claim of final ontological
closure. The zero-match inventory, matched surface forms, and evidence
sentences should be re-audited whenever the corpus or scientific scope changes.
