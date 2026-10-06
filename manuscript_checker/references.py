"""Cross-check the reference list against in-text citations.

Two citation systems are supported and detected automatically:

* numeric: [3], [1-4, 7], (3), superscripts (DOCX formatting or Unicode ¹²), "ref. 5";
* author-year: (Smith et al., 2019), Smith and Jones (2019), (Smith 2018, 2019a; Lee, 2020).

Author-year matching is driven by the reference list: each entry's first-author surname
and year are extracted from the list and looked up in the text, which is far more
robust than parsing every citation shape on its own. A citation is reported as missing
from the list only when its shape is unambiguous, so "In (2019)" never becomes an error.
"""

import re
import unicodedata
from dataclasses import dataclass, field

from .extract import Block
from .labels import Issue
from .structure import Structure

NUMERIC, AUTHOR_YEAR, NONE = "numeric", "author-year", "none"

# ---------------------------------------------------------------------------
# Reference entries
# ---------------------------------------------------------------------------

_NUM_PREFIX = re.compile(
    r"^\s*(?:\[(?P<a>\d{1,4})\]|\((?P<b>\d{1,4})\)|(?P<c>\d{1,4})\s*[.)](?!\d)|(?P<d>\d{1,4})(?=\t|\s{2,}|\s+[A-Z]))\s*"
)
_SPLIT_MARK = re.compile(r"(?:^|(?<=\s))(?:\[(\d{1,4})\]|(\d{1,4})\.)\s+(?=[^\W\d_]|\[)")
_YEAR_PAREN = re.compile(r"\(\s*((?:1[6-9]|20)\d\d[a-z]?)\s*[),;]")
_YEAR_ANY = re.compile(r"(?<![\d/.-])((?:1[6-9]|20)\d\d[a-z]?)(?![\d])")
_YEAR_SPECIAL = re.compile(r"\b(in\s+press|n\.\s?d\.|forthcoming)", re.IGNORECASE)
_DOI = re.compile(r"\b10\.\d{4,9}/[^\s\"<>]+", re.IGNORECASE)
_PARTICLES = {
    "van", "von", "de", "der", "den", "del", "della", "di", "da", "du", "dos", "das", "la", "le",
    "ter", "ten", "bin", "al", "el", "st", "st.",
}
_INITIALS = re.compile(r"(?:\s+(?:[A-Z]\.?\s?-?){1,4})+$")


def norm(text: str) -> str:
    """Accent-, case- and punctuation-insensitive key: "Müller-Lyer" -> "mullerlyer"."""
    text = unicodedata.normalize("NFKD", text)
    return "".join(c for c in text if c.isalpha() and not unicodedata.combining(c)).lower()


def surname_key(name: str) -> str:
    """Key for a surname: the last non-particle token ("van der Waals" -> "waals")."""
    tokens = [t for t in re.split(r"\s+", name.strip()) if t]
    while len(tokens) > 1 and tokens[0].lower().strip(".") in _PARTICLES:
        tokens = tokens[1:]
    return norm(tokens[-1]) if tokens else ""


@dataclass
class Citation:
    block: Block
    start: int  # offset in block.text
    matched: str
    number: int | None = None  # numeric
    key: str = ""  # author-year: surname key
    author: str = ""  # author-year: author text as written
    year: str = ""  # author-year: "2019a"
    confident: bool = True  # shape is unambiguous enough to report if it matches nothing
    in_caption: bool = False

    @property
    def label(self) -> str:
        return f"[{self.number}]" if self.number is not None else f"{self.author}, {self.year}"


@dataclass
class RefEntry:
    id: str
    text: str
    block: Block
    number: int | None = None
    author: str = ""  # first author as written
    key: str = ""
    year: str = ""
    doi: str = ""
    citations: list[Citation] = field(default_factory=list)
    alt_key: str = ""  # acronym of an organisation author: "World Health Organization" -> "who"

    @property
    def label(self) -> str:
        if self.number is not None:
            return f"[{self.number}]"
        return f"{self.author or '?'} {self.year or 'n.y.'}".strip()

    @property
    def status(self) -> str:
        return "OK" if self.citations else "UNCITED"


