"""Cross-check captions against citations for numbered objects: figures and tables.

Everything here is deterministic pattern matching. Labels follow a small, closed
grammar ("Fig. 2a-c", "Figures 1 and S3", "Supplementary Table 4"), so a grammar gives
exact, explainable answers where a learned model would only add error and latency.
"""

import re
from dataclasses import dataclass, field

from .extract import Block

MAIN, SUPP, EXT = "main", "supplementary", "extended"
KIND_ORDER = (MAIN, SUPP, EXT)
ROLE_ORDER = {"manuscript": 0, "figures": 1, "supplementary": 2}


@dataclass(frozen=True)
class Spec:
    name: str  # "figure" | "table"
    noun: str  # "Figure" | "Table"
    keyword: str  # regex for the label word
    legend: str  # what its caption is called, for messages


FIGURE = Spec("figure", "Figure", r"(?:Figures?|Figs?\.?)", "figure legends")
TABLE = Spec("table", "Table", r"(?:Tables?|Tabs?\.)", "table captions")
SPECS = {s.name: s for s in (FIGURE, TABLE)}

_PREFIX = r"(?P<prefix>Supplementary|Supplemental|Suppl?\.?|(?-i:SI)|Extended\s+Data)"
# "3", "S3", "S-3", and chapter-style thesis numbering "3.2" / "3.2.1". The lookahead
# stops "Figure 2019" or "Fig. 1234" from being read as a figure number.
_RAW_NUM = r"(?:S[-‐]?)?\d{1,3}(?:\.\d{1,3}){0,2}"
_NUM = rf"{_RAW_NUM}(?!\d)"
_PANEL = r"(?:[A-Za-z]{1,2}(?![A-Za-z])|\([A-Za-z]{1,2}\))"
_ITEM = rf"{_NUM}{_PANEL}?"
_SEP = r"\s*(?:,\s*(?:and\s+|&\s*)?|&|\band\b|\bor\b|\bto\b|[-–—‐])\s*"
_LIST = rf"{_ITEM}(?:{_SEP}(?:{_ITEM}|{_PANEL}))*"

_MENTION_RE = {
    s.name: re.compile(rf"\b(?:{_PREFIX}\s*)?{s.keyword}\s*(?P<items>{_LIST})", re.IGNORECASE) for s in SPECS.values()
}
_CAPTION_RE = {
    s.name: re.compile(
        rf"^[\s*_#>\[(]*(?:{_PREFIX}\s*)?{s.keyword}\s*(?P<num>{_NUM})(?P<panel>[A-Za-z](?![A-Za-z]))?(?P<after>.*)$",
        re.IGNORECASE | re.DOTALL,
    )
    for s in SPECS.values()
}
_TOKEN_RE = re.compile(rf"(?P<num>{_RAW_NUM})|(?P<range>[-–—‐]|\bto\b)|(?P<word>[A-Za-z]+)", re.I)
# "List of Figures" / table-of-contents entries: dot leaders or a tab before a page number.
# Four or more dots, so an ellipsis inside a caption ("1 ... 10") is not mistaken for a leader.
_TOC_ENTRY = re.compile(r"(?:(?:\.\s?){4,}|…{2,}|\t)\s*\d+\s*$")
# "(A)", "(a–c)", "(i, ii)" directly after the label: a panel key, which only captions have.
_PANEL_KEY = re.compile(r"\s*\(\s*[A-Za-z0-9]{1,3}(?:\s*[-–,]\s*[A-Za-z0-9]{1,3})*\s*\)\s*[A-Z]")
_MAX_RANGE = 50


@dataclass(frozen=True, order=True)
class LabelKey:
    spec: str  # "figure" | "table"
    kind_rank: int
    number: tuple[int, ...]

    @property
    def kind(self) -> str:
        return KIND_ORDER[self.kind_rank]

    @property
    def label(self) -> str:
        num = ".".join(map(str, self.number))
        noun = SPECS[self.spec].noun
        if self.kind == SUPP:
            return f"Supplementary {noun} {num} (S{num})"
        if self.kind == EXT:
            return f"Extended Data {noun} {num}"
        return f"{noun} {num}"


