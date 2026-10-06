"""Turn uploaded files into an ordered list of text blocks.

A block is roughly a paragraph. The checks need two guarantees from this layer: a
caption starts at the beginning of a block, and a citation such as "Fig.\n2" is never
split across two blocks. DOCX also yields formatting the checks rely on: superscript
spans (superscript numeric citations), table cells, Word list numbering, and
document-level leftovers (tracked changes, comments, highlights).
"""

import io
import re
from dataclasses import dataclass, field
from pathlib import Path

ROLES = ("manuscript", "figures", "supplementary")
ROLE_LABELS = {
    "manuscript": "Main manuscript",
    "figures": "Main figures/tables (legends file)",
    "supplementary": "Supplementary material",
}

SUPPORTED_SUFFIXES = (".docx", ".pdf", ".txt", ".md")

# Zero-width spaces/joiners, BOM, word joiner and soft hyphen: invisible in Word, but they
# break "Figure S\u200b6" apart for pattern matching. Pasted text is full of them.
_INVISIBLE = dict.fromkeys(map(ord, "\u200b\u200c\u200d\u2060\ufeff\u00ad"))


def clean(text: str) -> str:
    return text.translate(_INVISIBLE).replace("\u00a0", " ")


_SUPERSCRIPT_DIGITS = str.maketrans("⁰¹²³⁴⁵⁶⁷⁸⁹⁻", "0123456789-")
_UNICODE_SUP = re.compile(r"[⁰¹²³⁴⁵⁶⁷⁸⁹][⁰¹²³⁴⁵⁶⁷⁸⁹,⁻\-–]*")


def unicode_superscripts(text: str) -> tuple[str, list[tuple[int, int]]]:
    """Turn "shown¹²" into "shown12" and remember (start, end) of the superscript run."""
    spans = [m.span() for m in _UNICODE_SUP.finditer(text)]
    return text.translate(_SUPERSCRIPT_DIGITS), spans


@dataclass
class Block:
    text: str
    source: str  # file name
    role: str  # one of ROLES
    index: int  # 1-based paragraph (DOCX/TXT) or block (PDF) number within the file
    style: str = ""  # Word paragraph style name, if any
    page: int | None = None  # PDF page number, if any
    in_table: bool = False  # inside a Word table cell
    numbered: bool = False  # Word auto-numbered list item (the number is not in `text`)
    sup: list[tuple[int, int]] = field(default_factory=list)  # superscript (start, end) spans

    @property
    def plain(self) -> str:
        """`text` with superscripts blanked out (same length, so offsets still line up):
        "complements SPR3–5" -> "complements SPR   " for word-level checks."""
        if not self.sup:
            return self.text
        chars = list(self.text)
        for a, b in self.sup:
            chars[a:b] = " " * (b - a)
        return "".join(chars)

    @property
    def is_heading(self) -> bool:
        style = self.style.lower()
        return style.startswith("heading") or style in ("title", "subtitle")

    @property
    def location(self) -> str:
        where = f"p. {self.page}, block {self.index}" if self.page else f"paragraph {self.index}"
        return f"{self.source} ({where})"


def guess_role(filename: str) -> str:
    name = Path(filename).stem.lower()
    # "MOESM"/"ESM" is Springer Nature's name for electronic supplementary material.
    if re.search(r"supp|(^|[^a-z])(si|esm)([^a-z]|$)|moesm|appendix|extended", name):
        return "supplementary"
    if re.search(r"fig|legend|caption|table", name):
        return "figures"
    return "manuscript"


@dataclass
class Document:
    name: str
    role: str
    blocks: list[Block]
    # DOCX only: counts of leftovers that should not reach a journal.
    tracked_insertions: int = 0
    tracked_deletions: int = 0
    comments: int = 0
    highlights: int = 0


def load_document(filename: str, data: bytes, role: str) -> Document:
    if role not in ROLES:
        raise ValueError(f"Unknown role {role!r}; expected one of {ROLES}")
    suffix = Path(filename).suffix.lower()
    if suffix == ".docx":
        return _docx_document(data, filename, role)
    if suffix == ".pdf":
        return Document(filename, role, _pdf_blocks(data, filename, role))
    if suffix in (".txt", ".md"):
        return Document(filename, role, _text_blocks(data.decode("utf-8", errors="replace"), filename, role))
    if suffix == ".doc":
        raise ValueError(f"{filename}: legacy .doc is not supported; save it as .docx first.")
    raise ValueError(f"{filename}: unsupported file type {suffix!r} (supported: {', '.join(SUPPORTED_SUFFIXES)})")


def load_blocks(filename: str, data: bytes, role: str) -> list[Block]:
    return load_document(filename, data, role).blocks


# --- DOCX -------------------------------------------------------------------

_W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
_MC_FALLBACK = "{http://schemas.openxmlformats.org/markup-compatibility/2006}Fallback"


