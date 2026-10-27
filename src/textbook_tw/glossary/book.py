"""掃描 PDF，挑出出現過的術語，產生這本書專用的術語表 glossary/books/<檔名>.csv。

使用者可以用 Excel 或 App 編輯這個檔案：改 target 欄選譯名，清空 target 代表不使用。
之後翻譯同一本書（包括只翻部分頁面）都沿用這份術語表，全書譯名一致。

挑選規則：
- 多字詞組（Mach number、angle of attack）：收錄，譯名取科目優先順序最前面的名詞庫
- 單一單字：名詞庫裡大多是一般用字（can→罐、figure→數字、surface→翼面），
  所以只看英文裡少見的字（wordfreq 詞頻 Zipf < 3.6，例如 airfoil 2.4、equation 4.0 不算），
  而且至少兩個名詞庫首選譯名一致的才收（fuselage→機身）；
  首選譯名不一致的（airfoil：翼剖面／翼形）列為「待確認」，不自動採用

名詞庫譯名不一致的詞，之後再交給模型依這份文件的上下文挑選（見 resolve.py）。
target 可以用「｜」列出幾個譯名（剪力｜剪切），代表翻譯時依每一段的意思選一個。
"""

from __future__ import annotations

import csv
import json
import re
from dataclasses import asdict, dataclass, fields
from functools import cache
from pathlib import Path

import pymupdf
from wordfreq import zipf_frequency

from textbook_tw.config import Profile
from textbook_tw.glossary.fetch import GLOSSARY_DIR, load_sources
from textbook_tw.glossary.lexicon import (
    MY_TERMS_ID,
    Candidate,
    Lexicon,
    build_lexicon,
    decode_user_csv,
    read_user_csv,
)
from textbook_tw.glossary.naer import Term, read_mainland_names

BOOKS_DIR = GLOSSARY_DIR / "books"
FIELDS = [
    "source", "target", "status", "count", "origin", "alternatives", "page", "context", "note",
]  # fmt: skip

STATUS_REVIEW = "待確認"  # 單字譯名有衝突，沒有自動採用
STATUS_CONFLICT = "名詞庫譯名不同"  # 已採用優先順序最前面的，但其他名詞庫譯法不同
STATUS_SUGGESTED = "模型建議"  # 模型依這份文件的上下文選的譯名，note 是理由
STATUS_PER_PARAGRAPH = "依段落"  # 文中有不同意思，翻譯時每段從 target 列的譯名挑一個
STATUS_SKIPPED = "不套用"  # 模型判斷這裡不是術語或候選都不合適，交給翻譯時自行判斷
USER_ORIGIN = "你的選擇"  # 使用者在 App 裡選的譯名；重建術語表時保留
CHOICE_SEPARATOR = "｜"
ORIGIN_SEPARATOR = "、"

MAINLAND_SOURCE = "兩岸對照-航空"
# 台灣不用的大陸用語；含有這些字的候選譯名不列入（台灣：變異數、信賴、模數、資訊…）
MAINLAND_MARKERS = (
    "方差",
    "置信",
    "模量",
    "信息",
    "軟件",
    "硬件",
    "網絡",
    "傳感器",
    "量綱",
    "湍流",
)

MIN_SINGLE_WORD_LENGTH = 5
MAX_SINGLE_WORD_ZIPF = 3.6  # 高於這個詞頻的單字視為一般英文
MIN_REVIEW_COUNT = 3
CONTEXT_WORDS = 7  # 原文句子：術語前後各取幾個字

# 整個詞組都是這些字時不收（例如 less than）
_FUNCTION_WORDS = {
    "a", "an", "the", "of", "in", "on", "at", "to", "for", "by", "with", "from", "into",
    "and", "or", "not", "no", "as", "is", "be", "it", "this", "that", "than", "less", "more",
    "over", "under", "per", "up", "down", "out", "off", "all", "any", "each",
}  # fmt: skip
# 冠詞開頭的詞組不是術語（名詞庫的 a key→A 鍵 會把「a key factor」翻壞）
_ARTICLES = {"a", "an", "the"}

