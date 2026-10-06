"""Pre-submission hygiene: things that are cheap to detect exactly and embarrassing to
miss. Every check is a pattern or a count; none guesses at meaning."""

import re
from dataclasses import dataclass, field

from .extract import Block, Document
from .structure import Structure, is_heading_like

PASS, WARN, FAIL, INFO = "pass", "warn", "fail", "info"


@dataclass
class Finding:
    block: Block | None
    matched: str = ""
    start: int = -1
    note: str = ""


@dataclass
class Check:
    id: str
    title: str
    status: str  # pass | warn | fail | info
    summary: str
    findings: list[Finding] = field(default_factory=list)


@dataclass
class ProofReport:
    checks: list[Check]
    stats: dict


def _scan(blocks: list[Block], pattern: re.Pattern, limit: int = 200, plain: bool = False) -> list[Finding]:
    out = []
    for b in blocks:
        for m in pattern.finditer(b.plain if plain else b.text):
            out.append(Finding(b, m.group(0), m.start()))
            if len(out) >= limit:
                return out
    return out


# --- 1. Broken cross-references -------------------------------------------

_FIELD_ERROR = re.compile(
    r"Error!\s*(?:Reference source not found|Bookmark not defined|No text of specified style in document|"
    r"Not a valid bookmark(?: self-reference)?|Unknown switch argument|Main Document Only|No table of figures entries found|"
    r"Invalid character string|Undefined bookmark)\.?"
    r"|(?:Fig(?:ure)?s?\.?|Tables?|Eqs?\.?|Equations?|Sections?|Sec\.|Refs?\.|Chapter|Appendix)\s*\?\?"
    r"|\[\?\]|\(\?\)|\[\s*\?\s*,"
)


def _cross_refs(text_blocks):
    found = _scan(text_blocks, _FIELD_ERROR)
    if found:
        return Check("crossrefs", "Broken cross-references", FAIL,
                     f"{len(found)} broken Word field(s) or unresolved LaTeX reference(s). Update fields (Ctrl+A, F9) "
                     "or recompile LaTeX.", found)
    return Check("crossrefs", "Broken cross-references", PASS, "No “Error! Reference source not found.” or “??”.")


# --- 2. Tracked changes, comments, highlights --------------------------------

def _leftovers(docs: list[Document]):
    findings, fail, warn = [], False, False
    for d in docs:
        if d.tracked_insertions or d.tracked_deletions:
            fail = True
            findings.append(Finding(None, note=f"{d.name}: {d.tracked_insertions} tracked insertion(s), "
                                               f"{d.tracked_deletions} deletion(s). Accept or reject all changes."))
        if d.comments:
            fail = True
            findings.append(Finding(None, note=f"{d.name}: {d.comments} comment(s). Delete all comments."))
        if d.highlights:
            warn = True
            findings.append(Finding(None, note=f"{d.name}: {d.highlights} highlighted passage(s)."))
    if not any(d.name.lower().endswith(".docx") for d in docs):
        return Check("leftovers", "Tracked changes & comments", INFO, "Only checked for .docx files.")
    status = FAIL if fail else WARN if warn else PASS
    summary = {FAIL: "Editing leftovers found.", WARN: "Highlighted text found.",
               PASS: "No tracked changes, comments or highlights."}[status]
    return Check("leftovers", "Tracked changes & comments", status, summary, findings)


# --- 3. Placeholders ---------------------------------------------------------

_PLACEHOLDER = re.compile(
    r"\b(?:TODO|TBD|TBC|FIXME|XXX+|PLACEHOLDER)\b|(?<![A-Za-z])XX(?![A-Za-z])|\b[Ll]orem ipsum\b"
    r"|\[\s*(?:refs?|REFS?|citations?(?: needed)?|cite|insert[^\]]{0,40}|add[^\]]{0,40}|\?+)\s*\]"
    r"|\(\s*(?:refs?|REFS?|citations? needed|cite)\s*\)|\?{3,}"
)


def _placeholders(text_blocks):
    found = _scan(text_blocks, _PLACEHOLDER)
    if found:
        return Check("placeholders", "Placeholders & notes to self", WARN,
                     f"{len(found)} placeholder(s) such as TODO, XX or [ref].", found)
    return Check("placeholders", "Placeholders & notes to self", PASS, "No TODO, XX, [ref] or ??? left in the text.")


# --- 4. Required statements --------------------------------------------------

