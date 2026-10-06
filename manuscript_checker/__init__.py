"""Pre-submission checks for manuscripts: figures, tables, references and proofing."""

from .analyze import Analysis, analyze
from .extract import Block, Document, guess_role, load_blocks, load_document
from .labels import LabelReport, check_figures, check_tables

__all__ = ["Analysis", "Document", "analyze", "load_document", "Block", "LabelReport", "check_figures", "check_tables", "guess_role", "load_blocks"]
