"""下載 glossary/sources.toml 列出的名詞庫到 glossary/raw/。"""

from __future__ import annotations

import tomllib
import urllib.parse
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from textbook_tw.config import DATA_ROOT, PROJECT_ROOT

SOURCES_FILE = PROJECT_ROOT / "glossary" / "sources.toml"  # 隨程式發布
GLOSSARY_DIR = DATA_ROOT / "glossary"  # 會寫入：下載的名詞庫、各書術語表、my_terms.csv
RAW_DIR = GLOSSARY_DIR / "raw"


@dataclass(frozen=True)
class Source:
    id: str
    file: str
    tier: str
    url: str

    @property
    def path(self) -> Path:
        return RAW_DIR / self.file


def load_sources() -> list[Source]:
    with SOURCES_FILE.open("rb") as f:
        data = tomllib.load(f)
    base_url = data["naer"]["base_url"]
    return [
        Source(id=s["id"], file=s["file"], tier=s["tier"], url=base_url + s["file"])
        for s in data["source"]
    ]


def fetch(source: Source) -> Path:
    """下載單一名詞庫；先寫到暫存檔，完整下載後才改名，避免留下半個檔案。"""
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    url = urllib.parse.quote(source.url, safe=":/")
    partial = source.path.with_suffix(".part")
    with urllib.request.urlopen(url, timeout=120) as resp, partial.open("wb") as f:
        while chunk := resp.read(1 << 16):
            f.write(chunk)
    partial.replace(source.path)
    return source.path


def fetch_missing(
    sources: list[Source], force: bool = False, on_fetch: Callable[[Source], None] | None = None
) -> list[Path]:
    """下載還沒有的名詞庫（force=True 時全部重新下載），回傳所有名詞庫的路徑。"""
    for source in sources:
        if force or not source.path.exists():
            if on_fetch:
                on_fetch(source)
            fetch(source)
    return [s.path for s in sources]
