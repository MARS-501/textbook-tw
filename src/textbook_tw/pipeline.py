"""一個翻譯任務的完整流程：檢查模型 → BabelDOC 翻譯 → 整理檔名 → 組對照版。"""

from __future__ import annotations

import json
import shutil
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path

import pymupdf

from textbook_tw.compose import dual
from textbook_tw.config import Settings
from textbook_tw.engine import babeldoc_runner
from textbook_tw.engine.babeldoc_runner import ProgressCallback
from textbook_tw.pages import format_pages, parse_pages


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

    raw_mono = babeldoc_runner.translate_pdf(
        input_pdf,
        settings,
        work_dir,
        pages=babeldoc_pages,
        font_family=font_family,
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