def _docx_document(data: bytes, source: str, role: str) -> Document:
    import docx

    doc = docx.Document(io.BytesIO(data))
    style_names = {s.style_id: s.name for s in doc.styles}
    body = doc.element.body
    blocks = []
    paragraph_no = 0
    # Iterating every w:p in the body (not doc.paragraphs) also picks up paragraphs
    # inside tables and text boxes, which is where many figure captions live.
    for p in body.iter(f"{_W}p"):
        # Text boxes are stored twice (mc:Choice and a legacy mc:Fallback copy);
        # reading both would report every caption in a text box as a duplicate.
        ancestors = [a.tag for a in p.iterancestors()]
        if _MC_FALLBACK in ancestors:
            continue
        style_id = p.find(f"{_W}pPr/{_W}pStyle")
        style = ""
        if style_id is not None:
            sid = style_id.get(f"{_W}val", "")
            style = style_names.get(sid) or sid
        numbered = p.find(f"{_W}pPr/{_W}numPr") is not None
        segments = _docx_paragraph_segments(p)
        text = "".join(t for t, _ in segments)
        if not text.strip():
            continue
        paragraph_no += 1
        # A manual line break (Shift+Enter) often separates an image or panel labels from
        # the caption in the same paragraph; each line is its own block so the caption
        # still starts a block.
        for line, sup in _split_lines(segments):
            blocks.append(Block(line, source, role, paragraph_no, style=style, in_table=f"{_W}tc" in ancestors,
                                numbered=numbered, sup=sup))

    comments = 0
    for part in doc.part.package.iter_parts():
        if str(part.partname).endswith("/comments.xml"):
            comments += part.blob.count(b"<w:comment ")
    highlights = sum(1 for h in body.iter(f"{_W}highlight") if h.get(f"{_W}val", "none") != "none")
    return Document(
        source, role, blocks,
        tracked_insertions=sum(1 for _ in body.iter(f"{_W}ins")),
        tracked_deletions=sum(1 for _ in body.iter(f"{_W}del")),
        comments=comments,
        highlights=highlights,
    )


def _docx_paragraph_segments(p) -> list[tuple[str, bool]]:
    """(text, is_superscript) pieces of one paragraph, in order."""
    out: list[tuple[str, bool]] = []

    def walk(el, sup):
        for child in el:
            tag = child.tag
            if not isinstance(tag, str) or tag in (f"{_W}p", _MC_FALLBACK):
                # Nested paragraphs (text boxes) are visited separately by the caller.
                continue
            if tag == f"{_W}r":
                va = child.find(f"{_W}rPr/{_W}vertAlign")
                walk(child, va is not None and va.get(f"{_W}val") == "superscript")
                continue
            if tag == f"{_W}t":
                out.append((child.text or "", sup))
            elif tag == f"{_W}tab":
                out.append(("\t", sup))
            elif tag in (f"{_W}br", f"{_W}cr"):
                out.append(("\n", False))
            elif tag == f"{_W}noBreakHyphen":
                out.append(("-", sup))
            # w:delText (tracked deletions) and w:instrText (field codes) are skipped
            # by construction: only w:t contributes text.
            walk(child, sup)

    walk(p, False)
    return [(clean(t), sup) for t, sup in out]


def _split_lines(segments: list[tuple[str, bool]]) -> list[tuple[str, list[tuple[int, int]]]]:
    """Split segments at line breaks; return stripped lines with their superscript spans."""
    lines: list[tuple[str, list[tuple[int, int]]]] = []
    text, spans = "", []

    def flush():
        stripped = text.strip()
        if stripped:
            shift = len(text) - len(text.lstrip())
            u_text, u_spans = unicode_superscripts(stripped)
            own = [(a - shift, b - shift) for a, b in spans if b - shift > 0 and a - shift < len(stripped)]
            lines.append((u_text, own + u_spans))

    for piece, sup in segments:
        parts = piece.split("\n")
        for i, part in enumerate(parts):
            if i:
                flush()
                text, spans = "", []
            if sup and part:
                if spans and spans[-1][1] == len(text):  # merge adjacent superscript runs
                    spans[-1] = (spans[-1][0], len(text) + len(part))
                else:
                    spans.append((len(text), len(text) + len(part)))
            text += part
    flush()
    return lines


# --- PDF --------------------------------------------------------------------

