export function formatBytes(bytes: number): string {
  if (bytes >= 1024 ** 3) return `${(bytes / 1024 ** 3).toFixed(1)} GB`;
  if (bytes >= 1024 ** 2) return `${(bytes / 1024 ** 2).toFixed(1)} MB`;
  return `${Math.max(1, Math.round(bytes / 1024))} KB`;
}

export function formatGiB(bytes: number): string {
  return (bytes / 1024 ** 3).toFixed(1);
}

/** 秒數 → mm:ss（超過一小時 → h:mm:ss）。 */
export function clock(totalSeconds: number): string {
  const s = Math.max(0, Math.round(totalSeconds));
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  const sec = s % 60;
  const mm = String(m).padStart(2, "0");
  const ss = String(sec).padStart(2, "0");
  return h > 0 ? `${h}:${mm}:${ss}` : `${mm}:${ss}`;
}

export function stemOf(fileName: string): string {
  return fileName.replace(/\.pdf$/i, "");
}

/** 預設輸出位置：原檔所在資料夾裡的「<檔名> 翻譯」。 */
export function defaultOutputDir(pdfPath: string | null, fileName: string): string | null {
  if (!pdfPath) return null;
  const sep = pdfPath.includes("\\") ? "\\" : "/";
  const dir = pdfPath.slice(0, pdfPath.lastIndexOf(sep));
  return `${dir}${sep}${stemOf(fileName)} 翻譯`;
}

export function joinPath(dir: string, name: string): string {
  const sep = dir.includes("\\") ? "\\" : "/";
  return `${dir}${sep}${name}`;
}