def _first_author(text: str) -> str:
    m = re.match(r"\s*([^,(;]+?)(?:,|\s\(|\.\s|;|\s(?=(?:1[6-9]|20)\d\d))", text)
    seg = (m.group(1) if m else text.split(".")[0]).strip()
    seg = _INITIALS.sub("", seg).strip()  # Vancouver "Smith JA" -> "Smith"
    return seg


def _year(text: str) -> str:
    m = _YEAR_PAREN.search(text) or _YEAR_ANY.search(text)
    if m:
        return m.group(1)
    m = _YEAR_SPECIAL.search(text)
    return re.sub(r"\s+", " ", m.group(1).lower()) if m else ""


def _sequential_marks(text: str) -> list[tuple[int, int]]:
    """Positions of "1." "2." "3." ... (or "[1]" "[2]" ...) that number consecutive entries.
    Starting from a mark at the very beginning, each step takes the first later mark whose
    number is one higher, so volumes and page numbers inside an entry are skipped."""
    marks = [(m.start(), int(m.group(1) or m.group(2))) for m in _SPLIT_MARK.finditer(text)]
    if not marks or marks[0][0] != 0:
        return []
    chain = [marks[0]]
    for pos, n in marks[1:]:
        if n == chain[-1][1] + 1:
            chain.append((pos, n))
    return chain if len(chain) >= 2 else []


def _cut(text: str, chain: list[tuple[int, int]]) -> list[tuple[int, str]]:
    cuts = [p for p, _ in chain] + [len(text)]
    return [(a, text[a:b].strip()) for a, b in zip(cuts, cuts[1:]) if text[a:b].strip()]


def parse_entries(structure: Structure) -> list[RefEntry]:
    entries: list[RefEntry] = []
    for section in structure.ref_sections:
        # Numbered lists are cut on the number sequence over the whole section, because PDF
        # line merging can both split one entry and glue several together.
        joined, starts = "", []
        for b in section.blocks:
            joined += " " if joined else ""
            starts.append((len(joined), b))
            joined += b.text
        chain = _sequential_marks(joined)
        if chain and len(chain) >= sum(1 for b in section.blocks if _NUM_PREFIX.match(b.text)):
            owner = lambda pos: next(b for start, b in reversed(starts) if start <= pos)
            raw = [(t, owner(pos)) for pos, t in _cut(joined, chain)]
        else:
            raw = []
            for b in section.blocks:
                chain_b = _sequential_marks(b.text)
                raw += [(t, b) for _, t in _cut(b.text, chain_b)] if chain_b else [(b.text, b)]
        explicit = [_NUM_PREFIX.match(t) for t, _ in raw]
        numbered_list = sum(bool(m) for m in explicit) >= max(1, 0.6 * len(raw)) or any(b.numbered for _, b in raw)

        merged: list[tuple[str, Block, int | None]] = []
        for (text, b), m in zip(raw, explicit):
            number = int(next(g for g in m.groups() if g)) if m else None
            body = text[m.end():] if m else text
            if numbered_list and number is None and not b.numbered and merged:
                # A wrapped line of the previous entry (PDF), not a new reference.
                prev = merged[-1]
                merged[-1] = (prev[0] + " " + body, prev[1], prev[2])
                continue
            merged.append((body.strip(), b, number))

        file_count = sum(1 for e in entries if e.block.source == section.source)
        for i, (body, b, number) in enumerate(merged):
            if numbered_list and number is None:
                number = file_count + i + 1  # Word auto-numbering: the number is not in the text
            author = _first_author(body)
            entries.append(RefEntry(
                id=f"ref-{len(entries) + 1}",
                text=body,
                block=b,
                number=number if numbered_list else None,
                author=author,
                key=surname_key(author),
                year=_year(body),
                doi=(_DOI.search(body).group(0).rstrip(".,;)").lower() if _DOI.search(body) else ""),
                alt_key=_acronym(author),
            ))
    return entries


