"""Shared text normalization utilities for dark-matter corpus extraction."""

import html
import re
import unicodedata
from functools import lru_cache

TARGET = "dark matter"
pat = re.compile(r"\bdark(?:\s+|-)matter\b", re.IGNORECASE)

MAX_CTX_WORDS = 220
MIN_CTX_WORDS = 12
MIN_CENTER_SENT_WORDS = 6
SOFT_CTX_WORDS = 140
MAX_DM_PER_CTX = 2
MAX_MATH_TOKENS_PER_CTX = 2

MISSING_SPACE_AFTER_PUNCT_RE = re.compile(r"(?<=[\.\?\!;:])(?=[A-Za-z])")
ACRONYM_PAREN_RE = re.compile(
    r"(?P<prefix>\b(?:[A-Za-z][A-Za-z+\-/]*\s+){1,8})"
    r"\(\s*(?P<acro>(?:[A-Za-z][A-Za-z0-9+\-/]*\s+){0,5}[A-Za-z][A-Za-z0-9+\-/]*)\s*\)"
)
SHORT_LONG_PAREN_RE = re.compile(
    r"\b(?P<short>[A-Za-z][A-Za-z0-9+\-]{1,20})\s*"
    r"\(\s*(?P<long>(?:[A-Za-z][A-Za-z0-9+\-/]*\s+){1,8}[A-Za-z][A-Za-z0-9+\-/]*)\s*\)"
)

# ── Regex patterns ───────────────────────────────────────────────────────
TAG_RE = re.compile(r"<[^>]+>")
ADS_CODE_RE = re.compile(r"\b[A-Z]{4,}[A-Z0-9]{6,}\b")
DOI_RE = re.compile(r"\b10\.\d{4,9}/\S+\b", re.I)
ARXIV_RE = re.compile(
    r"\barxiv\s*:?\s*(?:\d{4}\.\d{4,5}(?:v\d+)?|[a-z\-]+(?:\.[A-Z]{2})?/\d{7})(?!\w)",
    re.I,
)
LATEX_INLINE_DOLLAR_RE = re.compile(r"\$[^$]{0,500}\$")
LATEX_PAREN_RE = re.compile(r"\\\((.{0,500}?)\\\)")
LATEX_BRACK_RE = re.compile(r"\\\[(.{0,2000}?)\\\]")
LATEX_CMD_ARG_RE = re.compile(r"\\[A-Za-z]+\*?(?:\[[^\]]{0,200}\])?\{[^{}]{0,500}\}")
LATEX_CMD_RE = re.compile(r"\\[A-Za-z]+\*?")
BRACE_RE = re.compile(r"[{}]")

BRACKET_CITEISH_RE = re.compile(
    r"\[(?=[^\]]{0,300}\])"
    r"(?=.*\b(et al\.|Phys\.|Rev\.|Lett\.|ApJ|MNRAS|A\&A|JCAP|JHEP|Nature|Science)\b"
    r"|.*\b(19|20)\d{2}\b"
    r"|.*\bdoi\b"
    r")"
    r"[^\]]{0,300}\]",
    re.I
)
SHORT_BRACKET_CITE_RE = re.compile(r"\[[A-Za-z&\.\s]{2,20},\s*\d{1,4},\s*\d{1,4}\]", re.I)
EMPTY_BRACKETS_RE = re.compile(r"\[\s*\]")
BULLET_RE = re.compile(r"(?:^|\s)\*\s+")
QUOTED_TERM_DQ_RE = re.compile(r'"([^"]{1,40})"')
QUOTED_TERM_SQ_RE = re.compile(r"'([^']{1,40})'")

SAFE_PHRASE_NORMALIZATIONS = [
    (r"\bdark-matter\b", "dark matter"),
    (r"\bweakly[-\s]+interacting[-\s]+massive[-\s]+particles?\b", "wimp"),
    (r"\bprimordial black holes?\b", "pbh"),
    (r"\baxion[-\s]+like particles?\b", "axion-like particle"),
    (r"\bself[-\s]+interacting dark matter\b", "self-interacting dark matter"),
    (r"\bcold dark matter\b", "cold dark matter"),
    (r"\bhot dark matter\b", "hot dark matter"),
    (r"\bwarm dark matter\b", "warm dark matter"),
    (r"\bfuzzy dark matter\b", "fuzzy dark matter"),
]

