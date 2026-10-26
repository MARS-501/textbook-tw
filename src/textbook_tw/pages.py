"""頁碼範圍：使用者輸入 1 起算的 "1-5,8,10-"，內部轉成 0 起算的索引。"""

from __future__ import annotations


def parse_pages(spec: str | None, page_count: int) -> list[int]:
    """把頁碼範圍轉成排序後、不重複的 0 起算索引；spec 為空代表全部頁面。"""
    if not spec:
        return list(range(page_count))

    indices: set[int] = set()
    for part in spec.replace(" ", "").split(","):
        if not part:
            continue
        if "-" in part:
            start_text, end_text = part.split("-", 1)
            start = int(start_text) if start_text else 1
            end = int(end_text) if end_text else page_count
        else:
            start = end = int(part)
        if start < 1 or end > page_count or start > end:
            raise ValueError(f"頁碼範圍 {part!r} 超出 1～{page_count}")
        indices.update(range(start - 1, end))
    return sorted(indices)


def format_pages(indices: list[int]) -> str:
    """parse_pages 的反向：[0, 1, 2, 7] → "1-3,8"。"""
    ranges: list[str] = []
    start = prev = None
    for i in indices:
        if prev is not None and i == prev + 1:
            prev = i
            continue
        if start is not None:
            ranges.append(f"{start + 1}" if start == prev else f"{start + 1}-{prev + 1}")
        start = prev = i
    if start is not None:
        ranges.append(f"{start + 1}" if start == prev else f"{start + 1}-{prev + 1}")
    return ",".join(ranges)
