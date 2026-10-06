"""Run every check over a set of uploaded documents."""

from dataclasses import dataclass

from .extract import Document
from .labels import FIGURE, MAIN, SUPP, TABLE, LabelReport, check_labels
from .proofing import ProofReport, run_proofing
from .references import RefReport, check_references
from .structure import Structure, analyse_structure


@dataclass
class Analysis:
    docs: list[Document]
    structure: Structure
    figures: LabelReport
    tables: LabelReport
    references: RefReport
    proofing: ProofReport


def analyze(docs: list[Document], ref_style: str = "auto", limits: dict | None = None) -> Analysis:
    structure = analyse_structure([b for d in docs for b in d.blocks])
    # Reference lists are excluded so "Figure 2" in a cited paper's title is not a citation.
    text = [b for b in structure.blocks if not structure.is_reference(b)]
    figures = check_labels(text, FIGURE)
    tables = check_labels(text, TABLE)
    references = check_references(structure, ref_style)

    def count(report: LabelReport, kind: str) -> int:
        return sum(1 for s in report.items if s.key.kind == kind and s.captions)

    counts = {
        "figures": count(figures, MAIN),
        "tables": count(tables, MAIN),
        "supplementary_figures": count(figures, SUPP),
        "supplementary_tables": count(tables, SUPP),
        "references": len(references.entries),
    }
    proofing = run_proofing(docs, structure, counts, limits)
    return Analysis(docs, structure, figures, tables, references, proofing)