def _acronym(author: str) -> str:
    words = [w for w in re.split(r"[\s\-]+", author) if w[:1].isupper()]
    return "".join(w[0] for w in words).lower() if len(words) >= 3 else ""


def _merge_author_year_fragments(entries: list[RefEntry]) -> list[RefEntry]:
    """PDF lines can split one entry in two; a yearless fragment belongs to the entry above."""
    out: list[RefEntry] = []
    for e in entries:
        if out and not e.year and out[-1].block.source == e.block.source and not re.match(r"[A-Z][^\s,]+,\s*[A-Z]", e.text):
            prev = out[-1]
            prev.text += " " + e.text
            prev.doi = prev.doi or e.doi
            continue
        out.append(e)
    return out


# ---------------------------------------------------------------------------
# Numeric citations
# ---------------------------------------------------------------------------

_LIST = r"\d{1,4}(?:\s*[-–—]\s*\d{1,4})?(?:\s*[,;]\s*\d{1,4}(?:\s*[-–—]\s*\d{1,4})?)*"
_BRACKET = re.compile(rf"\[\s*({_LIST})\s*\]")
_PAREN = re.compile(rf"\(\s*({_LIST})\s*\)")
_REFWORD = re.compile(rf"\b(?:[Rr]efs?\.?|[Rr]eferences?)\s+({_LIST})\b")
_NOT_REF_BEFORE = re.compile(
    r"(?:\b(?:eqs?|equations?|steps?|schemes?|figs?|figures?|tables?|sections?|sec|chapters?|chap|appendix|"
    r"panels?|n|p|lines?|days?|weeks?|months?|years?|ages?|grades?|stages?|groups?|types?|versions?|v)\.?|[=<>±×])\s*$",
    re.IGNORECASE,
)
_SUP_CITE = re.compile(r"^\d{1,4}(?:\s*[-–—,]\s*\d{1,4})*$")
_UNIT_BEFORE = re.compile(r"(?:\b(?:[kcmuµμnp]?m|[kmuµμn]?[lL]|s|K|Pa|Hz|ft|mi|yd)|[\^×])$")
_MAX_NUMBER = 999  # anything larger is a year, not a reference number


def _expand(spec: str) -> list[int]:
    numbers: list[int] = []
    for part in re.split(r"\s*[,;]\s*", spec.strip()):
        if not part:
            continue
        bounds = [int(x) for x in re.split(r"\s*[-–—]\s*", part) if x]
        if len(bounds) == 2 and 0 < bounds[1] - bounds[0] <= 300:
            numbers += range(bounds[0], bounds[1] + 1)
        else:
            numbers += bounds
    return [n for n in numbers if 0 < n <= _MAX_NUMBER]


def numeric_citations(block: Block, kinds: set[str], in_caption: bool, front: bool) -> dict[str, list[Citation]]:
    found: dict[str, list[Citation]] = {"bracket": [], "parenthesis": [], "superscript": [], "refword": []}
    text = block.text

    def add(kind, m_start, matched, spec):
        for n in _expand(spec):
            found[kind].append(Citation(block, m_start, matched, number=n, in_caption=in_caption))

    for m in _BRACKET.finditer(text):
        add("bracket", m.start(), m.group(0), m.group(1))
    for m in _REFWORD.finditer(text):
        add("refword", m.start(), m.group(0), m.group(1))
    if "parenthesis" in kinds:
        for m in _PAREN.finditer(text):
            if m.start() < 2 or not text[m.start() - 1].isspace() or _NOT_REF_BEFORE.search(text[:m.start()]):
                continue  # "(1) First item", "Eq. (3)", or glued like the issue in "295(2)"
            add("parenthesis", m.start(), m.group(0), m.group(1))
    if not front:  # superscripts on the title page are author affiliations
        for a, b in block.sup:
            sup = text[a:b].strip().strip(",.;")
            if a == 0 or not _SUP_CITE.match(sup) or not _is_citation_superscript(text, a, b):
                continue
            add("superscript", a, text[a:b], sup)
    return found


