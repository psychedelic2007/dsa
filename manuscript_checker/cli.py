"""Command-line entry point (run from the folder that contains manuscript_checker/):

    python -m manuscript_checker.cli paper.docx --figures legends.docx --supp SI.docx

Exits with status 1 if any error-level issue is found, so it can gate a build.
"""

import argparse
import json
import sys
from pathlib import Path

from .analyze import analyze
from .extract import load_document
from .report import to_dict


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Pre-submission checks: figures, tables, references, proofing.")
    ap.add_argument("manuscript", nargs="+", help="main manuscript file(s): .docx, .pdf, .txt, .md")
    ap.add_argument("--figures", nargs="*", default=[], help="separate figure/table legend file(s)")
    ap.add_argument("--supp", nargs="*", default=[], help="supplementary file(s)")
    ap.add_argument("--ref-style", choices=["auto", "numeric", "author-year"], default="auto")
    ap.add_argument("--json", action="store_true", help="print the full report as JSON")
    args = ap.parse_args(argv)

    docs = []
    for role, paths in (("manuscript", args.manuscript), ("figures", args.figures), ("supplementary", args.supp)):
        for path in paths:
            docs.append(load_document(Path(path).name, Path(path).read_bytes(), role))
    report = to_dict(analyze(docs, args.ref_style))

    if args.json:
        print(json.dumps(report, indent=2, ensure_ascii=False))
    else:
        refs = report["references"]
        print(f"Figures: {report['figures']['summary']['items']}   Tables: {report['tables']['summary']['items']}   "
              f"References: {refs['summary']['entries']} ({refs['style']}{', ' + refs['detail'] if refs['detail'] else ''})")
        print()
        for issue in report["issues"]:
            print(f"[{issue['severity'].upper():7}] {issue['category']:10} {issue['message']}")
        if not report["issues"]:
            print("No issues found.")
    return 1 if report["summary"]["errors"] else 0


if __name__ == "__main__":
    sys.exit(main())
