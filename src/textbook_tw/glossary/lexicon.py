"""依科目設定的優先順序合併名詞庫。"""

from __future__ import annotations

import csv
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

from textbook_tw.config import Profile
from textbook_tw.glossary import naer
from textbook_tw.glossary.fetch import GLOSSARY_DIR, fetch_missing, load_sources
from textbook_tw.glossary.naer import Term

MY_TERMS_ID = "my_terms"
MY_TERMS_FILE = GLOSSARY_DIR / "my_terms.csv"


@dataclass(frozen=True)
class Candidate:
    origin: str  # 名詞庫 id（sources.toml 的 id 或 my_terms）
    source: str  # 英文原文
    targets: tuple[str, ...]  # 中文譯名，第一個是首選


class Lexicon:
    """英文詞（小寫）→ 各名詞庫的譯名，依科目優先順序排列。"""

    def __init__(self, entries: dict[str, list[Candidate]]):
        self._entries = entries
        self.max_words = max((len(k.split()) for k in entries), default=1)

    def __contains__(self, key: str) -> bool:
        return key in self._entries

    def __getitem__(self, key: str) -> list[Candidate]:
        return self._entries[key]

    def __len__(self) -> int:
        return len(self._entries)


def read_user_csv(path: Path) -> list[Term]:
    """讀取使用者自己編輯的 source,target CSV；Excel 存檔可能是 UTF-8 或 Big5。"""
    if not path.exists():
        return []
    data = path.read_bytes()
    for encoding in ("utf-8-sig", "cp950"):
        try:
            text = data.decode(encoding)
            break
        except UnicodeDecodeError:
            continue
    else:
        raise ValueError(f"{path} 的編碼無法辨識，請另存成 UTF-8 CSV")
    terms = []
    for row in csv.DictReader(text.splitlines()):
        source = (row.get("source") or "").strip()
        target = (row.get("target") or "").strip()
        if source and target:
            terms.append(Term(source, (target,)))
    return terms


def read_my_terms() -> list[Term]:
    return read_user_csv(MY_TERMS_FILE)


def build_lexicon(profile: Profile) -> Lexicon:
    """讀取科目設定列出的名詞庫（缺少的會先下載）並依優先順序合併。"""
    sources = {s.id: s for s in load_sources()}
    unknown = [g for g in profile.glossaries if g != MY_TERMS_ID and g not in sources]
    if unknown:
        raise ValueError(f"科目設定 {profile.id} 的名詞庫 {', '.join(unknown)} 不在 sources.toml")
    fetch_missing([sources[g] for g in profile.glossaries if g in sources])

    entries: dict[str, list[Candidate]] = defaultdict(list)
    for glossary_id in profile.glossaries:
        if glossary_id == MY_TERMS_ID:
            terms = read_my_terms()
        else:
            terms = naer.read_csv(sources[glossary_id].path)
        seen: set[str] = set()
        for term in terms:
            if term.key in seen:  # 同一個名詞庫重複的詞只取第一筆
                continue
            seen.add(term.key)
            entries[term.key].append(Candidate(glossary_id, term.source, term.targets))
    return Lexicon(dict(entries))
