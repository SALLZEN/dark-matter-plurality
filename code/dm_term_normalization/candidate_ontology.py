"""Shared dark-matter candidate ontology and tag extraction helpers."""

from __future__ import annotations

import re
from typing import Iterable

from .normalization import normalize_segment


def normalize_text(text: str) -> str:
    if not isinstance(text, str):
        return ""
    return normalize_segment(str(text).lower(), mask_math=True)


PATTERNS: dict[str, list[str]] = {
    "wimp": [
        r"(?<!non-)(?<!non\s)\bwimp(?:s)?\b",
        r"(?<!non-)(?<!non\s)\bweakly(?:[-\s])?interacting massive particle(?:s)?\b",
    ],
    "neutralino": [r"\bneutralino(?:s)?\b"],
    "lsp": [
        r"(?<!next-to-)(?<!next-to\s)(?<!next\sto\s)(?<!next-)(?<!next\s)\blightest supersymmetric particle(?:s)?\b",
        r"\bLSP(?:s)?\b",
    ],
    "wino_dm": [r"\bw[-\s]?ino(?:s)?(?:\s+dark\s+matter)?\b"],
    "higgsino_dm": [r"\bhiggsino(?:s)?(?:\s+dark\s+matter)?\b"],
    "bino_dm": [r"\bb[-\s]?ino(?:s)?(?:\s+dark\s+matter)?\b"],
    "sneutrino_dm": [r"\bsneutrino(?:s)?(?:\s+dark\s+matter)?\b"],
    "axino_dm": [r"\baxino(?:s)?(?:\s+dark\s+matter)?\b"],
    "gravitino_dm": [r"\bgravitino(?:s)?(?:\s+dark\s+matter)?\b"],
    "superwimp": [
        r"\bsuper[-\s]?wimp(?:s)?\b",
        r"\bsuper\s*weakly\s*interacting massive particle(?:s)?\b",
        r"\bSWIMP(?:s)?\b",
    ],
    "axion": [r"\baxion(?:s)?\b", r"\bqcd\s+axion(?:s)?\b"],
    "alp": [r"\balp(?:s)?\b", r"\baxion(?:[-\s]?like)?\s+particle(?:s)?\b", r"\baxionlike\s+particle(?:s)?\b"],
    "ula": [r"\bula(?:s)?\b", r"\bultra[-\s]?light\s+axion(?:s)?\b"],
    "fuzzy_dm": [
        r"\bfuzzy\s+dark\s+matter\b",
        r"\bfdm\b",
        r"\bwave[-\s]?dm\b",
        r"\b(?:ψ|\u03c8)\s*dm\b",
        r"\bultra[-\s]?light\s+(?:scalar|boson)\s+dark\s+matter\b",
        r"\bbec\s+dark\s+matter\b",
    ],
    "scalar_field_dm": [r"\bscalar\s+field\s+dark\s+matter\b", r"\bSFDM\b"],
    "superfluid_dm": [r"\bsuperfluid\s+dark\s+matter\b"],
    "sterile_neutrino": [
        r"\bsterile[-\s]?neutrino(?:s)?\b",
        r"\bsterile\s+neutrino\s+dark\s+matter\b",
        r"\bDodelson[-\s]?Widrow\b",
        r"\bShi[-\s]?Fuller\b",
        r"\b\nu[_\s]?s\b",
        r"\bnu[_\s]?s\b",
    ],
    "pbh": [r"\bpbh(?:s)?\b", r"\bprimordial\s+black\s+hole(?:s)?\b", r"\bPBH(?:s)?\b"],
    "macho": [r"\bmacho(?:s)?\b", r"\bmassive\s+compact\s+halo\s+object(?:s)?\b"],
    "macro_dm": [r"\bmacro(?:s)?\b", r"\bmacroscopic\s+dark\s+matter\b"],
    "adm": [r"\basymmetric\s+dark\s+matter\b", r"\bADM\b"],
    "composite_dm": [r"\bcomposite\s+dark\s+matter\b", r"\bdark\s+(?:baryon|baryons|pion|pions|meson|mesons|hadron|hadrons)\b"],
    "atomic_dm": [r"\batomic\s+dark\s+matter\b", r"\bdark\s+atom(?:s)?\b", r"\bdark\s+hydrogen\b", r"\bO[-\s]?He(?:lium)?\b"],
    "mirror_dm": [r"\bmirror\s+(?:dark\s+)?matter\b", r"\bmirror\s+(?:baryon|baryons)\b"],
    "twin_higgs_dm": [r"\btwin\s+higgs\b", r"\btwin\s+baryon(?:s)?\s+dark\s+matter\b", r"\bmirror\s+twin\s+higgs\b"],
    "sidm": [r"\bself[-\s]?interacting\s+dark\s+matter\b", r"\bSIDM\b"],
    "wdm": [r"\bwarm\s+dark\s+matter\b", r"\bWDM\b"],
    "ldm": [r"\blight\s+dark\s+matter\b", r"\bLDM\b", r"\bsub[-\s]?GeV\s+dark\s+matter\b", r"\bMeV[-\s]?scale\s+dark\s+matter\b"],
    "simp": [r"\bstrongly\s+interacting\s+massive\s+particle(?:s)?\b", r"\bSIMP(?:s)?\b"],
    "elder": [r"\bELDER(?:\s*DM)?\b", r"\belastically\s+decoupling\s+relic\b"],
    "fimp": [r"\bfeebly\s+interacting\s+massive\s+particle(?:s)?\b", r"\bFIMP(?:s)?\b", r"\bfreeze[-\s]?in\b"],
    "forbidden_dm": [r"\bforbidden\s+dark\s+matter\b"],
    "secluded_dm": [r"\bsecluded\s+dark\s+matter\b"],
    "cannibal_dm": [r"\bcannibal\s+dark\s+matter\b"],
    "codecaying_dm": [r"\bco[-\s]?decay(?:ing)?\s+dark\s+matter\b"],
    "semiannihilating_dm": [r"\bsemi[-\s]?annihilat(?:ion|ing)\s+dark\s+matter\b"],
    "inelastic_dm": [r"\binelastic\s+dark\s+matter\b", r"\biDM\b", r"\bpseudo[-\s]?Dirac\b"],
    "excited_dm": [r"\bexcited\s+dark\s+matter\b", r"\bXDM\b"],
    "boosted_dm": [r"\bboosted\s+dark\s+matter\b", r"\bBDM\b"],
    "decaying_dm": [r"\bdecay(?:ing)?\s+dark\s+matter\b", r"\bdecay\s+of\s+dark\s+matter\b"],
    "self_heating_dm": [r"\bself[-\s]?heating\s+dark\s+matter\b"],
    "cointeracting_dm": [r"\bco[-\s]?interacting\s+dark\s+matter\b", r"\bCiDM\b"],
    "higgs_portal_dm": [
        r"\bhiggs\s+portal(?:\s+dark\s+matter)?\b",
        r"\bscalar\s+singlet(?:\s+dark\s+matter)?\b",
        r"\breal\s+singlet\s+scalar\b",
        r"\bcomplex\s+scalar\s+dark\s+matter\b",
        r"\bsinglet\s+scalar\s+dm\b",
    ],
    "z_portal_dm": [r"\bz['’\-]?\s*portal\b", r"\bz[-\s]?portal\b"],
    "neutrino_portal_dm": [r"\bneutrino\s+portal(?:\s+dark\s+matter)?\b"],
    "vector_dm": [r"\bvector\s+dark\s+matter\b", r"\bVDM\b"],
    "dark_photon_dm": [
        r"\bdark\s+photon(?:s)?\b",
        r"\bhidden\s+photon(?:s)?\b",
        r"\bpara[-\s]?photon(?:s)?\b",
        r"\bA['′]?\s*prime\b",
        r"\bA['′]\b",
        r"\bZ[_-]?[dD]\b",
        r"\bdark\s+Z\b",
        r"\bU\(1\)['’]?\b",
        r"\bdark\s+U\(1\)\b",
        r"\bkinetic\s+mixing\b",
    ],
    "millicharged_dm": [r"\bmilli[-\s]?charged\s+(?:particle|dark\s+matter)(?:s)?\b", r"\bmillicharged\b", r"\bmCP(?:s)?\b"],
    "anapole_dm": [r"\banapole\s+dark\s+matter\b"],
    "dipole_dm": [r"\b(?:magnetic|electric)\s+dipole\s+dark\s+matter\b", r"\brayleigh\s+dark\s+matter\b"],
    "glueball_dm": [r"\bglueball\s+dark\s+matter\b", r"\bdark\s+glueball(?:s)?\b", r"\bhidden[-\s]?glue\b"],
    "hidden_sector_dm": [r"\bhidden[-\s]?sector\s+(?:dark\s+)?matter\b", r"\bdark\s+sector\s+(?:dark\s+)?matter\b", r"\bsecluded\s+sector\b"],
    "kk_dm": [r"\bkaluza[-\s]?klein\s+(?:dark\s+)?matter\b", r"\bkk\s+dark\s+matter\b", r"\blightest\s+kaluza[-\s]?klein\s+particle\b", r"\bLKP\b"],
    "ued_dm": [r"\buniversal\s+extra\s+dimension(?:s)?\b", r"\bUED\b", r"\bB\(1\)\b"],
    "wimpzilla": [r"\bwimpzilla(?:s)?\b", r"\bsuperheavy\s+dark\s+matter\b"],
    "qball_dm": [r"\bq[-\s]?ball(?:s)?\b(?:.*?\bdark\s+matter\b)?"],
    "quark_nugget_dm": [r"\baxion\s+quark\s+nugget(?:s)?\b", r"\bAQN\b", r"\bquark\s+nugget(?:s)?\b", r"\bnuclearite(?:s)?\b", r"\bstrange\s+quark\s+matter\b", r"\bstrangelet(?:s)?\b"],
    "minimal_dm": [r"\bminimal\s+dark\s+matter\b"],
    "inert_doublet_dm": [r"\binert\s+doublet\s+model\b", r"\bIDM\b"],
    "inert_triplet_dm": [r"\binert\s+triplet\s+model\b", r"\bITM\b"],
    "scotogenic_dm": [r"\bscotogenic\b"],
    "majoron_dm": [r"\bmajoron(?:s)?\b"],
    "leptophilic_dm": [r"\bleptophilic\s+dark\s+matter\b"],
    "leptophobic_dm": [r"\bleptophobic\s+dark\s+matter\b"],
    "hadrophilic_dm": [r"\bhadrophilic\s+dark\s+matter\b"],
    "isospin_violating_dm": [r"\bisospin[-\s]?violat(?:ing|ion)\s+dark\s+matter\b", r"\bIVDM\b"],
    "planckian_dm": [r"\bplanckian\s+interacting\s+(?:massive\s+)?particle(?:s)?\b", r"\bPIDM\b"],
    "partially_interacting_dm": [r"\bpartially\s+interacting\s+dark\s+matter\b"],
}

