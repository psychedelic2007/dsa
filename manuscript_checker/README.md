# Manuscript figure check

Pre-submission check that every figure is **captioned** and **cited**, across a
main manuscript, a separate legends file, and supplementary files.

```bash
pip install -r manuscript_checker/requirements.txt
python manuscript_checker/run.py           # web UI at http://localhost:8000 (works from any directory)
```

From the repository root (the folder that contains `manuscript_checker/`) you can also run:

```bash
python -m manuscript_checker.cli paper.docx --supp SI.docx   # CLI; exit 1 on errors
python -m pytest manuscript_checker                          # tests
```

Requires Python 3.10+ (tested on 3.11 and 3.13).

The web UI: drag in files, set each file's role, and get a figure map (click a tile to see
its caption and every citation in context), a citation-flow plot showing where in the
manuscript each figure is cited and which are out of order, an issue list, and
CSV/JSON/checklist export. Click **Load example** to try it without your own files.

## What it reports

| Status    | Meaning |
|-----------|---------|
| `OK`      | Caption found and cited in body text |
| `UNCITED` | Caption found, never cited in body text (mentions inside other legends do not count) |
| `MISSING` | Cited in the text, no caption anywhere |

Also: duplicate captions, numbering gaps, figures first cited out of numerical
order, and supplementary figures cited only in the SI and never in the main text.

## What it understands

- Citations: `Fig. 2`, `Fig.2a`, `Figs. 1 and 4`, `Figures 2, 3 and 5`, `Figures 2–4`,
  `Fig. 2a–d` (panel range, not a figure range), `Figure 1(b)`, `Figures 1 and S2`,
  `Figure S1–S3`, `Supplementary/Suppl./SI Fig. 4`, `Extended Data Fig. 1`,
  thesis numbering `Figure 3.2`, `Figures 3.1–3.3`.
- Captions: `Figure 1.`, `Fig. 2 |`, `**Figure 3:**`, `Figure 4 Title…`, a bare `Figure 5`,
  `Figure S6a.`, `Figure S6 (A) Title…`, `Figure S-6.`, `[Figure S6] Title`, and anything in
  Word's *Caption* style. `Figure 2 shows…` is a citation, not a caption.
- Captions after a manual line break (Shift+Enter) in the same paragraph as the image or
  panel labels; invisible characters (zero-width spaces, soft hyphens) are ignored.
- When a figure is cited but no caption is accepted, paragraphs that *start* with its label
  are reported as "possible caption … not recognised", so you can see why.
- DOCX: paragraphs in tables and text boxes, Word SEQ/REF fields, tracked deletions ignored,
  "List of Figures" / TOC entries ignored.
- PDF: wrapped lines, captions under axis labels, line-numbered submission PDFs.

## File roles

- **Main manuscript**: body text; captions embedded here are detected too.
- **Figures/legends file**: everything is legend text, so it never counts as a citation.
- **Supplementary**: an unprefixed `Figure 1` here means Supplementary Figure 1, and
  `Supplementary Figure 1` / `Figure S1` are treated as the same figure.

## Known limitations

- **No LaTeX** yet. LaTeX uses `\label`/`\ref`, not literal numbers, so it needs its own parser.
- **PDF is heuristic.** A PDF has no paragraphs, only positioned lines. A body sentence that
  wraps to start a line with `Figure 2. The…` after a word not on the continuation list will
  be read as a caption. Prefer DOCX.
- A comma list followed by an unrelated small number (`Figure 2, 3 participants`) reads `3`
  as a figure. Numbers of 4+ digits are never figure numbers.
- Figures are matched by number only. Whether a caption actually describes the figure it
  labels is not checked.