def _is_citation_superscript(text: str, a: int, b: int) -> bool:
    """Tell "previously¹²" from chemistry and maths: "sp³", "Fsp³", "R²", "Å³", "m²", "10⁵",
    "sp³-hybridised", "¹³C"."""
    before, after = text[:a], text[b:]
    if _UNIT_BEFORE.search(before):
        return False  # unit (m², cm³)
    number = re.search(r"\d[\d.]*$", before)
    if number and "." not in number.group(0) and not re.fullmatch(r"(?:19|20)\d\d", number.group(0)):
        return False  # exponent (10⁵, 2³); after a version (ADMETlab 3.0³⁷) or a year it is a citation
    word = re.search(r"[^\W\d_]+$", before)
    if word:
        w = word.group(0)
        if len(w) <= 2 or w.lower().endswith("sp"):
            return False  # sp³, R², Å³, Fsp³, Csp³: citations follow words, not symbols
    if re.match(r"[^\W\d_]|-[^\W\d_]", after):
        return False  # the word continues: "sp³-hybridised", "¹³C"
    return True


# ---------------------------------------------------------------------------
# Author-year citations
# ---------------------------------------------------------------------------

_YEAR_TOKEN = r"(?:(?:1[6-9]|20)\d\d[a-z]?|in\s+press|n\.\s?d\.|forthcoming)"
_YEARS = rf"{_YEAR_TOKEN}(?:\s*,\s*(?:{_YEAR_TOKEN}|[a-z]\b))*"  # "2019a, b" too
_NAME_TOKEN = r"[^\W\d_][\w'’\-]*"
_PARTICLE = r"(?:van|von|de|der|den|del|della|di|da|du|dos|das|la|le|ter|ten|De|Van|Von|Du|Di|Da|La|Le|Del)"
_NAME = rf"(?:{_PARTICLE}\s+){{0,3}}{_NAME_TOKEN}"
_AUTHORS = rf"{_NAME}(?:\s+et\s+al\.?|(?:\s*,\s*{_NAME})*\s*,?\s*(?:and|&)\s+{_NAME}(?:\s+et\s+al\.?)?)?"
_NARRATIVE = re.compile(
    rf"(?P<auth>{_AUTHORS})(?:['’]s)?\s*\(\s*(?P<years>{_YEARS})\s*(?:,\s*(?:pp?\.|chap\.|ch\.)\s*[\d–-]+)?\s*\)"
)
_PAREN_GROUP = re.compile(r"\(([^()]{4,400})\)")
# A citation part: the author-years pair must run to the end of the part ("reviewed by Smith, 2019").
_PART_WORD = re.compile(rf"(?P<auth>{_AUTHORS})\s*,?\s*(?P<years>{_YEARS})\b(?:\s*,\s*(?:pp?\.|chap\.)\s*[\d–-]+)?\s*$")
_YEARS_ONLY = re.compile(rf"^(?P<years>{_YEARS})\b")
_LEAD_IN = re.compile(
    r"^(?:e\.g\.|i\.e\.|see(?:\s+also)?|cf\.|but\s+see|reviewed\s+(?:in|by)|for\s+(?:a\s+)?reviews?,?\s+see|"
    r"as\s+(?:in|described\s+(?:in|by))|adapted\s+from|from|and|also|data\s+from)[,:]?\s+",
    re.IGNORECASE,
)
_STOP_NAMES = {
    "in", "on", "at", "since", "from", "during", "until", "before", "after", "by", "the", "this", "these", "of",
    "and", "for", "to", "fig", "figure", "figures", "table", "tables", "supplementary", "january", "february",
    "march", "april", "may", "june", "july", "august", "september", "october", "november", "december", "spring",
    "summer", "autumn", "fall", "winter", "version", "release", "update", "vol", "volume", "issue", "accessed",
    "retrieved", "published", "data", "total", "mean", "year", "years", "cohort", "study", "wave", "phase",
    "round", "census", "survey", "report", "season", "between", "around", "approximately", "circa", "ca",
    "early", "late", "mid", "end", "start", "beginning", "et", "al", "n", "p", "ref", "refs",
}


