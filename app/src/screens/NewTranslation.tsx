import { useState } from "react";
import type { DragEvent } from "react";
import { isDesktop, pdfFromDrop, pickFolder, pickPdf, type OllamaStatus, type PdfFile } from "../bridge";
import { DualIcon, Notice, PageStrip, Section, SectionTitle, Segmented, Stat, SwitchRow, Tag } from "../components/ui";
import { DEMO_RECENT } from "../demo";
import { defaultOutputDir, formatBytes, formatGiB } from "../lib/format";
import { parsePages } from "../lib/pages";
import { summarizePdf } from "../lib/pdf";
import {
  MODEL_NAME,
  PROFILES,
  SEC_PER_PAGE,
  plannedOutputs,
  type Doc,
  type DualMode,
  type FontChoice,
  type JobOptions,
} from "../model";

const DUAL_OPTIONS: { value: DualMode; label: string }[] = [
  { value: "side_by_side", label: "左右並排" },
  { value: "alternating", label: "交替頁" },
  { value: "both", label: "兩種都要" },
  { value: "none", label: "不要" },
];

const DUAL_HINTS: Record<DualMode, string> = {
  side_by_side: "每一頁左邊原文、右邊譯文，適合在螢幕上對照。",
  alternating: "原文頁和譯文頁輪流，適合印出來或在平板上翻頁。",
  both: "兩種都輸出。只翻譯一次，對照版由譯文版組出來，不會多花時間。",
  none: "不輸出對照版。",
};

const FONT_OPTIONS: { value: FontChoice; label: string }[] = [
  { value: "auto", label: "自動" },
  { value: "serif", label: "明體" },
  { value: "sans-serif", label: "黑體" },
];

function fontHint(font: FontChoice, doc: Doc | null): string {
  if (font === "serif") return "明體：接近教科書內文。";
  if (font === "sans-serif") return "黑體：接近投影片與粗體標題。";
  const base = "自動：投影片（橫向頁面）用黑體，其他依原文判斷。";
  if (!doc) return base;
  return base + (doc.landscape ? "這份是橫向投影片，會用黑體。" : "這份是直向教科書，會用明體。");
}

