// 介面與原生功能之間的唯一入口。在 Electron 裡走 preload 開放的函式；
// 用一般瀏覽器開（預覽介面時）則改用瀏覽器能做到的替代方式。

export interface PdfFile {
  name: string;
  size: number;
  path: string | null; // 瀏覽器預覽時拿不到實際路徑
  load(): Promise<Uint8Array>;
}

export interface OllamaStatus {
  live: boolean;
  version: string | null;
  loaded: { name: string; sizeVram: number; size: number }[];
  gpuTotalBytes: number | null;
}

interface FileInfo {
  path: string;
  name: string;
  size: number;
}

interface NativeApi {
  pickPdf(): Promise<FileInfo | null>;
  pdfInfo(filePath: string): Promise<FileInfo | null>;
  readPdf(filePath: string): Promise<Uint8Array>;
  pickFolder(defaultPath?: string): Promise<string | null>;
  openPath(target: string): Promise<string>;
  revealPath(target: string): Promise<void>;
  ollamaStatus(): Promise<OllamaStatus>;
  pathForFile(file: File): string;
}

const native = (window as unknown as { textbookTw?: NativeApi }).textbookTw;

export const isDesktop = native !== undefined;

function fromInfo(api: NativeApi, info: FileInfo): PdfFile {
  return { ...info, load: () => api.readPdf(info.path) };
}

function fromBrowserFile(file: File): PdfFile {
  return {
    name: file.name,
    size: file.size,
    path: null,
    load: async () => new Uint8Array(await file.arrayBuffer()),
  };
}

export async function pickPdf(): Promise<PdfFile | null> {
  if (native) {
    const info = await native.pickPdf();
    return info ? fromInfo(native, info) : null;
  }
  return new Promise((resolve) => {
    const input = document.createElement("input");
    input.type = "file";
    input.accept = "application/pdf";
    input.onchange = () => resolve(input.files?.[0] ? fromBrowserFile(input.files[0]) : null);
    input.click();
  });
}

export async function pdfFromDrop(file: File): Promise<PdfFile | null> {
  if (!file.name.toLowerCase().endsWith(".pdf")) return null;
  if (native) {
    const info = await native.pdfInfo(native.pathForFile(file));
    return info ? fromInfo(native, info) : null;
  }
  return fromBrowserFile(file);
}

export async function pickFolder(defaultPath?: string): Promise<string | null> {
  return native ? native.pickFolder(defaultPath) : null;
}

/** 用系統預設程式開啟；失敗時回傳錯誤說明。 */
export async function openPath(target: string): Promise<string | null> {
  if (!native) return "預覽模式不能開啟檔案";
  const error = await native.openPath(target);
  return error || null;
}

export async function revealPath(target: string): Promise<void> {
  await native?.revealPath(target);
}

export async function ollamaStatus(): Promise<OllamaStatus> {
  if (native) return native.ollamaStatus();
  return { live: false, version: null, loaded: [], gpuTotalBytes: null };
}
