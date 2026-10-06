"""Cross-check figure captions against figure citations.

Everything here is deterministic pattern matching. Figure labels follow a small,
closed grammar ("Fig. 2a-c", "Figures 1 and S3", "Supplementary Fig. 4"), so a
grammar gives exact, explainable answers where a learned model would only add
error and latency.
"""

import re
from dataclasses import dataclass, field

from .extract import Block

MAIN, SUPP, EXT = "main", "supplementary", "extended"
KIND_ORDER = (MAIN, SUPP, EXT)
KIND_NAMES = {MAIN: "Figure", SUPP: "Supplementary Figure", EXT: "Extended Data Figure"}
ROLE_ORDER = {"manuscript": 0, "figures": 1, "supplementary": 2}

_PREFIX = r"(?P<prefix>Supplementary|Supplemental|Suppl?\.?|(?-i:SI)|Extended\s+Data)"
_KEYWORD = r"(?:Figures?|Figs?\.?)"
# "3", "S3", "S-3", and chapter-style thesis numbering "3.2" / "3.2.1". The lookahead
# stops "Figure 2019" or "Fig. 1234" from being read as a figure number.
_RAW_NUM = r"(?:S[-‐]?)?\d{1,3}(?:\.\d{1,3}){0,2}"
_NUM = rf"{_RAW_NUM}(?!\d)"
_PANEL = r"(?:[A-Za-z]{1,2}(?![A-Za-z])|\([A-Za-z]{1,2}\))"
_ITEM = rf"{_NUM}{_PANEL}?"
_SEP = r"\s*(?:,\s*(?:and\s+|&\s*)?|&|\band\b|\bor\b|\bto\b|[-–—‐])\s*"
_LIST = rf"{_ITEM}(?:{_SEP}(?:{_ITEM}|{_PANEL}))*"

MENTION_RE = re.compile(rf"\b(?:{_PREFIX}\s*)?{_KEYWORD}\s*(?P<items>{_LIST})", re.IGNORECASE)
CAPTION_RE = re.compile(
    rf"^[\s*_#>\[(]*(?:{_PREFIX}\s*)?{_KEYWORD}\s*(?P<num>{_NUM})(?P<panel>[A-Za-z](?![A-Za-z]))?(?P<after>.*)$",
    re.IGNORECASE | re.DOTALL,
)
_TOKEN_RE = re.compile(rf"(?P<num>{_RAW_NUM})|(?P<range>[-–—‐]|\bto\b)|(?P<word>[A-Za-z]+)", re.I)
# "List of Figures" / table-of-contents entries: dot leaders or a tab before a page number.
# Four or more dots, so an ellipsis inside a caption ("1 ... 10") is not mistaken for a leader.
_TOC_ENTRY = re.compile(r"(?:(?:\.\s?){4,}|…{2,}|\t)\s*\d+\s*$")
# "(A)", "(a–c)", "(i, ii)" directly after the label: a panel key, which only captions have.
_PANEL_KEY = re.compile(r"\s*\(\s*[A-Za-z0-9]{1,3}(?:\s*[-–,]\s*[A-Za-z0-9]{1,3})*\s*\)\s*[A-Z]")
_MAX_RANGE = 50


@dataclass(frozen=True, order=True)
class FigureKey:
    kind_rank: int
    number: tuple[int, ...]

    @property
    def kind(self) -> str:
        return KIND_ORDER[self.kind_rank]

    @property
    def label(self) -> str:
        num = ".".join(map(str, self.number))
        if self.kind == SUPP:
            return f"Supplementary Figure {num} (S{num})"
        return f"{KIND_NAMES[self.kind]} {num}"


@dataclass
class Caption:
    key: FigureKey
    text: str
    block: Block


