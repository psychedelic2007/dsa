"""Pre-submission consistency checks for manuscripts (figures first)."""

from .extract import Block, guess_role, load_blocks
from .figures import FigureReport, check_figures

__all__ = ["Block", "FigureReport", "check_figures", "guess_role", "load_blocks"]
