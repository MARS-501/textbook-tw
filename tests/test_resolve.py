from textbook_tw.engine.babeldoc_runner import rewrite_prompt
from textbook_tw.glossary import book, resolve
from textbook_tw.glossary.book import BookTerm
from textbook_tw.pipeline import count_choices

OPTIONS = [("積層板", "航空太空"), ("層板", "力學、金屬材料"), ("疊片", "陶瓷材料")]


def _term(status=book.STATUS_CONFLICT, target="積層板", origin="航空太空"):
    return BookTerm(
        "laminate", target, status, 20, origin, "層板（力學、金屬材料）；疊片（陶瓷材料）"
    )


def test_model_choice_becomes_suggestion_with_reason():
    term = _term()
    assert resolve.apply_answer(term, OPTIONS, {"choice": 2, "reason": "本文指金屬層板"})
    assert (term.target, term.origin, term.status, term.note) == (
        "層板",
        "力學、金屬材料",
        book.STATUS_SUGGESTED,
        "本文指金屬層板",
    )
    assert book.options_of(term)[0] == ("層板", "力學、金屬材料")
    assert "積層板（航空太空）" in term.alternatives


def test_choice_zero_skips_the_term():
    term = _term()
    assert resolve.apply_answer(term, OPTIONS, {"choice": 0, "reason": "一般用語"})
    assert term.target == "" and term.status == book.STATUS_SKIPPED
    assert [zh for zh, _ in book.options_of(term)] == ["積層板", "層板", "疊片"]


def test_per_paragraph_keeps_every_option_and_origin():
    term = _term()
    answer = {"choice": -1, "per_paragraph": [3, 1, 9], "reason": "兩種意思"}
    assert resolve.apply_answer(term, OPTIONS, answer)
    assert term.target == "疊片｜積層板" and term.status == book.STATUS_PER_PARAGRAPH
    assert book.options_of(term) == [OPTIONS[2], OPTIONS[0], OPTIONS[1]]


def test_per_paragraph_with_one_or_no_option_falls_back():
    term = _term()
    resolve.apply_answer(term, OPTIONS, {"choice": -1, "per_paragraph": [2], "reason": ""})
    assert term.target == "層板" and term.status == book.STATUS_SUGGESTED
    term = _term()
    resolve.apply_answer(term, OPTIONS, {"choice": -1, "reason": "都不對"})
    assert term.status == book.STATUS_SKIPPED


def test_unreadable_answer_leaves_term_alone():
    term = _term()
    assert not resolve.apply_answer(term, OPTIONS, {"choice": "two"})
    assert not resolve.apply_answer(term, OPTIONS, {"choice": 7})
    assert term.target == "積層板" and term.status == book.STATUS_CONFLICT


def test_which_terms_need_judgement():
    assert resolve.needs_judgement(_term())
    assert not resolve.needs_judgement(_term(origin=book.USER_ORIGIN))
    assert not resolve.needs_judgement(_term(status=book.STATUS_SUGGESTED))
    assert resolve.needs_judgement(_term(status=book.STATUS_SUGGESTED), force=True)
    common = BookTerm("first stage", "第一節", "", 3, "航空太空", "")
    rare = BookTerm("boundary layer", "邊界層", "", 30, "力學", "")
    assert resolve.needs_judgement(common)
    assert not resolve.needs_judgement(rare)


def test_prompt_rewrite_turns_choices_into_pick_one():
    prompt = (
        "## Glossary Tables\n\n### Glossary: terms\n\n| Source Term | Target Term |\n"
        "|-------------|-------------|\n| Mach number | 馬赫數 |\n\n"
        "### Glossary: per_paragraph\n\n| Source Term | Target Term |\n"
        "|-------------|-------------|\n| shear | 剪力｜剪切 |\n"
    )
    rewritten = rewrite_prompt(prompt)
    assert "| shear | 剪力 or 剪切 |" in rewritten
    assert "| Mach number | 馬赫數 |" in rewritten
    assert "exactly ONE" in rewritten and "### Glossary: per_paragraph" not in rewritten
    assert rewrite_prompt("no glossary") == "no glossary"


def test_count_choices_tallies_used_translations():
    counts: dict[str, dict[str, int]] = {}
    pairs = [
        ("The interlaminar shear strength", "層間剪力強度"),
        ("shear deformation of the core", "核心的剪切變形"),
        ("no term here", "沒有"),
    ]
    count_choices({"shear": ["剪力", "剪切"]}, pairs, counts)
    assert counts == {"shear": {"剪力": 1, "剪切": 1}}
