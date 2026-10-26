"""用原文 PDF 與純譯文 PDF 組出中英對照版。

純譯文 PDF 的第 k 頁對應原文的 page_indices[k] 頁（只翻部分頁面時兩者頁數不同）。
"""

from __future__ import annotations

from pathlib import Path

import pymupdf


def _check_page_count(translated: pymupdf.Document, page_indices: list[int]) -> None:
    if translated.page_count != len(page_indices):
        raise ValueError(
            f"譯文有 {translated.page_count} 頁，但應對應原文的 {len(page_indices)} 頁"
        )


def side_by_side(
    original: Path,
    translated: Path,
    out: Path,
    page_indices: list[int],
    translated_first: bool = False,
) -> None:
    """每一頁左右並排：預設左原文、右譯文。"""
    with pymupdf.open(original) as src, pymupdf.open(translated) as tr, pymupdf.open() as dst:
        _check_page_count(tr, page_indices)
        for t_no, o_no in enumerate(page_indices):
            pair = [(src, o_no), (tr, t_no)]
            if translated_first:
                pair.reverse()
            (left_doc, left_no), (right_doc, right_no) = pair
            left, right = left_doc[left_no].rect, right_doc[right_no].rect

            page = dst.new_page(
                width=left.width + right.width, height=max(left.height, right.height)
            )
            page.show_pdf_page(pymupdf.Rect(0, 0, left.width, left.height), left_doc, left_no)
            page.show_pdf_page(
                pymupdf.Rect(left.width, 0, left.width + right.width, right.height),
                right_doc,
                right_no,
            )
        dst.save(out, garbage=3, deflate=True)


def alternating(
    original: Path,
    translated: Path,
    out: Path,
    page_indices: list[int],
    translated_first: bool = False,
) -> None:
    """原文頁與譯文頁輪流：預設原文在前。"""
    with pymupdf.open(original) as src, pymupdf.open(translated) as tr, pymupdf.open() as dst:
        _check_page_count(tr, page_indices)
        # 整份插入再重新排列，圖片與字型只會複製一次
        dst.insert_pdf(src)
        dst.insert_pdf(tr)
        offset = src.page_count
        order: list[int] = []
        for t_no, o_no in enumerate(page_indices):
            pair = [o_no, offset + t_no]
            if translated_first:
                pair.reverse()
            order.extend(pair)
        dst.select(order)
        dst.save(out, garbage=3, deflate=True)