PATTERNS["alp"][0] = r"\bALP(?:s)?\b(?!\s*(?:II|III|experiment|collaboration))"

AMBIGUOUS_REQUIRES_DM_NEARBY = {
    "glueball_dm",
    "hidden_sector_dm",
    "ued_dm",
    "z_portal_dm",
    "dark_photon_dm",
    "kk_dm",
    "vector_dm",
    "millicharged_dm",
    "qball_dm",
    "majoron_dm",
    "scotogenic_dm",
    "inert_doublet_dm",
    "inert_triplet_dm",
    "minimal_dm",
    "higgs_portal_dm",
    "neutrino_portal_dm",
    "partially_interacting_dm",
}
CONTEXT_WINDOW_OVERRIDES = {
    # Development review found an explicit "dark glueball ... dark matter
    # candidate" construction whose short parenthetical description separates
    # the two expressions by more than the default 60-character window.
    "glueball_dm": 160,
}
NEAR_DM = re.compile(r"\b(dark\s+matter|DM)\b", re.I)
COMPILED = {tag: [re.compile(p, re.I) for p in pats] for tag, pats in PATTERNS.items()}


def dm_nearby_in_window(text: str, span: tuple[int, int], window: int = 60) -> bool:
    start = max(0, span[0] - window)
    end = min(len(text), span[1] + window)
    return bool(NEAR_DM.search(text[start:end]))


