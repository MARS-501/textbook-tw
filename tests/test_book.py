import csv

from textbook_tw.glossary import book
from textbook_tw.glossary.book import STATUS_CONFLICT, STATUS_REVIEW, select_term
from textbook_tw.glossary.lexicon import Candidate, Lexicon, read_user_csv
from textbook_tw.glossary.naer import Term


def c(origin, source, *targets):
    return Candidate(origin, source, targets)


def test_multi_word_takes_first_glossary_and_flags_conflicts():
    term = select_term(
        "turbulent boundary layer",
        10,
        [
            c("力學", "turbulent boundary layer", "亂流邊界層"),
            c("航空太空", "turbulent boundary layer", "紊流邊界層"),
        ],
    )
    assert term.target == "亂流邊界層"
    assert term.origin == "力學"
    assert term.status == STATUS_CONFLICT
    assert term.alternatives == "紊流邊界層（航空太空）"


def test_multi_word_synonyms_in_one_glossary_are_not_a_conflict():
    term = select_term("angle of attack", 19, [c("航空太空", "angle of attack", "攻角", "衝角")])
    assert (term.target, term.status, term.alternatives) == ("攻角", "", "衝角（航空太空）")


def test_function_word_phrases_are_skipped():
    assert select_term("less than", 9, [c("數學", "less than", "小於")]) is None


def test_single_words():
    # 太短：一般用字
    assert select_term("can", 154, [c("機械工程", "can", "罐"), c("造船工程", "can", "罐")]) is None
    # 只有一個名詞庫：不確定是不是一般用字
    assert select_term("transonic", 121, [c("氣象學", "transonic", "穿音速")]) is None
    # 英文常用字：即使名詞庫一致也不收
    surface = [c("機械工程", "surface", "面"), c("造船工程", "surface", "面")]
    assert select_term("surface", 118, surface) is None
    equation = [c("化學工程", "equation", "方程式"), c("物理學", "equation", "方程")]
    assert select_term("equation", 240, equation) is None
    # 多個名詞庫一致：採用
    agreed = select_term(
        "fuselage", 39, [c("航空太空", "fuselage", "機身"), c("機械工程", "fuselage", "機身")]
    )
    assert (agreed.target, agreed.status) == ("機身", "")
    # 不一致：留空待確認
    conflict = [c("力學", "airfoil", "翼剖面"), c("航空太空", "airfoil", "翼形", "翼切面")]
    review = select_term("airfoil", 103, conflict)
    assert (review.target, review.status) == ("", STATUS_REVIEW)
    # 沒有採用任何譯名，所以每個候選都列在 alternatives
    assert review.alternatives == "翼剖面（力學）；翼形（航空太空）；翼切面（航空太空）"
    # 不一致但出現次數太少：不列出
    assert select_term("airfoil", 2, conflict) is None


def test_my_terms_always_win():
    term = select_term(
        "airfoil", 1, [c("my_terms", "airfoil", "翼型"), c("力學", "airfoil", "翼剖面")]
    )
    assert (term.target, term.status, term.origin) == ("翼型", "", "my_terms")


def test_count_terms_matches_phrases_and_plurals():
    lexicon = Lexicon(
        {
            "shock wave": [c("力學", "shock wave", "震波")],
            "normal shock wave": [c("力學", "normal shock wave", "正震波")],
            "airfoil": [c("力學", "airfoil", "翼剖面")],
        }
    )
    words = "a normal shock wave and two shock waves over the airfoils".split()
    counts = book.count_terms(words, lexicon)
    assert counts == {"shock wave": 2, "normal shock wave": 1, "airfoil": 1}


def test_write_read_and_export(tmp_path):
    terms = [
        book.BookTerm("Mach number", "馬赫數", "", 208, "力學", ""),
        book.BookTerm("airfoil", "", STATUS_REVIEW, 103, "力學", "翼形（航空太空）"),
        book.BookTerm("shock wave", "震波", "", 199, "力學", ""),
    ]
    path = tmp_path / "book.csv"
    book.write_terms(path, terms)
    assert path.read_bytes().startswith(b"\xef\xbb\xbf")  # Excel 需要 BOM

    loaded = book.read_terms(path)
    assert [t.source for t in loaded] == ["Mach number", "shock wave"]  # 空白 target 不使用

    export = tmp_path / "terms.csv"
    per_paragraph = tmp_path / "per_paragraph.csv"
    my_terms = [Term("shock wave", ("激波測試",)), Term("Feng Chia University", ("逢甲大學",))]
    loaded.append(Term("shear", ("剪力｜剪切",)))
    assert book.export_for_babeldoc(loaded, my_terms, export, per_paragraph) == (3, 1)
    with export.open(encoding="utf-8") as f:
        rows = {r["source"]: r["target"] for r in csv.DictReader(f)}
    assert rows == {
        "shock wave": "激波測試",
        "Feng Chia University": "逢甲大學",
        "Mach number": "馬赫數",
    }
    with per_paragraph.open(encoding="utf-8") as f:
        assert {r["source"]: r["target"] for r in csv.DictReader(f)} == {"shear": "剪力｜剪切"}


def test_options_keep_origins_of_per_paragraph_choices():
    term = book.BookTerm(
        "shear",
        "剪力｜剪切",
        book.STATUS_PER_PARAGRAPH,
        33,
        "",
        "剪力（力學）；剪切（金屬材料）；剪（力學）",
    )
    assert book.options_of(term) == [("剪力", "力學"), ("剪切", "金屬材料"), ("剪", "力學")]


def test_options_merge_glossaries_and_drop_mainland_terms():
    candidates = [
        Candidate("電機工程", "confidence level", ("置信水平", "信賴水準")),
        Candidate("統計學", "confidence level", ("信賴水準",)),
    ]
    assert book._options(candidates) == [("信賴水準", "電機工程、統計學")]
    term = book.select_term("confidence level", 2, candidates)
    assert term.target == "信賴水準" and term.origin == "電機工程、統計學"


def test_phrases_starting_with_an_article_are_not_terms():
    assert book.select_term("a key", 3, [Candidate("電機工程", "A key", ("A 鍵",))]) is None


def test_read_user_csv_accepts_big5_from_excel(tmp_path):
    path = tmp_path / "my_terms.csv"
    path.write_bytes("source,target,note\nairfoil,翼型,\n,,\n".encode("cp950"))
    assert read_user_csv(path) == [Term("airfoil", ("翼型",))]


def test_write_terms_keeps_old_file_when_writing_fails(tmp_path):
    path = tmp_path / "book.csv"
    book.write_terms(path, [book.BookTerm("Mach number", "馬赫數", "", 1, "力學", "")])
    broken = book.BookTerm("shear", "\udcff", "", 1, "力學", "")  # 無法編碼的字元
    try:
        book.write_terms(path, [broken])
    except UnicodeEncodeError:
        pass
    assert [t.source for t in book.read_book(path)] == ["Mach number"]
