import pytest

from manuscript_checker.analyze import analyze
from manuscript_checker.extract import Block, Document, load_document
from manuscript_checker.labels import TABLE, check_labels, parse_caption

from .fixtures import numeric_manuscript


def blocks(*paras, role="manuscript"):
    return [Block(t, "m.docx", role, i + 1) for i, t in enumerate(paras)]


def table_status(*paras):
    return {s.key.label: s.status for s in check_labels(blocks(*paras), TABLE).items}


def test_tables_end_to_end():
    assert table_status(
        "Results are in Table 1 and Tables 3–4 (see also Table S1).",
        "Table 1. Kinetic constants.",
        "Table 2. Never cited.",
        "Table 3: Doses.",
        "Supplementary Table 1. Controls.",
    ) == {
        "Table 1": "OK", "Table 2": "UNCITED", "Table 3": "OK", "Table 4": "MISSING",
        "Supplementary Table 1 (S1)": "OK",
    }


@pytest.mark.parametrize("text, label", [
    ("Table 1. Title", "Table 1"),
    ("Table S2 | Title", "Supplementary Table 2 (S2)"),
    ("Extended Data Table 1. Title", "Extended Data Table 1"),
    ("Tab. 3: Title", "Table 3"),
])
def test_table_captions(text, label):
    parsed = parse_caption(Block(text, "m.docx", "manuscript", 1), TABLE)
    assert parsed and parsed[0].key.label == label


def test_figure_cited_inside_table_caption_is_not_a_body_citation():
    a = analyze([Document("m.docx", "manuscript", blocks(
        "We show Table 1.", "Table 1. Constants, see Figure 2.", "Figure 2. Traces."))])
    assert {s.key.label: s.status for s in a.figures.items} == {"Figure 2": "UNCITED"}


def test_table_and_figure_with_same_number_are_separate():
    a = analyze([Document("m.docx", "manuscript", blocks("Figure 1 and Table 1.", "Figure 1. A.", "Table 1. B."))])
    assert [s.status for s in a.figures.items] == ["OK"] and [s.status for s in a.tables.items] == ["OK"]


@pytest.fixture(scope="module")
def checks():
    a = analyze([load_document("paper.docx", numeric_manuscript(), "manuscript")],
                limits={"abstract_words": 10, "references": 50})
    return {c.id: c for c in a.proofing.checks}, a.proofing.stats


def test_proofing_on_fixture(checks):
    c, stats = checks
    assert c["crossrefs"].status == "fail"
    assert c["leftovers"].status == "fail"
    assert any("tracked insertion" in f.note for f in c["leftovers"].findings)
    assert any("comment" in f.note for f in c["leftovers"].findings)
    assert {f.matched for f in c["placeholders"].findings} == {"XX", "[ref]"}
    assert c["repeats"].findings[0].matched == "The the"
    assert "Author contributions" in c["statements"].summary and "Data availability" not in c["statements"].summary
    notes = [f.note for f in c["abbreviations"].findings]
    assert any(n.startswith("SPR is defined only in the abstract") for n in notes)
    assert not any(n.startswith("ITC") for n in notes)  # defined at first use, used again: fine
    assert c["limits"].status == "fail" and "Abstract words" in c["limits"].summary
    assert stats["references"] == 8 and stats["figures"] == 2 and stats["tables"] == 2


@pytest.mark.parametrize("text", [
    "As shown in Figure ??, the effect is large.",
    "See Error! Bookmark not defined.",
    "As reported [?], the effect",
])
def test_broken_crossrefs(text):
    a = analyze([Document("m.docx", "manuscript", blocks(text))])
    assert next(c for c in a.proofing.checks if c.id == "crossrefs").status == "fail"


def test_abbreviation_used_before_definition_and_defined_twice():
    a = analyze([Document("m.docx", "manuscript", blocks(
        "Introduction",
        "We used an MSM to sample states.",
        "A Markov state model (MSM) was built. Later MSM runs converged.",
        "Again, a Markov state model (MSM) was used.",
    ))])
    notes = [f.note for c in a.proofing.checks if c.id == "abbreviations" for f in c.findings]
    assert any("used before it is defined" in n for n in notes)
    assert any("defined again" in n for n in notes)


def test_inline_statements_are_found():
    a = analyze([Document("m.docx", "manuscript", blocks(
        "Funding: This work was supported by grant X.",
        "Competing interests: The authors declare none.",
        "Author contributions: J.D. designed the study.",
        "Data availability statement",
        "Data are on Zenodo.",
    ))])
    assert next(c for c in a.proofing.checks if c.id == "statements").status == "pass"


def test_clean_text_has_no_false_alarms():
    a = analyze([Document("m.docx", "manuscript", blocks(
        "Abstract", "We measured binding in 12 constructs.",
        "Introduction", "Binding is important. That that is true is clear, and we had had doubts.",
    ))])
    c = {c.id: c for c in a.proofing.checks}
    for cid in ("crossrefs", "placeholders", "repeats", "abbreviations"):
        assert c[cid].status == "pass", (cid, [f.note or f.matched for f in c[cid].findings])
