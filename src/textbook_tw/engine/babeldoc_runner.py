"""唯一直接呼叫 BabelDOC 的地方。

BabelDOC 官方表示它的 API 都屬於內部 API，所以版本鎖定在 pyproject.toml，
升級時只需要修改這個檔案。
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from collections.abc import Callable
from pathlib import Path

import babeldoc.format.pdf.high_level as high_level
from babeldoc.docvision.doclayout import DocLayoutModel
from babeldoc.format.pdf.translation_config import TranslationConfig, WatermarkOutputMode
from babeldoc.glossary import Glossary
from babeldoc.translator.translator import OpenAITranslator, set_translate_rate_limiter

from textbook_tw.config import Settings

logger = logging.getLogger(__name__)

# (階段名稱, 整體進度 0～100, 這個階段完成幾項, 這個階段共幾項)
ProgressCallback = Callable[[str, float, int, int], None]
# 剛翻好的一批段落：[(原文, 譯文), ...]，已去掉 BabelDOC 的公式佔位符號與樣式標籤
BatchCallback = Callable[[list[tuple[str, str]]], None]

TRANSLATE_STAGE = "Translate Paragraphs"

_INPUT_MARKER = "## Here is the input:"
_MARKUP = re.compile(r"</?style[^>]*>|\{v?\d+\}")
_FALLBACK_LOGGER = "babeldoc.format.pdf.document_il.midend.il_translator_llm_only"

# 同時送給模型的請求數；本地模型一次處理一批，太多只會排隊
QPS = 4

# 放在 BabelDOC 指令範本最前面的角色說明（範本其餘部分是 BabelDOC 的格式規則）
SYSTEM_PROMPT = """\
You are a professional translator of English university engineering course materials \
({description}). Translate into Traditional Chinese as used in Taiwan (zh-TW).
- Use the standard academic terminology of Taiwan (National Academy for Educational Research), \
never Simplified Chinese characters and never mainland China terms \
(e.g. 紊流 not 湍流, 無因次 not 無量綱, 軟體 not 軟件).
- Keep mathematical symbols, variable names, units, equation numbers, figure/table numbers \
and citations unchanged.
- Names of people, universities, departments, companies and organizations: copy them exactly \
as written in English. Never guess a Chinese name for them.
- Text that is already Chinese stays as it is."""


class TranslationError(RuntimeError):
    pass


def _plain(text: str) -> str:
    return " ".join(_MARKUP.sub("", text).split())


def parse_batch(prompt: str, output: str) -> list[tuple[str, str]]:
    """從 BabelDOC 送出的指令與模型回傳的 JSON，配對出每一段的原文與譯文。"""
    try:
        inputs = json.loads(prompt.split(_INPUT_MARKER, 1)[1])
        cleaned = output.strip().removeprefix("```json").removeprefix("```").removesuffix("```")
        outputs = {item["id"]: item["output"] for item in json.loads(cleaned)}
    except (IndexError, ValueError, KeyError, TypeError):
        return []
    return [
        (_plain(item["input"]), _plain(outputs[item["id"]]))
        for item in inputs
        if item.get("id") in outputs and _plain(item.get("input", ""))
    ]


# 依段落選譯名的術語另外放一份術語表，BabelDOC 會把它列成「### Glossary: <名稱>」
PER_PARAGRAPH_GLOSSARY = "per_paragraph"
_PER_PARAGRAPH_HEADER = f"### Glossary: {PER_PARAGRAPH_GLOSSARY}"
_PER_PARAGRAPH_NOTE = """\
### Terms with several possible translations