_WORD = re.compile(r"[A-Za-z][A-Za-z0-9'\-]*")
_LINE_BREAK_HYPHEN = re.compile(r"(?<=[a-z])-\n(?=[a-z])")
_OPTION = re.compile(r"^(.*)（(.*)）$")


@dataclass
class BookTerm:
    source: str
    target: str
    status: str
    count: int
    origin: str
    alternatives: str
    page: int = 0  # 第一次出現的頁碼（1 起算）
    context: str = ""  # 第一次出現時的原文片段
    note: str = ""  # 模型選這個譯名的理由


@dataclass(frozen=True)
class Token:
    word: str  # 原文
    page: int  # 1 起算

    @property
    def lower(self) -> str:
        return self.word.lower()


def book_path(pdf: Path) -> Path:
    return BOOKS_DIR / f"{pdf.stem}.csv"


def _meta_path(pdf: Path) -> Path:
    return BOOKS_DIR / f"{pdf.stem}.meta.json"


def extract_tokens(pdf: Path) -> list[Token]:
    tokens: list[Token] = []
    with pymupdf.open(pdf) as doc:
        for page_no, page in enumerate(doc, start=1):
            text = _LINE_BREAK_HYPHEN.sub("", page.get_text())  # 行尾斷字：com-\npressible
            tokens.extend(Token(w, page_no) for w in _WORD.findall(text))
    return tokens


def _singular(word: str) -> str:
    if word.endswith("ies") and len(word) > 4:
        return word[:-3] + "y"
    if word.endswith(("ses", "xes", "ches", "shes")):
        return word[:-2]
    if word.endswith("s") and not word.endswith("ss") and len(word) > 3:
        return word[:-1]
    return word


def locate_terms(words: list[str], lexicon: Lexicon) -> dict[str, tuple[int, int, int]]:
    """名詞庫裡的詞在文中出現幾次（最後一個字是複數也算）：{詞: (次數, 第一次位置, 字數)}。"""
    found: dict[str, tuple[int, int, int]] = {}
    for n in range(1, lexicon.max_words + 1):
        for i in range(len(words) - n + 1):
            gram = words[i : i + n]
            key = " ".join(gram)
            if key not in lexicon:
                key = " ".join([*gram[:-1], _singular(gram[-1])])
            if key in lexicon:
                count, first, _ = found.get(key, (0, i, n))
                found[key] = (count + 1, min(first, i), n)
    return found


def occurrences(words: list[str], keys: set[str]) -> dict[str, list[int]]:
    """這些詞在文中每次出現的位置（比對方式同 locate_terms）。"""
    found: dict[str, list[int]] = {}
    for n in {len(k.split(" ")) for k in keys}:
        for i in range(len(words) - n + 1):
            gram = words[i : i + n]
            key = " ".join(gram)
            if key not in keys:
                key = " ".join([*gram[:-1], _singular(gram[-1])])
            if key in keys:
                found.setdefault(key, []).append(i)
    return found


def count_terms(words: list[str], lexicon: Lexicon) -> dict[str, int]:
    return {key: count for key, (count, _, _) in locate_terms(words, lexicon).items()}


def context_of(tokens: list[Token], start: int, length: int, width: int = CONTEXT_WORDS) -> str:
    """術語前後各取 width 個字的原文片段。"""
    lo = max(0, start - width)
    hi = min(len(tokens), start + length + width)
    text = " ".join(t.word for t in tokens[lo:hi])
    return ("…" if lo > 0 else "") + text + ("…" if hi < len(tokens) else "")


@cache
def _mainland_names() -> frozenset[str]:
    """兩岸對照名詞裡的大陸譯名（名詞庫還沒下載時是空的）。"""
    sources = {s.id: s for s in load_sources()}
    source = sources.get(MAINLAND_SOURCE)
    if source is None or not source.path.exists():
        return frozenset()
    return frozenset(read_mainland_names(source.path))


def is_mainland(target: str) -> bool:
    """大陸用語：兩岸對照名詞列出的大陸譯名，或含有台灣不用的詞（方差、置信、模量…）。"""
    return target in _mainland_names() or any(m in target for m in MAINLAND_MARKERS)


