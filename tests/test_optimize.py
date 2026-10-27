import pymupdf
import pytest

from textbook_tw.compose import dual, optimize

PREFIX = "/Cs1 cs 1 scn/Gs1 gs/Gs2 gs/Gs1 gs"


def _glyph_block(prefix, size, x, y, gid, literal=False):
    code = gid.to_bytes(2, "big")
    if literal:
        escaped = (
            code.decode("latin-1").replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
        )
        text = f"({escaped})"
    else:
        text = f"<{code.hex()}>"
    return f"q {prefix} BT/F0 {size} Tf {x:.5f} {y} TD {text}Tj ET Q"


def _line(font, text, x, y, size, prefix=PREFIX, spacing=0.0, literal_every=0):
    """仿 BabelDOC：每個字一個 q BT … Tj ET Q，位置用字寬算，再加一點字距。"""
    blocks = []
    for i, ch in enumerate(text):
        gid = font.has_glyph(ord(ch))
        literal = bool(literal_every) and i % literal_every == 0
        blocks.append(_glyph_block(prefix, size, x, y, gid, literal))
        x += font.glyph_advance(ord(ch)) * size + spacing
    return blocks


@pytest.fixture(scope="module")
def font():
    return pymupdf.Font("cjk")


@pytest.fixture
def babeldoc_pdf(tmp_path, font):
    doc = pymupdf.open()
    page = doc.new_page(width=400, height=300)
    page.insert_font(fontname="F0", fontbuffer=font.buffer)
    page.draw_rect(pymupdf.Rect(10, 10, 390, 290), color=(0, 0, 1))  # 讓頁面有現成內容與 ExtGState
    extgstate = doc.get_new_xref()
    doc.update_object(extgstate, "<< /Type /ExtGState /CA 1 /ca 1 >>")
    colorspace = doc.get_new_xref()
    doc.update_object(colorspace, "[/ICCBased 0 0 R]")
    resources = doc.xref_get_key(page.xref, "Resources")
    if resources[0] == "xref":
        res_xref = int(resources[1].split()[0])
    else:
        res_xref = page.xref
    key = "Resources/" if res_xref == page.xref else ""
    doc.xref_set_key(
        res_xref, f"{key}ExtGState", f"<< /Gs1 {extgstate} 0 R /Gs2 {extgstate} 0 R >>"
    )
    doc.xref_set_key(res_xref, f"{key}ColorSpace", "<< /Cs1 /DeviceGray >>")

    blocks = []
    blocks += _line(font, "流體力學 Fluid mechanics", 30, 250, 12, literal_every=3)
    blocks += _line(font, "第二行，字距較寬", 30, 220, 12, spacing=0.7)
    blocks.append("q 0 0 1 RG 30 200 m 300 200 l S Q")  # 中間夾一條線，不能跨過去合併
    blocks += _line(font, "紅色的字", 30, 180, 10, prefix="1 0 0 rg")
    blocks += _line(font, "頁首", 30, 150, 9) + _line(font, "443", 350, 150, 9)  # 同一行相隔很遠
    stream = "\n".join(blocks)
    xref = page.get_contents()[0]
    original = doc.xref_stream(xref).decode("latin-1")
    doc.update_stream(xref, (original + "\n" + stream).encode("latin-1"))
    path = tmp_path / "babeldoc.pdf"
    doc.save(path)
    doc.close()
    return path


def _chars(page):
    return [
        (c["c"], c["origin"])
        for block in page.get_text("rawdict")["blocks"]
        for line in block.get("lines", [])
        for span in line["spans"]
        for c in span["chars"]
    ]


def test_merges_glyphs_without_moving_them(tmp_path, babeldoc_pdf):
    out = tmp_path / "optimized.pdf"
    stats = optimize.optimize_pdf(babeldoc_pdf, out)

    assert stats.glyphs == 37
    assert stats.blocks == 3  # 線條前一段、紅字、線條後的黑字
    with pymupdf.open(babeldoc_pdf) as before, pymupdf.open(out) as after:
        a, b = _chars(before[0]), _chars(after[0])
        assert [c for c, _ in a] == [c for c, _ in b]
        for (_, pa), (_, pb) in zip(a, b):
            assert pa == pytest.approx(pb, abs=1e-3)
        content = after[0].read_contents().decode("latin-1")
        assert content.count("BT") == 3
        assert "TJ" in content
        assert "0 0 1 RG 30 200 m 300 200 l S" in content  # 線條原樣保留
        assert before[0].get_pixmap(dpi=72).samples == after[0].get_pixmap(dpi=72).samples


def test_optimizes_translated_page_inside_side_by_side(tmp_path, babeldoc_pdf):
    combined = tmp_path / "sbs.pdf"
    dual.side_by_side(babeldoc_pdf, babeldoc_pdf, combined, [0])
    stats = optimize.optimize_pdf(combined)
    assert stats.glyphs == 37 * 2
    with pymupdf.open(combined) as doc:
        assert len(_chars(doc[0])) == 2 * len(
            [c for c in "流體力學 Fluid mechanics第二行，字距較寬紅色的字頁首443"]
        )


def test_dedupe_graphics_states_keeps_last_occurrence():
    text = "q /Gs1 gs/Gs2 gs/Gs1 gs/Gs2 gs .35 w/Gs5 gs /Gs5 gs (/Gs1 gs/Gs1 gs) Tj Q"
    result = optimize.dedupe_graphics_states(text)
    assert result.startswith("q /Gs1 gs/Gs2 gs .35 w/Gs5 gs ")
    assert "(/Gs1 gs/Gs1 gs)" in result  # 字串內容不動


def test_leaves_unknown_content_alone():
    text = "BT /F1 12 Tf 10 10 Td (abc) Tj ET q BT /F1 12 Tf 1 0 0 1 5 5 Tm (d) Tj ET Q"
    assert optimize.optimize_stream(text, {}) == (text, 0, 0)


def test_single_glyph_is_not_rewritten():
    text = "q 1 0 0 1 0 0 cm BT /F1 12 Tf 10 10 Td (abc) Tj ET Q 0 0 m 5 5 l S"
    assert optimize.optimize_stream(text, {}) == (text, 0, 0)


def test_horizontal_scaling_skips_page():
    block = "q BT/F0 10 Tf 1 2 TD <0001>Tj ET Q"
    text = "90 Tz " + block + " " + block
    assert optimize.optimize_stream(text, {})[1] == 0


def test_literal_string_escapes():
    assert optimize._literal_bytes(r"(a\(b\)\\\101\n)") == b"a(b)\\A\n"


def test_prune_keeps_pages_and_rendering(tmp_path, babeldoc_pdf):
    out = tmp_path / "pruned.pdf"
    optimize.optimize_pdf(babeldoc_pdf, out, prune=True)
    with pymupdf.open(babeldoc_pdf) as before, pymupdf.open(out) as after:
        assert after.page_count == before.page_count
        assert [c for c, _ in _chars(after[0])] == [c for c, _ in _chars(before[0])]
        assert "StructTreeRoot" not in after.xref_object(after.pdf_catalog())