SAFE_TOKEN_NORMALIZATIONS = [
    (r"\bxray\b", "x-ray"),
    (r"\bx ray\b", "x-ray"),
    (r"\bcmb\b", "cosmic microwave background"),
    (r"\bnonbaryonic\b", "non-baryonic"),
    (r"\bnon baryonic\b", "non-baryonic"),
    (r"\bnonlinear\b", "non-linear"),
    (r"\bnon linear\b", "non-linear"),
    (r"\beoss\b", "equations of state"),
    (r"\beos\b", "equation of state"),
    (r"\bn body\b", "n-body"),
    (r"\bq-balls\b", "qball"),
    (r"\bq-ball\b", "qball"),
    (r"\bq balls\b", "qball"),
    (r"\bq ball\b", "qball"),
    (r"\bwimps\b", "wimp"),
    (r"\bpbhs\b", "pbh"),
    (r"\balps\b", "axion-like particle"),
    (r"\balp\b", "axion-like particle"),
    (r"\bhaloes\b", "halo"),
    (r"\bhalos\b", "halo"),
    (r"\bsubhaloes\b", "subhalo"),
    (r"\bsubhalos\b", "subhalo"),
    (r"\brotation curves\b", "rotation curve"),
    (r"\bdensity profiles\b", "density profile"),
    (r"\bpower spectra\b", "power spectrum"),
    (r"\binitial conditions\b", "initial condition"),
    (r"\bgravitational waves\b", "gravitational wave"),
    (r"\bgamma rays\b", "gamma ray"),
    (r"\bneutron stars\b", "neutron star"),
    (r"\bnumerical simulations\b", "numerical simulation"),
    (r"\bhydrodynamical simulations\b", "hydrodynamical simulation"),
    (r"\bhigh-resolution simulations\b", "high-resolution simulation"),
    (r"\bzoom-in simulations\b", "zoom-in simulation"),
    (r"\bmatter-only simulations\b", "matter-only simulation"),
    (r"\bdark-matter-only simulations\b", "dark-matter-only simulation"),
    (r"\bsimulations\b", "simulation"),
    (r"\bfluctuations\b", "fluctuation"),
    (r"\bperturbations\b", "perturbation"),
    (r"\bcandidates\b", "candidate"),
]

# Safe, semantically helpful abbreviation expansions for the dark-matter
# annotation task. These are good candidates for explicit expansion if we
# later decide to make inference inputs more readable for the labeler model.
SAFE_ABBREV_EXPANSIONS = {
    "cdm": "cold dark matter",
    "wdm": "warm dark matter",
    "hdm": "hot dark matter",
    "chdm": "cold plus hot dark matter",
    "lcdm": "lambda cold dark matter",
    "lambda cdm": "lambda cold dark matter",
    "lambda-cdm": "lambda cold dark matter",
    "lambda cold dark matter": "lambda cold dark matter",
    "wimp": "weakly interacting massive particle",
    "wimps": "weakly interacting massive particle",
    "swimp": "super weakly interacting massive particle",
    "swimps": "super weakly interacting massive particle",
    "fimp": "feebly interacting massive particle",
    "fimps": "feebly interacting massive particle",
    "simp": "strongly interacting massive particle",
    "simps": "strongly interacting massive particle",
    "sidm": "self-interacting dark matter",
    "adm": "asymmetric dark matter",
    "pbh": "primordial black hole",
    "pbhs": "primordial black hole",
    "alp": "axion-like particle",
    "alps": "axion-like particle",
    "fdm": "fuzzy dark matter",
    "macho": "massive compact halo object",
    "machos": "massive compact halo object",
    "sm": "standard model",
    "mond": "modified newtonian dynamics",
    "mog": "modified gravity",
    "teves": "tensor-vector-scalar gravity",
}

# Useful but broader particle-physics / cosmology shorthand. Keep separate
# from the core list so we can opt in without over-normalizing the corpus.
SECONDARY_PHYSICS_EXPANSIONS = {
    "eos": "equation of state",
    "eoss": "equations of state",
    "susy": "supersymmetry",
    "sugra": "supergravity",
    "mssm": "minimal supersymmetric standard model",
    "nmssm": "next-to-minimal supersymmetric standard model",
    "pmssm": "phenomenological minimal supersymmetric standard model",
    "amsb": "anomaly mediated supersymmetry breaking",
    "gmsb": "gauge mediated supersymmetry breaking",
}

KNOWN_ABBREV_EXPANSIONS = {
    **SAFE_ABBREV_EXPANSIONS,
    **SECONDARY_PHYSICS_EXPANSIONS,
}

