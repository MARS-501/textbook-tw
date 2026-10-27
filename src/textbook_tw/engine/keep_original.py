"""決定哪些段落保留原文不翻，並收集圖表裡的英文詞。

BabelDOC 的版面模型會替每段文字標上類別（abandon＝頁首頁尾、title、table_caption…），
但除了圖片本身，幾乎都照翻。結果：
- 頁首頁尾、論文標題翻得很怪，讀者也不需要
- 表格每一格都被當成一段翻譯，硬塞進原本的格子，擠又難讀
- 參考文獻被重新排版，連結顏色與分段都不見

這裡在翻譯前掃一遍整份文件（BabelDOC 的中間格式），挑出要保留原文的段落。
保留原文的段落 BabelDOC 會照原本的字、位置、顏色畫回去。
表格與圖片裡的英文詞另外收集起來：內文提到時在中文後面附上英文，讀者對照圖表時找得到。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

# 版面模型的類別：整段保留原文
KEEP_LABELS = {
    "abandon", "header", "footer", "page_number", "number",
    "reference", "reference_content", "seal", "doc_title",
}  # fmt: skip
HEADING_LABELS = {"title", "paragraph_title", "doc_title", "section_title"}
# 這些區塊裡的文字保留原文（標題 table_caption、figure_caption 是另外的區塊，照翻）
TABLE_FIGURE_LAYOUTS = {"table", "figure"}
INSIDE_RATIO = 0.5  # 段落面積有一半以上在表格／圖片區塊內，就算表格內容

# 從這些標題開始到下一個一般章節標題之前都保留原文（參考文獻、作者貢獻與利益聲明）
_BACK_MATTER = re.compile(
    r"(references?|bibliography|literature cited|works cited|"
    r"credit authorship contribution statement|author contributions?|"
    r"declaration of competing interests?|competing interests?|conflicts? of interests?|"
    r"data availability( statement)?)",
    re.IGNORECASE,
)
# 第 1 頁這些標題以上（論文標題、作者、單位）保留原文
_FRONT_MATTER = {"abstract", "articleinfo", "keywords", "highlights"}
_NUMBERING = re.compile(r"^(\d+(\.\d+)*\.?|[ivx]+\.|[a-z]\.)\s+", re.IGNORECASE)
# 編號式參考文獻：[12] Author A, ... 2019
_REFERENCE_ENTRY = re.compile(r"^\[\d{1,3}\]\s+\S.*\b(19|20)\d{2}\b", re.DOTALL)

MAX_FIGURE_TERMS = 300
_TERM_SPLIT = re.compile(r"[,;:=()\[\]{}|/+*<>≤≥±%°]+|\s-\s|\d+(\.\d+)?")
_LETTERS = re.compile(r"[A-Za-z]")


@dataclass
class Plan:
    keep: set[int] = field(default_factory=set)  # 保留原文的段落（id(paragraph)）
    figure_terms: list[str] = field(default_factory=list)  # 圖表裡的英文詞
    counts: dict[str, int] = field(default_factory=dict)  # 各類保留了幾段（紀錄用）


def _text(paragraph) -> str:
    return " ".join((paragraph.unicode or "").split())


def _squash(text: str) -> str:
    """A R T I C L E  I N F O → articleinfo"""
    return re.sub(r"[\s.:]", "", text).lower()


def _heading_name(text: str) -> str:
    return _NUMBERING.sub("", text).strip(" .:").lower()


def is_back_matter_heading(text: str) -> bool:
    return len(text) <= 60 and _BACK_MATTER.fullmatch(_heading_name(text)) is not None


def is_front_matter_heading(text: str) -> bool:
    return len(text) <= 40 and _squash(_heading_name(text)) in _FRONT_MATTER


def is_reference_entry(text: str) -> bool:
    return _REFERENCE_ENTRY.match(text) is not None


def _area(box) -> float:
    return max(0.0, box.x2 - box.x) * max(0.0, box.y2 - box.y)


def _overlap(a, b) -> float:
    w = min(a.x2, b.x2) - max(a.x, b.x)
    h = min(a.y2, b.y2) - max(a.y, b.y)
    return w * h if w > 0 and h > 0 else 0.0


def _inside(box, regions) -> bool:
    area = _area(box)
    return area > 0 and any(_overlap(box, r) / area >= INSIDE_RATIO for r in regions)


def _page_width(page) -> float:
    for attr in ("cropbox", "mediabox"):
        holder = getattr(page, attr, None)
        if holder is not None and holder.box is not None:
            return holder.box.x2 - holder.box.x
    return 612.0


def _reading_order(page, paragraphs: list) -> list:
    """雙欄排版：左欄由上到下，再右欄由上到下（PDF 的 y 往上增加）。"""
    middle = _page_width(page) * 0.45

    def key(p):
        column = 0 if p.box.x < middle else 1
        return (column, -p.box.y2)

    return sorted((p for p in paragraphs if p.box is not None), key=key)


def _front_matter(page, paragraphs: list) -> list:
    """第 1 頁最上面的論文標題、作者、單位。"""
    headings = [p for p in paragraphs if is_front_matter_heading(_text(p))]
    if headings:
        top = max(h.box.y2 for h in headings)
        heading_ids = {id(h) for h in headings}
        return [p for p in paragraphs if p.box.y >= top - 1 and id(p) not in heading_ids]
    titles = [p for p in paragraphs if p.layout_label in HEADING_LABELS]
    return [max(titles, key=lambda p: p.box.y2)] if titles else []


def _words_in(page, regions) -> list[str]:
    """圖片裡沒變成段落的字（Nose、Load…），依位置串成一行一行的文字。"""
    chars = [
        c
        for c in getattr(page, "pdf_character", []) or []
        if c.box is not None and c.char_unicode and _inside(c.box, regions)
    ]
    chars.sort(key=lambda c: (-round(c.box.y2), c.box.x))
    lines: list[str] = []
    current = ""
    last = None
    for c in chars:
        size = max(1.0, c.box.y2 - c.box.y)
        if last is not None and abs(c.box.y2 - last.box.y2) > size * 0.5:
            lines.append(current)
            current = ""
        elif last is not None and c.box.x - last.box.x2 > size * 0.3:
            current += " "
        current += c.char_unicode
        last = c
    if current:
        lines.append(current)
    return lines


def figure_terms_from(texts: list[str]) -> list[str]:
    """圖表文字裡值得在內文附英文的詞：拿掉數字、單位、代號（GGG、Vf,C）。"""
    terms: dict[str, str] = {}
    for text in texts:
        for part in _TERM_SPLIT.split(text):
            if not part:
                continue
            term = " ".join(part.split()).strip(" .-")
            words = term.split()
            if not words or len(words) > 6 or len(_LETTERS.findall(term)) < 3:
                continue
            if len(words) == 1 and term.isupper() and len(term) <= 5:
                continue  # 代號
            terms.setdefault(term.lower(), term)
    return list(terms.values())[:MAX_FIGURE_TERMS]


def plan(docs) -> Plan:
    """掃描整份文件（BabelDOC 的 Document），決定保留原文的段落。"""
    result = Plan()
    counts = {"頁首頁尾": 0, "標題與作者": 0, "表格": 0, "參考文獻與聲明": 0}
    figure_texts: list[str] = []
    in_back_matter = False

    def keep(paragraph, kind: str) -> None:
        result.keep.add(id(paragraph))
        counts[kind] += 1

    for page in docs.page:
        paragraphs = [p for p in page.pdf_paragraph if p.box is not None]
        regions = [
            layout.box
            for layout in page.page_layout
            if layout.class_name in TABLE_FIGURE_LAYOUTS and layout.box is not None
        ]
        front = {id(p) for p in _front_matter(page, paragraphs)} if page.page_number == 0 else set()
        for p in _reading_order(page, paragraphs):
            text = _text(p)
            if is_back_matter_heading(text):
                in_back_matter = True
            elif in_back_matter and p.layout_label in HEADING_LABELS:
                in_back_matter = False  # 參考文獻後面還有附錄之類的章節
            if p.layout_label in KEEP_LABELS:
                keep(p, "頁首頁尾")
            elif id(p) in front:
                keep(p, "標題與作者")
            elif in_back_matter or is_reference_entry(text):
                keep(p, "參考文獻與聲明")
            elif p.layout_label not in ("table_caption", "figure_caption") and _inside(
                p.box, regions
            ):
                keep(p, "表格")
                figure_texts.append(text)
        figure_texts.extend(_words_in(page, regions))

    result.figure_terms = figure_terms_from(figure_texts)
    result.counts = counts
    return result


def terms_in(text: str, terms: list[str]) -> list[str]:
    """這段文字裡用到的圖表詞（不分大小寫、整個字比對）。"""
    lower = text.lower()
    found = []
    for term in terms:
        if re.search(rf"(?<![A-Za-z]){re.escape(term.lower())}(?![A-Za-z])", lower):
            found.append(term)
    return found