def _valid_author(auth: str) -> bool:
    first = re.split(r"\s+et\s+al|\s*,\s*|\s+(?:and|&)\s+", auth.strip())[0]
    tokens = first.split()
    return bool(tokens) and tokens[-1][:1].isupper() and norm(tokens[-1]) not in _STOP_NAMES and bool(surname_key(first))


def _match_at_words(pattern: re.Pattern, text: str, start: int = 0, end: int | None = None, anchored: bool = False):
    """Like finditer, but when a match's leading author is not a name ("disagreed, and van der
    Waals (1873)") retry from the next word instead of losing the citation inside it."""
    end = len(text) if end is None else end
    pos = start
    while pos < end:
        m = pattern.match(text, pos, end) if anchored else pattern.search(text, pos, end)
        if not m:
            return
        if _valid_author(m.group("auth")):
            yield m
            pos = m.end()
            continue
        nxt = re.search(r"\s+\S", text[m.start():end])
        if not nxt:
            return
        pos = m.start() + nxt.end() - 1


def _cite(block, start, matched, auth, years_text, confident, in_caption) -> list[Citation]:
    first = re.split(r"\s+et\s+al|\s*,\s*|\s+(?:and|&)\s+", auth.strip())[0]
    key = surname_key(first)
    if not _valid_author(auth):
        return []
    years: list[str] = []
    for y in re.split(r"\s*,\s*", years_text):
        y = re.sub(r"\s+", " ", y.strip().lower())
        if len(y) == 1 and years and years[-1][:4].isdigit():
            y = years[-1][:4] + y  # "2019a, b" -> 2019b
        if y:
            years.append(y)
    return [Citation(block, start, matched, key=key, author=auth.strip(), year=y, confident=confident,
                     in_caption=in_caption) for y in years]


def author_year_citations(block: Block, in_caption: bool) -> list[Citation]:
    text = block.text
    found: list[Citation] = []
    for g in _PAREN_GROUP.finditer(text):
        inner = g.group(1)
        if not re.search(_YEAR_TOKEN, inner):
            continue
        offset = g.start(1)
        last_auth = ""
        for part_match in re.finditer(r"[^;]+", inner):
            part = part_match.group(0)
            lead = len(part) - len(part.lstrip())
            stripped = part.strip()
            while True:
                m = _LEAD_IN.match(stripped)
                if not m:
                    break
                lead += m.end()
                stripped = stripped[m.end():]
            pos = offset + part_match.start() + lead
            m = next(_match_at_words(_PART_WORD, stripped, anchored=True), None)
            if m:
                last_auth = m.group("auth")
                found += _cite(block, pos + m.start(), m.group(0), last_auth, m.group("years"), True, in_caption)
            elif last_auth and (m := _YEARS_ONLY.match(stripped)):
                found += _cite(block, pos, m.group(0), last_auth, m.group("years"), True, in_caption)
    for m in _match_at_words(_NARRATIVE, text):
        auth = m.group("auth")
        # "Smith et al. (2019)" or "Smith and Jones (2019)" are unambiguous; "Smith (2019)" could be
        # "In (2019)", so it only counts when it matches the reference list.
        confident = bool(re.search(r"et\s+al|\band\b|&", auth))
        found += _cite(block, m.start(), m.group(0), auth, m.group("years"), confident, in_caption)
    return found


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------


@dataclass
class Unresolved:
    citation: Citation
    hint: str = ""


@dataclass
class RefReport:
    style: str  # numeric | author-year | none
    detail: str  # bracket | superscript | parenthesis | "" (author-year)
    detected: dict[str, int]  # citation counts per style, for transparency
    entries: list[RefEntry]
    unresolved: list[Unresolved]
    issues: list[Issue]
    list_found: bool

    @property
    def cited(self) -> int:
        return sum(1 for e in self.entries if e.citations)


def _issue(severity: str, message: str, code: str, target: str = "") -> Issue:
    return Issue(severity, message, None, code=code, target=target)


