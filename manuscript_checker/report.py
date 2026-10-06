"""Plain-data views of a FigureReport, shared by the CLI and the web UI."""

from .extract import Block
from .figures import SUPP, EXT, FigureKey, FigureReport


def short_label(key: FigureKey) -> str:
    num = ".".join(map(str, key.number))
    return {SUPP: f"S{num}", EXT: f"ED{num}"}.get(key.kind, num)


def figure_id(key: FigureKey) -> str:
    return f"{key.kind}-{'.'.join(map(str, key.number))}"


def to_dict(report: FigureReport, blocks: list[Block] | None = None) -> dict:
    """Serialise the report. With `blocks`, citations also carry their relative position
    within their file (0-1), which the UI uses to draw where in the text each figure is cited."""
    ordinal: dict[int, tuple[int, int]] = {}
    files: list[dict] = []
    if blocks:
        per_file: dict[str, list[Block]] = {}
        for b in blocks:
            per_file.setdefault(b.source, []).append(b)
        for name, file_blocks in per_file.items():
            files.append({"name": name, "role": file_blocks[0].role, "blocks": len(file_blocks)})
            for i, b in enumerate(file_blocks):
                ordinal[id(b)] = (i, len(file_blocks))

    def position(b: Block) -> float | None:
        if id(b) not in ordinal:
            return None
        i, n = ordinal[id(b)]
        return round(i / max(n - 1, 1), 4)

    def citation(m) -> dict:
        text = m.block.text
        start = text.find(m.matched)
        lo, hi = max(0, start - 140), min(len(text), start + len(m.matched) + 140)
        return {
            "location": m.block.location,
            "file": m.block.source,
            "role": m.block.role,
            "position": position(m.block),
            "matched": m.matched,
            "before": ("…" if lo else "") + text[lo:start],
            "after": text[start + len(m.matched):hi] + ("…" if hi < len(text) else ""),
            "in_legend": m.in_caption,
        }

    statuses = [f.status for f in report.figures]
    return {
        "summary": {
            "figures": len(report.figures),
            "ok": statuses.count("OK"),
            "uncited": statuses.count("UNCITED"),
            "missing": statuses.count("MISSING"),
            "errors": sum(i.severity == "error" for i in report.issues),
            "warnings": sum(i.severity == "warning" for i in report.issues),
        },
        "files": files,
        "figures": [
            {
                "id": figure_id(f.key),
                "label": f.key.label,
                "short": short_label(f.key),
                "kind": f.key.kind,
                "number": ".".join(map(str, f.key.number)),
                "status": f.status,
                "captions": [{"location": c.block.location, "text": c.text} for c in f.captions],
                "citations": [citation(m) for m in f.mentions],
                "suspects": [{"location": b.location, "text": b.text} for b in f.suspects],
            }
            for f in report.figures
        ],
        "issues": [
            {
                "severity": i.severity,
                "code": i.code,
                "message": i.message,
                "figure": figure_id(i.key) if i.key else None,
                "short": short_label(i.key) if i.key else None,
                "kind": i.key.kind if i.key else None,
            }
            for i in report.issues
        ],
    }

