import { useState } from "react";
import { openPath, revealPath } from "../bridge";
import { Notice, PageStrip, Section, SectionTitle, Stat } from "../components/ui";
import { DEMO_CHECKS, DEMO_FIXES } from "../demo";
import { clock, defaultOutputDir, joinPath } from "../lib/format";
import { MODEL_NAME, SEC_PER_PAGE, plannedOutputs, profileName, type Doc, type JobOptions } from "../model";

export interface FinishedJob {
  doc: Doc | null;
  options: JobOptions;
  pages: number[];
  seconds: number;
  finishedAt: Date;
}

function stamp(d: Date): string {
  const days = ["SUN", "MON", "TUE", "WED", "THU", "FRI", "SAT"];
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${days[d.getDay()]} ${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

export function Done({ result, onNext, onEditGlossary }: { result: FinishedJob | null; onNext: () => void; onEditGlossary: () => void }) {
  const [openError, setOpenError] = useState<string | null>(null);
  const [showAllChecks, setShowAllChecks] = useState(false);

  if (!result) {
    return (
      <main className="main">
        <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
          <h1 className="t-title">紀錄</h1>
          <p className="t-body c-muted">翻好的檔案會列在這裡。</p>
        </div>
        <div>
          <button type="button" className="btn-primary" onClick={onNext}>
            翻譯第一份
          </button>
        </div>
      </main>
    );
  }

  const { doc, options, pages } = result;
  const name = doc?.file.name ?? "示範.pdf";
  const total = pages.length;
  const flagged = new Set(DEMO_CHECKS.map((c) => c.page).filter((p) => pages.includes(p)));
  // 頁面條用的是第幾個翻譯頁（1 起算）
  const flaggedIndex = new Set(pages.map((p, i) => (flagged.has(p) ? i + 1 : 0)).filter(Boolean));
  const checks = DEMO_CHECKS.filter((c) => flagged.has(c.page));
  // 對照版排前面：翻完最常打開的是並排版
  const order = { side_by_side: 0, alternating: 1, mono: 2 };
  const outputs = plannedOutputs(name, options, pages, doc?.pageCount ?? total).sort((a, b) => order[a.kind] - order[b.kind]);
  const outputDir = options.outputDir ?? (doc ? defaultOutputDir(doc.file.path, doc.file.name) : null);

  async function open(file: string) {
    if (!outputDir) return setOpenError("預覽模式不能開啟檔案。");
    const error = await openPath(joinPath(outputDir, file));
    setOpenError(error ? "找不到檔案。目前是示範資料，還沒有真的產生檔案。" : null);
  }

  return (
    <main className="main">
      <div className="hero">
        <div style={{ display: "flex", flexDirection: "column", gap: 8, minWidth: 0 }}>
          <span className="t-label c-faint">
            {stamp(result.finishedAt)} · {profileName(options.profile)} · {MODEL_NAME}
          </span>
          <div style={{ display: "flex", alignItems: "baseline", gap: 16, flexWrap: "wrap" }}>
            <span className="t-display">{clock(result.seconds)}</span>
            <span className="t-focus wrap-any">{name} 翻好了</span>
          </div>
        </div>
        <div className="stats" style={{ textAlign: "right" }}>
          <Stat label="頁數" value={total} align="right" />
          <Stat label="每頁" value={`${SEC_PER_PAGE} 秒`} align="right" />
          <Stat label="要檢查" value={`${checks.reduce((n, c) => n + c.count, 0)} 段`} align="right" />
        </div>
      </div>

      <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
        <PageStrip
          total={total}
          height={160}
          label={`${total} 頁都翻好了，其中 ${flagged.size} 頁有段落需要檢查`}
          bar={(i) => ({ height: flaggedIndex.has(i) ? 112 : 160, background: flaggedIndex.has(i) ? "var(--line-strong)" : "var(--ink)" })}
          marks={(i) => (flaggedIndex.has(i) ? { width: 6, margin: "0 -2.5px", background: "var(--warn)" } : {})}
        />
        {flagged.size > 0 && <Notice kind="due">短線與下方的點：這一頁有段落沒有套用術語表，建議對照原文看一下。</Notice>}
      </div>

      <div className="columns">
        <div className="col-main">
          <Section gap={0}>
            <div style={{ marginBottom: 8 }}>
              <SectionTitle index="01" right={outputDir ?? ""}>
                檔案
              </SectionTitle>
            </div>
            {outputs.map((o, i) => (
              <div
                key={o.file}
                className={`row-line${i === outputs.length - 1 ? " row-line-bottom" : ""}`}
                style={{ display: "flex", flexWrap: "wrap", alignItems: "center", justifyContent: "space-between", gap: "0 24px", minHeight: 64 }}
              >
                <div style={{ display: "flex", flexDirection: "column", minWidth: 0, padding: "8px 0" }}>
                  <span className="t-body wrap-any">{o.file}</span>
                  <span className="t-caption c-faint">{o.desc}</span>
                </div>
                {i === 0 ? (
                  <button type="button" className="btn-primary" onClick={() => open(o.file)}>
                    開啟
                  </button>
                ) : (
                  <button type="button" className="btn-text" style={{ padding: "0 24px", textShadow: "none" }} onClick={() => open(o.file)}>
                    開啟
                  </button>
                )}
              </div>
            ))}
            {openError && (
              <div style={{ paddingTop: 12 }}>
                <Notice kind="err">{openError}</Notice>
              </div>
            )}
            <div style={{ display: "flex", flexWrap: "wrap", gap: "0 24px" }}>
              <button type="button" className="btn-text secondary" onClick={() => outputDir && revealPath(outputDir)}>
                顯示資料夾
              </button>
              <button type="button" className="btn-text secondary" onClick={onNext}>
                翻下一份
              </button>
            </div>
          </Section>

          {checks.length > 0 && (
            <Section gap={0}>
              <h2 className="t-label" style={{ display: "flex", gap: 12, marginBottom: 8 }}>
                <span className="c-faint">02</span>
                <span>需要檢查的段落</span>
              </h2>
              <p className="t-caption c-muted" style={{ marginBottom: 8 }}>
                模型回傳的格式不對，這些段落改用簡單指令重翻，沒有套用術語表。點一下會在並排版跳到那一頁。
              </p>
              {(showAllChecks ? checks : checks.slice(0, 4)).map((c) => (
                <a
                  key={c.page}
                  href="#"
                  className="row-line"
                  onClick={(e) => e.preventDefault()}
                  style={{ display: "grid", gridTemplateColumns: "56px minmax(0, 1fr) auto", alignItems: "center", gap: 16, minHeight: 56 }}
                >
                  <span className="t-data">P.{c.page}</span>
                  <span className="t-body c-muted" style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                    {c.text}
                  </span>
                  <span className="t-label c-faint">{c.count} 段</span>
                </a>
              ))}
              {checks.length > 4 && (
                <button type="button" className="btn-text secondary row-line" onClick={() => setShowAllChecks(!showAllChecks)}>
                  {showAllChecks ? "收起" : `顯示全部 ${checks.length} 頁`}
                </button>
              )}
            </Section>
          )}
        </div>

        <aside className="col-side">
          <Section gap={0}>
            <h2 className="t-label" style={{ marginBottom: 8 }}>
              已修正的大陸用語
            </h2>
            {DEMO_FIXES.slice(0, 4).map((f) => (
              <div
                key={f.cn}
                className="row-line"
                style={{ display: "grid", gridTemplateColumns: "minmax(0, 1fr) minmax(0, 1fr) 40px", alignItems: "center", gap: 12, minHeight: 44 }}
              >
                <span className="t-body c-faint" style={{ textDecoration: "line-through" }}>
                  {f.cn}
                </span>
                <span className="t-body">{f.tw}</span>
                <span className="t-data" style={{ textAlign: "right" }}>
                  {f.n}
                </span>
              </div>
            ))}
          </Section>

          <Section gap={12}>
            <SectionTitle>看到翻錯的詞</SectionTitle>
            <p className="t-body c-muted">把它加進你的修正表，下次翻這本書的其他章節就會用對的譯名。</p>
            <div>
              <button type="button" className="btn-text" onClick={onEditGlossary}>
                編輯術語表
              </button>
            </div>
          </Section>
        </aside>
      </div>
    </main>
  );
}