# Words after which a line break is almost certainly mid-sentence, so a following
# line such as "Figure 2. The ..." is a wrapped citation, not a caption.
_CONTINUATION_WORDS = {
    "in", "see", "and", "or", "of", "to", "from", "with", "by", "also", "as", "both",
    "the", "our", "on", "at", "cf.", "e.g.,", "i.e.,", "(see", "(cf.", "in", "shown",
    "illustrated", "depicted", "presented", "summarized", "summarised", "listed",
}
_CAPTION_START = re.compile(
    r"^\s*(?:Supplementary|Supplemental|Suppl?\.?|SI|Extended\s+Data)?\s*"
    r"(?:Figures?|Figs?\.?|Tables?)\s*S?\d{1,3}(?:\.\d{1,3}){0,2}\s*(?:[.:|–—-]|$)",
    re.IGNORECASE,
)
_SENTENCE_END = re.compile(r"[.!?:][\"')\]]*$")
_LINE_NUMBER = re.compile(r"^\d{1,5}\s+")
_KEYWORDS_LINE = re.compile(r"^\s*(?:key\s*words?|index\s+terms)\b", re.IGNORECASE)
# A period that ends an abbreviation, not a sentence: "(Fig." / "S7)." must stay together.
_ABBREV_END = re.compile(
    r"\b(?:Figs?|Tabs?|Refs?|Eqs?|Suppl|Supp|No|Nos|Vol|vs|cf|e\.g|i\.e|al|approx|ca|Dr|Prof|St|Sec|Ch|pp?)\.$",
    re.IGNORECASE,
)
# Section headings that must stay on their own line: otherwise "References" merges into the
# first entry ("References 1. Hampel...") and the reference list is never found.
_HEADING_LINE = re.compile(
    r"^\s*(?:\d+(?:\.\d+)*\.?\s+)?(?:abstract|summary|introduction|background|results?|discussion|conclusions?|"
    r"methods?|materials\s+and\s+methods|online\s+methods|references?|bibliography|literature\s+cited|"
    r"acknowledge?ments?|data\s+(?:and\s+code\s+)?availability|code\s+availability|author\s+contributions?|"
    r"competing\s+interests?|conflicts?\s+of\s+interests?|funding|additional\s+information|"
    r"supplementary\s+(?:information|materials?)|supporting\s+information|declarations?|ethics(?:\s+statement)?|"
    r"abbreviations|keywords?)\s*:?\s*$",
    re.IGNORECASE,
)


