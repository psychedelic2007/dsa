import pytest

from manuscript_checker.analyze import analyze
from manuscript_checker.extract import Block, Document, load_document
from manuscript_checker.references import check_references, surname_key
from manuscript_checker.structure import analyse_structure

from .fixtures import author_year_manuscript, numeric_manuscript


def refs(paras, style="auto", role="manuscript"):
    blocks = [Block(t, "m.docx", role, i + 1) for i, t in enumerate(paras)]
    return check_references(analyse_structure(blocks), style)


def statuses(report):
    return {e.label: e.status for e in report.entries}


def codes(report):
    return [i.code for i in report.issues]


NUMBERED = ["References"] + [f"{n}. Author{n} X. Title {n}. J. Biol. {n}, 1 ({2000 + n})." for n in range(1, 9)]


@pytest.mark.parametrize("text, cited", [
    ("Shown before [1].", {1}),
    ("Shown before [1, 2].", {1, 2}),
    ("Shown before [1–3, 5].", {1, 2, 3, 5}),
    ("Shown before [2-4].", {2, 3, 4}),
    ("Shown in refs. 6–7.", {6, 7}),
    ("Shown in ref. 8.", {8}),
])
def test_numeric_bracket_forms(text, cited):
    r = refs(["Intro", text] + NUMBERED)
    assert r.style == "numeric"
    assert {e.number for e in r.entries if e.citations} == cited


def test_numeric_uncited_unresolved_and_order():
    r = refs(["Prior work [1, 2] and others [4–6] showed effects [3].", "Also ref. 7 and [9]."] + NUMBERED)
    assert statuses(r)["[8]"] == "UNCITED"
    assert "unresolved" in codes(r)  # [9] is not in the list
    order = [i for i in r.issues if i.code == "order"]
    assert len(order) == 1 and "Reference 4" in order[0].message and "reference 3" in order[0].message


def test_years_and_equation_numbers_are_not_citations():
    # Brackets dominate, so "(1)" is an enumeration, not a citation; years and "Eq. (3)" never are.
    r = refs(["Smith (2019) and Eq. (3) and (1) list items [2019].", "Cited [4] and [5]."] + NUMBERED, style="numeric")
    assert {e.number for e in r.entries if e.citations} == {4, 5}
    assert not r.unresolved


def test_parenthesis_style_when_dominant():
    r = refs(["Shown before (1) and later (2, 3).", "Also (4–5) and (6) and (7) and (8)."] + NUMBERED)
    assert r.detail == "parenthesis"
    assert {e.number for e in r.entries if e.citations} == {1, 2, 3, 4, 5, 6, 7, 8}


def test_numbered_list_split_from_one_pdf_block():
    r = refs(["Cited [1] [2] [3].", "References",
              "1. Smith J. Title. Nature 5 (2019). 2. Lee K. Title. Cell 6 (2018). 3. Doe J. Title. Science 7 (2017)."])
    assert [e.number for e in r.entries] == [1, 2, 3]
    assert all(e.citations for e in r.entries)


def test_superscript_citations_skip_affiliations_units_and_exponents():
    doc = load_document("paper.docx", numeric_manuscript(), "manuscript")
    r = analyze([doc]).references
    assert r.style == "numeric" and r.detail == "superscript"
    # "Jane Doe^1,2" (affiliation) and "10 m^2" (unit) must not cite refs 1 and 2 extra times.
    by_number = {e.number: len(e.citations) for e in r.entries}
    assert by_number[1] == 1 and by_number[2] == 1
    assert "duplicate" in codes(r)  # refs 1 and 8 share a DOI


AY_LIST = [
    "References",
    "Garcia, M. (2018). Wrong year. Science, 1, 1–2.",
    "Lee, K., & Park, J. (2018a). Title one. J Biol, 5, 1–10.",
    "Lee, K., & Park, J. (2018b). Title two. J Biol, 6, 1–10.",
    "Müller, H. (2020). Something. Cell, 1, 2.",
    "Smith, J. A., Jones, B., & Doe, C. (2019). Binding. Nature, 570, 1–5.",
    "van der Waals, J. D. (1873). Over de continuiteit. Leiden.",
    "World Health Organization. (2020). Report.",
    "Zed, A. (2010). Some work. Journal, 1, 1.",
]


