"""Locate the parts of a manuscript the checks need to tell apart: front matter
(title, authors, affiliations), abstract, reference lists, captions and main text."""

import re
from dataclasses import dataclass, field

from .extract import Block
from .labels import ROLE_ORDER, is_caption

_SECTION_PREFIX = r"^\s*(?:\d+(?:\.\d+)*\.?\s+|[IVX]+\.\s+)?"
REF_HEADING = re.compile(
    _SECTION_PREFIX
    + r"(?:(?:supplementary|supplemental|additional|methods|online\s+methods)\s+)?"
    r"(?:references?(?:\s+(?:cited|and\s+notes))?|bibliography|literature\s+cited|works\s+cited|reference\s+list|cited\s+literature)"
    r"(?:\s+for\s+[\w\s]+)?\s*:?\s*$",
    re.IGNORECASE,
)
_STOP_HEADING = re.compile(
    _SECTION_PREFIX
    + r"(?:acknowledge?ments?|supplementary|supporting\s+information|appendix|appendices|"
    r"figure\s+(?:legends|captions|titles)|figures?|tables?|author\s+contributions?|contributions|funding|"
    r"competing\s+interests?|conflicts?\s+of\s+interests?|declarations?|data\s+(?:and\s+code\s+)?availability|"
    r"code\s+availability|abbreviations|extended\s+data|methods|online\s+methods|ethics|additional\s+information)\b",
    re.IGNORECASE,
)
_ABSTRACT_HEADING = re.compile(_SECTION_PREFIX + r"(?:abstract|summary)\s*:?\s*$", re.IGNORECASE)
_ABSTRACT_INLINE = re.compile(r"^\s*(?:abstract|summary)\s*[:.—–-]\s*", re.IGNORECASE)
_KEYWORDS = re.compile(r"^\s*(?:key\s*words?|index\s+terms)\b", re.IGNORECASE)


def is_heading_like(block: Block) -> bool:
    """A Word heading, or a short line without sentence punctuation ("Results", "2.1 Data")."""
    if block.is_heading:
        return True
    text = block.text.strip()
    return len(text) <= 70 and not re.search(r"[.:;,]\s*$", text) and len(text.split()) <= 9 and text[:1].isalnum()


@dataclass
class RefSection:
    source: str
    heading: Block | None
    blocks: list[Block] = field(default_factory=list)


@dataclass
class Structure:
    blocks: list[Block]  # all blocks, document order (manuscript, legends, supplementary)
    ref_sections: list[RefSection]
    ref_ids: set[int]
    caption_ids: set[int]
    front_ids: set[int]  # title page of the main manuscript
    abstract: list[Block]
    abstract_text: str
    main_text: list[Block]  # manuscript body: no front matter, abstract, refs, captions, tables, headings

    def is_reference(self, b: Block) -> bool:
        return id(b) in self.ref_ids


def find_reference_sections(blocks: list[Block]) -> list[RefSection]:
    sections: list[RefSection] = []
    current: RefSection | None = None
    for b in blocks:
        if current and current.source != b.source:
            current = None
        short = len(b.text) <= 80
        if short and REF_HEADING.match(b.text):
            current = RefSection(b.source, b)
            sections.append(current)
            continue
        if current and ((short and (_STOP_HEADING.match(b.text) or b.is_heading)) or is_caption(b)):
            current = None
        bibliography_style = "bibliograph" in b.style.lower()
        if current is None and bibliography_style:
            # Zotero/EndNote/Mendeley bibliography paragraphs, even without a heading.
            current = RefSection(b.source, None)
            sections.append(current)
        if current is not None:
            current.blocks.append(b)
    return [s for s in sections if s.blocks]


def analyse_structure(blocks: list[Block]) -> Structure:
    blocks = sorted(blocks, key=lambda b: ROLE_ORDER.get(b.role, 99))
    sections = find_reference_sections(blocks)
    ref_ids = {id(b) for s in sections for b in s.blocks} | {id(s.heading) for s in sections if s.heading}
    caption_ids = {id(b) for b in blocks if id(b) not in ref_ids and is_caption(b)}

    manuscript = [b for b in blocks if b.role == "manuscript"]
    front_ids: set[int] = set()
    abstract: list[Block] = []
    abstract_text = ""
    start = 0
    for i, b in enumerate(manuscript[:60]):
        if len(b.text) <= 30 and _ABSTRACT_HEADING.match(b.text):
            front_ids = {id(x) for x in manuscript[:i + 1]}
            j = i + 1
            while j < len(manuscript) and not is_heading_like(manuscript[j]) and not _KEYWORDS.match(manuscript[j].text):
                abstract.append(manuscript[j])
                j += 1
            start = j
            break
        if len(b.text) > 150 and _ABSTRACT_INLINE.match(b.text):
            front_ids = {id(x) for x in manuscript[:i]}
            abstract = [b]
            start = i + 1
            break
    if abstract:
        abstract_text = " ".join(b.text for b in abstract)
        abstract_text = _ABSTRACT_INLINE.sub("", abstract_text, count=1)

    excluded = ref_ids | caption_ids | front_ids | {id(b) for b in abstract}
    main_text = [
        b for b in manuscript[start:]
        if id(b) not in excluded and not b.in_table and not is_heading_like(b) and not _KEYWORDS.match(b.text)
    ]
    return Structure(blocks, sections, ref_ids, caption_ids, front_ids, abstract, abstract_text, main_text)
