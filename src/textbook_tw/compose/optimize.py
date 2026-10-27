"""把 BabelDOC 逐字輸出的文字合併，讓譯文 PDF 開起來不卡（畫面完全不變）。

BabelDOC 每個字都寫成一個獨立的文字物件：

    q <圖形狀態> BT /字型 字級 Tf x y TD <字> Tj ET Q

一頁幾千個，閱讀器要逐一處理。這裡把連續、圖形狀態相同的字合進同一個 BT…ET，
同一條基線的字合成一個 TJ，字距用字型裡的字寬算出來，每個字的位置不變。
認不出來的內容（圖、線條、其他寫法的文字）原樣保留。
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

import pymupdf

_NUM = r"-?(?:\d+\.?\d*|\.\d+)"
_GLYPH = re.compile(
    r"(?<![^\s\]>)])q(?=[\s/])\s*((?:(?!BT\b)[^qQ()<>\[\]])*?)\s*BT\s*"
    rf"(/[^\s/\[\]()<>]+)\s+({_NUM})\s+Tf\s+({_NUM})\s+({_NUM})\s+T[dD]\s*"
    r"(<[0-9a-fA-F\s]*>|\((?:\\.|[^\\()])*\))\s*Tj\s+ET\s+Q(?![^\s\[<(/%])",
    re.S,
)
_BETWEEN = re.compile(r"\s*")
# BabelDOC 每個物件前都重設一串 /Gs1 gs/Gs2 gs/Gs1 gs…，同一串裡重複的只有最後一次有作用
_GS_RUN = re.compile(r"(?:/[^\s/\[\]()<>{}%]+\s*gs(?![\w])\s*){2,}")
_GS_NAME = re.compile(r"(/[^\s/\[\]()<>{}%]+)\s*gs")
_STRING = re.compile(r"(\((?:\\.|[^\\()])*\)|<[0-9a-fA-F\s]*>)")
_INLINE_IMAGE = re.compile(r"(?<![/\w])BI(?![\w])")
# 這些會改變字距或字形的指令若出現在頁面其他地方，合併後的 TJ 字距可能算錯，整頁跳過
_UNSAFE = re.compile(r"(?<![/\w])Tz(?!\w)")
_STATE = re.compile(r"(?<![/\w])T[cw](?!\w)")
# 同一行兩個字相距超過幾個字寬就重新定位（通常是分欄或頁首頁碼）
_MAX_GAP_EM = 3.0


@dataclass
class _Glyph:
    raw: str  # 原本的整段文字，單獨一個字時原樣寫回
    prefix: str
    font: str
    size: str
    x: str
    y: str
    data: bytes


@dataclass
class _FontWidths:
    two_byte: bool
    widths: dict[int, float]
    default: float

    def advance(self, data: bytes) -> float:
        """字串的總寬度（千分之一字級）。"""
        step = 2 if self.two_byte else 1
        codes = (int.from_bytes(data[i : i + step], "big") for i in range(0, len(data), step))
        return sum(self.widths.get(code, self.default) for code in codes)


@dataclass
class Stats:
    pages: int = 0
    glyphs: int = 0  # 合併掉的逐字文字物件數
    blocks: int = 0  # 合併後剩下的文字物件數
    bytes_before: int = 0
    bytes_after: int = 0


# ---- PDF 字串與物件解析 ------------------------------------------------------

_ESCAPES = {b"n": b"\n", b"r": b"\r", b"t": b"\t", b"b": b"\b", b"f": b"\f"}


def _literal_bytes(token: str) -> bytes:
    """(…) 字串轉成位元組，處理反斜線跳脫。"""
    raw = token[1:-1].encode("latin-1")
    out = bytearray()
    i = 0
    while i < len(raw):
        c = raw[i : i + 1]
        if c != b"\\":
            out += c
            i += 1
            continue
        nxt = raw[i + 1 : i + 2]
        if nxt in _ESCAPES:
            out += _ESCAPES[nxt]
            i += 2
        elif nxt.isdigit():
            j = i + 1
            while j < len(raw) and j < i + 4 and raw[j : j + 1] in b"01234567":
                j += 1
            out.append(int(raw[i + 1 : j], 8) & 0xFF)
            i = j
        elif nxt in (b"\r", b"\n"):  # 行尾的反斜線代表接續下一行
            i += 2
            if nxt == b"\r" and raw[i : i + 1] == b"\n":
                i += 1
        else:
            out += nxt
            i += 2
    return bytes(out)


def _string_bytes(token: str) -> bytes:
    if token.startswith("<"):
        digits = re.sub(r"\s", "", token[1:-1])
        if len(digits) % 2:
            digits += "0"
        return bytes.fromhex(digits)
    return _literal_bytes(token)


def _resolve(doc: pymupdf.Document, xref: int, key: str) -> str | None:
    kind, value = doc.xref_get_key(xref, key)
    if kind == "null":
        return None
    if kind == "xref":
        return doc.xref_object(int(value.split()[0]), compressed=True)
    return value


def _numbers(text: str) -> list[float]:
    return [float(n) for n in re.findall(_NUM, text)]


def _cid_widths(text: str) -> dict[int, float]:
    """解析 Type0 字型的 /W：`c [w1 w2 …]` 或 `c1 c2 w`。"""
    widths: dict[int, float] = {}
    tokens = re.findall(rf"\[|\]|{_NUM}", text.strip()[1:-1])
    i = 0
    while i < len(tokens):
        first = int(float(tokens[i]))
        if tokens[i + 1] == "[":
            j = i + 2
            code = first
            while tokens[j] != "]":
                widths[code] = float(tokens[j])
                code += 1
                j += 1
            i = j + 1
        else:
            last, width = int(float(tokens[i + 1])), float(tokens[i + 2])
            for code in range(first, last + 1):
                widths[code] = width
            i += 3
    return widths


def _font_widths(doc: pymupdf.Document, xref: int) -> _FontWidths | None:
    """讀字型的字寬；不認得的字型（Type3、直排、非 Identity 編碼）回傳 None。"""
    subtype = doc.xref_get_key(xref, "Subtype")[1]
    if subtype == "/Type0":
        if doc.xref_get_key(xref, "Encoding")[1] != "/Identity-H":
            return None
        descendants = _resolve(doc, xref, "DescendantFonts")
        match = re.search(r"(\d+) 0 R", descendants or "")
        if not match:
            return None
        cid_font = int(match.group(1))
        w = _resolve(doc, cid_font, "W")
        dw = _resolve(doc, cid_font, "DW")
        return _FontWidths(True, _cid_widths(w) if w else {}, float(dw) if dw else 1000.0)
    if subtype in ("/Type1", "/TrueType", "/MMType1"):
        first = _resolve(doc, xref, "FirstChar")
        widths = _resolve(doc, xref, "Widths")
        if first is None or widths is None:
            return None  # 標準 14 字型沒有附字寬
        missing = 0.0
        descriptor = doc.xref_get_key(xref, "FontDescriptor")
        if descriptor[0] == "xref":
            value = _resolve(doc, int(descriptor[1].split()[0]), "MissingWidth")
            missing = float(value) if value else 0.0
        table = {int(first) + i: w for i, w in enumerate(_numbers(widths))}
        return _FontWidths(False, table, missing)
    return None


def _streams(
    doc: pymupdf.Document, page: pymupdf.Page
) -> list[tuple[int, dict[str, _FontWidths | None]]]:
    """頁面上要處理的內容串流，以及各自可用的字型名稱 → 字寬。

    除了頁面本身，也包含表單物件（對照版把譯文頁包成表單放進頁面）。
    """
    fonts_by_owner: dict[int, dict[str, _FontWidths | None]] = {}
    for xref, _ext, _type, _base, name, _enc, referencer in page.get_fonts(full=True):
        fonts = fonts_by_owner.setdefault(referencer, {})
        if name not in fonts:
            fonts[name] = _font_widths(doc, xref)
    streams = [(xref, fonts_by_owner.get(0, {})) for xref in page.get_contents()]
    streams += [(xref, fonts_by_owner.get(xref, {})) for xref, *_ in page.get_xobjects()]
    return streams


# ---- 改寫內容串流 ------------------------------------------------------------


def _fmt(value: float) -> str:
    text = f"{value:.3f}".rstrip("0").rstrip(".")
    return "0" if text in ("", "-0") else text


def _font_key(name: str) -> str:
    """內容串流裡的字型名稱（/Abc#20D）轉成資源名稱。"""
    return re.sub(r"#([0-9a-fA-F]{2})", lambda m: chr(int(m.group(1), 16)), name[1:])


