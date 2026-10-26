// 頁碼範圍：與 Python 端 textbook_tw/pages.py 相同的規則（1 起算，"1-5,8,10-"）。

/** 回傳排序後、不重複的頁碼（1 起算）；看不懂時回傳 null，空白代表全部。 */
export function parsePages(spec: string, total: number): number[] | null {
  const text = spec.replace(/\s+/g, "");
  if (!text) return Array.from({ length: total }, (_, i) => i + 1);

  const picked = new Set<number>();
  for (const part of text.split(",")) {
    if (!part) continue;
    const match = /^(\d*)-(\d*)$/.exec(part) ?? /^(\d+)$/.exec(part);
    if (!match) return null;
    let start: number;
    let end: number;
    if (match.length === 3) {
      start = match[1] ? Number(match[1]) : 1;
      end = match[2] ? Number(match[2]) : total;
    } else {
      start = end = Number(match[1]);
    }
    if (start < 1 || end > total || start > end) return null;
    for (let n = start; n <= end; n++) picked.add(n);
  }
  return [...picked].sort((a, b) => a - b);
}

/** parsePages 的反向：[1, 2, 3, 8] → "1-3,8"。 */
export function formatPages(pages: number[]): string {
  const ranges: string[] = [];
  let start = -1;
  let prev = -1;
  for (const n of pages) {
    if (n === prev + 1) {
      prev = n;
      continue;
    }
    if (start > 0) ranges.push(start === prev ? `${start}` : `${start}-${prev}`);
    start = prev = n;
  }
  if (start > 0) ranges.push(start === prev ? `${start}` : `${start}-${prev}`);
  return ranges.join(",");
}
