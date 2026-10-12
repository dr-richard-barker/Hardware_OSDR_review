"""Keyword lexicons shared by the classification and consistency stages.

Every pattern is a whole-word regex. They are deliberately conservative: a
record is only assigned a class when the text says so, otherwise it stays
'unknown'. Matching is case-insensitive.
"""
from __future__ import annotations

import re

ORGANISM_CLASSES: dict[str, str] = {
    "plant": r"plants?|arabidopsis|seedlings?|seeds?|wheat|lettuce|peppers?|chile|tomato|"
             r"mizuna|radish|flax|brassica|rice|moss|ferns?|tradescantia|capsicum|crops?|"
             r"root(s|ing)?|shoots?|germinat\w*|carrot|soybean|pea|cress",
    "rodent": r"rodents?|mice|mouse|rats?|murine|mus musculus|rattus",
    "aquatic_vertebrate": r"fish|medaka|zebrafish|goldfish|toadfish|newts?|frogs?|tadpoles?|"
                          r"xenopus|rana|cynops|fundulus|aquatic animals?",
    "invertebrate": r"drosophila|fruit fl(y|ies)|c\.? ?elegans|nematodes?|worms?|tardigrades?|"
                    r"insects?|beetles?|tribolium|wasps?|habrobracon|jellyfish|sea urchin|"
                    r"squid|daphnia|planaria|invertebrates?",
    "microbe": r"microbes?|microbial|microorganisms?|bacteri\w*|e\.? ?coli|b\.? ?subtilis|"
               r"yeast|fung(i|us|al)|neurospora|algae|microalgae|cyanobacteria|spores?|"
               r"biofilms?|amoeba|pelomyxa|euglena|archaea",
    "cell_tissue": r"cells? cultures?|cell lines?|tissues?|mammalian cells?|organoids?|"
                   r"organs?[- ]on[- ](a[- ])?chips?|tissue chips?|stem cells?|"
                   r"cultured cells|in vitro",
    "primate": r"primates?|monkeys?|rhesus|macaca",
    "avian": r"quail|avian|chick(en)?s?|eggs? of birds",
    "human": r"humans?|human subjects?|blood|saliva|urine",
}

NONBIO_HINTS = (
    r"combustion|flames?|fuels?|alloys?|semiconductors?|metals?|ceramics?|crystal melts?|"
    r"superconductors?|cold atoms?|ultracold|rb87|plasma|dosimet\w*|scintillat\w*|"
    r"radiation (detector|spectrometer)s?|levitat\w*|furnace|boiling|perfluorohexane|"
    r"earth observation|vibration isolation|thin films?"
)

NUTRIENT_MODES: dict[str, str] = {
    "agar_gel": r"agar|phyta-?agar|phytagel|gellan|nutrient gel|agarose",
    "arcillite_substrate": r"arcillite|calcined (clay|montmorillonite)|turface|profile greens|"
                           r"plant pillows?|veggie pillows?|rooting pillows?|potting (mix|soil)|vermiculite|"
                           r"perlite|peat|granular (ceramic )?substrate|ceramic substrate|growth substrate|"
                           r"plant growth substrate|substrate moisture",
    "hydroponic_aeroponic": r"hydroponic\w*|aeroponic\w*|nutrient (film|solution)|hoagland\w*|"
                            r"recirculat\w* (nutrient|water)|xroots|ponds|passive orbital nutrient delivery|"
                            r"root (module|zone) (delivery|watering)",
    "liquid_culture_medium": r"culture medi(um|a)|growth medi(um|a)|cell culture medi\w*|media exchange|"
                             r"medi(um|a) perfusion|perfusion of (the )?medi\w*|fresh medi(um|a)|"
                             r"liquid (culture|media|medium)|broth|lb medi\w*|murashige|ms (salts|medi\w*)|"
                             r"rpmi|dmem|fetal bovine serum|hollow fib(er|re)",
    "animal_food_water": r"food ?bars?|nutribloc|nutri-?bloc|lixits?|drinking (water|valves?)|water (bottle|box|lixit)|"
                      r"feeders?|feeding|paste (food|diet)|pellet feeder|chow|ad lib(itum)?",
    "aquatic_water_loop": r"water (loop|circulat\w*|filtration)|aquari(a|um|ums)|liquid loop|water pump|"
                          r"air-water interface",
    "water_only_wick": r"(?-i:wicks?|wicking)\b(?! et al)|water reservoir|water delivery|automatic watering|"
                       r"watering (system|unit)|water injection|imbibition|hydrat(ed|ion) (the )?seeds?",
}