STATEMENTS = [
    ("data", "Data availability", r"data\s+(?:and\s+(?:code|materials?)\s+)?availability|availability\s+of\s+data|data\s+access(?:ibility)?|data\s+sharing", True),
    ("contrib", "Author contributions", r"author(?:s['’])?\s+contributions?|contributions|credit\s+(?:author|taxonomy)", True),
    ("coi", "Competing interests", r"competing\s+(?:financial\s+)?interests?|conflicts?\s+of\s+interests?|declaration\s+of\s+(?:competing\s+)?interests?|disclosures?", True),
    ("funding", "Funding", r"funding(?:\s+(?:statement|information|sources?))?|financial\s+support|grant\s+support", True),
    ("ack", "Acknowledgements", r"acknowledge?ments?", False),
    ("code", "Code availability", r"code\s+availability|software\s+availability|data\s+and\s+code\s+availability", False),
    ("ethics", "Ethics statement", r"ethics(?:\s+(?:statement|approval|declarations?))?|ethical\s+(?:approval|statement)|institutional\s+review\s+board|informed\s+consent", False),
]


def _statements(blocks):
    present: dict[str, Block] = {}
    for b in blocks:
        if b.role == "figures":
            continue
        text = b.text.strip()
        for sid, _, pattern, _ in STATEMENTS:
            if sid in present:
                continue
            heading = re.match(rf"^(?:\d+(?:\.\d+)*\.?\s*)?(?:{pattern})\s*(?:statement)?\s*[:.—–-]?\s*$", text, re.I)
            inline = re.match(rf"^(?:{pattern})\s*(?:statement)?\s*[:.—–-]\s+\S", text, re.I)
            if (heading and (is_heading_like(b) or len(text) < 60)) or inline:
                present[sid] = b
    findings, missing_required = [], []
    for sid, name, _, required in STATEMENTS:
        if sid in present:
            findings.append(Finding(present[sid], note=f"✓ {name}"))
        else:
            findings.append(Finding(None, note=f"{'✗' if required else '–'} {name}{'' if required else ' (if applicable)'}"))
            if required:
                missing_required.append(name)
    if missing_required:
        return Check("statements", "Required statements", WARN,
                     f"Not found: {', '.join(missing_required)}. Most journals require these.", findings)
    return Check("statements", "Required statements", PASS, "Data, contributions, competing interests and funding found.",
                 findings)


# --- 5. Word counts and limits ----------------------------------------------

_WORD = re.compile(r"[^\W_]+(?:['’\-][^\W_]+)*")


def words(text: str) -> int:
    return len(_WORD.findall(text))


def _limits(stats: dict, limits: dict) -> Check:
    names = {"abstract_words": "Abstract words", "main_text_words": "Main-text words", "figures": "Main figures",
             "tables": "Main tables", "references": "References"}
    findings, over = [], []
    for key, label in names.items():
        limit = limits.get(key)
        value = stats.get(key)
        if not limit or value is None:
            continue
        ok = value <= limit
        findings.append(Finding(None, note=f"{'✓' if ok else '✗'} {label}: {value} / {limit}"))
        if not ok:
            over.append(f"{label} {value} > {limit}")
    if not findings:
        return Check("limits", "Journal limits", INFO, "Enter your journal's limits to check word, figure, table and "
                                                       "reference counts.")
    if over:
        return Check("limits", "Journal limits", FAIL, "Over the limit: " + "; ".join(over) + ".", findings)
    return Check("limits", "Journal limits", PASS, "Within all limits you entered.", findings)


# --- 6. Abbreviations --------------------------------------------------------

_ABBR_DEF = re.compile(r"(?P<long>(?:[A-Za-z][\w\-’']*\s+){1,9}?[A-Za-z][\w\-’']*)\s+\((?P<abbr>[A-Z][A-Za-z0-9\-]*[A-Z0-9][a-z]?s?)\)")
_COMMON = {"DNA", "RNA", "USA", "UK", "EU", "UN", "WHO", "PCR", "ATP", "HIV", "AIDS", "COVID", "SARS", "CI", "SD", "SE",
           "SEM", "ID", "PhD", "MD", "MSc", "BSc", "AI", "ML", "OK", "PDF", "URL", "GPU", "CPU", "NaCl", "pH", "UV", "IR",
           "NMR", "MRI", "CT", "IQ", "BMI", "GDP", "US", "NASA", "NIH", "NSF", "II", "III", "IV", "VI", "VII", "VIII",
           "IX", "XI", "XII", "ANOVA", "ROC", "AUC", "OR", "HR", "RR", "IQR", "ICU", "ED"}


def _initials_match(long: str, abbr: str) -> bool:
    letters = [c.lower() for c in abbr if c.isalpha()]
    words_ = [w for w in re.split(r"[\s\-]+", long) if w]
    if not letters or not words_:
        return False
    # The first letter of the abbreviation must start one of the last few words of the long form.
    return any(w[0].lower() == letters[0] for w in words_[-(len(letters) + 2):])


