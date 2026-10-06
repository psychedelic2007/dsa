"""Plain-data views of a FigureReport, shared by the CLI and the web UI."""

from .figures import FigureReport


def figure_rows(report: FigureReport) -> list[dict]:
    rows = []
    for f in report.figures:
        body = f.body_mentions
        rows.append({
            "Figure": f.key.label,
            "Status": f.status,
            "Caption found in": "; ".join(c.block.location for c in f.captions) or "—",
            "Body citations": len(body),
            "First cited at": body[0].block.location if body else "—",
            "Caption": (f.captions[0].text[:120] + ("…" if len(f.captions[0].text) > 120 else "")) if f.captions else "",
        })
    return rows


def to_dict(report: FigureReport) -> dict:
    return {
        "figures": [
            {
                "label": f.key.label,
                "kind": f.key.kind,
                "number": ".".join(map(str, f.key.number)),
                "status": f.status,
                "captions": [{"location": c.block.location, "text": c.text} for c in f.captions],
                "citations": [
                    {"location": m.block.location, "matched": m.matched, "in_legend": m.in_caption, "context": m.snippet}
                    for m in f.mentions
                ],
            }
            for f in report.figures
        ],
        "issues": [{"severity": i.severity, "message": i.message} for i in report.issues],
    }
