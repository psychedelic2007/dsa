# Submission check

Pre-submission checks for a manuscript, its figure/table legends and supplementary files:
figures and tables captioned and cited, references cited and in the list, and the
leftovers that should never reach a journal.

```bash
pip install -r manuscript_checker/requirements.txt
python manuscript_checker/run.py           # web UI at http://localhost:8000 (works from any directory)
```

From the repository root (the folder that contains `manuscript_checker/`) you can also run:

```bash
python -m manuscript_checker.cli paper.docx --supp SI.docx   # CLI; exit 1 on errors
python -m pytest manuscript_checker                          # tests
```

Requires Python 3.10+ (tested on 3.11 and 3.13). Everything is rule-based; no AI model
reads your manuscript, and nothing is stored.

## Figures and tables

| Status    | Meaning |
|-----------|---------|
| `OK`      | Caption found and cited in body text |
| `UNCITED` | Caption found, never cited in body text (mentions inside other captions do not count) |
| `MISSING` | Cited in the text, no caption anywhere |

Also: duplicate captions, numbering gaps, items first cited out of numerical order, and
supplementary items cited only in the SI. Figures and tables are separate (Figure 1 and
Table 1 never collide), and a figure mentioned inside a *table* caption is legend text.

- Citations: `Fig. 2`, `Figs. 1 and 4`, `Figures 2–4`, `Fig. 2a–d` (panels), `Figures 1 and S2`,
  `Supplementary/Suppl./SI Fig. 4`, `Extended Data Fig. 1`, `Table 3`, `Tab. 3`, `Tables S1–S3`,
  thesis numbering `Figure 3.2`.
- Captions: `Figure 1.`, `Fig. 2 |`, `Table 1:`, `Figure 4 Title…`, `Figure S6a.`,
  `Figure S6 (A) Title…`, `[Figure S6] Title`, and anything in Word's *Caption* style.
  `Figure 2 shows…` is a citation, not a caption. Captions after a manual line break, in
  tables and in text boxes are found; "List of Figures/Tables" entries are ignored.
- When an item is cited but no caption is accepted, paragraphs that *start* with its label
  are reported as "possible caption … not recognised".

## References

The style is detected automatically (override it in the UI or with `--ref-style`).

- **Numeric**: `[3]`, `[1–4, 7]`, `(3)` (only when parentheses are the dominant style),
  superscripts (Word formatting or Unicode ¹²), `ref. 5`/`refs 3–5`. Author-affiliation
  superscripts on the title page, units (`m²`) and exponents (`10⁵`) are ignored. Lists may
  be numbered as text (`1.`, `[1]`) or by Word's list numbering.
  Reports: entries never cited, citations beyond the list, references not numbered in order
  of first citation (skipped when the list is evidently alphabetical), duplicate entries
  (same DOI or text), numbering gaps, mixed citation styles.
- **Author–year**: `(Smith et al., 2019)`, `Smith and Jones (2019)`, `(e.g., Smith 2018, 2019a, b;
  Lee, 2020)`, `(reviewed by Zed, 2010)`, particles (`van der Waals`), accents (`Müller` = `Muller`),
  organisation acronyms (`WHO` = `World Health Organization`). Matching is driven by the
  list's first-author surnames and years, so prose like "In (2019)" is never an error.
  Reports: entries never cited, citations not in the list (with hints: "the list has Garcia
  2018: is the year wrong?", "did you mean Smyth 2019?"), ambiguous years needing a/b,
  duplicates, non-alphabetical lists, entries without a year.
- The list is found under a `References`/`Bibliography`/`Literature cited` heading (also
  "Methods references", "Supplementary references") or by Word's Bibliography styles
  (Zotero, EndNote, Mendeley). A citation in the SI resolves to the SI's own list first, then
  to the main list.

## Proofing

| Check | What it catches |
|-------|-----------------|
| Broken cross-references | `Error! Reference source not found.`, `Error! Bookmark not defined.`, LaTeX `Figure ??`, `[?]` |
| Tracked changes & comments | Unaccepted insertions/deletions, comments, highlights (DOCX) |
| Placeholders | `TODO`, `TBD`, `XX`, `[ref]`, `[citation needed]`, `???`, lorem ipsum |
| Required statements | Data availability, author contributions, competing interests, funding (plus acknowledgements, code, ethics) |
| Journal limits | Abstract and main-text words, figures, tables, references vs. limits you enter |
| Abbreviations | Used before definition, defined twice, defined but never used again, defined only in the abstract |
| Repeated words | "the the" (allowing "that that", "had had") |

Main-text word count excludes the title page, abstract, headings, captions, table cells and
references.

## File roles

- **Main manuscript**: body text; captions embedded here are detected too.
- **Figures/legends file**: everything is legend text, so it never counts as a figure or table
  citation (reference citations in legends do count).
- **Supplementary**: an unprefixed `Figure 1` here means Supplementary Figure 1, and
  `Supplementary Figure 1` / `Figure S1` are treated as the same figure.

## Known limitations

- **No LaTeX source** yet (`\label`/`\ref`/`\cite` need their own parser). Check the compiled PDF.
- **PDF is heuristic.** PDFs have no paragraphs or formatting, so superscript citations are
  invisible in PDF (they read as "shown12"), and line wrapping can split or merge
  reference entries. Prefer DOCX.
- **Author–year** matching uses the first author's surname and the year; it does not check
  that "Smith and Jones" names the right second author. Numeric `(3)` citations are only
  recognised when parentheses are the dominant style, because `(1)` is usually an enumeration.
- **Abbreviation** checks only see "long form (ABBR)" definitions and skip common ones (DNA, PCR…).
- Everything is matched by labels and numbers. Whether a caption describes the right image,
  or a reference supports the claim it is cited for, is not checked.
