import pymupdf
import pytest

from textbook_tw.compose import dual


def _make_pdf(path, labels, width=300, height=400):
    doc = pymupdf.open()
    for label in labels:
        page = doc.new_page(width=width, height=height)
        page.insert_text((50, 100), label)
    doc.save(path)
    doc.close()


@pytest.fixture
def pdfs(tmp_path):
    original = tmp_path / "original.pdf"
    translated = tmp_path / "translated.pdf"
    _make_pdf(original, ["orig-1", "orig-2", "orig-3"])
    # 只翻了第 1、3 頁
    _make_pdf(translated, ["trans-1", "trans-3"])
    return original, translated, [0, 2]


def _texts(path):
    with pymupdf.open(path) as doc:
        return [page.get_text().split() for page in doc]


def test_side_by_side_puts_original_left(tmp_path, pdfs):
    original, translated, indices = pdfs
    out = tmp_path / "sbs.pdf"
    dual.side_by_side(original, translated, out, indices)

    with pymupdf.open(out) as doc:
        assert doc.page_count == 2
        assert doc[0].rect.width == 600 and doc[0].rect.height == 400
        left = doc[0].get_text(clip=pymupdf.Rect(0, 0, 300, 400)).split()
        right = doc[0].get_text(clip=pymupdf.Rect(300, 0, 600, 400)).split()
    assert left == ["orig-1"] and right == ["trans-1"]


def test_side_by_side_translated_first(tmp_path, pdfs):
    original, translated, indices = pdfs
    out = tmp_path / "sbs.pdf"
    dual.side_by_side(original, translated, out, indices, translated_first=True)

    with pymupdf.open(out) as doc:
        left = doc[1].get_text(clip=pymupdf.Rect(0, 0, 300, 400)).split()
    assert left == ["trans-3"]


def test_alternating_order(tmp_path, pdfs):
    original, translated, indices = pdfs
    out = tmp_path / "alt.pdf"
    dual.alternating(original, translated, out, indices)
    assert _texts(out) == [["orig-1"], ["trans-1"], ["orig-3"], ["trans-3"]]

    dual.alternating(original, translated, out, indices, translated_first=True)
    assert _texts(out) == [["trans-1"], ["orig-1"], ["trans-3"], ["orig-3"]]


def test_page_count_mismatch_is_rejected(tmp_path, pdfs):
    original, translated, _ = pdfs
    with pytest.raises(ValueError):
        dual.alternating(original, translated, tmp_path / "x.pdf", [0, 1, 2])