def _options(candidates: list[Candidate]) -> list[tuple[str, str]]:
    """所有候選譯名（不重複），依優先順序：[(譯名, 名詞庫), ...]

    同一個譯名出現在好幾個名詞庫時，名詞庫用「、」串起來（標準差（航空太空、統計學））。
    大陸用語不列入，除非只剩它。
    """
    origins: dict[str, list[str]] = {}
    for c in candidates:
        for target in c.targets:
            listed = origins.setdefault(target, [])
            if c.origin not in listed:
                listed.append(c.origin)
    options = [(t, ORIGIN_SEPARATOR.join(o)) for t, o in origins.items()]
    taiwan = [o for o in options if not is_mainland(o[0])]
    return taiwan or options


def _join_options(options: list[tuple[str, str]]) -> str:
    return "；".join(f"{t}（{origin}）" for t, origin in options)


def split_choices(target: str) -> list[str]:
    """target 欄的譯名；依段落選的詞會有好幾個。"""
    return [t.strip() for t in target.split(CHOICE_SEPARATOR) if t.strip()]


def options_of(term: BookTerm) -> list[tuple[str, str]]:
    """這個詞所有的候選譯名：目前採用的排第一，其餘照 alternatives 欄。

    依段落選的詞，alternatives 也會列出 target 裡的譯名，用來保留它們出自哪個名詞庫。
    """
    listed: list[tuple[str, str]] = []
    for part in term.alternatives.split("；"):
        match = _OPTION.match(part.strip())
        if match:
            listed.append((match.group(1), match.group(2)))
    origins = dict(reversed(listed))
    options = [(t, origins.get(t, term.origin)) for t in split_choices(term.target)]
    for zh, origin in listed:
        if all(zh != t for t, _ in options):
            options.append((zh, origin))
    return options


def join_options(options: list[tuple[str, str]]) -> str:
    return _join_options(options)


def select_term(key: str, count: int, candidates: list[Candidate]) -> BookTerm | None:
    first = candidates[0]
    options = _options(candidates)
    primaries = {c.targets[0] for c in candidates}

    def term(target: str, status: str, origin: str = first.origin) -> BookTerm:
        # alternatives 列出採用的譯名以外的所有候選；待確認的詞沒有採用，全部列出
        alternatives = _join_options([o for o in options if o[0] != target])
        return BookTerm(first.source, target, status, count, origin, alternatives)

    if first.origin == MY_TERMS_ID:
        return term(first.targets[0], "")

    words = key.split(" ")
    if len(words) > 1 or "-" in key:
        if set(words) <= _FUNCTION_WORDS or words[0] in _ARTICLES:
            return None
        # 優先順序最前面、而且不是大陸用語的譯名
        target, origin = options[0]
        return term(target, STATUS_CONFLICT if len(primaries) > 1 else "", origin)

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
    tokens = extract_tokens(pdf)
    found = locate_terms([t.lower for t in tokens], lexicon)
    terms: list[BookTerm] = []
    for key, (count, start, length) in found.items():
        term = select_term(key, count, lexicon[key])
        if term is not None:
            term.page = tokens[start].page
            term.context = context_of(tokens, start, length)
            terms.append(term)
    sort_terms(terms)
    return terms


def sort_terms(terms: list[BookTerm]) -> None:
    """需要使用者看的排前面，再依出現次數。"""
    order = {STATUS_REVIEW: 0, STATUS_PER_PARAGRAPH: 1, STATUS_SUGGESTED: 2, STATUS_CONFLICT: 3}
    terms.sort(key=lambda t: (order.get(t.status, 4), -t.count, t.source.lower()))


def read_meta(pdf: Path) -> dict:
    """術語表的建立資訊：{"profile": 科目, "resolved": 用哪個模型判斷過上下文（沒判斷過是空的）}"""
    meta = _meta_path(pdf)
    return json.loads(meta.read_text(encoding="utf-8")) if meta.exists() else {}


def write_meta(pdf: Path, **values) -> None:
    meta = _meta_path(pdf)
    meta.parent.mkdir(parents=True, exist_ok=True)
    meta.write_text(json.dumps({**read_meta(pdf), **values}, ensure_ascii=False), encoding="utf-8")