@pytest.mark.parametrize("text, label", [
    ("(Smith et al., 2019)", "Smith 2019"),
    ("Smith et al. (2019)", "Smith 2019"),
    ("Smith et al.'s (2019) work", "Smith 2019"),
    ("(e.g., Smith et al. 2019)", "Smith 2019"),
    ("(Smith, Jones, & Doe, 2019)", "Smith 2019"),
    ("(Lee and Park 2018b)", "Lee 2018b"),
    ("(Lee & Park, 2018a, b)", "Lee 2018b"),
    ("Muller (2020)", "Müller 2020"),  # accents ignored
    ("as disagreed, and van der Waals (1873) explained", "van der Waals 1873"),
    ("(WHO, 2020)", "World Health Organization 2020"),
    ("(reviewed by Zed, 2010)", "Zed 2010"),
    ("(Garcia 2017; 2018)", "Garcia 2018"),  # second year inherits the author
])
def test_author_year_forms(text, label):
    r = refs(["Intro", f"Growth was shown {text}. More text (Smith et al., 2019)."] + AY_LIST)
    assert r.style == "author-year"
    assert statuses(r)[label] == "OK"


def test_author_year_errors_and_hints():
    r = refs(["Intro", "Shown by Garcia et al. (2017) and (Jones, 2016). In (2019) we saw it. (Smith et al., 2019) "
                       "(Lee, 2018a; Lee 2018b; Müller 2020; van der Waals 1873; WHO 2020; Zed 2010)."] + AY_LIST)
    messages = " ".join(i.message for i in r.issues)
    assert "“Jones, 2016” is cited" in messages
    assert "The list has Garcia 2018: is the year wrong?" in messages
    assert "In, 2019" not in messages and "“In" not in messages  # not a citation
    assert statuses(r)["Garcia 2018"] == "UNCITED"


def test_ambiguous_year_without_suffix():
    r = refs(["Intro", "Shown (Lee and Park, 2018) and (Smith et al., 2019) and (Zed 2010)."] + AY_LIST)
    assert "ambiguous" in codes(r)


def test_author_year_alphabetical_order():
    r = refs(["Intro", "(Zed, 2010; Abe, 2011; Smith et al., 2019)", "References",
              "Zed, A. (2010). Z.", "Abe, B. (2011). A.", "Smith, J. (2019). S."])
    assert "alphabetical" in codes(r)


def test_author_year_fixture_docx():
    r = analyze([load_document("ay.docx", author_year_manuscript(), "manuscript")]).references
    assert r.style == "author-year"
    assert statuses(r)["Zed 2010"] == "UNCITED" and statuses(r)["van der Waals 1873"] == "OK"


def test_no_reference_list():
    r = refs(["Intro", "Shown [1, 2] and [3]."])
    assert "no_list" in codes(r)


def test_style_override():
    r = refs(["Intro", "Shown [1]."] + NUMBERED, style="author-year")
    assert r.style == "author-year"


@pytest.mark.parametrize("name, key", [("van der Waals", "waals"), ("Müller-Lyer", "mullerlyer"), ("O'Brien", "obrien")])
def test_surname_key(name, key):
    assert surname_key(name) == key


def test_reference_titles_do_not_count_as_figure_citations():
    blocks = [Block(t, "m.docx", "manuscript", i + 1) for i, t in enumerate(
        ["We show Figure 1 [1].", "Figure 1. Caption.", "References", "1. Smith J. Figure 2 of the atlas. Nature (2019)."])]
    a = analyze([Document("m.docx", "manuscript", blocks)])
    assert [i.key.label for i in a.figures.items] == ["Figure 1"]