@dataclass
class Caption:
    key: LabelKey
    text: str
    block: Block


@dataclass
class Mention:
    key: LabelKey
    matched: str  # the exact text that was matched, e.g. "Figs. 2-4"
    block: Block
    in_caption: bool  # mention sits inside a figure legend / table caption rather than body text

    @property
    def snippet(self) -> str:
        text = self.block.text
        i = text.find(self.matched)
        lo, hi = max(0, i - 60), min(len(text), i + len(self.matched) + 60)
        return ("…" if lo else "") + text[lo:hi].strip() + ("…" if hi < len(text) else "")


@dataclass
class LabelStatus:
    key: LabelKey
    captions: list[Caption] = field(default_factory=list)
    mentions: list[Mention] = field(default_factory=list)
    # Blocks that start with this figure's label but were not accepted as its caption.
    suspects: list[Block] = field(default_factory=list)
    # Supplementary item cited while no supplementary file was uploaded: cannot be checked.
    unchecked: bool = False

    @property
    def body_mentions(self) -> list[Mention]:
        return [m for m in self.mentions if not m.in_caption]

    @property
    def status(self) -> str:
        if self.unchecked:
            return "UNCHECKED"
        if not self.captions:
            return "MISSING"  # cited, but no caption found anywhere
        if not self.body_mentions:
            return "UNCITED"  # caption exists, never cited in body text
        return "OK"


@dataclass
class Issue:
    severity: str  # "error" | "warning" | "info"
    message: str
    key: LabelKey | None = None
    code: str = ""  # missing | suspect | uncited | duplicate | supp_only | gap | order | ...
    target: str = ""  # id of the item the issue is about, for linking in the UI


@dataclass
class LabelReport:
    spec: Spec
    items: list[LabelStatus]
    issues: list[Issue]

    @property
    def errors(self) -> list[Issue]:
        return [i for i in self.issues if i.severity == "error"]


def _parse_number(raw: str) -> tuple[bool, tuple[int, ...]]:
    supp = raw[:1] in "sS"
    return supp, tuple(int(p) for p in raw.lstrip("sS-‐").split("."))


def _kind(prefix: str | None, s_prefixed: bool, role: str) -> str:
    if prefix:
        return EXT if prefix.lower().startswith("extended") else SUPP
    if s_prefixed:
        return SUPP
    # Supplementary files often restart numbering at "Figure 1" for what the main
    # text calls "Supplementary Figure 1".
    return SUPP if role == "supplementary" else MAIN


def _key(spec: Spec, kind: str, number: tuple[int, ...]) -> LabelKey:
    return LabelKey(spec.name, KIND_ORDER.index(kind), number)


def _expand(start: tuple[int, ...], end: tuple[int, ...]) -> list[tuple[int, ...]]:
    if start[:-1] == end[:-1] and 0 < end[-1] - start[-1] <= _MAX_RANGE:
        return [start[:-1] + (n,) for n in range(start[-1] + 1, end[-1] + 1)]
    return [end]  # cross-chapter or implausible range: keep only the endpoint


def parse_mentions(
    block: Block, in_caption: bool, skip_span: tuple[int, int] | None = None, spec: Spec = FIGURE
) -> list[Mention]:
    mentions = []
    for m in _MENTION_RE[spec.name].finditer(block.text):
        if skip_span and m.start() < skip_span[1] and m.end() > skip_span[0]:
            continue
        prefix = m.group("prefix")
        keys: list[LabelKey] = []
        last: tuple[str, tuple[int, ...]] | None = None
        pending_range = False
        for tok in _TOKEN_RE.finditer(m.group("items")):
            if tok.group("num"):
                s_prefixed, number = _parse_number(tok.group("num"))
                kind = _kind(prefix, s_prefixed, block.role)
                if pending_range and last:
                    kind = last[0]  # "S1-3": the end inherits the start's kind
                    keys += [_key(spec, kind, n) for n in _expand(last[1], number)]
                else:
                    keys.append(_key(spec, kind, number))
                last = (kind, number)
                pending_range = False
            elif tok.group("range"):
                pending_range = True
            elif tok.group("word") and tok.group("word").lower() not in ("and", "or"):
                pending_range = False  # "2a-d" is a panel range, not a figure range
        for key in dict.fromkeys(keys):
            mentions.append(Mention(key, m.group(0), block, in_caption))
    return mentions


