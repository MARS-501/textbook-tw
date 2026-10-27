"""給桌面 App 呼叫的指令。結果以 JSON 寫到標準輸出；翻譯時每行一個事件。

BabelDOC 有時會直接 print 除錯訊息，所以執行時把 sys.stdout 換成標準錯誤，
JSON 一律寫到保留下來的原始標準輸出，App 才不會讀到混雜的內容。
"""

from __future__ import annotations

import json
import sys
import threading
import traceback
from pathlib import Path
from typing import Any, TextIO

import pymupdf

from textbook_tw import pipeline
from textbook_tw.config import Settings, load_settings
from textbook_tw.glossary import book, resolve
from textbook_tw.glossary.lexicon import add_my_term
from textbook_tw.pages import parse_pages

RECENT_PARAGRAPHS = 3

_out: TextIO = sys.stdout
_lock = threading.Lock()


def _claim_stdout() -> None:
    global _out
    _out = sys.stdout
    _out.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    sys.stdout = sys.stderr


def emit(event: dict[str, Any]) -> None:
    with _lock:
        _out.write(json.dumps(event, ensure_ascii=False) + "\n")
        _out.flush()


# pick 的特殊值（與 app/src/bridge.ts 相同）
PICK_NONE = -1  # 還沒選
PICK_PER_PARAGRAPH = -2  # 依段落選（target 有好幾個譯名）
PICK_SKIP = -3  # 不套用

REVIEW_STATUSES = (
    book.STATUS_REVIEW,
    book.STATUS_PER_PARAGRAPH,
    book.STATUS_SUGGESTED,
    book.STATUS_SKIPPED,
    book.STATUS_CONFLICT,
)


def _review_item(term: book.BookTerm) -> dict[str, Any]:
    options = book.options_of(term)
    chosen = book.split_choices(term.target)
    if len(chosen) > 1:
        pick = PICK_PER_PARAGRAPH
    elif chosen:
        pick = 0
    else:
        pick = PICK_SKIP if term.status == book.STATUS_SKIPPED else PICK_NONE
    return {
        "source": term.source,
        "status": term.status,
        "count": term.count,
        "page": term.page,
        "context": term.context,
        "note": term.note,
        "options": [{"zh": zh, "src": src} for zh, src in options],
        "pick": pick,
        "paragraph": list(range(len(chosen))) if len(chosen) > 1 else [],
    }


def _review(pdf: Path, path: Path, terms: list[book.BookTerm], created: bool, profile: str):
    return {
        "path": str(path),
        "created": created,
        "profile": profile,
        "total": len(terms),
        "resolved": bool(book.read_meta(pdf).get("resolved")),
        "pending": sum(resolve.needs_judgement(t) for t in terms),
        "review": [_review_item(t) for t in terms if t.status in REVIEW_STATUSES],
    }


def glossary(pdf: Path, profile: str | None) -> int:
    """沿用或建立這本書的術語表，回傳需要使用者看一下的詞。"""
    _claim_stdout()
    pdf = pdf.resolve()
    settings = load_settings().with_overrides(profile=profile)
    path, terms, created = book.ensure_book_glossary(pdf, settings.profile)
    emit(_review(pdf, path, terms, created, settings.profile.id))
    return 0


def resolve_terms(pdf: Path, profile: str | None) -> int:
    """讓模型依上下文判斷術語譯名；每判斷完一批輸出進度，最後輸出新的確認清單。"""
    _claim_stdout()
    pdf = pdf.resolve()
    settings = load_settings().with_overrides(profile=profile)
    try:
        pipeline.check_model(settings)
        path, _, _ = book.ensure_book_glossary(pdf, settings.profile)
        terms = resolve.resolve_book(
            pdf,
            settings,
            on_progress=lambda done, total: emit(
                {"type": "progress", "done": done, "total": total}
            ),
        )
    except (pipeline.SetupError, resolve.ResolveError) as e:
        emit({"type": "error", "message": str(e)})
        return 1
    emit({"type": "done", **_review(pdf, path, terms, False, settings.profile.id)})
    return 0


def apply(pdf: Path) -> int:
    """從標準輸入讀 {"choices": {英文: 譯名}, "my_terms": [[英文, 譯名], ...]} 並寫入。"""
    _claim_stdout()
    # 不依賴系統編碼（Windows 預設是 cp950），一律當 UTF-8 讀
    payload = json.loads(sys.stdin.buffer.read().decode("utf-8"))
    choices: dict[str, str] = payload.get("choices") or {}
    updated = book.apply_choices(book.book_path(pdf), choices) if choices else 0
    my_terms = payload.get("my_terms") or []
    for source, target in my_terms:
        add_my_term(source, target)
    emit({"updated": updated, "my_terms": len(my_terms)})
    return 0


def translate(pdf: Path, settings: Settings, pages: str | None, out_dir: Path | None) -> int:
    _claim_stdout()
    pdf = pdf.resolve()
    try:
        with pymupdf.open(pdf) as doc:
            indices = parse_pages(pages, doc.page_count)
        emit({"type": "start", "pages": [i + 1 for i in indices]})

        fallbacks = 0

        def on_fallback() -> None:
            nonlocal fallbacks
            fallbacks += 1
            emit({"type": "fallback", "count": fallbacks})

        outputs = pipeline.translate(
            pdf,
            settings,
            pages=pages,
            out_dir=out_dir,
            on_message=lambda text: emit({"type": "message", "text": text}),
            on_progress=lambda stage, percent, current, total: emit(
                {
                    "type": "progress",
                    "stage": stage,
                    "percent": percent,
                    "current": current,
                    "total": total,
                }
            ),
            on_batch=lambda pairs: emit(
                {
                    "type": "paragraphs",
                    "items": [{"en": en, "zh": zh} for en, zh in pairs[-RECENT_PARAGRAPHS:]],
                }
            ),
            on_fallback=on_fallback,
            # App 在術語確認畫面已經讓模型判斷過（或使用者選擇略過）
            resolve_terms=False,
        )
    except (pipeline.SetupError, ValueError) as e:
        emit({"type": "error", "message": str(e)})
        return 1
    except Exception as e:  # noqa: BLE001 — App 要拿到錯誤說明，細節寫到標準錯誤
        traceback.print_exc()
        emit({"type": "error", "message": f"翻譯失敗：{e}"})
        return 1

    files = [
        {"kind": kind, "path": str(path), "size": path.stat().st_size}
        for kind, path in (
            ("side_by_side", outputs.side_by_side),
            ("alternating", outputs.alternating),
            ("mono", outputs.mono),
        )
        if path
    ]
    emit(
        {
            "type": "done",
            "seconds": outputs.seconds,
            "pages": outputs.pages,
            "fallbacks": fallbacks,
            "outputs": files,
            "per_paragraph": [
                {"source": source, "counts": counts}
                for source, counts in sorted(outputs.choice_usage.items())
            ],
        }
    )
    return 0