def _pdf_line(line: dict) -> tuple[str, list[tuple[int, int]]]:
    """Rebuild a PDF line from its characters, marking superscripts: smaller than the line's
    main font and raised above its baseline (subscripts like H2O sit lower, so they are not)."""
    # pdfplumber can list raised characters before the rest of the line; restore reading order.
    chars = sorted((c for c in line.get("chars", []) if c.get("text")), key=lambda c: c["x0"])
    if not chars:
        return clean(line.get("text", "")), [], False
    sizes: dict[float, int] = {}
    for c in chars:
        sizes[round(c["size"], 1)] = sizes.get(round(c["size"], 1), 0) + len(c["text"])
    main = max(sizes, key=sizes.get)
    main_bottoms = sorted(c["bottom"] for c in chars if round(c["size"], 1) == main)
    baseline = main_bottoms[len(main_bottoms) // 2]
    # Walk pdfplumber's own line text (its word spacing is reliable) and align each
    # character to it; anything not matching a character is an inserted space.
    line_text = line.get("text", "")
    text, spans, i, j = "", [], 0, 0
    while i < len(line_text):
        # Resynchronise over glyphs the line text does not contain (duplicated ligatures such
        # as "ff", dropped spaces) by looking a few characters ahead.
        k = next((k for k in range(j, min(j + 4, len(chars)))
                  if chars[k]["text"] and line_text.startswith(chars[k]["text"], i)), None)
        if k is None:
            text += line_text[i]  # a space pdfplumber inserted between words
            i += 1
            continue
        c, j = chars[k], k + 1
        piece = c["text"]
        sup = c["size"] <= 0.82 * main and c["bottom"] < baseline - 0.15 * main and not piece.isspace()
        if sup:
            if spans and spans[-1][1] == len(text):
                spans[-1] = (spans[-1][0], len(text) + len(piece))
            else:
                spans.append((len(text), len(text) + len(piece)))
        text += piece
        i += len(piece)
    visible = [c for c in chars if not c["text"].isspace()]
    bold = bool(visible) and all(re.search(r"bold|black|heavy|semibold", c.get("fontname", ""), re.I) for c in visible)
    return clean(text), spans, bold


def _strip_running_lines(pages: list[list[tuple]]) -> list[list[tuple]]:
    """Drop running headers/footers ("Scientific Reports | (2025) 15:13504 | ... 6"): lines in
    the first or last two positions of a page that recur, digits aside, on most pages."""
    if len(pages) < 3:
        return pages
    key = lambda t: re.sub(r"\d+", "#", t).strip(" /|").lower()
    counts: dict[str, int] = {}
    for lines in pages:
        for k in {key(ln[0]) for ln in lines[:2] + lines[-2:] if len(ln[0]) <= 160}:
            counts[k] = counts.get(k, 0) + 1
    running = {k for k, n in counts.items() if n >= max(3, 0.5 * len(pages))}
    out = []
    for lines in pages:
        edge = set(range(min(2, len(lines)))) | set(range(max(0, len(lines) - 2), len(lines)))
        out.append([ln for i, ln in enumerate(lines) if not (i in edge and key(ln[0]) in running)])
    return out


def _pdf_blocks(data: bytes, source: str, role: str) -> list[Block]:
    import pdfplumber

    with pdfplumber.open(io.BytesIO(data)) as pdf:
        pages = []
        for page in pdf.pages:
            lines = []
            for ln in page.extract_text_lines(return_chars=True):
                text, spans, bold = _pdf_line(ln)
                stripped = text.strip()
                if stripped:
                    shift = len(text) - len(text.lstrip())
                    lines.append((stripped, [(a - shift, b - shift) for a, b in spans if b - shift > 0], bold))
            pages.append(lines)
    pages = _strip_running_lines(pages)

    blocks: list[Block] = []
    current_text, current_sup = "", []
    current_page = 1
    current_heading = False
    prev_line, prev_bold_heading = "", False

    def flush():
        nonlocal current_text, current_sup, current_heading
        if current_text.strip():
            text, uni = unicode_superscripts(current_text)
            blocks.append(Block(text, source, role, len(blocks) + 1, page=current_page, sup=current_sup + uni,
                                style="Heading (bold)" if current_heading else ""))
        current_text, current_sup, current_heading = "", [], False

    for page_no, lines in enumerate(pages, start=1):
        # Submission PDFs often carry line numbers. Strip them only when most lines have one,
        # so "...in Figure\n2 shows" keeps its "2" in normal PDFs.
        if lines and sum(bool(_LINE_NUMBER.match(t)) for t, _, _ in lines) > 0.6 * len(lines):
            stripped = []
            for t, spans, bold in lines:
                m = _LINE_NUMBER.match(t)
                cut = m.end() if m else 0
                stripped.append((t[cut:], [(a - cut, b - cut) for a, b in spans if a >= cut], bold))
            lines = stripped
        # A short run (one or two lines) of entirely bold text is a (sub)section heading, e.g.
        # "Root mean square deviation (RMSD)", and must not merge into the paragraph below it.
        # Longer bold runs are bold paragraphs (Scientific Reports sets its abstract in bold).
        run_len = [0] * len(lines)
        i = 0
        while i < len(lines):
            j = i
            while j < len(lines) and lines[j][2]:
                j += 1
            for k in range(i, j):
                run_len[k] = j - i
            i = max(j, i + 1)
        for line_no, (line, spans, bold) in enumerate(lines):
            bold_heading = (bold and run_len[line_no] <= 2 and len(line) <= 100
                            and not line.rstrip().endswith(".") and not _CAPTION_START.match(line))
            heading = bool(_HEADING_LINE.match(line) or _KEYWORDS_LINE.match(line)) or bold_heading
            prev_word = prev_line.split()[-1].lower() if prev_line.split() else ""
            # A caption at the top of a page interrupts a sentence running over from the previous
            # page ("...interacting with" / "Fig. 2. Known inhibitors..."), so the wrapped-citation
            # guard does not apply there.
            starts_caption = bool(_CAPTION_START.match(line)) and (line_no == 0 or prev_word not in _CONTINUATION_WORDS)
            new_sentence = (bool(_SENTENCE_END.search(prev_line)) and not _ABBREV_END.search(prev_line)
                            and line[:1].isupper())
            prev_heading = bool(_HEADING_LINE.match(prev_line) or _KEYWORDS_LINE.match(prev_line)) or prev_bold_heading
            # A finished caption sentence followed by a lowercase line is body text resuming
            # around the figure ("...residue range." / "that although..."), not more caption.
            resumes_body = (bool(_CAPTION_START.match(current_text)) and bool(_SENTENCE_END.search(prev_line))
                            and line[:1].islower())
            if current_text and (starts_caption or new_sentence or heading or prev_heading or resumes_body):
                flush()
            if not current_text:
                current_page = page_no
            else:
                current_text += " "
            offset = len(current_text)
            current_sup += [(a + offset, b + offset) for a, b in spans]
            current_text += line
            current_heading = current_heading or bold_heading
            prev_line, prev_bold_heading = line, bold_heading
    flush()
    return blocks


# --- Plain text / Markdown --------------------------------------------------


def _text_blocks(text: str, source: str, role: str) -> list[Block]:
    text = clean(text)
    blocks = []
    for para in re.split(r"\n\s*\n", text):
        para, sup = unicode_superscripts(" ".join(ln.strip() for ln in para.splitlines()).strip())
        if para:
            blocks.append(Block(para, source, role, len(blocks) + 1, sup=sup))
    return blocks
