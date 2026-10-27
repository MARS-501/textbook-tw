"""依文件上下文挑術語譯名。

一份論文或課本常常跨好幾個領域（複合材料論文裡有材料、力學、統計用語），
只靠科目設定的名詞庫優先順序會選錯（confidence level 被航太名詞庫譯成「信任度」）。
這裡把需要判斷的詞連同它在文中的幾段原文、各名詞庫的候選譯名交給本地模型，讓模型挑：

- 選一個譯名 → 狀態「模型建議」，note 寫理由
- 都不合適，或這裡只是一般英文 → 「不套用」，翻譯時由模型自行處理
- 文中確實有不同意思 → 「依段落」，target 列出幾個譯名，翻譯時每段挑一個

需要判斷的詞：名詞庫譯名不一致的，以及每個字都很常見的詞組（first stage、key factor，
名詞庫雖然有，但在文中多半只是一般說法）。使用者自己選過的、my_terms 裡的不動。
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from collections.abc import Callable
from pathlib import Path

import pymupdf
from wordfreq import zipf_frequency

from textbook_tw.config import Settings
from textbook_tw.glossary import book
from textbook_tw.glossary.lexicon import MY_TERMS_ID

BATCH_SIZE = 8  # 一次問幾個詞；小模型一次太多容易漏答
MAX_EXCERPTS = 3
EXCERPT_WORDS = 12  # 原文片段：術語前後各取幾個字
COMMON_PHRASE_ZIPF = 4.5  # 詞組裡每個字都比這常見時，可能只是一般說法
MAX_OPTIONS = 8
OPENING_WORDS = 80

ProgressCallback = Callable[[int, int], None]  # (已判斷幾個詞, 共幾個詞)

_RESOLVED = {book.STATUS_SUGGESTED, book.STATUS_PER_PARAGRAPH, book.STATUS_SKIPPED}

SYSTEM_PROMPT = """\
You are an expert in English to Taiwan Traditional Chinese academic terminology \
(國家教育研究院學術名詞). You decide how technical terms should be translated in one specific \
document, based on how the document actually uses them."""

USER_PROMPT = """\
Document title: {title}
Opening text: {opening}

For each item below, read how the term is used in the excerpts from this document, then pick \
the Chinese translation that fits that meaning. Each option shows, in parentheses, the field of \
the glossary it comes from.

How to choose:
1. Work out what the term means in the excerpts, then prefer an option from the field that \
matches that meaning, even if the document as a whole is about something else. Statistics \
(standard deviation, confidence level, analysis of variance, mean value) → 統計學 or 數學. \
Material properties, testing and processing → 金屬材料, 高分子材料, 陶瓷材料 or 力學. \
Structures and loads → 力學, 航空太空 or 土木工程.
2. Use Taiwan usage. Never pick mainland China wording (方差, 置信, 水平 for "level", 模量, \
數據, 信息, 質量 for "quality") when another option exists.
3. Pick what a Taiwan engineering professor would write in a textbook. Reject translations from \
an unrelated sense of the word (e.g. "cell" in a battery paper is 電池, never 細胞).

Answer:
- "choice": the number of the best option.
- "choice": 0 when no option fits the meaning here, or when the words are just ordinary English \
in this document rather than a technical term (the translator will then translate them freely).
- "choice": -1 only when the excerpts clearly use the term with different meanings that need \
different translations; then put those option numbers in "per_paragraph".
- "reason": one short phrase in Traditional Chinese (at most 20 characters) explaining the \
choice, e.g. 本文指複合材料的疊層結構.

