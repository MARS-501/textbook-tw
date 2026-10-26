"""唯一直接呼叫 BabelDOC 的地方。

BabelDOC 官方表示它的 API 都屬於內部 API，所以版本鎖定在 pyproject.toml，
升級時只需要修改這個檔案。
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from pathlib import Path

import babeldoc.format.pdf.high_level as high_level
from babeldoc.docvision.doclayout import DocLayoutModel
from babeldoc.format.pdf.translation_config import TranslationConfig, WatermarkOutputMode
from babeldoc.translator.translator import OpenAITranslator, set_translate_rate_limiter

from textbook_tw.config import Settings

logger = logging.getLogger(__name__)

# (階段名稱, 整體進度 0～100)
ProgressCallback = Callable[[str, float], None]

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
    on_progress: ProgressCallback | None = None,
) -> Path:
    """翻譯 input_pdf，回傳純譯文 PDF 的路徑。

    指定 pages 時，輸出只包含被翻譯的那些頁面，順序與原文相同。
    font_family 為 "serif"、"sans-serif" 或 None（由 BabelDOC 依原文判斷）。
    """
    translator = OpenAITranslator(
        lang_in=settings.lang_in,
        lang_out=settings.lang_out,
        model=settings.model,
        base_url=settings.base_url,
        api_key="ollama",  # Ollama 不檢查金鑰，但 OpenAI 用戶端要求一定要有
        # 關閉 Qwen3.5 的思考模式；不關的話每段慢約 20 倍
        reasoning="none",
    )
    set_translate_rate_limiter(QPS)

    layout_model = _get_layout_model()
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

    result = asyncio.run(_run(config, on_progress))
    if result.mono_pdf_path is None:
        raise TranslationError("BabelDOC 沒有產生譯文 PDF")
    return Path(result.mono_pdf_path)


async def _run(config: TranslationConfig, on_progress: ProgressCallback | None):
    async for event in high_level.async_translate(config):
        kind = event["type"]
        if kind == "progress_update" and on_progress:
            on_progress(event["stage"], event["overall_progress"])
        elif kind == "error":
            raise TranslationError(str(event["error"]))
        elif kind == "finish":
            return event["translate_result"]
    raise TranslationError("BabelDOC 在完成前就結束了")
