"""一個翻譯任務的完整流程：檢查模型 → 術語表 → BabelDOC 翻譯 → 整理檔名 → 組對照版。"""

from __future__ import annotations

import gc
import json
import shutil
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import pymupdf

from textbook_tw.compose import dual, optimize
from textbook_tw.config import PROJECT_ROOT, Settings
from textbook_tw.engine import babeldoc_runner
from textbook_tw.engine.babeldoc_runner import BatchCallback, ProgressCallback
from textbook_tw.glossary import book, resolve
from textbook_tw.glossary.lexicon import read_my_terms
from textbook_tw.pages import format_pages, parse_pages

MessageCallback = Callable[[str], None]
RESOLVE_STAGE = "Resolve Terms"  # 進度回報用的階段名稱（模型依上下文判斷術語）


class SetupError(RuntimeError):
    """環境沒準備好（Ollama 沒開、模型沒下載），使用者可以自己處理的錯誤。"""


@dataclass
class Outputs:
    mono: Path | None
    side_by_side: Path | None
    alternating: Path | None
    seconds: float
    pages: list[int]  # 翻了哪些頁（1 起算）
    # 依段落選譯名的詞實際用了哪些譯名：{英文（小寫）: {譯名: 段落數}}
    choice_usage: dict[str, dict[str, int]]


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


@dataclass
class GlossaryFiles:
    fixed: Path  # 固定譯名
    per_paragraph: Path  # 依段落選譯名
    choices: dict[str, list[str]]  # 依段落選的詞（小寫英文）→ 候選譯名，翻完統計用


def prepare_glossary(
    input_pdf: Path,
    settings: Settings,
    work_dir: Path,
    on_message: MessageCallback,
    resolve_terms: bool = True,
    on_progress: ProgressCallback | None = None,
) -> GlossaryFiles:
    """沿用這本書的術語表（沒有、或科目不同就掃描建立），合併 my_terms 後輸出給 BabelDOC。

    resolve_terms 時，還沒讓模型判斷過上下文的術語表會先判斷（App 在術語確認畫面就做了）。
    """
    path, terms, created = book.ensure_book_glossary(input_pdf, settings.profile)
    on_message(("已建立" if created else "使用") + describe_book_glossary(path, terms))
    if resolve_terms and not book.read_meta(input_pdf).get("resolved"):
        on_message("依文件上下文判斷術語譯名…")

        def report(done: int, total: int) -> None:
            if on_progress:
                on_progress(RESOLVE_STAGE, 0.0, done, total)

        terms = resolve.resolve_book(input_pdf, settings, on_progress=report)
        suggested = sum(t.status == book.STATUS_SUGGESTED for t in terms)
        on_message(f"模型依上下文選了 {suggested} 個術語的譯名（可在術語表檢查）")

    fixed = work_dir / "terms.csv"
    per_paragraph = work_dir / "per_paragraph.csv"
    book_terms = book.read_terms(path)
    count, flexible = book.export_for_babeldoc(book_terms, read_my_terms(), fixed, per_paragraph)
    on_message(f"本次使用 {count} 個術語（含 my_terms.csv），{flexible} 個依段落選譯名")
    choices = {
        t.key: book.split_choices(t.targets[0])
        for t in book_terms
        if len(book.split_choices(t.targets[0])) > 1
    }
    return GlossaryFiles(fixed, per_paragraph, choices)


def count_choices(
    choices: dict[str, list[str]], pairs: list[tuple[str, str]], counts: dict[str, dict[str, int]]
) -> None:
    """依段落選的詞，每段實際用了哪個譯名。"""
    for en, zh in pairs:
        lower = en.lower()
        for key, options in choices.items():
            if key in lower:
                for option in options:
                    if option in zh:
                        counts.setdefault(key, {}).setdefault(option, 0)
                        counts[key][option] += 1


def _remove_work_dir(path: Path) -> None:
    """BabelDOC 有些 PDF 沒有關閉就結束，Windows 上檔案會被鎖住；先回收再重試。"""
    for _ in range(3):
        shutil.rmtree(path, ignore_errors=True)
        if not path.exists():
            return
        gc.collect()
        time.sleep(0.5)


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
    on_batch: BatchCallback | None = None,
    on_fallback: Callable[[], None] | None = None,
    out_dir: Path | None = None,
    resolve_terms: bool = True,
) -> Outputs:
    """翻譯一份 PDF。out_dir 是輸出檔所在的資料夾；預設為設定的 output 底下的 <檔名>/。

    resolve_terms：術語表還沒讓模型判斷過上下文時，翻譯前先判斷。
    """
    started = time.perf_counter()
    input_pdf = input_pdf.resolve()
    check_model(settings)

    with pymupdf.open(input_pdf) as doc:
        page_indices = parse_pages(pages, doc.page_count)
        font_family = _resolve_font(settings.font, doc)
    babeldoc_pages = format_pages(page_indices) if pages else None

    stem = input_pdf.stem
    out_dir = out_dir or settings.output_dir / stem
    work_dir = out_dir / ".work"
    work_dir.mkdir(parents=True, exist_ok=True)
    # 只翻部分頁面時檔名加上頁碼，避免蓋掉整份的結果
    prefix = f"{stem}.p{babeldoc_pages}" if babeldoc_pages else stem

    glossary = (
        prepare_glossary(input_pdf, settings, work_dir, on_message, resolve_terms, on_progress)
        if settings.glossary
        else None
    )
    usage: dict[str, dict[str, int]] = {}

    def observe(pairs: list[tuple[str, str]]) -> None:
        if glossary and glossary.choices:
            count_choices(glossary.choices, pairs, usage)
        if on_batch:
            on_batch(pairs)

    raw_mono = babeldoc_runner.translate_pdf(
        input_pdf,
        settings,
        work_dir,
        pages=babeldoc_pages,
        font_family=font_family,
        glossary_csv=glossary.fixed if glossary else None,
        on_progress=on_progress,
        on_batch=observe,
        on_fallback=on_fallback,
        per_paragraph_csv=glossary.per_paragraph if glossary else None,
    )
    mono = out_dir / f"{prefix}.譯文.pdf"
    raw_mono.replace(mono)
    # BabelDOC 逐字輸出，閱讀器開起來很卡；先合併，對照版也跟著受益
    optimize.optimize_pdf(mono, prune=bool(pages))

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
    _remove_work_dir(work_dir)

    pages_done = [i + 1 for i in page_indices]
    return Outputs(
        mono, side_by_side, alternating, time.perf_counter() - started, pages_done, usage
    )