def _trim_long(long: str, abbr: str) -> str:
    words_ = long.split()
    n = len([c for c in abbr if c.isupper()]) + 1
    return " ".join(words_[-n:])


def _abbreviations(structure: Structure) -> Check:
    findings: list[Finding] = []
    zones = [("abstract", structure.abstract), ("main text", structure.main_text)]
    defined_in: dict[str, dict[str, tuple[Block, str]]] = {}
    for zone, blocks in zones:
        defs: dict[str, list[tuple[Block, int, str]]] = {}
        for b in blocks:
            for m in _ABBR_DEF.finditer(b.plain):
                abbr, long = m.group("abbr"), m.group("long")
                if abbr in _COMMON or len(abbr) < 2 or not _initials_match(long, abbr):
                    continue
                defs.setdefault(abbr, []).append((b, m.start("abbr") - 1, _trim_long(long, abbr)))
        defined_in[zone] = {abbr: (places[0][0], places[0][2]) for abbr, places in defs.items()}
        order = {id(b): i for i, b in enumerate(blocks)}
        for abbr, places in defs.items():
            first_block, first_pos, long = places[0]
            if len(places) > 1:
                findings.append(Finding(places[1][0], f"({abbr})", places[1][1],
                                        note=f"{abbr} is defined again in the {zone} (first at {first_block.location})."))
            pattern = re.compile(rf"(?<![\w-]){re.escape(abbr)}(?![\w-])")
            uses_before, uses_after = None, 0
            for b in blocks:
                for m in pattern.finditer(b.plain):
                    before = (order[id(b)], m.start()) < (order[id(first_block)], first_pos)
                    if before and uses_before is None:
                        uses_before = Finding(b, abbr, m.start(), note=f"{abbr} is used before it is defined "
                                                                       f"(“{long} ({abbr})” at {first_block.location}).")
                    elif not before and (b is not first_block or m.start() > first_pos + 1):
                        uses_after += 1
            if uses_before:
                findings.append(uses_before)
            if uses_after == 0 and zone == "main text":
                findings.append(Finding(first_block, f"({abbr})", first_pos,
                                        note=f"{abbr} is defined but never used again: spell it out instead."))
    # Journals treat the abstract as standalone: an abbreviation defined only there must be
    # defined again at its first use in the main text.
    for abbr, (block, long) in defined_in.get("abstract", {}).items():
        if abbr in defined_in.get("main text", {}):
            continue
        pattern = re.compile(rf"(?<![\w-]){re.escape(abbr)}(?![\w-])")
        use = next(((b, m) for b in structure.main_text for m in pattern.finditer(b.plain)), None)
        if use:
            findings.append(Finding(use[0], abbr, use[1].start(),
                                    note=f"{abbr} is defined only in the abstract; define it again at first use in the "
                                         f"main text (“{long} ({abbr})”)."))
    if not structure.main_text and not structure.abstract:
        return Check("abbreviations", "Abbreviations", INFO, "No main text found to check.")
    if findings:
        return Check("abbreviations", "Abbreviations", WARN, f"{len(findings)} abbreviation issue(s).", findings)
    return Check("abbreviations", "Abbreviations", PASS, "Abbreviations are defined once, before first use.")


# --- 7. Repeated words ------------------------------------------------------

_REPEAT = re.compile(r"\b([A-Za-z]{2,})\s+\1\b", re.IGNORECASE)
_REPEAT_OK = {"that", "had", "is", "bye", "very", "so", "no", "yes"}


def _repeats(text_blocks):
    found = [f for f in _scan(text_blocks, _REPEAT, plain=True) if f.matched.split()[0].lower() not in _REPEAT_OK]
    if found:
        return Check("repeats", "Repeated words", WARN, f"{len(found)} repeated word(s), e.g. “{found[0].matched}”.", found)
    return Check("repeats", "Repeated words", PASS, "No accidental “the the”.")


# ---------------------------------------------------------------------------


def run_proofing(docs: list[Document], structure: Structure, counts: dict, limits: dict | None = None) -> ProofReport:
    text_blocks = [b for b in structure.blocks if not structure.is_reference(b)]
    stats = {
        "abstract_words": words(structure.abstract_text) if structure.abstract else None,
        "main_text_words": sum(words(b.text) for b in structure.main_text),
        **counts,
    }
    checks = [
        _cross_refs(structure.blocks),
        _leftovers(docs),
        _placeholders(text_blocks),
        _statements(structure.blocks),
        _limits(stats, limits or {}),
        _abbreviations(structure),
        _repeats(text_blocks),
    ]
    return ProofReport(checks, stats)