def parse_caption(block: Block, spec: Spec = FIGURE) -> tuple[Caption, tuple[int, int]] | None:
    """Return the caption defined by this block, if it starts with a label of this spec."""
    m = _CAPTION_RE[spec.name].match(block.text)
    if not m:
        return None
    after = re.sub(r"^[\])]", "", m.group("after"))  # "[Figure 2] Title"
    is_caption_style = "caption" in block.style.lower()
    looks_like_caption = (
        is_caption_style
        or re.match(r"\s*(?:[.:|–—-]|$)", after)  # "Figure 2.", "Fig. 2 |", "Figure 2" alone
        or re.match(r"\s+[A-Z]", after)  # "Figure 2 Overview of ..." (no punctuation)
        or _PANEL_KEY.match(after)  # "Figure 2 (A) Overview ..."
    )
    # Body sentences such as "Figure 2 shows ..." continue in lower case.
    if not looks_like_caption:
        return None
    s_prefixed, number = _parse_number(m.group("num"))
    key = _key(spec, _kind(m.group("prefix"), s_prefixed, block.role), number)
    return Caption(key, block.text, block), m.span("num")


def is_caption(block: Block) -> bool:
    """True if the block is a caption of any kind (figure or table)."""
    return not is_toc_entry(block) and any(parse_caption(block, s) for s in SPECS.values())


def is_toc_entry(block: Block) -> bool:
    style = block.style.lower()
    if "toc" in style or "table of figures" in style:
        return True
    return "caption" not in style and bool(_TOC_ENTRY.search(block.text))


def check_labels(blocks: list[Block], spec: Spec) -> LabelReport:
    """Captions vs. citations for one spec. Pass blocks in document order, reference
    lists already removed."""
    blocks = sorted(blocks, key=lambda b: ROLE_ORDER.get(b.role, 99))  # stable: keeps file order
    statuses: dict[LabelKey, LabelStatus] = {}

    def status(key: LabelKey) -> LabelStatus:
        return statuses.setdefault(key, LabelStatus(key))

    label_starts: list[tuple[Block, list[Mention]]] = []
    for block in blocks:
        if is_toc_entry(block):
            continue
        parsed = parse_caption(block, spec)
        if not parsed:
            # Only labels at (or within a short panel-key prefix of) the start of a block, and
            # not in parentheses: "Mutational scanning (Fig. S5) ..." is a citation, not a caption.
            early = []
            for m in parse_mentions(block, in_caption=False, spec=spec):
                start = block.text.find(m.matched)
                if start <= 12 and not block.text[:start].rstrip().endswith(("(", "[")):
                    early.append(m)
            if early:
                label_starts.append((block, early))
        if parsed:
            caption, own_span = parsed
            status(caption.key).captions.append(caption)
            # Other labels named inside a caption ("as in Fig. 2") do not count as citations.
            mentions = parse_mentions(block, in_caption=True, skip_span=(0, own_span[1]), spec=spec)
        else:
            # Text in a dedicated legends file, or inside a caption of another kind ("Table 1.
            # ... see Figure 2"), is legend text, not a citation.
            legend = block.role == "figures" or is_caption(block)
            mentions = parse_mentions(block, in_caption=legend, spec=spec)
        for mention in mentions:
            status(mention.key).mentions.append(mention)

    for block, early in label_starts:
        for m in early:
            if m.key in statuses and not statuses[m.key].captions:
                statuses[m.key].suspects.append(block)

    items = sorted(statuses.values(), key=lambda s: s.key)
    if not any(b.role == "supplementary" for b in blocks):
        for s in items:
            if s.key.kind == SUPP and not s.captions:
                s.unchecked = True
    position = {id(b): i for i, b in enumerate(blocks)}
    return LabelReport(spec, items, _issues(items, position, spec))


