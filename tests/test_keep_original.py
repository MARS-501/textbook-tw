from types import SimpleNamespace as NS

from textbook_tw.engine import keep_original as ko
from textbook_tw.engine.babeldoc_runner import rewrite_prompt


def box(x, y, x2, y2):
    return NS(x=x, y=y, x2=x2, y2=y2)


def para(text, label="plain text", b=(40, 100, 280, 120)):
    return NS(unicode=text, layout_label=label, box=box(*b))


def page(number, paragraphs, layouts=(), chars=()):
    return NS(
        page_number=number,
        pdf_paragraph=list(paragraphs),
        page_layout=[NS(class_name=name, box=box(*b)) for name, b in layouts],
        pdf_character=list(chars),
        cropbox=NS(box=box(0, 0, 595, 842)),
    )


def kept(plan, *paragraphs):
    return [id(p) in plan.keep for p in paragraphs]


def test_headers_title_and_authors_on_first_page_stay_original():
    header = para("Engineering Structures 265 (2022) 114498", "abandon", (230, 800, 370, 810))
    title = para("Interlaminar shear strength of laminates", "title", (40, 700, 470, 730))
    authors = para("Ozkan Ozbek a, Mehmet Bulut b", b=(40, 670, 380, 685))
    info = para("A R T I C L E I N F O", "title", (40, 600, 120, 610))
    abstract = para("A B S T R A C T", "title", (200, 600, 260, 610))
    body = para("Interlaminar shear strength (ILSS) was investigated.", b=(200, 500, 560, 590))
    plan = ko.plan(NS(page=[page(0, [header, title, authors, info, abstract, body])]))
    assert kept(plan, header, title, authors, info, abstract, body) == [
        True, True, True, False, False, False,
    ]  # fmt: skip


def test_table_cells_stay_original_but_captions_are_translated():
    caption = para(
        "Table 2 Stacking sequence of the composites", "table_caption", (40, 720, 260, 740)
    )
    cell = para("Density", "fallback_line", (480, 700, 500, 710))
    unit = para("(kg/m3)", "fallback_line", (480, 690, 500, 698))
    body = para("The density of each sample is listed in Table 2.", b=(40, 300, 280, 360))
    plan = ko.plan(
        NS(page=[page(3, [caption, cell, unit, body], layouts=[("table", (34, 560, 560, 720))])])
    )
    assert kept(plan, caption, cell, unit, body) == [False, True, True, False]
    assert "Density" in plan.figure_terms


def test_references_and_declarations_stay_original_until_next_section():
    left = para("It is clear from Fig. 11 that ILSS ranges were significant.", b=(38, 52, 289, 135))
    credit = para("CRediT authorship contribution statement", "title", (307, 353, 468, 362))
    roles = para("Ozkan Ozbek: Writing - review & editing.", b=(307, 290, 558, 341))
    refs_title = para("References", "title", (307, 198, 348, 204))
    ref1 = para(
        "[1] Fan Z, Santare MH. Interlaminar shear strength. 2008;39:540-54.", b=(311, 51, 562, 186)
    )
    caption = para("Fig. 11. Range of ILSS.", "figure_caption", (38, 294, 288, 313))
    next_page_ref = para(
        "[8] Kojima Y, Usuki A. Mechanical properties. 1993;8:1185-9.", b=(38, 334, 293, 740)
    )
    appendix = para("Appendix A. Supplementary data", "title", (307, 300, 500, 310))
    appendix_text = para(
        "Supplementary data to this article can be found online.", b=(307, 250, 560, 290)
    )
    plan = ko.plan(
        NS(
            page=[
                page(13, [left, credit, roles, refs_title, ref1, caption]),
                page(14, [next_page_ref, appendix, appendix_text]),
            ]
        )
    )
    assert kept(plan, left, credit, roles, refs_title, ref1, caption) == [
        False, True, True, True, True, False,
    ]  # fmt: skip
    assert kept(plan, next_page_ref, appendix, appendix_text) == [True, False, False]


def test_numbered_reference_entries_are_recognised_without_heading():
    assert ko.is_reference_entry("[25] Ray PK, Mula S. Effect of shock cycles. 2007;26(5):519-24.")
    assert not ko.is_reference_entry("[7]. Several researchers studied nanoparticles.")
    assert ko.is_back_matter_heading("7. References")
    assert ko.is_back_matter_heading("Declaration of Competing Interest")
    assert not ko.is_back_matter_heading("6. Conclusions")
    assert ko.is_front_matter_heading("A B S T R A C T")


def test_figure_terms_drop_numbers_units_and_codes():
    terms = ko.figure_terms_from(
        ["Stacking sequence and fiber configurations", "73.95", "GGG", "(kg/m3)", "Span length: 4t"]
    )
    assert terms == ["Stacking sequence and fiber configurations", "Span length"]


def test_prompt_asks_for_english_beside_figure_terms_used_in_the_batch():
    prompt = 'Rules...\n## Here is the input:\n[{"id": 0, "input": "The density was measured."}]'
    rewritten = rewrite_prompt(prompt, ["Density", "Thickness"])
    assert "- Density" in rewritten and "Thickness" not in rewritten
    assert rewritten.index("密度（Density）") < rewritten.index("## Here is the input:")
    assert rewrite_prompt(prompt, ["Thickness"]) == prompt