Items:
{items}"""

RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "items": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "id": {"type": "integer"},
                    "choice": {"type": "integer"},
                    "per_paragraph": {"type": "array", "items": {"type": "integer"}},
                    "reason": {"type": "string"},
                },
                "required": ["id", "choice", "reason"],
            },
        }
    },
    "required": ["items"],
}


class ResolveError(RuntimeError):
    pass


def needs_judgement(term: book.BookTerm, force: bool = False) -> bool:
    if term.origin in (book.USER_ORIGIN, MY_TERMS_ID):
        return False
    if term.status in (book.STATUS_REVIEW, book.STATUS_CONFLICT):
        return True
    if term.status in _RESOLVED:
        return force
    words = term.source.lower().replace("-", " ").split()
    return len(words) > 1 and min(zipf_frequency(w, "en") for w in words) >= COMMON_PHRASE_ZIPF


def describe_document(pdf: Path) -> tuple[str, str]:
    """（標題, 開頭文字）讓模型知道這份文件在講什麼。"""
    with pymupdf.open(pdf) as doc:
        title = (doc.metadata or {}).get("title", "").strip()
        first = doc[0].get_text() if doc.page_count else ""
    words = first.split()
    if not title:
        title = " ".join(words[:15])
    return title, " ".join(words[:OPENING_WORDS])


def collect_excerpts(pdf: Path, terms: list[book.BookTerm]) -> dict[str, list[str]]:
    """每個詞在文中的幾段原文，盡量取自不同頁。"""
    tokens = book.extract_tokens(pdf)
    keys = {t.source.lower() for t in terms}
    found = book.occurrences([t.lower for t in tokens], keys)
    excerpts: dict[str, list[str]] = {}
    for key, positions in found.items():
        length = len(key.split(" "))
        per_page: dict[int, int] = {}
        for i in positions:
            per_page.setdefault(tokens[i].page, i)
        pool = list(per_page.values()) if len(per_page) >= MAX_EXCERPTS else positions
        # 平均分散取樣，看到文件前後不同處的用法
        last = len(pool) - 1
        chosen = sorted(
            {pool[round(k * last / max(1, MAX_EXCERPTS - 1))] for k in range(MAX_EXCERPTS)}
        )
        excerpts[key] = [book.context_of(tokens, i, length, EXCERPT_WORDS) for i in chosen]
    return excerpts


def build_items(
    terms: list[book.BookTerm], excerpts: dict[str, list[str]]
) -> list[tuple[book.BookTerm, list[tuple[str, str]], dict]]:
    """（術語, 候選譯名, 給模型看的內容）"""
    items = []
    for term in terms:
        options = book.options_of(term)
        options = [o for o in options if not book.is_mainland(o[0])] or options
        # 越多名詞庫採用的譯名排越前面；一樣多時維持科目優先順序
        options.sort(key=lambda o: -len(o[1].split(book.ORIGIN_SEPARATOR)))
        options = options[:MAX_OPTIONS]
        if not options:
            continue
        payload = {
            "id": len(items) + 1,
            "term": term.source,
            "excerpts": excerpts.get(term.source.lower(), [term.context])[:MAX_EXCERPTS],
            "options": {str(i): f"{zh}（{src}）" for i, (zh, src) in enumerate(options, 1)},
        }
        items.append((term, options, payload))
    return items


def _ollama_root(settings: Settings) -> str:
    return settings.base_url.rstrip("/").removesuffix("/v1")


def ask_model(settings: Settings, title: str, opening: str, payloads: list[dict]) -> list[dict]:
    """問一批詞，回傳模型的答案 [{"id", "choice", "per_paragraph", "reason"}, ...]。"""
    prompt = USER_PROMPT.format(
        title=title,
        opening=opening,
        items=json.dumps(payloads, ensure_ascii=False, indent=1),
    )
    body = {
        "model": settings.model,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
        "stream": False,
        "think": False,  # Qwen3.5 開思考模式會慢很多
        "format": RESPONSE_SCHEMA,
        "options": {"temperature": 0},
    }
    request = urllib.request.Request(
        _ollama_root(settings) + "/api/chat",
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=300) as resp:
            content = json.load(resp)["message"]["content"]
    except (urllib.error.URLError, TimeoutError) as e:
        raise ResolveError(f"連不到 Ollama（{settings.base_url}）") from e
    try:
        answers = json.loads(content)["items"]
    except (ValueError, KeyError, TypeError):
        return []
    return [a for a in answers if isinstance(a, dict)]


def apply_answer(term: book.BookTerm, options: list[tuple[str, str]], answer: dict) -> bool:
    """把模型的答案寫進術語；答案看不懂時不動，回傳是否有更新。"""
    reason = str(answer.get("reason") or "").strip()[:40]
    choice = answer.get("choice")
    if not isinstance(choice, int):
        return False
    if 1 <= choice <= len(options):
        zh, origin = options[choice - 1]
        term.target, term.origin, term.status = zh, origin, book.STATUS_SUGGESTED
        term.alternatives = book.join_options([o for o in options if o[0] != zh])
    elif choice == 0:
        term.target, term.status = "", book.STATUS_SKIPPED
        term.alternatives = book.join_options(options)
    elif choice == -1:
        numbers = [n for n in answer.get("per_paragraph") or [] if isinstance(n, int)]
        picked = list(dict.fromkeys(options[n - 1] for n in numbers if 1 <= n <= len(options)))
        if len(picked) == 1:  # 只剩一個就當作選了它
            return apply_answer(term, options, {**answer, "choice": options.index(picked[0]) + 1})
        if not picked:  # 小模型有時用 -1 表示「都不合適」
            return apply_answer(term, options, {**answer, "choice": 0})
        term.target = book.CHOICE_SEPARATOR.join(zh for zh, _ in picked)
        term.origin, term.status = "", book.STATUS_PER_PARAGRAPH
        # 全部候選都留在 alternatives，才知道每個譯名出自哪個名詞庫
        term.alternatives = book.join_options(picked + [o for o in options if o not in picked])
    else:
        return False
    term.note = reason
    return True


def resolve_book(
    pdf: Path,
    settings: Settings,
    on_progress: ProgressCallback | None = None,
    force: bool = False,
) -> list[book.BookTerm]:
    """讓模型判斷這本書術語表裡需要判斷的詞，寫回術語表並回傳全部術語。

    force 時連已經判斷過的也重新判斷（使用者自己選的仍然不動）。
    """
    path = book.book_path(pdf)
    terms = book.read_book(path)
    pending = [t for t in terms if needs_judgement(t, force)]
    items = build_items(pending, collect_excerpts(pdf, pending)) if pending else []
    title, opening = describe_document(pdf)
    total = len(items)
    if on_progress:
        on_progress(0, total)
    for start in range(0, total, BATCH_SIZE):
        batch = items[start : start + BATCH_SIZE]
        payloads = [dict(payload, id=i) for i, (_, _, payload) in enumerate(batch, 1)]
        answers = {a.get("id"): a for a in ask_model(settings, title, opening, payloads)}
        for i, (term, options, _) in enumerate(batch, 1):
            if i in answers:
                apply_answer(term, options, answers[i])
        book.write_terms(path, terms)  # 每批都存，中斷也不會白做
        if on_progress:
            on_progress(min(start + BATCH_SIZE, total), total)
    book.sort_terms(terms)
    book.write_terms(path, terms)
    book.write_meta(pdf, resolved=settings.model)
    return terms
