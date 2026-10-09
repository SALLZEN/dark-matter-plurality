
import re

TOK_PAT = re.compile(r"[a-z]+(?:-[a-z]+)?")

def norm(s: str) -> str:
    return re.sub(r"\s+", " ", s.lower()).strip()

def _flex_phrase(phrase: str) -> str:
    p = re.escape(phrase.strip())
    p = p.replace(r"\ ", r"[\s\-]+")
    return rf"\b{p}\b"

def preproc(text: str) -> str:
    text = norm(text)

    # ── strip parenthetical abbreviations ────────────────────────────────────
    text = re.sub(r"\(\s*[\w\-']+\s*\)", "", text)
    text = norm(text)

    # ── possessive/plural apostrophe normalization ────────────────────────────
    text = re.sub(r"\bpbh's\b",  "pbh",                 text)
    text = re.sub(r"\bwimp's\b", "wimp",                text)
    text = re.sub(r"\blsp's\b",  "neutralino",          text)
    text = re.sub(r"\bxray\b",  "x-ray",                text)
    text = re.sub(r"\bx ray\b",  "x-ray",                text)
    text = re.sub(r"\bpeculiar\b(?!\s+velocity)", "",   text)
    text = re.sub(r"\bn-body\b", "n-body",               text)
    text = re.sub(r"\bn body\b", "n-body",               text)
    text = re.sub(r"\bweakly[-\s]+interacting[-\s]+massive[-\s]+particle(s)?\b", "wimp", text)
    text = re.sub(r"\bnonbaryonic\b", "non-baryonic",   text)
    text = re.sub(r"\bnon baryonic\b", "non-baryonic",  text)
    text = re.sub(r"\bnonlinear\b", "non-linear",       text)
    text = re.sub(r"\bnon linear\b", "non-linear",      text)
    text = re.sub(r"\bq-balls\b", "qball",              text)
    text = re.sub(r"\bq balls\b", "qball",             text)
    text = re.sub(r"\bq-ball\b", "qball",              text)
    text = re.sub(r"\bq ball\b", "qball",              text)
    text = re.sub(r"\bbiased\b", "bias",                text)
    text = re.sub(r"\bnonrelativistic\b", "non-relativistic", text)
    text = re.sub(r"\bvectorlike\b", "vector-like", text)
    text = re.sub(r"\bgamma[-\s]+ray(s)?\b", "gamma-ray", text)
    text = re.sub(r"\bcosmic[-\s]+ray(s)?\b", "cosmic-ray", text)
    text = re.sub(r"\bx[-\s]+ray(s)?\b", "x-ray", text)

    # ── multi-word phrase normalization (longest first) ───────────────────────
    phrase_map = [
        ("deep learning",                       "deep-learning"),
        ("supervised learning",                 "supervised-learning"),
        ("unsupervised learning",               "unsupervised-learning"),
        ("milky way-like",                      "milky-way-like"),
        ("milky-way like",                      "milky-way-like"),
        ("milky way",                           "milky-way"),
        ("feebly interacting",                  "feebly-interacting"),
        ("feeble interaction",                  "feeble-interaction"),
        ("las campanas redshift survey",        "las-campanas"),
        ("las campanas",                        "las-campanas"),
        ("hubble space telescope",              "hst"),
        ("hubble telescope",                    "hst"),
        ("event horizon telescope",             "eht"),
        ("baryon acoustic oscillation",         "bao"),
        ("baryon acoustic oscillations",        "bao"),
        ("acoustic oscillations",               "bao"),
        ("markov chain monte carlo",            "mcmc"),
        ("monte carlo markov chain",            "mcmc"),
        ("james webb space telescope",          "jwst"),
        ("james webb telescope",                "jwst"),
        ("james webb",                          "jwst"),
        ("lambda cold dark matter",             "lambda-cold-dark-matter"),
        ("weakly interacting massive particles", "wimp"),
        ("weakly interacting massive particle",  "wimp"),
        ("primordial black holes",               "pbh"),
        ("primordial black hole",                "pbh"),
        ("lightest supersymmetry particle",      "neutralino"),
        ("lightest supersymmetric particle",     "neutralino"),
        ("modified newtonian dynamics",          "mond"),
        ("cold dark matter",                     "cold-dark-matter"),
        ("hot dark matter",                      "hot-dark-matter"),
        ("warm dark matter",                     "warm-dark-matter"),
        ("fuzzy dark matter",                    "fuzzy-dark-matter"),
        ("self-interacting dark matter",         "sidm"),
        ("modified gravity",                     "modified-gravity"),
        ("direct detection",                     "direct-detection"),
        ("indirect detection",                   "indirect-detection"),
        ("direct search",                        "direct-search"),
        ("indirect search",                      "indirect-search"),
        ("direct and indirect detection",        "direct-indirect-detection"),
        ("direct and indirect searches",         "direct-indirect-search"),
        ("direct and indirect search",           "direct-indirect-search"),
        ("direct indirect",                      "direct-indirect"),
        ("elastic scattering",                   "elastic-scattering"),
        ("cross section",                        "cross-section"),
        ("density profile",                      "density-profile"),
        ("central density",                      "central-density"),
        ("neutrino masses",                      "neutrino-mass"),
        ("neutrino mass",                        "neutrino-mass"),
        ("future experiments",                   "future-experiment"),
        ("future experiment",                    "future-experiment"),
        ("direct-detection experiments",         "direct-detection-experiment"),
        ("direct-detection experiment",          "direct-detection-experiment"),
        ("search experiments",                   "search-experiment"),
        ("search experiment",                    "search-experiment"),
        ("detector search",                      "detector-search"),
        ("physics search",                       "physics-search"),
        ("region parameter",                     "region-parameter"),
        ("right-handed neutrinos",               "right-handed-neutrino"),
        ("right-handed neutrino",                "right-handed-neutrino"),
        ("stellar masses",                       "stellar-mass"),
        ("stellar mass",                         "stellar-mass"),
        ("white dwarfs",                         "white-dwarf"),
        ("white dwarf",                          "white-dwarf"),
        ("white-dwarf star",                     "white-dwarf"),
        ("brown dwarfs",                         "brown-dwarf"),
        ("brown dwarf",                          "brown-dwarf"),
        ("brown-dwarf star",                     "brown-dwarf"),
        ("massive compact objects",              "massive-compact-object"),
        ("massive compact object",               "massive-compact-object"),
        ("n-body simulation",                    "n-body-simulation"),
        ("hydrodynamic simulation",              "hydrodynamic-simulation"),
        ("hydrodynamical simulation",            "hydrodynamic-simulation"),
        ("numerical simulation",                 "numerical-simulation"),
        ("body simulation",                      "n-body-simulation"),
        ("neutrinoless double beta decay",       "neutrinoless-double-beta-decay"),
        ("viable candidate",                     "viable-candidate"),
        ("powerful probe",                       "powerful-probe"),
        ("excellent agreement",                  "excellent-agreement"),
        ("evidence existence",                   "evidence-existence"),
        ("initial conditions",                   "initial-condition"),
        ("initial condition",                    "initial-condition"),
        ("gravitational lensing",                "gravitational-lensing"),
        ("galactic center",                      "galactic-center"),
        ("pulsar timing",                        "pulsar-timing"),
        ("axion-like particles",                 "axion-like particle"),
        ("axionlike particles",                  "axion-like particle"),
        ("axionlike particle",                   "axion-like particle"),
        ("dark-matter",                          "dark matter"),
        ("sloan digital sky survey",             "sdss"),
        ("sloan digital sky",                    "sdss"),
        ("weak gravitational lensing",           "weak-lensing"),
        ("weak lensing",                         "weak-lensing"),
        ("missing transverse momentum",          "missing-transverse-momentum"),
        ("missing transverse energy",            "missing-transverse-energy"),
    ]

    for phrase, replacement in phrase_map:
        text = re.sub(_flex_phrase(phrase), replacement, text)

    # ── abbreviation normalization ────────────────────────────────────────────
    abbrev_map = [
        (r"\bwimps\b",          "wimp"),
        (r"\bwimp's\b",         "wimp"),
        (r"\bsusy\b",           "supersymmetry"),
        (r"\bsupersymmetric\b", "supersymmetry"),
        (r"\blsp\b",            "neutralino"),
        (r"\bpbhs\b",           "pbh"),
        (r"\bmond\b",           "mond"),
        (r"\balp\b",            "axion-like particle"),
        (r"\balps\b",           "axion-like particle"),
        (r"\bmcmcs\b",          "mcmc"),
        (r"\bmcmc's\b",         "mcmc"),
        (r"\btrain\b",          "trained"),
    ]

    for pattern, replacement in abbrev_map:
        text = re.sub(pattern, replacement, text)

    # ── plural normalization ──────────────────────────────────────────────────
    plural_map = [
        (r"\bdistributions\b", "distribution"),
        (r"\bprofiles\b", "profile"),
        (r"\blimits\b", "limit"),
        (r"\bdecays\b", "decay"),
        (r"\bcouplings\b", "coupling"),
        (r"\binteractions\b", "interaction"),
        (r"\bstructures\b", "structure"),
        (r"\bsignals\b", "signal"),
        (r"\bfunctions\b", "function"),
        (r"\bbounds\b", "bound"),
        (r"\bmasses\b", "mass"),
        (r"\bradii\b", "radius"),
        (r"\bcomponents\b", "component"),
        (r"\bbaryons\b", "baryon"),
        (r"\bmesons\b", "meson"),
        (r"\bdoublets\b", "doublet"),
        (r"\bdetectors\b", "detector"),
        (r"\bsingletons\b", "singlet"),
        (r"\bsinglets\b", "singlet"),
        (r"\bpredictions\b", "prediction"),
        (r"\bperturbations\b", "perturbation"),
        (r"\bsurveys\b", "survey"),
        (r"\bsources\b", "source"),
        (r"\bestimates\b", "estimate"),
        (r"\bestimated\b", "estimate"),
        (r"\bbiases\b", "bias"),
        (r"\bmergers\b", "merger"),
        ("black holes",                         "black-hole"),
        ("black hole",                          "black-hole"),
        ("supermassive black hole",             "supermassive-black-hole"),
        (r"\bredshifts\b",                      "redshift"),
        (r"\bvelocities\b",                     "velocity"),
        (r"\baxions\b",                         "axion"),
        (r"\bdetectors\b",                      "detector"),
        (r"\bparticles\b",                      "particle"),
        (r"\bneutralinos\b",                    "neutralino"),
        (r"\bneutrinos\b",                      "neutrino"),
        (r"\bphotons\b",                        "photon"),
        (r"\bclusters\b",                       "cluster"),
        (r"\bhalos\b",                          "halo"),
        (r"\bhaloes\b",                         "halo"),
        (r"\bsubhalos\b",                       "subhalo"),
        (r"\bsubhaloes\b",                      "subhalo"),
        (r"\bphotinos\b",                       "photino"),
        (r"\bholes\b",                          "hole"),
        (r"\bgravitational waves\b",            "gravitational wave"),
        (r"\bneutron stars\b",                  "neutron star"),
        (r"\brotation curves\b",                "rotation curve"),
        (r"\bdensity profiles\b",               "density-profile"),
        (r"\bgamma rays\b",                     "gamma-ray"),
        (r"\bpeculiar velocities\b",            "peculiar velocity"),
        (r"\bexperiments\b",                    "experiment"),
        (r"\bsearches\b",                       "search"),
        (r"\bdirect detections\b",              "direct-detection"),
        (r"\bindirect detections\b",            "indirect-detection"),
        (r"\bdirect searches\b",                "direct-search"),
        (r"\bindirect searches\b",              "indirect-search"),
        (r"\belastic scatterings\b",            "elastic-scattering"),
        (r"\bgravitational lensings\b",         "gravitational-lensing"),
        (r"\bgalactic centers\b",               "galactic-center"),
        (r"\bpulsar timings\b",                 "pulsar-timing"),
        (r"\bbody simulations\b",               "n-body-simulation"),
        (r"\borders\b",                         "order"),
        (r"\brecoils\b",                        "recoil"),
        (r"\bneural networks\b",                "neural-network"),
        (r"\bneural network\b",                 "neural-network"),
        (r"\bmachine learning\b",               "machine-learning"),
        (r"\bnumerical simulations\b",          "numerical-simulation"),
        (r"\bhigh-resolution simulations\b",    "high-resolution simulation"),
        (r"\bhydrodynamical simulations\b",     "hydrodynamic-simulation"),
        (r"\bhydrodynamic simulations\b",       "hydrodynamic-simulation"),
        (r"\bzoom-in simulations\b",            "zoom-in simulation"),
        (r"\bmatter-only simulations\b",        "matter-only simulation"),
        (r"\bdark-matter-only simulations\b",   "dark-matter-only simulation"),
        (r"\bdensity perturbations\b",          "density perturbation"),
        (r"\bdensity fluctuations\b",           "density fluctuation"),
        (r"\bangular scales\b",                 "angular scale"),
        (r"\bpower spectra\b",                  "power spectrum"),
        (r"\bsimulations\b",                    "simulation"),
        (r"\bfluctuations\b",                   "fluctuation"),
        (r"\bperturbations\b",                  "perturbation"),
        (r"\bcandidates\b",                     "candidate"),
        (r"\bcosmions\b",                       "cosmion"),
        (r"\bcross sections\b",                 "cross-section"),
        (r"\bcentral densities\b",              "central-density"),
        (r"\bfuture experiments\b",             "future-experiment"),
        (r"\bdirect-detection experiments\b",   "direct-detection-experiment"),
        (r"\bright-handed neutrinos\b",         "right-handed-neutrino"),
        (r"\bstellar masses\b",                 "stellar-mass"),
        (r"\bstars\b",                          "star"),
    ]

    for pattern, replacement in plural_map:
        text = re.sub(pattern, replacement, text)

    # ── final variant collapsing ──────────────────────────────────────────────
    text = re.sub(r"\bgravitational[- ]wave\b", "gravitational_wave", text)
    text = re.sub(r"\bgamma[- ]ray\b", "gamma_ray", text)
    text = re.sub(r"\blambda-cold-dark matter\b", "lambda-cold-dark-matter", text)
    text = re.sub(r"\bn-n-body-simulation\b", "n-body-simulation", text)
    text = re.sub(r"\bneutrinoless[- ]double\b", "neutrinoless-double", text)

    # ── deduplicate adjacent identical tokens ─────────────────────────────────
    prev = None
    while text != prev:
        prev = text
        text = re.sub(r"\b(\w[\w\-]*)\s+\1\b", r"\1", text)

    return text


def tokenize_preproc_text(text: str) -> list[str]:
    processed = preproc(text)
    if not processed:
        return []
    return TOK_PAT.findall(processed)