# A delivery mode is only credited when the hardware carries an organism that can use it.
MODE_ORGANISMS: dict[str, set[str]] = {
    "agar_gel": {"plant", "microbe", "cell_tissue", "invertebrate"},
    "arcillite_substrate": {"plant"},
    "hydroponic_aeroponic": {"plant"},
    "liquid_culture_medium": {"microbe", "cell_tissue", "invertebrate", "plant"},
    "animal_food_water": {"rodent", "primate", "avian", "aquatic_vertebrate", "invertebrate"},
    "aquatic_water_loop": {"aquatic_vertebrate", "invertebrate"},
    "water_only_wick": {"plant"},
}

LOCATIONS: dict[str, str] = {
    "ISS_EXPRESS_rack": r"express rack|expedite the processing|er[- ]?\d\b",
    "ISS_JEM_Kibo": r"kibo|jem\b|japanese experiment module|ryutai|saibo",
    "ISS_Columbus": r"columbus|european drawer rack|\bedr\b|biolab",
    "ISS_US_lab_MSG": r"microgravity science glovebox|\bmsg\b|life sciences glovebox|destiny",
    "ISS_external": r"external (platform|payload)|exposed facility|misse|expose|outside the iss",
    "ISS_general": r"\biss\b|international space station|space station",
    "Shuttle_middeck": r"middeck|shuttle|sts[- ]?\d+|orbiter",
    "Spacelab": r"spacelab|sl-?\d|neurolab|slj|iml-?\d",
    "Free_flyer_Bion_Cosmos": r"bion|cosmos|biosatellite|foton|kosmos|free[- ]?fl(y|ier|yer)|"
                              r"cubesat|smallsat|\d+u\b",
    "Mir": r"\bmir\b",
    "Suborbital": r"suborbital|sounding rocket|new shepard|parabolic",
    "Lunar_or_beyond": r"gateway|lunar|moon|artemis|mars|beyond leo|europa|enceladus",
    "Ground_facility": r"accelerator|synchrotron|reactor|gammacell|x-?rad|faxitron|"
                       r"irradiat\w*|ground[- ]based|simulator|centrifuge facility|"
                       r"underground|nsrl|himac|sarrp|raraf",
}


def compile_lexicon(d: dict[str, str]) -> dict[str, re.Pattern]:
    return {k: re.compile(rf"(?<![\w-])(?:{v})(?![\w-])", re.I) for k, v in d.items()}


ORG_RE = compile_lexicon(ORGANISM_CLASSES)
NUT_RE = compile_lexicon(NUTRIENT_MODES)
LOC_RE = compile_lexicon(LOCATIONS)
NONBIO_RE = re.compile(rf"(?<![\w-])(?:{NONBIO_HINTS})(?![\w-])", re.I)


def classes_in(text: str, lex: dict[str, re.Pattern]) -> set[str]:
    text = text or ""
    return {k for k, rx in lex.items() if rx.search(text)}


def evidence(text: str, rx: re.Pattern, width: int = 70) -> str | None:
    """Return a verbatim window around the first match (the quote we cite)."""
    if not text:
        return None
    m = rx.search(text)
    if not m:
        return None
    a, b = max(0, m.start() - width), min(len(text), m.end() + width)
    return ("…" if a else "") + " ".join(text[a:b].split()) + ("…" if b < len(text) else "")