def extract_dm_tags_with_spans(text: str, window: int = 60) -> tuple[list[str], list[tuple[int, int]]]:
    """Return canonical tags and spans in first-mention order."""
    text = text if isinstance(text, str) else ""
    if not text:
        return [], []

    hits: list[tuple[int, str, tuple[int, int]]] = []
    for tag, regexes in COMPILED.items():
        for regex in regexes:
            match = regex.search(text)
            if not match:
                continue
            context_window = CONTEXT_WINDOW_OVERRIDES.get(tag, window)
            if tag in AMBIGUOUS_REQUIRES_DM_NEARBY and not dm_nearby_in_window(
                text, match.span(), context_window
            ):
                break
            hits.append((match.start(), tag, match.span()))
            break

    seen: set[str] = set()
    tags: list[str] = []
    spans: list[tuple[int, int]] = []
    for _, tag, span in sorted(hits, key=lambda item: item[0]):
        if tag in seen:
            continue
        seen.add(tag)
        tags.append(tag)
        spans.append(span)
    return tags, spans


DM_TAGS_INFO: dict[str, dict[str, str]] = {
    "wimp": {"full": "Weakly Interacting Massive Particle (WIMP)", "category": "candidate"},
    "neutralino": {"full": "Neutralino (SUSY LSP)", "category": "candidate"},
    "lsp": {"full": "Lightest Supersymmetric Particle (LSP)", "category": "candidate"},
    "wino_dm": {"full": "Wino", "category": "candidate"},
    "higgsino_dm": {"full": "Higgsino", "category": "candidate"},
    "bino_dm": {"full": "Bino", "category": "candidate"},
    "sneutrino_dm": {"full": "Sneutrino", "category": "candidate"},
    "axino_dm": {"full": "Axino", "category": "candidate"},
    "gravitino_dm": {"full": "Gravitino", "category": "candidate"},
    "superwimp": {"full": "SuperWIMP", "category": "candidate"},
    "axion": {"full": "QCD Axion", "category": "candidate"},
    "alp": {"full": "Axion-Like Particle (ALP)", "category": "candidate"},
    "ula": {"full": "Ultralight Axion (ULA)", "category": "candidate"},
    "fuzzy_dm": {"full": "Fuzzy / waveDM", "category": "candidate"},
    "scalar_field_dm": {"full": "Scalar Field (SFDM)", "category": "candidate"},
    "superfluid_dm": {"full": "Superfluid", "category": "candidate"},
    "sterile_neutrino": {"full": "Sterile Neutrino", "category": "candidate"},
    "pbh": {"full": "Primordial Black Hole (PBH)", "category": "candidate"},
    "macho": {"full": "Massive Compact Halo Object (MACHO)", "category": "candidate"},
    "macro_dm": {"full": "Macroscopic (Macros)", "category": "candidate"},
    "quark_nugget_dm": {"full": "Quark Nugget / Nuclearite / Strangelet (AQN)", "category": "candidate"},
    "adm": {"full": "Asymmetric (ADM)", "category": "candidate"},
    "composite_dm": {"full": "Composite", "category": "candidate"},
    "atomic_dm": {"full": "Atomic", "category": "candidate"},
    "mirror_dm": {"full": "Mirror Sector", "category": "candidate"},
    "twin_higgs_dm": {"full": "Twin Higgs", "category": "candidate"},
    "glueball_dm": {"full": "Glueball", "category": "candidate"},
    "dark_photon_dm": {"full": "Dark Photon / Hidden Photon", "category": "candidate"},
    "vector_dm": {"full": "Vector", "category": "candidate"},
    "higgs_portal_dm": {"full": "Higgs Portal", "category": "portal"},
    "neutrino_portal_dm": {"full": "Neutrino Portal", "category": "portal"},
    "z_portal_dm": {"full": "Z/Z' Portal", "category": "portal"},
    "hidden_sector_dm": {"full": "Hidden Sector / Dark Sector", "category": "umbrella"},
    "secluded_dm": {"full": "Secluded", "category": "portal"},
    "kk_dm": {"full": "Kaluza-Klein", "category": "candidate"},
    "ued_dm": {"full": "Universal Extra Dimensions (LKP)", "category": "candidate"},
    "wimpzilla": {"full": "WIMPzilla", "category": "candidate"},
    "planckian_dm": {"full": "Planckian Interacting (PIDM)", "category": "candidate"},
    "partially_interacting_dm": {"full": "Partially Interacting", "category": "interaction"},
    "qball_dm": {"full": "Q-ball", "category": "candidate"},
    "majoron_dm": {"full": "Majoron", "category": "candidate"},
    "minimal_dm": {"full": "Minimal SU(2)_L multiplet", "category": "candidate"},
    "inert_doublet_dm": {"full": "Inert Doublet Model (IDM)", "category": "candidate"},
    "inert_triplet_dm": {"full": "Inert Triplet Model (ITM)", "category": "candidate"},
    "scotogenic_dm": {"full": "Scotogenic Model", "category": "candidate"},
    "wdm": {"full": "Warm (WDM)", "category": "umbrella"},
    "ldm": {"full": "Light (sub-GeV/MeV-scale)", "category": "umbrella"},
    "sidm": {"full": "Self-Interacting (SIDM)", "category": "interaction"},
    "inelastic_dm": {"full": "Inelastic (iDM)", "category": "interaction"},
    "excited_dm": {"full": "Excited (XDM)", "category": "interaction"},
    "boosted_dm": {"full": "Boosted (BDM)", "category": "interaction"},
    "simp": {"full": "Strongly Interacting Massive Particle (SIMP)", "category": "interaction"},
    "fimp": {"full": "Feebly Interacting Massive Particle (FIMP)", "category": "mechanism"},
    "elder": {"full": "ELDER", "category": "mechanism"},
    "forbidden_dm": {"full": "Forbidden-Channel", "category": "mechanism"},
    "codecaying_dm": {"full": "Co-decaying", "category": "mechanism"},
    "cointeracting_dm": {"full": "Co-interacting", "category": "interaction"},
    "semiannihilating_dm": {"full": "Semi-annihilating", "category": "interaction"},
    "cannibal_dm": {"full": "Cannibal", "category": "mechanism"},
    "self_heating_dm": {"full": "Self-heating", "category": "mechanism"},
    "decaying_dm": {"full": "Decaying", "category": "mechanism"},
    "isospin_violating_dm": {"full": "Isospin-Violating (IVDM)", "category": "interaction"},
    "leptophilic_dm": {"full": "Leptophilic", "category": "interaction"},
    "leptophobic_dm": {"full": "Leptophobic", "category": "interaction"},
    "hadrophilic_dm": {"full": "Hadrophilic", "category": "interaction"},
    "millicharged_dm": {"full": "Millicharged", "category": "interaction"},
    "dipole_dm": {"full": "Dipole-Interacting", "category": "interaction"},
    "anapole_dm": {"full": "Anapole", "category": "interaction"},
}

