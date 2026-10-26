"""一個翻譯任務的完整流程：檢查模型 → 術語表 → BabelDOC 翻譯 → 整理檔名 → 組對照版。"""

from __future__ import annotations

import json
import shutil
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import pymupdf

from textbook_tw.compose import dual
from textbook_tw.config import PROJECT_ROOT, Settings
from textbook_tw.engine import babeldoc_runner
from textbook_tw.engine.babeldoc_runner import ProgressCallback
from textbook_tw.glossary import book
from textbook_tw.glossary.lexicon import read_my_terms
from textbook_tw.pages import format_pages, parse_pages

MessageCallback = Callable[[str], None]


class SetupError(RuntimeError):
    """環境沒準備好（Ollama 沒開、模型沒下載），使用者可以自己處理的錯誤。"""


@dataclass
class Outputs:
    mono: Path | None
    side_by_side: Path | None
    alternating: Path | None
    seconds: float


def check_model(settings: Settings) -> None:
    """確認 Ollama 有在執行，而且設定的模型已經下載。"""
    try:
        with urllib.request.urlopen(settings.base_url.rstrip("/") + "/models", timeout=5) as resp:
            models = {m["id"] for m in json.load(resp)["data"]}
    except (urllib.error.URLError, TimeoutError) as e:
        raise SetupError(f"連不到 Ollama（{settings.base_url}）。請先開啟 Ollama 再試一次。") from e
    if settings.model not in models:
        raise SetupError(
            f"Ollama 裡沒有模型 {settings.model}。請先執行：ollama pull {settings.model}"
        )


def display_path(path: Path) -> str:
    try:
        return str(path.relative_to(PROJECT_ROOT))
    except ValueError:
        return str(path)


def describe_book_glossary(path: Path, terms: list[book.BookTerm]) -> str:
    review = sum(t.status == book.STATUS_REVIEW for t in terms)
    return (
        f"術語表 {display_path(path)}：{len(terms)} 個詞，其中 {review} 個待確認（可用 Excel 編輯）"
    )


def prepare_glossary(
    input_pdf: Path, settings: Settings, work_dir: Path, on_message: MessageCallback
) -> Path:
    """沿用這本書的術語表（沒有就掃描建立），合併 my_terms 後輸出給 BabelDOC。"""
    path = book.book_path(input_pdf)
    if path.exists():
        on_message(f"使用術語表 {display_path(path)}")
    else:
        on_message("掃描全文、建立術語表…")
        path, terms = book.create_book_glossary(input_pdf, settings.profile)
        on_message("已建立" + describe_book_glossary(path, terms))

    export = work_dir / "terms.csv"
    count = book.export_for_babeldoc(book.read_terms(path), read_my_terms(), export)
    on_message(f"本次使用 {count} 個術語（含 my_terms.csv）")
    return export


def _resolve_font(font: str, doc: pymupdf.Document) -> str | None:
    """auto：投影片（第一頁是橫向）用黑體，其他交給 BabelDOC 依原文判斷。"""
    if font != "auto":
        return font
    first = doc[0].rect
    return "sans-serif" if first.width > first.height else None


def translate(
    input_pdf: Path,
    settings: Settings,
    pages: str | None = None,
    on_progress: ProgressCallback | None = None,
    on_message: MessageCallback = lambda _message: None,
) -> Outputs:
    started = time.perf_counter()
    input_pdf = input_pdf.resolve()
    check_model(settings)

    with pymupdf.open(input_pdf) as doc:
        page_indices = parse_pages(pages, doc.page_count)
        font_family = _resolve_font(settings.font, doc)
    babeldoc_pages = format_pages(page_indices) if pages else None

    stem = input_pdf.stem
    out_dir = settings.output_dir / stem
    work_dir = out_dir / ".work"
    work_dir.mkdir(parents=True, exist_ok=True)
    # 只翻部分頁面時檔名加上頁碼，避免蓋掉整份的結果
    prefix = f"{stem}.p{babeldoc_pages}" if babeldoc_pages else stem

    glossary_csv = (
        prepare_glossary(input_pdf, settings, work_dir, on_message) if settings.glossary else None
    )
    raw_mono = babeldoc_runner.translate_pdf(
        input_pdf,
        settings,
        work_dir,
        pages=babeldoc_pages,
        font_family=font_family,
        glossary_csv=glossary_csv,
        on_progress=on_progress,
    )
    mono = out_dir / f"{prefix}.譯文.pdf"
    raw_mono.replace(mono)

    side_by_side = alternating = None
    if settings.dual in ("side_by_side", "both"):
        side_by_side = out_dir / f"{prefix}.對照-並排.pdf"
        dual.side_by_side(input_pdf, mono, side_by_side, page_indices, settings.translated_first)
    if settings.dual in ("alternating", "both"):
        alternating = out_dir / f"{prefix}.對照-交替.pdf"
        dual.alternating(input_pdf, mono, alternating, page_indices, settings.translated_first)

    if not settings.mono:
        mono.unlink()
        mono = None
    # 成功才清掉 BabelDOC 的中間檔；失敗時留著方便除錯
    shutil.rmtree(work_dir, ignore_errors=True)

    return Outputs(mono, side_by_side, alternating, time.perf_counter() - started)
