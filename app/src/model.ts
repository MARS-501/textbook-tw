import type { ChoiceUsage, OutputInfo, PdfFile } from "./bridge";
import { formatPages } from "./lib/pages";
import { stemOf } from "./lib/format";

export type Screen = "new" | "glossary" | "progress" | "done" | "settings";
export type DualMode = "side_by_side" | "alternating" | "both" | "none";
export type FontChoice = "auto" | "serif" | "sans-serif";

export interface Profile {
  id: string;
  name: string;
  desc: string;
  order: string; // 名詞庫優先順序（顯示用）
}

// 與 config/profiles/*.toml 對應；接上後端後改成向後端讀取
export const PROFILES: Profile[] = [
  { id: "fluid-mechanics", name: "流體力學", desc: "流體力學、空氣動力學、熱流、計算流體力學", order: "力學 › 航空太空 › 機械工程" },
  { id: "aerospace", name: "航太", desc: "飛行力學、推進、結構、太空任務、航電", order: "航空太空 › 力學 › 機械工程" },
  { id: "engineering-math", name: "工程數學", desc: "微分方程、線性代數、向量分析、複變、轉換、數值方法", order: "數學 › 統計學 › 力學" },
  { id: "materials", name: "材料與結構", desc: "複合材料、積層板、金屬與高分子材料、材料試驗、結構力學", order: "力學 › 金屬材料 › 高分子材料" },
];

export const MODEL_NAME = "qwen3.5:4b";
export const SEC_PER_PAGE = 13; // 第 1 階段實測：RTX 2060 + qwen3.5:4b

export interface JobOptions {
  pages: string;
  profile: string;
  dual: DualMode;
  font: FontChoice;
  mono: boolean;
  translatedFirst: boolean;
  outputDir: string | null; // null = 預設（原檔旁邊）
}

export const DEFAULT_OPTIONS: JobOptions = {
  pages: "",
  profile: "fluid-mechanics",
  dual: "both",
  font: "auto",
  mono: true,
  translatedFirst: false,
  outputDir: null,
};

export interface Doc {
  file: PdfFile;
  pageCount: number;
  landscape: boolean;
}

export interface OutputFile {
  file: string;
  desc: string;
  kind: "mono" | "side_by_side" | "alternating";
}

/** 會產生的檔名：與 Python 端 pipeline.py 相同的規則。 */
export function plannedOutputs(fileName: string, options: JobOptions, pages: number[] | null, total: number): OutputFile[] {
  const partial = pages !== null && options.pages.trim() !== "" && pages.length < total;
  const prefix = stemOf(fileName) + (partial && pages ? `.p${formatPages(pages)}` : "");
  const first = options.translatedFirst;
  const outputs: OutputFile[] = [];
  if (options.mono) outputs.push({ file: `${prefix}.譯文.pdf`, desc: "純譯文版", kind: "mono" });
  if (options.dual === "side_by_side" || options.dual === "both") {
    outputs.push({ file: `${prefix}.對照-並排.pdf`, desc: first ? "每頁左譯文、右原文" : "每頁左原文、右譯文", kind: "side_by_side" });
  }
  if (options.dual === "alternating" || options.dual === "both") {
    outputs.push({ file: `${prefix}.對照-交替.pdf`, desc: first ? "譯文頁、原文頁輪流" : "原文頁、譯文頁輪流", kind: "alternating" });
  }
  return outputs;
}

/** 翻譯中畫面要顯示的狀態（真實翻譯與示範共用）。 */
export interface JobView {
  pages: number[]; // 要翻的頁碼（1 起算）
  pagesDone: number; // 估計已翻好幾頁
  percent: number;
  step: 0 | 1 | 2 | 3; // 分析版面、套用術語表、翻譯段落、組對照版
  elapsed: number; // 秒
  remaining: number | null; // 秒；還估不出來時為 null
  perPage: number | null; // 秒
  paragraphs: { en: string; zh: string | null; fixed?: { from: string; to: string } }[];
  fallbacks: number;
  fixes: number | null; // 大陸用語修正次數；還沒做這個功能時為 null
  error: string | null;
}

/** 翻完的紀錄（存在 localStorage，所以只放可序列化的資料）。 */
export interface FinishedJob {
  fileName: string;
  totalPages: number;
  options: JobOptions;
  pages: number[];
  seconds: number;
  finishedAt: string; // ISO
  fallbacks: number;
  outputs: (Omit<OutputInfo, "size"> & { size: number | null })[];
  perParagraph?: ChoiceUsage[]; // 較早的紀錄沒有這一欄
  demo: boolean;
}

export function profileName(id: string): string {
  return PROFILES.find((p) => p.id === id)?.name ?? id;
}