CANDIDATE_TAGS = {tag for tag, info in DM_TAGS_INFO.items() if info.get("category") == "candidate"}

SPECIES_LABEL_MAP = {
    "wimp": "Generic WIMP",
    "neutralino": "Neutralino",
    "lsp": "LSP",
    "wino_dm": "Wino",
    "higgsino_dm": "Higgsino",
    "bino_dm": "Bino",
    "sneutrino_dm": "Sneutrino",
    "axino_dm": "Axino",
    "gravitino_dm": "Gravitino",
    "superwimp": "SuperWIMP",
    "axion": "Axion + ALP",
    "alp": "Axion + ALP",
    "ula": "ULA / Fuzzy",
    "fuzzy_dm": "ULA / Fuzzy",
    "scalar_field_dm": "SFDM",
    "superfluid_dm": "Superfluid DM",
    "sterile_neutrino": "Sterile nu",
    "pbh": "PBH",
    "macho": "MACHO",
    "macro_dm": "Macroscopic DM",
    "quark_nugget_dm": "Quark Nugget / AQN",
    "adm": "Asymmetric DM",
    "composite_dm": "Generic Composite",
    "atomic_dm": "Atomic DM",
    "mirror_dm": "Mirror DM",
    "twin_higgs_dm": "Twin Higgs",
    "glueball_dm": "Glueball",
    "dark_photon_dm": "Dark Photon",
    "vector_dm": "Vector DM",
    "kk_dm": "LKP Kaluza-Klein",
    "ued_dm": "LKP Kaluza-Klein",
    "wimpzilla": "WIMPzilla",
    "planckian_dm": "Planckian DM",
    "qball_dm": "Q-ball",
    "majoron_dm": "Majoron",
    "minimal_dm": "Minimal SU(2)L",
    "inert_doublet_dm": "Inert Doublet Model",
    "inert_triplet_dm": "Inert Triplet Model",
    "scotogenic_dm": "Scotogenic Model",
}


