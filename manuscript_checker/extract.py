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
    if re.search(r"supp|(^|[^a-z])si([^a-z]|$)|appendix|extended", name):
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


def _pdf_blocks(data: bytes, source: str, role: str) -> list[Block]:
    import pdfplumber

    blocks: list[Block] = []
    current: list[str] = []
    current_page = 1
    prev_line = ""

    def flush():
        text, sup = unicode_superscripts(" ".join(current).strip())
        if text:
            blocks.append(Block(text, source, role, len(blocks) + 1, page=current_page, sup=sup))
        current.clear()

    with pdfplumber.open(io.BytesIO(data)) as pdf:
        for page_no, page in enumerate(pdf.pages, start=1):
            lines = [ln.strip() for ln in clean(page.extract_text() or "").splitlines() if ln.strip()]
            # Submission PDFs often carry line numbers. Strip them only when most lines
            # have one, so "...in Figure\n2 shows" keeps its "2" in normal PDFs.
            if lines and sum(bool(_LINE_NUMBER.match(ln)) for ln in lines) > 0.6 * len(lines):
                lines = [_LINE_NUMBER.sub("", ln, count=1) for ln in lines]
            for line in lines:
                prev_word = prev_line.split()[-1].lower() if prev_line.split() else ""
                starts_caption = bool(_CAPTION_START.match(line)) and prev_word not in _CONTINUATION_WORDS
                new_sentence = bool(_SENTENCE_END.search(prev_line)) and line[:1].isupper()
                if current and (starts_caption or new_sentence):
                    flush()
                if not current:
                    current_page = page_no
                current.append(line)
                prev_line = line
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