def check_figures(blocks: list[Block]) -> LabelReport:
    return check_labels(blocks, FIGURE)


def check_tables(blocks: list[Block]) -> LabelReport:
    return check_labels(blocks, TABLE)


def _issues(items: list[LabelStatus], position: dict[int, int], spec: Spec) -> list[Issue]:
    issues: list[Issue] = []
    for f in items:
        if f.status == "MISSING":
            where = f.body_mentions[0].block.location if f.body_mentions else f.mentions[0].block.location
            issues.append(Issue("error", f"{f.key.label} is cited (first at {where}) but no caption was found.", f.key, code="missing"))
            for b in sorted(f.suspects, key=lambda b: b.role == "manuscript")[:3]:
                text = b.text if len(b.text) <= 90 else b.text[:90] + "…"
                issues.append(Issue(
                    "info",
                    f"Possible caption for {f.key.label} at {b.location} was not recognised as one: “{text}”. "
                    "A caption should begin with the label followed by '.', ':' or '|', or use Word's Caption style.",
                    f.key,
                    code="suspect",
                ))
        elif f.status == "UNCITED":
            note = f" It is only mentioned inside other {spec.legend}." if f.mentions else ""
            issues.append(Issue("error", f"{f.key.label} has a caption but is never cited in the text.{note}", f.key, code="uncited"))
        if len(f.captions) > 1:
            places = "; ".join(c.block.location for c in f.captions)
            issues.append(Issue("warning", f"{f.key.label} has {len(f.captions)} captions: {places}.", f.key, code="duplicate"))
        if f.key.kind == SUPP and f.body_mentions and all(m.block.role == "supplementary" for m in f.body_mentions):
            issues.append(Issue("info", f"{f.key.label} is cited only in the supplementary text, never in the main manuscript.", f.key, code="supp_only"))

    # Numbering gaps among captioned items, per kind and per chapter prefix.
    groups: dict[tuple[int, tuple[int, ...]], set[int]] = {}
    for f in items:
        if f.captions:
            groups.setdefault((f.key.kind_rank, f.key.number[:-1]), set()).add(f.key.number[-1])
    unchecked = [f for f in items if f.status == "UNCHECKED"]
    if unchecked:
        names = ", ".join(f"S{'.'.join(map(str, f.key.number))}" for f in unchecked)
        issues.append(Issue("warning", f"Supplementary {spec.noun.lower()}s {names} are cited, but no supplementary "
                                       "file was uploaded, so their captions could not be checked. Add the SI file "
                                       "with the role SUPPLEMENTARY.", unchecked[0].key, code="unchecked"))
    for (rank, chapter), numbers in groups.items():
        for n in sorted(set(range(1, max(numbers) + 1)) - numbers):
            key = LabelKey(spec.name, rank, chapter + (n,))
            if key not in {f.key for f in items}:
                issues.append(Issue("warning", f"Numbering gap: no caption or citation for {key.label}.", key, code="gap"))

    # Journals expect items to be first cited in numerical order.
    first_seen: list[LabelKey] = []
    all_mentions = [m for f in items for m in f.body_mentions]
    all_mentions.sort(key=lambda m: (position[id(m.block)], m.block.text.find(m.matched)))
    for m in all_mentions:
        if m.key not in first_seen:
            later = [k for k in first_seen if k.kind_rank == m.key.kind_rank and k.number > m.key.number]
            if later:
                issues.append(Issue(
                    "warning",
                    f"{m.key.label} is first cited at {m.block.location}, after {max(later).label} was already cited "
                    f"({spec.noun.lower()}s should be cited in numerical order).",
                    m.key,
                    code="order",
                ))
            first_seen.append(m.key)

    severity_rank = {"error": 0, "warning": 1, "info": 2}
    issues.sort(key=lambda i: (severity_rank[i.severity], i.key or LabelKey(spec.name, 0, ())))
    return issues