These terms are used with different meanings in different parts of this document. \
For each paragraph, use exactly ONE of the listed translations: the one that fits what the \
term means in that paragraph. Never write more than one of them."""
_PER_PARAGRAPH_ROW = re.compile(r"^\| (.+?) \| (.+?｜.+?) \|$", re.M)


def rewrite_prompt(prompt: str) -> str:
    """BabelDOC 的指令要求「一律使用術語表譯名」；依段落選的術語改寫成「從這幾個挑一個」。"""
    if _PER_PARAGRAPH_HEADER not in prompt:
        return prompt
    prompt = prompt.replace(_PER_PARAGRAPH_HEADER, _PER_PARAGRAPH_NOTE)
    return _PER_PARAGRAPH_ROW.sub(
        lambda m: f"| {m.group(1)} | {' or '.join(m.group(2).split('｜'))} |", prompt
    )


class _ObservedTranslator(OpenAITranslator):
    """每翻好一批就回報，讓介面能顯示「剛翻好的段落」；並改寫依段落選譯名的術語。"""

    on_batch: BatchCallback | None = None

    def llm_translate(self, text, ignore_cache=False, rate_limit_params=None):
        # 在這裡回報（而不是 do_llm_translate），用到快取的段落也算得到
        result = super().llm_translate(text, ignore_cache, rate_limit_params)
        if self.on_batch and text and result:
            pairs = parse_batch(text, result)
            if pairs:
                self.on_batch(pairs)
        return result

    def do_llm_translate(self, text, rate_limit_params=None):
        return super().do_llm_translate(rewrite_prompt(text) if text else text, rate_limit_params)

    def do_translate(self, text, rate_limit_params=None):
        # 格式出錯改逐段重翻時走這裡，指令裡一樣有術語表
        return super().do_translate(rewrite_prompt(text) if text else text, rate_limit_params)


class _FallbackCounter(logging.Handler):
    """BabelDOC 在模型回傳格式不對時會逐段改用簡單指令重翻（不帶術語表），只會寫在紀錄裡。"""

    def __init__(self, on_fallback: Callable[[], None]):
        super().__init__(logging.WARNING)
        self.on_fallback = on_fallback

    def emit(self, record: logging.LogRecord) -> None:
        if "Fallback to simple translation" in record.getMessage():
            self.on_fallback()


_layout_model: DocLayoutModel | None = None


def _get_layout_model() -> DocLayoutModel:
    """版面辨識模型載入一次後重複使用（第一次會下載模型與字型）。"""
    global _layout_model
    if _layout_model is None:
        high_level.init()
        _layout_model = DocLayoutModel.load_onnx()
    return _layout_model


def translate_pdf(
    input_pdf: Path,
    settings: Settings,
    work_dir: Path,
    pages: str | None = None,
    font_family: str | None = None,
    glossary_csv: Path | None = None,
    on_progress: ProgressCallback | None = None,
    on_batch: BatchCallback | None = None,
    on_fallback: Callable[[], None] | None = None,
    per_paragraph_csv: Path | None = None,
) -> Path:
    """翻譯 input_pdf，回傳純譯文 PDF 的路徑。

    指定 pages 時，輸出只包含被翻譯的那些頁面，順序與原文相同。
    font_family 為 "serif"、"sans-serif" 或 None（由 BabelDOC 依原文判斷）。
    glossary_csv 是 source,target 格式的術語表；BabelDOC 會把每批文字裡出現的術語附在指令中。
    per_paragraph_csv 的 target 是「A｜B」，翻譯時每段依意思挑一個。
    """
    translator = _ObservedTranslator(
        lang_in=settings.lang_in,
        lang_out=settings.lang_out,
        model=settings.model,
        base_url=settings.base_url,
        api_key="ollama",  # Ollama 不檢查金鑰，但 OpenAI 用戶端要求一定要有
        # 關閉 Qwen3.5 的思考模式；不關的話每段慢約 20 倍
        reasoning="none",
    )
    translator.on_batch = on_batch
    set_translate_rate_limiter(QPS)

    layout_model = _get_layout_model()
    glossaries = [Glossary.from_csv(glossary_csv, settings.lang_out)] if glossary_csv else []
    if per_paragraph_csv:
        per_paragraph = Glossary.from_csv(per_paragraph_csv, settings.lang_out)
        if per_paragraph.entries:
            per_paragraph.name = PER_PARAGRAPH_GLOSSARY
            glossaries.append(per_paragraph)
    config = TranslationConfig(
        translator=translator,
        input_file=str(input_pdf),
        lang_in=settings.lang_in,
        lang_out=settings.lang_out,
        doc_layout_model=layout_model,
        pages=pages,
        only_include_translated_page=bool(pages),
        output_dir=str(work_dir),
        working_dir=str(work_dir / "babeldoc"),
        qps=QPS,
        # 對照版由 compose 模組自己組，BabelDOC 只輸出純譯文版
        no_dual=True,
        watermark_output_mode=WatermarkOutputMode.NoWatermark,
        # 自動抽取術語會讓本地模型多跑一輪；術語改由 glossary 模組提供
        glossaries=glossaries,
        auto_extract_glossary=False,
        save_auto_extracted_glossary=False,
        custom_system_prompt=SYSTEM_PROMPT.format(description=settings.profile.description),
        primary_font_family=font_family,
        # 譯文與原文相同時（例如照指示保留的校名、人名），BabelDOC 預設會改用簡單指令重翻，
        # 小模型在那一步會亂編中文名稱（Feng Chia University → 國立清華大學），所以關掉
        disable_same_text_fallback=True,
        use_rich_pbar=False,
    )
    getattr(layout_model, "init_font_mapper", lambda _config: None)(config)

    fallback_logger = logging.getLogger(_FALLBACK_LOGGER)
    counter = _FallbackCounter(on_fallback) if on_fallback else None
    if counter:
        fallback_logger.addHandler(counter)
    try:
        result = asyncio.run(_run(config, on_progress))
    finally:
        if counter:
            fallback_logger.removeHandler(counter)
    if result.mono_pdf_path is None:
        raise TranslationError("BabelDOC 沒有產生譯文 PDF")
    return Path(result.mono_pdf_path)


async def _run(config: TranslationConfig, on_progress: ProgressCallback | None):
    async for event in high_level.async_translate(config):
        kind = event["type"]
        if kind == "progress_update" and on_progress:
            on_progress(
                event["stage"],
                event["overall_progress"],
                event.get("stage_current", 0),
                event.get("stage_total", 0),
            )
        elif kind == "error":
            raise TranslationError(str(event["error"]))
        elif kind == "finish":
            return event["translate_result"]
    raise TranslationError("BabelDOC 在完成前就結束了")