@dataclass
class Mention:
    key: FigureKey
    matched: str  # the exact text that was matched, e.g. "Figs. 2-4"
    block: Block
    in_caption: bool  # mention sits inside a figure legend rather than body text

    @property
    def snippet(self) -> str:
        text = self.block.text
        i = text.find(self.matched)
        lo, hi = max(0, i - 60), min(len(text), i + len(self.matched) + 60)
        return ("…" if lo else "") + text[lo:hi].strip() + ("…" if hi < len(text) else "")


@dataclass
class FigureStatus:
    key: FigureKey
    captions: list[Caption] = field(default_factory=list)
    mentions: list[Mention] = field(default_factory=list)
    # Blocks that start with this figure's label but were not accepted as its caption.
    suspects: list[Block] = field(default_factory=list)

    @property
    def body_mentions(self) -> list[Mention]:
        return [m for m in self.mentions if not m.in_caption]

    @property
    def status(self) -> str:
        if not self.captions:
            return "MISSING"  # cited, but no caption/legend found anywhere
        if not self.body_mentions:
            return "UNCITED"  # caption exists, never cited in body text
        return "OK"


@dataclass
class Issue:
    severity: str  # "error" | "warning" | "info"
    message: str
    key: FigureKey | None = None
    code: str = ""  # missing | suspect | uncited | duplicate | supp_only | gap | order


@dataclass
class FigureReport:
    figures: list[FigureStatus]
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


def _key(kind: str, number: tuple[int, ...]) -> FigureKey:
    return FigureKey(KIND_ORDER.index(kind), number)


def _expand(start: tuple[int, ...], end: tuple[int, ...]) -> list[tuple[int, ...]]:
    if start[:-1] == end[:-1] and 0 < end[-1] - start[-1] <= _MAX_RANGE:
        return [start[:-1] + (n,) for n in range(start[-1] + 1, end[-1] + 1)]
    return [end]  # cross-chapter or implausible range: keep only the endpoint


def parse_mentions(block: Block, in_caption: bool, skip_span: tuple[int, int] | None = None) -> list[Mention]:
    mentions = []
    for m in MENTION_RE.finditer(block.text):
        if skip_span and m.start() < skip_span[1] and m.end() > skip_span[0]:
            continue
        prefix = m.group("prefix")
        keys: list[FigureKey] = []
        last: tuple[str, tuple[int, ...]] | None = None
        pending_range = False
        for tok in _TOKEN_RE.finditer(m.group("items")):
            if tok.group("num"):
                s_prefixed, number = _parse_number(tok.group("num"))
                kind = _kind(prefix, s_prefixed, block.role)
                if pending_range and last:
                    kind = last[0]  # "S1-3": the end inherits the start's kind
                    keys += [_key(kind, n) for n in _expand(last[1], number)]
                else:
                    keys.append(_key(kind, number))
                last = (kind, number)
                pending_range = False
            elif tok.group("range"):
                pending_range = True
            elif tok.group("word") and tok.group("word").lower() not in ("and", "or"):
                pending_range = False  # "2a-d" is a panel range, not a figure range
        for key in dict.fromkeys(keys):
            mentions.append(Mention(key, m.group(0), block, in_caption))
    return mentions


def parse_caption(block: Block) -> tuple[Caption, tuple[int, int]] | None:
    """Return the caption defined by this block, if it starts with a figure label."""
    m = CAPTION_RE.match(block.text)
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
    key = _key(_kind(m.group("prefix"), s_prefixed, block.role), number)
    return Caption(key, block.text, block), m.span("num")


def _is_toc_entry(block: Block) -> bool:
    style = block.style.lower()
    if "toc" in style or "table of figures" in style:
        return True
    return "caption" not in style and bool(_TOC_ENTRY.search(block.text))