UNIT_TOKEN_RE = r"(?:ev|kev|mev|gev|tev|cm|mm|km|pc|kpc|mpc|s|yr|hz|k|g|kg|m|c)(?:\^[+\-]?\d+\^)?"
UNIT_SLASH_RE = re.compile(rf"\b({UNIT_TOKEN_RE})\s*/\s*({UNIT_TOKEN_RE})\b", re.I)


def canon_dm(s: str) -> str:
    return re.sub(r"\s+", " ", s.casefold().replace("-", " ")).strip()


def _canon_for_match(s: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9]+", " ", s.casefold())).strip()


@lru_cache(maxsize=None)
def _compile_abbrev_pattern(key: str):
    escaped = re.escape(key).replace(r"\ ", r"\s+")
    return re.compile(rf"(?<![A-Za-z0-9]){escaped}(?![A-Za-z0-9])", re.I)


SAFE_ABBREV_PATTERNS = [
    (_compile_abbrev_pattern(key), value)
    for key, value in sorted(SAFE_ABBREV_EXPANSIONS.items(), key=lambda kv: (-len(kv[0]), kv[0]))
]


def _expand_safe_abbreviations(seg: str) -> str:
    for pattern, expansion in SAFE_ABBREV_PATTERNS:
        seg = pattern.sub(expansion, seg)
    return seg


def _collapse_repeated_token(match):
    return match.group(1)


def _collapse_known_parenthetical_glosses(seg: str) -> str:
    def replace_long_short(m):
        prefix = m.group("prefix").rstrip()
        acro = m.group("acro").strip()
        acro_norm = _canon_for_match(acro)
        expansion = KNOWN_ABBREV_EXPANSIONS.get(acro_norm)
        if acro_norm and acro_norm in _canon_for_match(prefix):
            return prefix
        if expansion and _canon_for_match(expansion) in _canon_for_match(prefix):
            return prefix
        return m.group(0)

    def replace_short_long(m):
        short = m.group("short").strip()
        long = m.group("long").strip()
        short_norm = _canon_for_match(short)
        expansion = KNOWN_ABBREV_EXPANSIONS.get(short_norm)
        if expansion and _canon_for_match(expansion) in _canon_for_match(long):
            return long
        return m.group(0)

    seg = ACRONYM_PAREN_RE.sub(replace_long_short, seg)
    seg = SHORT_LONG_PAREN_RE.sub(replace_short_long, seg)
    return seg

