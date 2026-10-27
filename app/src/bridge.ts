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

// pick 的特殊值（與 Python 端 app_api.py 相同）
export const PICK_NONE = -1; // 還沒選
export const PICK_PER_PARAGRAPH = -2; // 依段落選：翻譯時每段從 paragraph 列的譯名挑一個
export const PICK_SKIP = -3; // 不套用：翻譯時由模型自行處理

/** 需要使用者看一下的術語（待確認、模型建議、或各名詞庫譯名不同）。 */
export interface ReviewTerm {
  source: string;
  status: string; // "待確認" | "依段落" | "模型建議" | "不套用" | "名詞庫譯名不同"
  count: number;
  page: number;
  context: string;
  note: string; // 模型的理由
  options: { zh: string; src: string }[];
  pick: number; // 目前採用第幾個；或 PICK_NONE、PICK_PER_PARAGRAPH、PICK_SKIP
  paragraph: number[]; // 依段落選時，候選譯名是 options 的哪幾個
}

export interface GlossaryReview {
  path: string;
  created: boolean;
  profile: string;
  total: number;
  resolved: boolean; // 已經讓模型依上下文判斷過
  pending: number; // 還需要模型判斷的詞數
  review: ReviewTerm[];
}

export interface ResolveProgress {
  type: "progress";
  done: number;
  total: number;
}

/** 依段落選譯名的詞，翻譯時實際用了哪些譯名。 */
export interface ChoiceUsage {
  source: string;
  counts: Record<string, number>; // 譯名 → 段落數
}

export interface GlossaryChoices {
  choices: Record<string, string>; // 英文 → 譯名
  my_terms: [string, string][];
}

export interface JobSpec {
  pdf: string;
  pages: string;
  profile: string;
  dual: string;
  font: string;
  mono: boolean;
  translatedFirst: boolean;
  outDir: string | null;
}

export interface OutputInfo {
  kind: "mono" | "side_by_side" | "alternating";
  path: string;
  size: number;
}

export type JobEvent =
  | { type: "start"; pages: number[] }
  | { type: "message"; text: string }
  | { type: "progress"; stage: string; percent: number; current: number; total: number }
  | { type: "paragraphs"; items: { en: string; zh: string }[] }
  | { type: "fallback"; count: number }
  | { type: "done"; seconds: number; pages: number[]; fallbacks: number; outputs: OutputInfo[]; per_paragraph: ChoiceUsage[] }
  | { type: "error"; message: string }
  | { type: "cancelled" };

interface NativeApi {
  pickPdf(): Promise<FileInfo | null>;
  pdfInfo(filePath: string): Promise<FileInfo | null>;
  readPdf(filePath: string): Promise<Uint8Array>;
  pickFolder(defaultPath?: string): Promise<string | null>;
  openPath(target: string): Promise<string>;
  revealPath(target: string): Promise<void>;
  ollamaStatus(): Promise<OllamaStatus>;
  pathForFile(file: File): string;
  glossaryReview(pdfPath: string, profile: string): Promise<GlossaryReview>;
  applyGlossary(pdfPath: string, payload: GlossaryChoices): Promise<{ updated: number }>;
  resolveGlossary(pdfPath: string, profile: string): Promise<GlossaryReview | null>;
  cancelResolve(): Promise<void>;
  onResolveEvent(callback: (event: ResolveProgress) => void): () => void;
  startJob(spec: JobSpec): Promise<void>;
  cancelJob(): Promise<void>;
  onJobEvent(callback: (event: JobEvent) => void): () => void;
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

// ---- Python 後端（只有在 Electron 裡才有；瀏覽器預覽改用示範資料） ----

/** Electron 主程序把錯誤包成 "Error invoking remote method ...: Error: 說明"，只留說明。 */
function cleanError(e: unknown): Error {
  const message = e instanceof Error ? e.message : String(e);
  return new Error(message.replace(/^Error invoking remote method '[^']+': (Error: )?/, ""));
}

function backend(): NativeApi {
  if (!native) throw new Error("預覽模式沒有後端");
  return native;
}

export const hasBackend = isDesktop;

export async function glossaryReview(pdfPath: string, profile: string): Promise<GlossaryReview> {
  try {
    return await backend().glossaryReview(pdfPath, profile);
  } catch (e) {
    throw cleanError(e);
  }
}

export async function applyGlossary(pdfPath: string, payload: GlossaryChoices): Promise<void> {
  try {
    await backend().applyGlossary(pdfPath, payload);
  } catch (e) {
    throw cleanError(e);
  }
}

/** 讓模型依上下文判斷術語譯名；完成時回傳新的確認清單，被中斷時回傳 null。 */
export async function resolveGlossary(pdfPath: string, profile: string): Promise<GlossaryReview | null> {
  try {
    return await backend().resolveGlossary(pdfPath, profile);
  } catch (e) {
    throw cleanError(e);
  }
}

export async function cancelResolve(): Promise<void> {
  await native?.cancelResolve();
}

export function onResolveEvent(callback: (event: ResolveProgress) => void): () => void {
  return native ? native.onResolveEvent(callback) : () => {};
}

export async function startJob(spec: JobSpec): Promise<void> {
  try {
    await backend().startJob(spec);
  } catch (e) {
    throw cleanError(e);
  }
}

export async function cancelJob(): Promise<void> {
  await native?.cancelJob();
}

export function onJobEvent(callback: (event: JobEvent) => void): () => void {
  return native ? native.onJobEvent(callback) : () => {};
}