def check_figures(blocks: list[Block]) -> FigureReport:
    blocks = sorted(blocks, key=lambda b: ROLE_ORDER.get(b.role, 99))  # stable: keeps file order
    statuses: dict[FigureKey, FigureStatus] = {}

    def status(key: FigureKey) -> FigureStatus:
        return statuses.setdefault(key, FigureStatus(key))

    label_starts: list[tuple[Block, list[Mention]]] = []
    for block in blocks:
        if _is_toc_entry(block):
            continue
        parsed = parse_caption(block)
        if not parsed:
            # Only labels at (or within a short panel-key prefix of) the start of a block, and
            # not in parentheses: "Mutational scanning (Fig. S5) ..." is a citation, not a caption.
            early = []
            for m in parse_mentions(block, in_caption=False):
                start = block.text.find(m.matched)
                if start <= 12 and not block.text[:start].rstrip().endswith(("(", "[")):
                    early.append(m)
            if early:
                label_starts.append((block, early))
        if parsed:
            caption, own_span = parsed
            status(caption.key).captions.append(caption)
            # Other figures named inside a legend ("as in Fig. 2") do not count as citations.
            mentions = parse_mentions(block, in_caption=True, skip_span=(0, own_span[1]))
        else:
            # Everything in a dedicated legends file is legend text, even continuation paragraphs.
            mentions = parse_mentions(block, in_caption=block.role == "figures")
        for mention in mentions:
            status(mention.key).mentions.append(mention)

    for block, early in label_starts:
        for m in early:
            if m.key in statuses and not statuses[m.key].captions:
                statuses[m.key].suspects.append(block)

    figures = sorted(statuses.values(), key=lambda s: s.key)
    position = {id(b): i for i, b in enumerate(blocks)}
    return FigureReport(figures, _issues(figures, position))


def _issues(figures: list[FigureStatus], position: dict[int, int]) -> list[Issue]:
    issues: list[Issue] = []
    for f in figures:
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
            note = " It is only mentioned inside other figure legends." if f.mentions else ""
            issues.append(Issue("error", f"{f.key.label} has a caption but is never cited in the text.{note}", f.key, code="uncited"))
        if len(f.captions) > 1:
            places = "; ".join(c.block.location for c in f.captions)
            issues.append(Issue("warning", f"{f.key.label} has {len(f.captions)} captions: {places}.", f.key, code="duplicate"))
        if f.key.kind == SUPP and f.body_mentions and all(m.block.role == "supplementary" for m in f.body_mentions):
            issues.append(Issue("info", f"{f.key.label} is cited only in the supplementary text, never in the main manuscript.", f.key, code="supp_only"))

    # Numbering gaps among captioned figures, per kind and per chapter prefix.
    groups: dict[tuple[int, tuple[int, ...]], set[int]] = {}
    for f in figures:
        if f.captions:
            groups.setdefault((f.key.kind_rank, f.key.number[:-1]), set()).add(f.key.number[-1])
    for (rank, chapter), numbers in groups.items():
        for n in sorted(set(range(1, max(numbers) + 1)) - numbers):
            key = FigureKey(rank, chapter + (n,))
            if key not in {f.key for f in figures}:
                issues.append(Issue("warning", f"Numbering gap: no caption or citation for {key.label}.", key, code="gap"))

    # Journals expect figures to be first cited in numerical order.
    first_seen: list[FigureKey] = []
    all_mentions = [m for f in figures for m in f.body_mentions]
    all_mentions.sort(key=lambda m: (position[id(m.block)], m.block.text.find(m.matched)))
    for m in all_mentions:
        if m.key not in first_seen:
            later = [k for k in first_seen if k.kind_rank == m.key.kind_rank and k.number > m.key.number]
            if later:
                issues.append(Issue(
                    "warning",
                    f"{m.key.label} is first cited at {m.block.location}, after {max(later).label} was already cited "
                    "(figures should be cited in numerical order).",
                    m.key,
                    code="order",
                ))
            first_seen.append(m.key)

    severity_rank = {"error": 0, "warning": 1, "info": 2}
    issues.sort(key=lambda i: (severity_rank[i.severity], i.key or FigureKey(0, ())))
    return issues

