"""Turn uploaded files into an ordered list of text blocks.

A block is roughly a paragraph. Figure detection only needs two guarantees from
this layer: a caption starts at the beginning of a block, and a citation such as
"Fig.\n2" is never split across two blocks.
"""

import io
import re
from dataclasses import dataclass
from pathlib import Path

ROLES = ("manuscript", "figures", "supplementary")
ROLE_LABELS = {
    "manuscript": "Main manuscript",
    "figures": "Main figures/tables (legends file)",
    "supplementary": "Supplementary material",
}

SUPPORTED_SUFFIXES = (".docx", ".pdf", ".txt", ".md")


@dataclass
class Block:
    text: str
    source: str  # file name
    role: str  # one of ROLES
    index: int  # 1-based paragraph (DOCX/TXT) or block (PDF) number within the file
    style: str = ""  # Word paragraph style name, if any
    page: int | None = None  # PDF page number, if any

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


def load_blocks(filename: str, data: bytes, role: str) -> list[Block]:
    if role not in ROLES:
        raise ValueError(f"Unknown role {role!r}; expected one of {ROLES}")
    suffix = Path(filename).suffix.lower()
    if suffix == ".docx":
        return _docx_blocks(data, filename, role)
    if suffix == ".pdf":
        return _pdf_blocks(data, filename, role)
    if suffix in (".txt", ".md"):
        return _text_blocks(data.decode("utf-8", errors="replace"), filename, role)
    if suffix == ".doc":
        raise ValueError(f"{filename}: legacy .doc is not supported; save it as .docx first.")
    raise ValueError(f"{filename}: unsupported file type {suffix!r} (supported: {', '.join(SUPPORTED_SUFFIXES)})")


# --- DOCX -------------------------------------------------------------------

_W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
_MC_FALLBACK = "{http://schemas.openxmlformats.org/markup-compatibility/2006}Fallback"


def _docx_blocks(data: bytes, source: str, role: str) -> list[Block]:
    import docx

    doc = docx.Document(io.BytesIO(data))
    style_names = {s.style_id: s.name for s in doc.styles}
    blocks = []
    # Iterating every w:p in the body (not doc.paragraphs) also picks up paragraphs
    # inside tables and text boxes, which is where many figure captions live.
    for p in doc.element.body.iter(f"{_W}p"):
        # Text boxes are stored twice (mc:Choice and a legacy mc:Fallback copy);
        # reading both would report every caption in a text box as a duplicate.
        if any(a.tag == _MC_FALLBACK for a in p.iterancestors()):
            continue
        text = _docx_paragraph_text(p).strip()
        if not text:
            continue
        style_id = p.find(f"{_W}pPr/{_W}pStyle")
        style = ""
        if style_id is not None:
            sid = style_id.get(f"{_W}val", "")
            style = style_names.get(sid) or sid
        blocks.append(Block(text, source, role, len(blocks) + 1, style=style))
    return blocks


def _docx_paragraph_text(p) -> str:
    out = []

    def walk(el):
        for child in el:
            tag = child.tag
            if not isinstance(tag, str) or tag in (f"{_W}p", _MC_FALLBACK):
                # Nested paragraphs (text boxes) are visited separately by the caller.
                continue
            if tag == f"{_W}t":
                out.append(child.text or "")
            elif tag == f"{_W}tab":
                out.append("\t")
            elif tag in (f"{_W}br", f"{_W}cr"):
                out.append(" ")
            elif tag == f"{_W}noBreakHyphen":
                out.append("-")
            # w:delText (tracked deletions) and w:instrText (field codes) are skipped
            # by construction: only w:t contributes text.
            walk(child)

    walk(p)
    return "".join(out)


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
        text = " ".join(current).strip()
        if text:
            blocks.append(Block(text, source, role, len(blocks) + 1, page=current_page))
        current.clear()

    with pdfplumber.open(io.BytesIO(data)) as pdf:
        for page_no, page in enumerate(pdf.pages, start=1):
            lines = [ln.strip() for ln in (page.extract_text() or "").splitlines() if ln.strip()]
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
    blocks = []
    for para in re.split(r"\n\s*\n", text):
        para = " ".join(ln.strip() for ln in para.splitlines()).strip()
        if para:
            blocks.append(Block(para, source, role, len(blocks) + 1))
    return blocks