def expand_dm_tags(tags: Iterable[str] | None) -> list[str]:
    if not isinstance(tags, (list, tuple)):
        return []
    return [DM_TAGS_INFO.get(tag, {}).get("full", tag) for tag in tags]


def filter_candidate_tags(tags: Iterable[str] | None) -> list[str]:
    if not isinstance(tags, (list, tuple)):
        return []
    return [tag for tag in tags if tag in CANDIDATE_TAGS]


def candidate_species_labels(tags: Iterable[str] | None) -> list[str]:
    if not isinstance(tags, (list, tuple)):
        return []
    labels: list[str] = []
    seen: set[str] = set()
    for tag in tags:
        label = SPECIES_LABEL_MAP.get(tag, DM_TAGS_INFO.get(tag, {}).get("full", tag))
        if label in seen:
            continue
        seen.add(label)
        labels.append(label)
    return labels


def primary_arxiv_class(classes: Iterable[str] | None) -> str | None:
    if isinstance(classes, (list, tuple)):
        for value in classes:
            if isinstance(value, str) and value.strip():
                return value.strip()
    return None


def categorize_arxiv(arxiv_class: str | None) -> str:
    if not isinstance(arxiv_class, str):
        return "Other"
    if re.match(r"^astro", arxiv_class):
        return "astrophysics"
    if re.match(r"^hep-", arxiv_class):
        return "high-energy physics"
    if re.match(r"^cond-mat", arxiv_class):
        return "condensed matter"
    if re.match(r"^math", arxiv_class):
        return "mathematics"
    if re.match(r"^cs", arxiv_class):
        return "computer science"
    if re.match(r"^quant-ph", arxiv_class):
        return "quantum physics"
    if re.match(r"^gr-qc", arxiv_class):
        return "general relativity and quantum cosmology"
    if re.match(r"^nucl-", arxiv_class):
        return "nuclear physics"
    if re.match(r"^physics", arxiv_class):
        return "physics"
    if re.match(r"^q-bio", arxiv_class):
        return "quantitative biology"
    if re.match(r"^q-fin", arxiv_class):
        return "quantitative finance"
    if re.match(r"^stat", arxiv_class):
        return "statistics"
    if re.match(r"^econ", arxiv_class):
        return "economics"
    if re.match(r"^eess", arxiv_class):
        return "electrical engineering and systems science"
    if re.match(r"^nlin", arxiv_class):
        return "nonlinear sciences"
    return "Other"


__all__ = [
    "PATTERNS",
    "AMBIGUOUS_REQUIRES_DM_NEARBY",
    "CONTEXT_WINDOW_OVERRIDES",
    "NEAR_DM",
    "COMPILED",
    "DM_TAGS_INFO",
    "CANDIDATE_TAGS",
    "SPECIES_LABEL_MAP",
    "normalize_text",
    "dm_nearby_in_window",
    "extract_dm_tags_with_spans",
    "expand_dm_tags",
    "filter_candidate_tags",
    "candidate_species_labels",
    "primary_arxiv_class",
    "categorize_arxiv",
]