def normalize_segment(seg: str, *, mask_math: bool = True) -> str:
    if not isinstance(seg, str):
        return ""

    seg = unicodedata.normalize("NFKC", seg)
    seg = html.unescape(seg)

    seg = seg.replace("–", "-").replace("—", "-").replace("−", "-")
    seg = seg.replace("“", '"').replace("”", '"')
    seg = seg.replace("‘", "'").replace("’", "'")

    seg = re.sub(r"</?SUB>", "_", seg, flags=re.I)
    seg = re.sub(r"</?SUP>", "^", seg, flags=re.I)
    seg = TAG_RE.sub(" ", seg)

    # Repair OCR/export cases like "scales.evidence"
    seg = MISSING_SPACE_AFTER_PUNCT_RE.sub(" ", seg)

    seg = re.sub(r"([=<>±≲≳~])", r" \1 ", seg)
    seg = re.sub(r"(?<=\S)([,;:/()])(?=\S)", r" \1 ", seg)

    seg = re.sub(r"\bdark\s+matter\s*\(\s*DM\s*\)", "dark matter", seg, flags=re.I)
    seg = re.sub(r"\(\s*DM\s*\)", "(dark matter)", seg, flags=re.I)
    seg = re.sub(r"\(\s*dm\s*\)", "(dark matter)", seg, flags=re.I)
    seg = re.sub(
        r"\bDM(?=\s+(halo|halos|particle|particles|candidate|candidates|density|densities|mass|profile|profiles|velocity|distribution|distributions|direct|indirect|annihilation|decay|search|searches|detection|constraints|fraction|fractions|model|models|signal|signals)\b)",
        "dark matter",
        seg,
        flags=re.I,
    )
    seg = re.sub(r"(?<![A-Za-z0-9])DM(?![A-Za-z0-9])", "dark matter", seg, flags=re.I)

    seg = seg.replace("Λ", "Lambda").replace("λ", "Lambda")
    seg = seg.replace("$Lambda$", "Λ")
    seg = re.sub(r"\bLambda\s*CDM\b", "LCDM", seg, flags=re.I)
    seg = re.sub(r"\bLambda\s*cold\s*dark\s*matter\b", "LCDM", seg, flags=re.I)
    seg = re.sub(r"\bLambdaCDM\b", "LCDM", seg, flags=re.I)

    # Strip common TeX command wrappers that survive abstract text export
    seg = LATEX_CMD_ARG_RE.sub(" MATH_TOKEN ", seg)
    seg = LATEX_CMD_RE.sub(" MATH_TOKEN ", seg)
    seg = BRACE_RE.sub(" ", seg)

    for pattern, replacement in SAFE_PHRASE_NORMALIZATIONS:
        seg = re.sub(pattern, replacement, seg, flags=re.I)

    if mask_math:
        seg = LATEX_BRACK_RE.sub(" MATH_TOKEN ", seg)
        seg = LATEX_PAREN_RE.sub(" MATH_TOKEN ", seg)
        seg = LATEX_INLINE_DOLLAR_RE.sub(" MATH_TOKEN ", seg)

    seg = DOI_RE.sub(" ", seg)
    seg = ARXIV_RE.sub(" ", seg)
    seg = ADS_CODE_RE.sub(" ", seg)
    seg = BRACKET_CITEISH_RE.sub(" ", seg)
    seg = SHORT_BRACKET_CITE_RE.sub(" ", seg)
    seg = EMPTY_BRACKETS_RE.sub(" ", seg)
    seg = re.sub(r"\bet\s*\.?\s*al\s*\.?\b", " ", seg, flags=re.I)

    for pattern, replacement in SAFE_TOKEN_NORMALIZATIONS:
        seg = re.sub(pattern, replacement, seg, flags=re.I)

    seg = _expand_safe_abbreviations(seg)

    seg = re.sub(r"\bgravitational[- ]wave\b", "gravitational_wave", seg, flags=re.I)
    seg = re.sub(r"\bgamma[- ]ray\b", "gamma_ray", seg, flags=re.I)

    seg = BULLET_RE.sub(" ", seg)
    seg = QUOTED_TERM_DQ_RE.sub(r"\1", seg)
    seg = QUOTED_TERM_SQ_RE.sub(r"\1", seg)

    # Remove parenthetical acronym glosses left behind by export noise,
    # in either direction, when they match our known safe abbreviations.
    seg = _collapse_known_parenthetical_glosses(seg)
    seg = re.sub(r"\(\s*([^()]*?\S)\s+\)", r"(\1)", seg)

    seg = re.sub(r"\bMATH_TOKEN(?:\s+MATH_TOKEN)+\b", "MATH_TOKEN", seg)
    seg = UNIT_SLASH_RE.sub(r"\1/\2", seg)
    seg = re.sub(r"\s*-\s*", "-", seg)
    seg = re.sub(r"([,;:])(?:\s*\1)+", r"\1", seg)
    seg = re.sub(r"(?<=\w)\s*;\s*(?=[.,])", "", seg)
    seg = re.sub(r"\s+([,.;:!?])", r"\1", seg)
    seg = re.sub(r"\b(\w[\w\-]*)\s+\1\b", _collapse_repeated_token, seg, flags=re.I)
    seg = re.sub(
        r"\b([A-Za-z][A-Za-z0-9+\-/]*(?:\s+[A-Za-z][A-Za-z0-9+\-/]*){0,5})\s*\(\s*\1\s*\)",
        r"\1",
        seg,
        flags=re.I,
    )

    # Collapse parenthetical self-duplicates created by normalization, e.g. "wimp (wimp)".
    seg = re.sub(
        r"\b([A-Za-z][A-Za-z0-9\-]*)\s*\(\s*\1\s*\)",
        r"\1",
        seg,
        flags=re.I,
    )

    seg = re.sub(r"\s+", " ", seg).strip()
    return seg



def iter_sentences_norm(text: str):
    t = normalize_segment(text, mask_math=True)
    for s in re.split(r"(?<=[\.\?\!])\s+", t):
        s = s.strip()
        if s:
            yield s


__all__ = [
    "TARGET",
    "pat",
    "MAX_CTX_WORDS",
    "MIN_CTX_WORDS",
    "MIN_CENTER_SENT_WORDS",
    "SOFT_CTX_WORDS",
    "MAX_DM_PER_CTX",
    "MAX_MATH_TOKENS_PER_CTX",
    "SAFE_ABBREV_EXPANSIONS",
    "SECONDARY_PHYSICS_EXPANSIONS",
    "canon_dm",
    "normalize_segment",
    "iter_sentences_norm",
]