def _write_group(glyphs: list[_Glyph], fonts: dict[str, _FontWidths | None], reset: bool) -> str:
    """一組圖形狀態相同的字寫成一個 BT…ET。"""
    out = [f"q {glyphs[0].prefix} BT" if glyphs[0].prefix else "q BT"]
    if reset:
        out.append("0 Tc 0 Tw")
    items: list[str] = []  # 目前這一段 TJ 的內容
    font = size = None
    pen: tuple[float, float] | None = None  # 上一個字畫完後的筆位置

    def flush() -> None:
        if not items:
            return
        if len(items) == 1:
            out.append(f"{items[0]}Tj")
        else:
            out.append(f"[{' '.join(items)}]TJ")
        items.clear()

    for g in glyphs:
        if (g.font, g.size) != (font, size):
            flush()
            font, size = g.font, g.size
            out.append(f"{g.font} {g.size} Tf")
            pen = None
        size_value = float(g.size)
        x, y = float(g.x), float(g.y)
        hex_text = f"<{g.data.hex()}>"
        shift = None
        if pen is not None and pen[1] == y and size_value:
            shift = round((pen[0] - x) * 1000 / size_value, 3)
            if abs(shift) > _MAX_GAP_EM * 1000:
                shift = None
        if shift is None:
            flush()
            out.append(f"1 0 0 1 {g.x} {g.y} Tm")
            items.append(hex_text)
            placed = x
        else:
            if shift:
                items.append(_fmt(shift))
                items.append(hex_text)
            elif items and items[-1].startswith("<"):
                items[-1] = items[-1][:-1] + g.data.hex() + ">"
            else:
                items.append(hex_text)
            placed = pen[0] - shift * size_value / 1000
        widths = fonts.get(_font_key(g.font))
        pen = (placed + widths.advance(g.data) * size_value / 1000, y) if widths else None
    flush()
    out.append("ET Q")
    return "\n".join(out)


