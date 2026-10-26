"""掃描 PDF，挑出出現過的術語，產生這本書專用的術語表 glossary/books/<檔名>.csv。

使用者可以用 Excel 編輯這個檔案：改 target 欄選譯名，清空 target 代表不使用。
之後翻譯同一本書（包括只翻部分頁面）都沿用這份術語表，全書譯名一致。

挑選規則：
- 多字詞組（Mach number、angle of attack）：收錄，譯名取科目優先順序最前面的名詞庫
- 單一單字：名詞庫裡大多是一般用字（can→罐、figure→數字、surface→翼面），
  所以只看英文裡少見的字（wordfreq 詞頻 Zipf < 3.6，例如 airfoil 2.4、equation 4.0 不算），
  而且至少兩個名詞庫首選譯名一致的才收（fuselage→機身）；
  首選譯名不一致的（airfoil：翼剖面／翼形）列為「待確認」，不自動採用
"""

from __future__ import annotations

import csv
import re
from collections import Counter
from dataclasses import asdict, dataclass
from pathlib import Path

import pymupdf
from wordfreq import zipf_frequency

from textbook_tw.config import Profile
from textbook_tw.glossary.fetch import GLOSSARY_DIR
from textbook_tw.glossary.lexicon import (
    MY_TERMS_ID,
    Candidate,
    Lexicon,
    build_lexicon,
    read_user_csv,
)
from textbook_tw.glossary.naer import Term

BOOKS_DIR = GLOSSARY_DIR / "books"
FIELDS = ["source", "target", "status", "count", "origin", "alternatives"]

STATUS_REVIEW = "待確認"  # 單字譯名有衝突，沒有自動採用
STATUS_CONFLICT = "名詞庫譯名不同"  # 已採用優先順序最前面的，但其他名詞庫譯法不同

MIN_SINGLE_WORD_LENGTH = 5
MAX_SINGLE_WORD_ZIPF = 3.6  # 高於這個詞頻的單字視為一般英文
MIN_REVIEW_COUNT = 3

# 整個詞組都是這些字時不收（例如 less than）
_FUNCTION_WORDS = {
    "a", "an", "the", "of", "in", "on", "at", "to", "for", "by", "with", "from", "into",
    "and", "or", "not", "no", "as", "is", "be", "it", "this", "that", "than", "less", "more",
    "over", "under", "per", "up", "down", "out", "off", "all", "any", "each",
}  # fmt: skip

_WORD = re.compile(r"[A-Za-z][A-Za-z0-9'\-]*")
_LINE_BREAK_HYPHEN = re.compile(r"(?<=[a-z])-\n(?=[a-z])")


@dataclass
class BookTerm:
    source: str
    target: str
    status: str
    count: int
    origin: str
    alternatives: str


def book_path(pdf: Path) -> Path:
    return BOOKS_DIR / f"{pdf.stem}.csv"


def extract_words(pdf: Path) -> list[str]:
    with pymupdf.open(pdf) as doc:
        text = "\n".join(page.get_text() for page in doc)
    text = _LINE_BREAK_HYPHEN.sub("", text)  # 行尾斷字：com-\npressible → compressible
    return [w.lower() for w in _WORD.findall(text)]


def _singular(word: str) -> str:
    if word.endswith("ies") and len(word) > 4:
        return word[:-3] + "y"
    if word.endswith(("ses", "xes", "ches", "shes")):
        return word[:-2]
    if word.endswith("s") and not word.endswith("ss") and len(word) > 3:
        return word[:-1]
    return word


def count_terms(words: list[str], lexicon: Lexicon) -> Counter[str]:
    """計算名詞庫裡的詞在文中出現幾次（最後一個字是複數也算）。"""
    counts: Counter[str] = Counter()
    for n in range(1, lexicon.max_words + 1):
        for i in range(len(words) - n + 1):
            gram = words[i : i + n]
            key = " ".join(gram)
            if key not in lexicon:
                key = " ".join([*gram[:-1], _singular(gram[-1])])
            if key in lexicon:
                counts[key] += 1
    return counts


def _options(candidates: list[Candidate]) -> list[tuple[str, str]]:
    """所有候選譯名（不重複），依優先順序：[(譯名, 名詞庫), ...]"""
    options: list[tuple[str, str]] = []
    for c in candidates:
        for target in c.targets:
            if all(target != t for t, _ in options):
                options.append((target, c.origin))
    return options


def select_term(key: str, count: int, candidates: list[Candidate]) -> BookTerm | None:
    first = candidates[0]
    options = _options(candidates)
    alternatives = "；".join(f"{t}（{origin}）" for t, origin in options[1:])
    primaries = {c.targets[0] for c in candidates}

    def term(target: str, status: str) -> BookTerm:
        return BookTerm(first.source, target, status, count, first.origin, alternatives)

    if first.origin == MY_TERMS_ID:
        return term(first.targets[0], "")

    words = key.split(" ")
    if len(words) > 1 or "-" in key:
        if set(words) <= _FUNCTION_WORDS:
            return None
        return term(first.targets[0], STATUS_CONFLICT if len(primaries) > 1 else "")

    if (
        len(key) < MIN_SINGLE_WORD_LENGTH
        or len(candidates) < 2
        or zipf_frequency(key, "en") >= MAX_SINGLE_WORD_ZIPF
    ):
        return None
    if len(primaries) == 1:
        return term(first.targets[0], "")
    if count >= MIN_REVIEW_COUNT:
        return term("", STATUS_REVIEW)
    return None


def build_terms(pdf: Path, lexicon: Lexicon) -> list[BookTerm]:
    counts = count_terms(extract_words(pdf), lexicon)
    terms = [
        t
        for key, count in counts.items()
        if (t := select_term(key, count, lexicon[key])) is not None
    ]
    status_order = {STATUS_REVIEW: 0, STATUS_CONFLICT: 1, "": 2}
    terms.sort(key=lambda t: (status_order[t.status], -t.count, t.source.lower()))
    return terms


def create_book_glossary(pdf: Path, profile: Profile) -> tuple[Path, list[BookTerm]]:
    """掃描 PDF 並寫出（覆蓋）這本書的術語表。"""
    terms = build_terms(pdf, build_lexicon(profile))
    path = book_path(pdf)
    write_terms(path, terms)
    return path, terms


def write_terms(path: Path, terms: list[BookTerm]) -> None:
    """寫成 UTF-8 BOM，Excel 打開中文才不會變亂碼。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(asdict(t) for t in terms)


def read_terms(path: Path) -> list[Term]:
    """讀回（可能被使用者編輯過的）術語表；target 空白的不使用。"""
    return read_user_csv(path)


def export_for_babeldoc(book: list[Term], my_terms: list[Term], path: Path) -> int:
    """合併成 BabelDOC 的 source,target CSV；my_terms 優先。回傳詞數。"""
    merged: dict[str, Term] = {}
    for term in [*my_terms, *book]:
        merged.setdefault(term.key, term)
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["source", "target"])
        for term in merged.values():
            writer.writerow([term.source, term.targets[0]])
    return len(merged)
