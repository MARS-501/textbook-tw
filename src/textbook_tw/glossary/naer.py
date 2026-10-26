"""解析國家教育研究院「學術名詞」CSV。

原始資料的寫法：
- 一個英文詞對多個中文譯名，用「；」「;」「，」「、」隔開，第一個是首選
- 中文裡的 [天]、【物】、{螺槳}、｛數學｝ 是領域標記或附註
- 中文括號在詞尾且兩字以上是註解（房室阻滯（心電圖）），其他是可省略的字（加速（度）梯度）
- 英文倒裝：acceleration; gravitational 代表 gravitational acceleration
- 英文括號是縮寫或註解：angle of attack (AOA)
"""

from __future__ import annotations

import csv
import re
from dataclasses import dataclass
from pathlib import Path

_TAG = re.compile(r"\[[^\]]*\]|【[^】]*】|\{[^}]*\}|｛[^｝]*｝")
_ZH_SEPARATORS = re.compile(r"[；;，,、]")
_PAREN = re.compile(r"[（(]([^）)]*)[）)]")
_EN_PAREN = re.compile(r"\s*[（(][^）)]*[）)]")
_SPACES = re.compile(r"\s+")


@dataclass(frozen=True)
class Term:
    source: str  # 英文原文（保留大小寫）
    targets: tuple[str, ...]  # 中文譯名，第一個是首選

    @property
    def key(self) -> str:
        return self.source.lower()


def _clean_target(text: str) -> str:
    text = text.strip()
    match = _PAREN.search(text)
    while match:
        inner = match.group(1)
        at_end = match.end() == len(text)
        if at_end and len(inner) >= 2:
            text = text[: match.start()]  # 詞尾註解：刪掉
        else:
            text = text[: match.start()] + inner + text[match.end() :]  # 可省略的字：保留
        text = text.strip()
        match = _PAREN.search(text)
    return text


def parse_targets(zh: str) -> tuple[str, ...]:
    """把中文欄位拆成譯名清單，去掉標記與註解。"""
    targets: list[str] = []
    for part in _ZH_SEPARATORS.split(_TAG.sub("", zh)):
        target = _clean_target(part)
        if target and target not in targets:
            targets.append(target)
    return tuple(targets)


def parse_source(en: str) -> str | None:
    """把英文欄位整理成文章裡會出現的寫法；無法判斷的寫法回傳 None。"""
    en = _EN_PAREN.sub("", en)
    parts = [p.strip() for p in re.split(r"[;；]", en) if p.strip()]
    if len(parts) == 2:
        en = f"{parts[1]} {parts[0]}"
    elif len(parts) != 1:
        return None
    en = _SPACES.sub(" ", en).strip()
    if not en or "/" in en or "," in en or "，" in en:
        return None
    return en


def read_csv(path: Path) -> list[Term]:
    terms: list[Term] = []
    with path.open(encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            source = parse_source(row.get("英文名稱") or "")
            targets = parse_targets(row.get("中文名稱") or "")
            if source and targets:
                terms.append(Term(source, targets))
    return terms


def read_mainland_names(path: Path) -> dict[str, str]:
    """兩岸對照名詞：大陸譯名 → 台灣首選譯名（之後用來抓大陸用語）。"""
    mapping: dict[str, str] = {}
    with path.open(encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            taiwan = parse_targets(row.get("中文名稱") or "")
            mainland = (row.get("中國大陸譯名") or "").strip()
            if taiwan and mainland and mainland not in taiwan:
                mapping[mainland] = taiwan[0]
    return mapping