def check_references(structure: Structure, style: str = "auto") -> RefReport:
    entries = parse_entries(structure)
    list_found = bool(entries)
    citable = [b for b in structure.blocks if not structure.is_reference(b)]
    position = {id(b): i for i, b in enumerate(structure.blocks)}

    numeric_found: dict[str, list[Citation]] = {"bracket": [], "parenthesis": [], "superscript": [], "refword": []}
    ay_found: list[Citation] = []
    for b in citable:
        in_caption = id(b) in structure.caption_ids or b.role == "figures"
        front = id(b) in structure.front_ids
        for k, v in numeric_citations(b, {"parenthesis"}, in_caption, front).items():
            numeric_found[k] += v
        if not front:
            ay_found += author_year_citations(b, in_caption)

    def distinct(cites):  # count citation sites, not expanded numbers
        return len({(id(c.block), c.start) for c in cites})

    detected = {k: distinct(v) for k, v in numeric_found.items() if k != "refword"}
    ay_keys = {e.key for e in entries if e.key}
    ay_matching = [c for c in ay_found if c.confident or c.key in ay_keys]
    detected["author_year"] = distinct(ay_matching)
    numbered_list = any(e.number is not None for e in entries)

    if style not in (NUMERIC, AUTHOR_YEAR):
        strong_numeric = detected["bracket"] + detected["superscript"]
        if detected["author_year"] >= 3 and detected["author_year"] > strong_numeric and not numbered_list:
            style = AUTHOR_YEAR
        elif strong_numeric or numbered_list or (detected["parenthesis"] >= 5 and not detected["author_year"]):
            style = NUMERIC
        elif detected["author_year"]:
            style = AUTHOR_YEAR
        else:
            style = NONE if not entries else (NUMERIC if numbered_list else AUTHOR_YEAR)

    issues: list[Issue] = []
    unresolved: list[Unresolved] = []
    detail = ""
    if style == NUMERIC:
        if not numbered_list:  # unnumbered list with numeric citations: number by position, per file
            counts: dict[str, int] = {}
            for e in entries:
                counts[e.block.source] = counts.get(e.block.source, 0) + 1
                e.number = counts[e.block.source]
        # "(3)" is also how lists, equations and issue numbers look, so parentheses are only
        # treated as citations when they clearly dominate the other numeric styles.
        strong = max(("bracket", "superscript"), key=lambda k: detected[k])
        paren_dominant = detected["parenthesis"] >= 5 and detected["parenthesis"] >= 2 * max(detected[strong], 1)
        detail = "parenthesis" if paren_dominant else strong if detected[strong] else "bracket"
        use = ["bracket", "superscript", "refword"] + (["parenthesis"] if detail == "parenthesis" else [])
        cites = [c for k in use for c in numeric_found[k]]
        _resolve_numeric(entries, cites, unresolved, structure)
        _numeric_issues(entries, cites, unresolved, issues, detected, detail, position)
    elif style == AUTHOR_YEAR:
        entries = _merge_author_year_fragments(entries)
        for e in entries:
            e.number = None
        _resolve_author_year(entries, ay_found, unresolved, issues)
        _author_year_issues(entries, issues)

    if not list_found:
        any_cites = detected["bracket"] + detected["superscript"] + detected["author_year"]
        if any_cites:
            issues.insert(0, _issue("error", f"Found {any_cites} citation(s) but no reference list. Add a "
                                             "“References” heading before the list (or use Word's Bibliography style).",
                                    "no_list"))
    for e in entries:
        e.citations.sort(key=lambda c: (position[id(c.block)], c.start))
    severity_rank = {"error": 0, "warning": 1, "info": 2}
    issues.sort(key=lambda i: severity_rank[i.severity])
    return RefReport(style, detail, detected, entries, unresolved, issues, list_found)


def _lists_for(source: str, structure: Structure) -> list[str]:
    """Which files' reference lists a citation in `source` may resolve to, in order."""
    manuscript = [s.source for s in structure.ref_sections if any(b.role == "manuscript" for b in s.blocks)]
    others = [s.source for s in structure.ref_sections]
    return list(dict.fromkeys([source] + manuscript + others))