def create_book_glossary(
    pdf: Path, profile: Profile, keep_user_choices: bool = False
) -> tuple[Path, list[BookTerm]]:
    """掃描 PDF 並寫出這本書的術語表；keep_user_choices 時保留使用者在 App 裡選過的譯名。"""
    terms = build_terms(pdf, build_lexicon(profile))
    path = book_path(pdf)
    if keep_user_choices and path.exists():
        chosen = {t.source.lower(): t for t in read_book(path) if t.origin == USER_ORIGIN}
        terms = [chosen.get(t.source.lower(), t) for t in terms]
    write_terms(path, terms)
    write_meta(pdf, profile=profile.id, resolved="")
    return path, terms


def ensure_book_glossary(pdf: Path, profile: Profile) -> tuple[Path, list[BookTerm], bool]:
    """沿用這本書的術語表；沒有、或是用別的科目建立的就重建。回傳 (路徑, 術語, 是否新建)。"""
    path = book_path(pdf)
    built_with = read_meta(pdf).get("profile")
    if path.exists() and built_with in (None, profile.id):
        return path, read_book(path), False
    path, terms = create_book_glossary(pdf, profile, keep_user_choices=True)
    return path, terms, True


def write_terms(path: Path, terms: list[BookTerm]) -> None:
    """寫成 UTF-8 BOM，Excel 打開中文才不會變亂碼。

    先寫暫存檔、完整寫好才取代，寫到一半出錯也不會把原本的術語表清空。
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + ".tmp")
    with temp.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(asdict(t) for t in terms)
    temp.replace(path)


def read_book(path: Path) -> list[BookTerm]:
    """讀回完整的術語表列（可能被 Excel 編輯過，缺的欄位用預設值）。"""
    names = {f.name for f in fields(BookTerm)}
    terms = []
    for row in csv.DictReader(decode_user_csv(path).splitlines()):
        values = {k: (v or "").strip() for k, v in row.items() if k in names}
        if not values.get("source"):
            continue
        values["count"] = int(values.get("count") or 0)
        values["page"] = int(values.get("page") or 0)
        terms.append(
            BookTerm(**{"target": "", "status": "", "origin": "", "alternatives": "", **values})
        )
    return terms


def apply_choices(path: Path, choices: dict[str, str]) -> int:
    """把使用者選的譯名寫回術語表（source → target），回傳更新幾個詞。"""
    terms = read_book(path)
    updated = 0
    for term in terms:
        target = choices.get(term.source)
        if target is None:
            continue
        options = options_of(term)
        picked = split_choices(target)
        term.alternatives = _join_options([o for o in options if o[0] not in picked])
        term.target, term.status, term.origin = target, "", USER_ORIGIN
        term.note = ""
        updated += 1
    write_terms(path, terms)
    return updated


def read_terms(path: Path) -> list[Term]:
    """讀回（可能被使用者編輯過的）術語表；target 空白的不使用。"""
    return read_user_csv(path)


def export_for_babeldoc(
    book: list[Term], my_terms: list[Term], path: Path, per_paragraph_path: Path
) -> tuple[int, int]:
    """合併成 BabelDOC 的 source,target CSV；my_terms 優先。

    target 有好幾個譯名（依段落選）的詞另外寫到 per_paragraph_path，譯名之間用「｜」。
    回傳（固定譯名的詞數、依段落選的詞數）。
    """
    merged: dict[str, Term] = {}
    for term in [*my_terms, *book]:
        merged.setdefault(term.key, term)
    fixed: list[tuple[str, str]] = []
    per_paragraph: list[tuple[str, str]] = []
    for term in merged.values():
        choices = split_choices(term.targets[0])
        if len(choices) > 1:
            per_paragraph.append((term.source, CHOICE_SEPARATOR.join(choices)))
        elif choices:
            fixed.append((term.source, choices[0]))
    for out, rows in ((path, fixed), (per_paragraph_path, per_paragraph)):
        with out.open("w", encoding="utf-8", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["source", "target"])
            writer.writerows(rows)
    return len(fixed), len(per_paragraph)
