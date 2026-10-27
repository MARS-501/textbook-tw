import csv

from textbook_tw.engine.babeldoc_runner import parse_batch
from textbook_tw.glossary import book
from textbook_tw.glossary.book import STATUS_CONFLICT, STATUS_REVIEW, USER_ORIGIN, BookTerm
from textbook_tw.glossary.lexicon import add_my_term, read_user_csv
from textbook_tw.glossary.naer import Term


def test_parse_batch_pairs_inputs_with_outputs():
    prompt = (
        "You are a translator...\n## Here is the input:\n\n"
        '[{"id": 0, "input": "{v1}<style id=\'2\'>lift</style> coefficient", "layout_label": "text"},'
        ' {"id": 1, "input": "drag", "layout_label": "text"}]'
    )
    output = '```json\n[{"id": 1, "output": "阻力"}, {"id": 0, "output": "{v1}<style id=\'2\'>升力</style>係數"}]\n```'
    assert parse_batch(prompt, output) == [("lift coefficient", "升力係數"), ("drag", "阻力")]


def test_parse_batch_ignores_unparsable_output():
    assert parse_batch("no marker here", "[]") == []
    assert parse_batch('## Here is the input:\n[{"id": 0, "input": "x"}]', "not json") == []


def test_options_of_lists_current_target_first():
    term = BookTerm(
        "airfoil", "翼剖面", STATUS_CONFLICT, 3, "力學", "翼形（航空太空）；翼切面（航空太空）"
    )
    assert book.options_of(term) == [
        ("翼剖面", "力學"),
        ("翼形", "航空太空"),
        ("翼切面", "航空太空"),
    ]
    review = BookTerm(
        "stall", "", STATUS_REVIEW, 3, "航空太空", "失速（航空太空）；停轉（機械工程）"
    )
    assert book.options_of(review) == [("失速", "航空太空"), ("停轉", "機械工程")]


def test_apply_choices_keeps_every_option(tmp_path):
    path = tmp_path / "book.csv"
    book.write_terms(
        path,
        [
            BookTerm(
                "airfoil",
                "翼剖面",
                STATUS_CONFLICT,
                103,
                "力學",
                "翼形（航空太空）",
                2,
                "thin airfoil theory",
            ),
            BookTerm(
                "stall", "", STATUS_REVIEW, 12, "航空太空", "失速（航空太空）；停轉（機械工程）"
            ),
        ],
    )
    assert book.apply_choices(path, {"airfoil": "翼形", "stall": "失速"}) == 2

    rows = {t.source: t for t in book.read_book(path)}
    assert (rows["airfoil"].target, rows["airfoil"].status, rows["airfoil"].origin) == (
        "翼形",
        "",
        USER_ORIGIN,
    )
    assert rows["airfoil"].alternatives == "翼剖面（力學）"  # 原本的譯名留在候選裡
    assert (rows["airfoil"].page, rows["airfoil"].context) == (2, "thin airfoil theory")
    assert rows["stall"].alternatives == "停轉（機械工程）"


def test_add_my_term_replaces_same_source(tmp_path):
    path = tmp_path / "my_terms.csv"
    add_my_term("shock", "震波", path)
    add_my_term("airfoil", "翼型", path)
    add_my_term("Shock", "激震波", path)
    assert read_user_csv(path) == [Term("airfoil", ("翼型",)), Term("Shock", ("激震波",))]
    with path.open(encoding="utf-8") as f:
        assert next(csv.reader(f)) == ["source", "target", "note"]