def _resolve_numeric(entries, cites, unresolved, structure):
    if not entries:
        return  # no list at all: reported once as "no_list", not as N "not in list" errors
    by_file: dict[str, dict[int, RefEntry]] = {}
    for e in entries:
        by_file.setdefault(e.block.source, {}).setdefault(e.number, e)
    for c in cites:
        target = next((by_file[src][c.number] for src in _lists_for(c.block.source, structure)
                       if src in by_file and c.number in by_file[src]), None)
        if target:
            target.citations.append(c)
        else:
            unresolved.append(Unresolved(c))


def _numeric_issues(entries, cites, unresolved, issues, detected, detail, position):
    total = len(entries)
    for e in entries:
        if not e.citations:
            issues.append(_issue("error", f"Reference {e.number} is never cited in the text: “{_short(e.text)}”.",
                                 "uncited", e.id))
    seen: set[int] = set()
    for u in sorted(unresolved, key=lambda u: (position[id(u.citation.block)], u.citation.start)):
        n = u.citation.number
        if n in seen:
            continue
        seen.add(n)
        u.hint = f"The reference list has {total} entries." if total else "No reference list was found."
        issues.append(_issue("error", f"Reference {n} is cited (first at {u.citation.block.location}) but is not in "
                                      f"the reference list. {u.hint}", "unresolved"))

    # Numbered lists should be ordered by first citation (Vancouver). Only checked when the
    # document mostly follows that order, so alphabetically numbered lists are not spammed.
    body = [c for c in cites if not c.in_caption and any(c.number == e.number for e in entries)]
    body.sort(key=lambda c: (position[id(c.block)], c.start, c.number))
    first: list[Citation] = []
    for c in body:
        if c.number not in {f.number for f in first}:
            first.append(c)
    if len(first) >= 5:
        in_order = sum(1 for a, b in zip(first, first[1:]) if b.number > a.number)
        if in_order / (len(first) - 1) >= 0.7:
            high = 0
            reported = 0
            for c in first:
                if c.number > high + 1 and reported < 10:
                    missing = high + 1
                    issues.append(_issue(
                        "warning",
                        f"Reference {c.number} is first cited at {c.block.location}, before reference {missing}. "
                        "References should be numbered in order of first citation.",
                        "order",
                        next((e.id for e in entries if e.number == c.number), ""),
                    ))
                    reported += 1
                high = max(high, c.number)
        else:
            issues.append(_issue("info", "References are not numbered in order of first citation (the list may be "
                                         "alphabetical), so citation order was not checked.", "order_skipped"))

    numbers = [e.number for e in entries if e.number is not None]
    dupes = sorted({n for n in numbers if numbers.count(n) > 1})
    if dupes:
        issues.append(_issue("warning", f"Reference number(s) {', '.join(map(str, dupes))} appear more than once in the list.",
                             "list_numbering"))
    if numbers:
        gaps = sorted(set(range(1, max(numbers) + 1)) - set(numbers))
        if gaps and len(gaps) <= 20:
            issues.append(_issue("warning", f"Reference list numbering skips {', '.join(map(str, gaps))}.", "list_numbering"))
    _duplicate_entries(entries, issues)
    # "(3)" is ambiguous (lists, equations), so it only counts as a competing style when chosen.
    considered = ("bracket", "superscript", "parenthesis") if detail == "parenthesis" else ("bracket", "superscript")
    styles = {k: v for k, v in detected.items() if k in considered and v}
    if len(styles) > 1 and detail:
        others = ", ".join(f"{v} {k}" for k, v in styles.items() if k != detail)
        issues.append(_issue("info", f"Citations are mostly {detail} style ({styles[detail]}), but there are also "
                                     f"{others} citation(s). Check they are consistent.", "mixed_style"))