export function NewTranslation({
  doc,
  onDoc,
  options,
  onOptions,
  ollama,
  notice,
  onStart,
  onSaveDefault,
  onOpenRecent,
}: {
  doc: Doc | null;
  onDoc: (doc: Doc) => void;
  options: JobOptions;
  onOptions: (next: JobOptions) => void;
  ollama: OllamaStatus | null;
  notice: string | null;
  onStart: () => void;
  onSaveDefault: () => void;
  onOpenRecent: () => void;
}) {
  const [loading, setLoading] = useState(false);
  const [fileError, setFileError] = useState<string | null>(null);
  const [startError, setStartError] = useState<string | null>(null);
  const [dragging, setDragging] = useState(false);
  const [saved, setSaved] = useState(false);

  const set = (patch: Partial<JobOptions>) => {
    setSaved(false);
    setStartError(null);
    onOptions({ ...options, ...patch });
  };

  const total = doc?.pageCount ?? 0;
  const picked = doc ? parsePages(options.pages, total) : [];
  const rangeError = doc !== null && picked === null;
  const selected = picked?.length ?? 0;
  const pickedSet = new Set(picked ?? []);
  const outputs = doc ? plannedOutputs(doc.file.name, options, picked, total) : [];
  const outputDir = options.outputDir ?? (doc ? defaultOutputDir(doc.file.path, doc.file.name) : null);

  async function load(file: PdfFile | null) {
    if (!file) return;
    setLoading(true);
    setFileError(null);
    try {
      const summary = await summarizePdf(await file.load());
      onDoc({ file, ...summary });
      onOptions({ ...options, pages: "", outputDir: null });
    } catch {
      setFileError("讀不了這個 PDF。檔案可能損毀或有密碼保護。");
    } finally {
      setLoading(false);
    }
  }

  async function onDrop(e: DragEvent) {
    e.preventDefault();
    setDragging(false);
    const file = e.dataTransfer.files[0];
    if (!file) return;
    const pdf = await pdfFromDrop(file);
    if (!pdf) {
      setFileError("只能翻譯 PDF 檔。");
      return;
    }
    await load(pdf);
  }

  function start() {
    if (!doc) return setStartError("先選一個 PDF。");
    if (rangeError) return setStartError("頁面範圍寫錯了，請先修正。");
    if (outputs.length === 0) return setStartError("至少要輸出一種檔案。");
    onStart();
  }

  async function changeOutputDir() {
    const dir = await pickFolder(outputDir ?? undefined);
    if (dir) set({ outputDir: dir });
  }

  const loadedModel = ollama?.loaded.find((m) => m.name === MODEL_NAME);
  const gpuTotal = ollama?.gpuTotalBytes ?? null;

  return (
    <main className="main" style={{ flexDirection: "row", flexWrap: "wrap", gap: "48px 64px", alignItems: "flex-start" }}>
      <div className="col-main tight">
        {notice && (
          <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
            <Tag kind="outline">PAUSED</Tag>
            <span className="t-caption">{notice}</span>
          </div>
        )}

        <Section>
          <SectionTitle index="01">檔案</SectionTitle>
          <div
            role="button"
            tabIndex={0}
            aria-label={doc ? `已選 ${doc.file.name}，按一下換一個檔案` : "選擇要翻譯的 PDF"}
            onClick={() => pickPdf().then(load)}
            onKeyDown={(e) => {
              if (e.key === "Enter" || e.key === " ") {
                e.preventDefault();
                pickPdf().then(load);
              }
            }}
            onDragOver={(e) => {
              e.preventDefault();
              setDragging(true);
            }}
            onDragLeave={() => setDragging(false)}
            onDrop={onDrop}
            style={{
              display: "flex",
              flexDirection: "column",
              gap: 20,
              padding: 24,
              border: `1px ${dragging ? "solid var(--ink)" : "dashed var(--line-strong)"}`,
              cursor: "pointer",
            }}
          >
            {doc ? (
              <>
                <div style={{ display: "flex", flexWrap: "wrap", justifyContent: "space-between", alignItems: "baseline", gap: "8px 24px" }}>
                  <span className="t-focus wrap-any">{doc.file.name}</span>
                  <span className="btn-text secondary">{loading ? "讀取中…" : "換一個檔案"}</span>
                </div>
                <div className="stats">
                  <Stat label="頁數" value={doc.pageCount} />
                  <Stat label="版面" value={doc.landscape ? "橫向，投影片" : "直向，教科書"} />
                  <Stat label="大小" value={formatBytes(doc.file.size)} />
                  <Stat label="預估時間" value={`約 ${Math.max(1, Math.round((selected * SEC_PER_PAGE) / 60))} 分`} />
                </div>
                <PageStrip
                  total={total}
                  height={48}
                  label={`全書 ${total} 頁，已選 ${selected} 頁`}
                  bar={(p) => ({ height: pickedSet.has(p) ? 48 : 20, background: pickedSet.has(p) ? "var(--ink)" : "var(--line-strong)" })}
                />
              </>
            ) : (
              <div style={{ display: "flex", flexWrap: "wrap", justifyContent: "space-between", alignItems: "baseline", gap: "8px 24px", minHeight: 96 }}>
                <span className="t-focus">{loading ? "讀取中…" : "把 PDF 拖到這裡"}</span>
                <span className="btn-text secondary">選擇檔案</span>
              </div>
            )}
          </div>
          {fileError ? (
            <Notice kind="err">{fileError}</Notice>
          ) : (
            <p className="t-caption c-muted">把 PDF 拖到上面的框，或按一下框選擇檔案。翻譯在這台電腦上進行，檔案不會上傳。</p>
          )}
        </Section>

        <Section>
          <SectionTitle index="02">頁面範圍</SectionTitle>
          <div style={{ display: "flex", flexWrap: "wrap", alignItems: "flex-end", gap: "16px 32px" }}>
            <div style={{ flex: "1 1 280px", display: "flex", flexDirection: "column", gap: 8 }}>
              <label htmlFor="pages" className="t-label c-faint">
                要翻的頁面
              </label>
              <input
                id="pages"
                className={`input-line${rangeError ? " invalid" : ""}`}
                type="text"
                inputMode="numeric"
                placeholder="全部"
                value={options.pages}
                aria-invalid={rangeError}
                onChange={(e) => set({ pages: e.target.value })}
              />
            </div>
            <Stat label="已選" value={doc ? `${selected} / ${total}` : "—"} align="right" />
          </div>
          {rangeError ? (
            <Notice kind="err">看不懂這個範圍。請寫成 1-20 或 1-5,8，頁碼從 1 起算。</Notice>
          ) : (
            <p className="t-caption c-muted">留白就翻整份。只翻部分頁面時，輸出檔名會加上頁碼，不會蓋掉整份的結果。</p>
          )}
        </Section>

        <Section gap={8}>
          <SectionTitle index="03">科目</SectionTitle>
          <div role="radiogroup" aria-label="科目" style={{ display: "flex", flexDirection: "column" }}>
            {PROFILES.map((p) => {
              const on = options.profile === p.id;
              return (
                <button
                  key={p.id}
                  type="button"
                  role="radio"
                  aria-checked={on}
                  onClick={() => set({ profile: p.id })}
                  className="row-line-bottom"
                  style={{ display: "flex", alignItems: "flex-start", gap: 16, padding: "16px 0", width: "100%" }}
                >
                  <span
                    aria-hidden="true"
                    style={{ flex: "none", width: 16, height: 16, marginTop: 4, border: "1px solid var(--line-strong)", display: "flex", alignItems: "center", justifyContent: "center" }}
                  >
                    <span style={{ display: "block", width: 8, height: 8, background: on ? "var(--ink)" : "transparent", boxShadow: on ? "var(--glow-ink)" : "none" }} />
                  </span>
                  <span style={{ flex: "1 1 auto", minWidth: 0, display: "flex", flexDirection: "column", gap: 4 }}>
                    <span className="t-heading">{p.name}</span>
                    <span className="t-caption c-muted">{p.desc}</span>
                  </span>
                  <span className="t-label c-faint" style={{ flex: "0 1 260px", textAlign: "right", paddingTop: 4 }}>
                    {p.order}
                  </span>
                </button>
              );
            })}
          </div>
          <p className="t-caption c-muted">同一個英文詞在不同名詞庫有不同譯名時，右邊排越前面的名詞庫優先。你的修正表永遠最優先。</p>
        </Section>

        <Section>
          <SectionTitle index="04">輸出</SectionTitle>
          <SwitchRow id="mono-label" label="純譯文版" hint="只有中文，版面和原文一樣" checked={options.mono} onChange={(mono) => set({ mono })} />
          <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
            <span id="dual-label" className="t-body">
              中英對照版
            </span>
            <Segmented
              labelledBy="dual-label"
              value={options.dual}
              onChange={(dual) => set({ dual })}
              options={DUAL_OPTIONS.map((o) => ({
                value: o.value,
                label: (
                  <>
                    <DualIcon mode={o.value} translatedFirst={options.translatedFirst} />
                    <span>{o.label}</span>
                  </>
                ),
              }))}
            />
            <p className="t-caption c-muted">{DUAL_HINTS[options.dual]}</p>
          </div>
          <SwitchRow
            id="first-label"
            label="對照版譯文放前面"
            hint="預設是原文在左、在前"
            checked={options.translatedFirst}
            disabled={options.dual === "none"}
            onChange={(translatedFirst) => set({ translatedFirst })}
          />
        </Section>

        <Section>
          <SectionTitle index="05">譯文字型</SectionTitle>
          <Segmented label="譯文字型" value={options.font} onChange={(font) => set({ font })} options={FONT_OPTIONS} />
          <p
            style={{
              fontFamily: options.font === "sans-serif" || (options.font === "auto" && doc?.landscape) ? "var(--font-sans)" : "var(--font-serif)",
              fontSize: 18,
              lineHeight: "30px",
              fontWeight: 500,
            }}
          >
            邊界層在雷諾數升高後轉為紊流，翼型的升力係數隨攻角增加。
          </p>
          <p className="t-caption c-muted">{fontHint(options.font, doc)}</p>
        </Section>

        <div style={{ display: "flex", flexDirection: "column", gap: 8, paddingTop: 8 }}>
          <div style={{ display: "flex", flexWrap: "wrap", alignItems: "center", gap: "8px 24px" }}>
            <button type="button" className="btn-primary" onClick={start}>
              {doc && !rangeError ? `開始翻譯 · ${selected} 頁` : "開始翻譯"}
            </button>
            <button
              type="button"
              className="btn-text secondary"
              onClick={() => {
                onSaveDefault();
                setSaved(true);
              }}
            >
              {saved ? "已存成預設" : "存成我的預設"}
            </button>
            <span className="t-caption c-faint">開始前會先掃描術語，有多個譯名的詞請你選一次。</span>
          </div>
          {startError && <Notice kind="err">{startError}</Notice>}
        </div>
      </div>

      <aside className="col-side tight">
        <Section gap={12}>
          <SectionTitle>本機模型</SectionTitle>
          {ollama && !ollama.live && <Notice kind="err">連不到 Ollama。請先開啟 Ollama。</Notice>}
          <div style={{ display: "flex", justifyContent: "space-between", gap: 16 }}>
            <span className="t-label c-faint" style={{ lineHeight: "20px" }}>MODEL</span>
            <span className="t-data">{MODEL_NAME}</span>
          </div>
          <div style={{ display: "flex", justifyContent: "space-between", gap: 16 }}>
            <span className="t-label c-faint" style={{ lineHeight: "20px" }}>THINK</span>
            <span className="t-data">OFF</span>
          </div>
          <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
            <div style={{ display: "flex", justifyContent: "space-between", gap: 16 }}>
              <span className="t-label c-faint" style={{ lineHeight: "20px" }}>VRAM</span>
              <span className="t-data">
                {loadedModel ? formatGiB(loadedModel.sizeVram) : "0.0"}
                {gpuTotal ? ` / ${formatGiB(gpuTotal)}` : ""} GiB
              </span>
            </div>
            <div
              role="img"
              aria-label={loadedModel ? `顯示記憶體使用 ${formatGiB(loadedModel.sizeVram)} GiB` : "模型還沒載入"}
              style={{ height: 2, background: "var(--line)" }}
            >
              <div
                style={{
                  width: loadedModel && gpuTotal ? `${Math.min(100, (loadedModel.sizeVram / gpuTotal) * 100)}%` : 0,
                  height: 2,
                  background: "var(--ink)",
                  boxShadow: "var(--glow-ink)",
                }}
              />
            </div>
          </div>
          <p className="t-caption c-muted">
            {loadedModel
              ? loadedModel.sizeVram >= loadedModel.size
                ? "模型整個放在顯示卡上。換模型到「設定」。"
                : "模型有一部分放在記憶體，速度會變慢。換模型到「設定」。"
              : "模型會在開始翻譯時載入。換模型到「設定」。"}
          </p>
        </Section>

        <Section gap={12}>
          <SectionTitle>會產生的檔案</SectionTitle>
          <span className="t-data c-muted wrap-any">{outputDir ?? "原檔所在資料夾"}</span>
          {isDesktop && (
            <div style={{ display: "flex", flexWrap: "wrap", gap: "0 16px" }}>
              <button type="button" className="btn-text secondary" onClick={changeOutputDir}>
                變更位置
              </button>
              {options.outputDir && (
                <button type="button" className="btn-text secondary" onClick={() => set({ outputDir: null })}>
                  改回原檔旁邊
                </button>
              )}
            </div>
          )}
          {outputs.map((o) => (
            <div key={o.file} className="row-line" style={{ display: "flex", flexDirection: "column", gap: 2, padding: "8px 0" }}>
              <span className="t-body wrap-any">{o.file}</span>
              <span className="t-caption c-faint">{o.desc}</span>
            </div>
          ))}
          {doc && outputs.length === 0 && <Notice kind="due">沒有選任何輸出。打開純譯文版，或選一種對照版。</Notice>}
          {!doc && <p className="t-caption c-faint">選好 PDF 後會列出檔名。</p>}
        </Section>

        <Section gap={0}>
          <SectionTitle>最近翻譯</SectionTitle>
          <div style={{ height: 8 }} />
          {DEMO_RECENT.map((r) => (
            <a
              key={r.name}
              href="#"
              className="row-line"
              onClick={(e) => {
                e.preventDefault();
                onOpenRecent();
              }}
              style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 12, minHeight: 56 }}
            >
              <span style={{ display: "flex", flexDirection: "column", minWidth: 0 }}>
                <span className="t-body wrap-any">{r.name}</span>
                <span className="t-label c-faint">{r.meta}</span>
              </span>
              <Tag kind="done">DONE</Tag>
            </a>
          ))}
        </Section>
      </aside>
    </main>
  );
}