def _dedupe_run(match: re.Match[str]) -> str:
    names = _GS_NAME.findall(match.group(0))
    kept = [name for i, name in enumerate(names) if name not in names[i + 1 :]]
    if len(kept) == len(names):
        return match.group(0)
    return "".join(f"{name} gs" for name in kept) + " "


def dedupe_graphics_states(text: str) -> str:
    """連續的 gs 指令只留每個名稱的最後一次（結果的圖形狀態相同）。字串內容不動。"""
    if _INLINE_IMAGE.search(text):
        return text  # 內嵌圖片是二進位資料，不冒險
    parts = _STRING.split(text)
    for i in range(0, len(parts), 2):
        parts[i] = _GS_RUN.sub(_dedupe_run, parts[i])
    return "".join(parts)


def optimize_stream(text: str, fonts: dict[str, _FontWidths | None]) -> tuple[str, int, int]:
    """改寫一段內容串流，回傳（新內容、合併前的字數、合併後的文字物件數）。"""
    if _UNSAFE.search(text):
        return text, 0, 0
    text = dedupe_graphics_states(text)
    reset = bool(_STATE.search(_GLYPH.sub(" ", text)))
    out: list[str] = []
    run: list[_Glyph] = []  # 中間只隔著空白的連續逐字物件
    run_start = last = 0
    merged = blocks = 0

    def close_run() -> None:
        nonlocal merged, blocks
        groups: list[list[_Glyph]] = []
        for g in run:
            if groups and groups[-1][0].prefix == g.prefix:
                groups[-1].append(g)
            else:
                groups.append([g])
        if all(len(group) == 1 for group in groups):
            out.append(text[run_start:last])  # 沒有可合併的，原樣保留
        else:
            for group in groups:
                if len(group) == 1:
                    out.append(f"\n{group[0].raw}\n")
                else:
                    out.append(f"\n{_write_group(group, fonts, reset)}\n")
                    merged += len(group)
                    blocks += 1
        run.clear()

    for m in _GLYPH.finditer(text):
        gap = text[last : m.start()]
        if run and not _BETWEEN.fullmatch(gap):
            close_run()
        if not run:
            out.append(gap)
            run_start = m.start()
        prefix, font, size, x, y, string = m.groups()
        run.append(_Glyph(m.group(0), prefix.strip(), font, size, x, y, _string_bytes(string)))
        last = m.end()
    if run:
        close_run()
    out.append(text[last:])
    return "".join(out), merged, blocks


def optimize_pdf(path: Path, out: Path | None = None, prune: bool = False) -> Stats:
    """改寫整份 PDF；out 省略時覆蓋原檔。

    prune：只翻部分頁面時，BabelDOC 輸出的檔案仍透過結構標記、連結保留沒翻的原文頁
    （連同上面的圖片，2 頁的譯文可能有 16 MB）。重新組一份只含現有頁面的 PDF，畫面不變；
    書籤與結構標記會拿掉（指向的頁面本來就不在了）。
    """
    stats = Stats()
    with pymupdf.open(path) as doc:
        done: set[int] = set()
        for page in doc:
            for xref, fonts in _streams(doc, page):
                if xref in done:
                    continue
                done.add(xref)
                data = doc.xref_stream(xref)
                if data is None:
                    continue
                text = data.decode("latin-1")
                new, merged, blocks = optimize_stream(text, fonts)
                stats.bytes_before += len(data)
                if new != text:
                    encoded = new.encode("latin-1")
                    doc.update_stream(xref, encoded)
                    stats.bytes_after += len(encoded)
                    stats.glyphs += merged
                    stats.blocks += blocks
                    stats.pages += 1
                else:
                    stats.bytes_after += len(data)
        target = out or path
        temp = target.with_name(target.name + ".tmp")
        if prune:
            with pymupdf.open() as pruned:
                pruned.insert_pdf(doc)
                pruned.set_metadata(doc.metadata)
                pruned.save(temp, garbage=3, deflate=True)
        else:
            doc.save(temp, garbage=3, deflate=True)
    temp.replace(target)
    return stats