def _resolve_author_year(entries, cites, unresolved, issues):
    if not entries:
        return
    by_key: dict[str, list[RefEntry]] = {}
    for e in entries:
        by_key.setdefault(e.key, []).append(e)
        if e.alt_key and e.alt_key != e.key:
            by_key.setdefault(e.alt_key, []).append(e)
    ambiguous_reported: set[tuple[str, str]] = set()
    for c in cites:
        candidates = by_key.get(c.key, [])
        exact = [e for e in candidates if e.year == c.year]
        base = [e for e in candidates if e.year[:4] == c.year[:4]] if c.year[:4].isdigit() else exact
        matched = exact or (base if len(base) == 1 else [])
        if not matched and len(base) > 1:
            matched = base
            if (c.key, c.year) not in ambiguous_reported:
                ambiguous_reported.add((c.key, c.year))
                issues.append(_issue("warning", f"“{c.author}, {c.year}” (at {c.block.location}) matches "
                                     f"{len(base)} references: {', '.join(e.label for e in base)}. Add a/b suffixes to "
                                     "the years in the list and the text.", "ambiguous", base[0].id))
        for e in matched:
            if c not in e.citations:
                e.citations.append(c)
        if not matched and c.confident:
            unresolved.append(Unresolved(c, _author_year_hint(c, entries, by_key)))
    seen: set[tuple[str, str]] = set()
    for u in unresolved:
        c = u.citation
        if (c.key, c.year) in seen:
            continue
        seen.add((c.key, c.year))
        issues.append(_issue("error", f"“{c.author}, {c.year}” is cited (first at {c.block.location}) but is not in "
                                      f"the reference list.{(' ' + u.hint) if u.hint else ''}", "unresolved"))


def _author_year_hint(c: Citation, entries: list[RefEntry], by_key: dict[str, list[RefEntry]]) -> str:
    same_author = by_key.get(c.key, [])
    if same_author:
        return f"The list has {', '.join(e.label for e in same_author)}: is the year wrong?"
    close = [e for e in entries if e.key and _edit_distance(e.key, c.key) <= 1 and e.year[:4] == c.year[:4]]
    if close:
        return f"Did you mean {close[0].label}? (spelling differs)"
    return ""


def _author_year_issues(entries, issues):
    for e in entries:
        if not e.citations:
            issues.append(_issue("error", f"{e.label} is in the reference list but never cited: “{_short(e.text)}”.",
                                 "uncited", e.id))
        if not e.year:
            issues.append(_issue("warning", f"No year found in reference “{_short(e.text)}”.", "no_year", e.id))
    # Author-year lists are alphabetical by first author.
    keyed = [e for e in entries if e.key]
    out_of_order = [(a, b) for a, b in zip(keyed, keyed[1:])
                    if a.block.source == b.block.source and norm(b.author) < norm(a.author)]
    if out_of_order and len(out_of_order) <= max(3, len(keyed) // 5):
        for a, b in out_of_order[:5]:
            issues.append(_issue("warning", f"Reference list is not alphabetical: {b.label} comes after {a.label}.",
                                 "alphabetical", b.id))
    elif out_of_order:
        issues.append(_issue("info", f"The reference list is not in alphabetical order ({len(out_of_order)} places).",
                             "alphabetical"))
    _duplicate_entries(entries, issues)


def _duplicate_entries(entries, issues):
    seen: dict[str, RefEntry] = {}
    for e in entries:
        keys = [("doi", e.doi)] if e.doi else []
        keys.append(("text", norm(e.text)[:150]))
        for kind, k in keys:
            if len(k) < 20 and kind == "text":
                continue
            if (kind, k) in seen and seen[(kind, k)] is not e:
                first = seen[(kind, k)]
                why = "same DOI" if kind == "doi" else "same text"
                issues.append(_issue("warning", f"{e.label} duplicates {first.label} ({why}): “{_short(e.text)}”.",
                                     "duplicate", e.id))
                break
            seen.setdefault((kind, k), e)


def _short(text: str, n: int = 90) -> str:
    return text if len(text) <= n else text[:n].rstrip() + "…"


def _edit_distance(a: str, b: str) -> int:
    if abs(len(a) - len(b)) > 1:
        return 2
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1]
