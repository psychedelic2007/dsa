"""Plain-data view of an Analysis, shared by the CLI (--json) and the web UI."""

from .analyze import Analysis
from .extract import Block
from .labels import EXT, SUPP, LabelKey, LabelReport
from .proofing import FAIL, WARN

CATEGORIES = ("figures", "tables", "references", "proofing")


def short_label(key: LabelKey) -> str:
    num = ".".join(map(str, key.number))
    return {SUPP: f"S{num}", EXT: f"ED{num}"}.get(key.kind, num)


def item_id(key: LabelKey) -> str:
    return f"{key.spec}-{key.kind}-{'.'.join(map(str, key.number))}"


class _Positions:
    """Relative position (0-1) of each block within its file, for the citation-flow plots."""

    def __init__(self, blocks: list[Block]):
        self._pos: dict[int, float] = {}
        per_file: dict[str, list[Block]] = {}
        for b in blocks:
            per_file.setdefault(b.source, []).append(b)
        self.files = [{"name": n, "role": bs[0].role, "blocks": len(bs)} for n, bs in per_file.items()]
        for bs in per_file.values():
            for i, b in enumerate(bs):
                self._pos[id(b)] = round(i / max(len(bs) - 1, 1), 4)

    def context(self, block: Block | None, start: int = -1, matched: str = "", span: int = 140) -> dict:
        if block is None:
            return {}
        text = block.text
        if start < 0:
            start = text.find(matched) if matched else 0
        start = max(start, 0)
        end = start + len(matched)
        lo, hi = max(0, start - span), min(len(text), end + span)
        return {
            "location": block.location,
            "file": block.source,
            "role": block.role,
            "position": self._pos.get(id(block)),
            "matched": matched,
            "before": ("…" if lo else "") + text[lo:start],
            "after": text[end:hi] + ("…" if hi < len(text) else ""),
        }


def _labels(report: LabelReport, pos: _Positions) -> dict:
    statuses = [s.status for s in report.items]
    return {
        "summary": {
            "items": len(report.items),
            "ok": statuses.count("OK"),
            "uncited": statuses.count("UNCITED"),
            "missing": statuses.count("MISSING"),
            "errors": sum(i.severity == "error" for i in report.issues),
            "warnings": sum(i.severity == "warning" for i in report.issues),
        },
        "items": [
            {
                "id": item_id(s.key),
                "label": s.key.label,
                "short": short_label(s.key),
                "kind": s.key.kind,
                "number": ".".join(map(str, s.key.number)),
                "status": s.status,
                "captions": [{"location": c.block.location, "text": c.text} for c in s.captions],
                "citations": [
                    {**pos.context(m.block, matched=m.matched), "in_legend": m.in_caption} for m in s.mentions
                ],
                "suspects": [{"location": b.location, "text": b.text} for b in s.suspects],
            }
            for s in report.items
        ],
        "issues": [
            {
                "severity": i.severity,
                "code": i.code,
                "message": i.message,
                "target": item_id(i.key) if i.key else "",
                "short": short_label(i.key) if i.key else None,
                "kind": i.key.kind if i.key else None,
            }
            for i in report.issues
        ],
    }


def _references(a: Analysis, pos: _Positions) -> dict:
    r = a.references
    return {
        "style": r.style,
        "detail": r.detail,
        "detected": r.detected,
        "list_found": r.list_found,
        "summary": {
            "entries": len(r.entries),
            "cited": r.cited,
            "uncited": len(r.entries) - r.cited,
            "unresolved": len({c.citation.label for c in r.unresolved}),
            "errors": sum(i.severity == "error" for i in r.issues),
            "warnings": sum(i.severity == "warning" for i in r.issues),
        },
        "entries": [
            {
                "id": e.id,
                "label": e.label,
                "number": e.number,
                "author": e.author,
                "year": e.year,
                "doi": e.doi,
                "text": e.text,
                "location": e.block.location,
                "status": e.status,
                "citations": [{**pos.context(c.block, c.start, c.matched), "in_legend": c.in_caption} for c in e.citations],
            }
            for e in r.entries
        ],
        "unresolved": [
            {"label": u.citation.label, "hint": u.hint, **pos.context(u.citation.block, u.citation.start, u.citation.matched)}
            for u in r.unresolved
        ],
        "issues": [{"severity": i.severity, "code": i.code, "message": i.message, "target": i.target} for i in r.issues],
    }


def _proofing(a: Analysis, pos: _Positions) -> dict:
    return {
        "stats": a.proofing.stats,
        "checks": [
            {
                "id": c.id,
                "title": c.title,
                "status": c.status,
                "summary": c.summary,
                "findings": [{"note": f.note, **pos.context(f.block, f.start, f.matched, span=90)} for f in c.findings],
            }
            for c in a.proofing.checks
        ],
    }


def to_dict(a: Analysis) -> dict:
    pos = _Positions(a.structure.blocks)
    out = {
        "files": pos.files,
        "figures": _labels(a.figures, pos),
        "tables": _labels(a.tables, pos),
        "references": _references(a, pos),
        "proofing": _proofing(a, pos),
    }
    issues = []
    for cat in ("figures", "tables", "references"):
        issues += [{**i, "category": cat} for i in out[cat]["issues"]]
    for c in out["proofing"]["checks"]:
        if c["status"] in (FAIL, WARN):
            issues.append({"severity": "error" if c["status"] == FAIL else "warning", "code": c["id"],
                           "message": f"{c['title']}: {c['summary']}", "target": c["id"], "category": "proofing"})
    rank = {"error": 0, "warning": 1, "info": 2}
    issues.sort(key=lambda i: rank[i["severity"]])
    out["issues"] = issues
    out["summary"] = {
        "errors": sum(i["severity"] == "error" for i in issues),
        "warnings": sum(i["severity"] == "warning" for i in issues),
        "by_category": {
            cat: {
                "errors": sum(i["severity"] == "error" and i["category"] == cat for i in issues),
                "warnings": sum(i["severity"] == "warning" and i["category"] == cat for i in issues),
            }
            for cat in CATEGORIES
        },
    }
    return out
