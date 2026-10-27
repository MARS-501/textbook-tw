import { useState } from "react";
import { openPath, revealPath } from "../bridge";
import { Notice, PageStrip, Section, SectionTitle, Stat } from "../components/ui";
import { DEMO_CHECKS, DEMO_FIXES } from "../demo";
import { clock, formatBytes } from "../lib/format";
import { MODEL_NAME, profileName, type FinishedJob } from "../model";

const OUTPUT_LABELS = {
  side_by_side: (first: boolean) => (first ? "每頁左譯文、右原文" : "每頁左原文、右譯文"),
  alternating: (first: boolean) => (first ? "譯文頁、原文頁輪流" : "原文頁、譯文頁輪流"),
  mono: () => "純譯文版",
};

function stamp(iso: string): string {
  const d = new Date(iso);
  const days = ["SUN", "MON", "TUE", "WED", "THU", "FRI", "SAT"];
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${days[d.getDay()]} ${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

function baseName(p: string): string {
  return p.split(/[\\/]/).pop() ?? p;
}

function dirName(p: string): string {
  const i = Math.max(p.lastIndexOf("\\"), p.lastIndexOf("/"));
  return i > 0 ? p.slice(0, i) : p;
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

  const { options, pages } = result;
  const total = pages.length;
  const folder = result.outputs.length > 0 ? dirName(result.outputs[0].path) : null;
  // 示範資料才有「哪幾頁要檢查」；真實翻譯目前只知道總段數
  const checks = result.demo ? DEMO_CHECKS.filter((c) => pages.includes(c.page)) : [];
  const flaggedIndex = new Set(pages.map((p, i) => (checks.some((c) => c.page === p) ? i + 1 : 0)).filter(Boolean));
  const toCheck = result.demo ? checks.reduce((n, c) => n + c.count, 0) : result.fallbacks;
  const perPage = total > 0 ? Math.round(result.seconds / total) : 0;

  async function open(target: string) {
    const error = await openPath(target);
    setOpenError(error ? (result?.demo ? "找不到檔案。這是示範資料，沒有真的產生檔案。" : `打不開這個檔案：${error}`) : null);
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
            <span className="t-focus wrap-any">{result.fileName} 翻好了</span>
          </div>
        </div>
        <div className="stats" style={{ textAlign: "right" }}>
          <Stat label="頁數" value={total} align="right" />
          <Stat label="每頁" value={`${perPage} 秒`} align="right" />
          <Stat label="要檢查" value={`${toCheck} 段`} align="right" />
        </div>
      </div>

      <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
        <PageStrip
          total={total}
          height={160}
          label={`${total} 頁都翻好了${flaggedIndex.size > 0 ? `，其中 ${flaggedIndex.size} 頁有段落需要檢查` : ""}`}
          bar={(i) => ({ height: flaggedIndex.has(i) ? 112 : 160, background: flaggedIndex.has(i) ? "var(--line-strong)" : "var(--ink)" })}
          marks={flaggedIndex.size > 0 ? (i) => (flaggedIndex.has(i) ? { width: 6, margin: "0 -2.5px", background: "var(--warn)" } : {}) : undefined}
        />
        {flaggedIndex.size > 0 && <Notice kind="due">短線與下方的點：這一頁有段落沒有套用術語表，建議對照原文看一下。</Notice>}
      </div>

      <div className="columns">
        <div className="col-main">
          <Section gap={0}>
            <div style={{ marginBottom: 8 }}>
              <SectionTitle index="01" right={folder ?? ""}>
                檔案
              </SectionTitle>
            </div>
            {result.outputs.map((o, i) => (
              <div
                key={o.path}
                className={`row-line${i === result.outputs.length - 1 ? " row-line-bottom" : ""}`}
                style={{ display: "flex", flexWrap: "wrap", alignItems: "center", justifyContent: "space-between", gap: "0 24px", minHeight: 64 }}
              >
                <div style={{ display: "flex", flexDirection: "column", minWidth: 0, padding: "8px 0" }}>
                  <span className="t-body wrap-any">{baseName(o.path)}</span>
                  <span className="t-caption c-faint">
                    {OUTPUT_LABELS[o.kind](options.translatedFirst)}
                    {o.kind === "alternating" ? `，${total * 2} 頁` : ""}
                    {o.size !== null ? ` · ${formatBytes(o.size)}` : ""}
                  </span>
                </div>
                {i === 0 ? (
                  <button type="button" className="btn-primary" onClick={() => open(o.path)}>
                    開啟
                  </button>
                ) : (
                  <button type="button" className="btn-text" style={{ padding: "0 24px", textShadow: "none" }} onClick={() => open(o.path)}>
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
              {result.outputs[0] && (
                <button type="button" className="btn-text secondary" onClick={() => revealPath(result.outputs[0].path)}>
                  顯示資料夾
                </button>
              )}
              <button type="button" className="btn-text secondary" onClick={onNext}>
                翻下一份
              </button>
            </div>
          </Section>

          {toCheck > 0 && (
            <Section gap={0}>
              <h2 className="t-label" style={{ display: "flex", gap: 12, marginBottom: 8 }}>
                <span className="c-faint">02</span>
                <span>需要檢查的段落</span>
              </h2>
              <p className="t-caption c-muted" style={{ marginBottom: 8 }}>
                模型回傳的格式不對，這些段落改用簡單指令重翻，沒有套用術語表。
                {result.demo ? "點一下會在並排版跳到那一頁。" : `這次共 ${result.fallbacks} 段；目前還無法對應到頁碼，請在並排版大致瀏覽一下。`}
              </p>
              {(showAllChecks ? checks : checks.slice(0, 4)).map((c) => (
                <div
                  key={c.page}
                  className="row-line"
                  style={{ display: "grid", gridTemplateColumns: "56px minmax(0, 1fr) auto", alignItems: "center", gap: 16, minHeight: 56 }}
                >
                  <span className="t-data">P.{c.page}</span>
                  <span className="t-body c-muted" style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                    {c.text}
                  </span>
                  <span className="t-label c-faint">{c.count} 段</span>
                </div>
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
          {result.demo && (
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
          )}

          {result.perParagraph && result.perParagraph.length > 0 && (
            <Section gap={0}>
              <h2 className="t-label" style={{ marginBottom: 8 }}>
                依段落選的譯名
              </h2>
              <p className="t-caption c-muted" style={{ marginBottom: 8 }}>
                這些詞在文中有不同意思，模型逐段挑了譯名。數字是用到的段落數。
              </p>
              {result.perParagraph.map((u) => (
                <div
                  key={u.source}
                  className="row-line"
                  style={{ display: "flex", flexWrap: "wrap", justifyContent: "space-between", alignItems: "center", gap: "4px 12px", minHeight: 44 }}
                >
                  <span lang="en" className="t-data">
                    {u.source}
                  </span>
                  <span className="t-body">
                    {Object.entries(u.counts)
                      .map(([zh, n]) => `${zh} ${n}`)
                      .join(" · ")}
                  </span>
                </div>
              ))}
            </Section>
          )}

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
