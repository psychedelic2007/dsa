"""Command-line entry point.

    python -m manuscript_checker.cli paper.docx --figures legends.docx --supp SI.docx

Exits with status 1 if any error-level issue is found, so it can gate a build.
"""

import argparse
import json
import sys
from pathlib import Path

from .extract import load_blocks
from .figures import check_figures
from .report import to_dict


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Check that every figure is captioned and cited.")
    ap.add_argument("manuscript", nargs="+", help="main manuscript file(s): .docx, .pdf, .txt, .md")
    ap.add_argument("--figures", nargs="*", default=[], help="separate main figure/legend file(s)")
    ap.add_argument("--supp", nargs="*", default=[], help="supplementary file(s)")
    ap.add_argument("--json", action="store_true", help="print the full report as JSON")
    args = ap.parse_args(argv)

    blocks = []
    for role, paths in (("manuscript", args.manuscript), ("figures", args.figures), ("supplementary", args.supp)):
        for path in paths:
            blocks += load_blocks(Path(path).name, Path(path).read_bytes(), role)
    report = check_figures(blocks)

    if args.json:
        print(json.dumps(to_dict(report), indent=2, ensure_ascii=False))
    else:
        for f in report.figures:
            print(f"{f.status:8} {f.key.label:40} captions={len(f.captions)} body citations={len(f.body_mentions)}")
        print()
        for issue in report.issues:
            print(f"[{issue.severity.upper()}] {issue.message}")
        if not report.issues:
            print("No issues found.")
    return 1 if report.errors else 0


if __name__ == "__main__":
    sys.exit(main())
