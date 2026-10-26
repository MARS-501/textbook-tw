import { PageStrip, Section, SectionTitle, Tag } from "../components/ui";
import { DEMO_ANALYSIS_SECONDS, DEMO_PARAGRAPHS } from "../demo";
import { clock } from "../lib/format";
import { MODEL_NAME, SEC_PER_PAGE, profileName, type Doc, type JobOptions } from "../model";

export interface RunningJob {
  pages: number[]; // 要翻的頁碼（1 起算）
  done: number; // 已翻好幾頁
}

function Step({ index, label, state }: { index: string; label: string; state: "done" | "active" | "todo"; }) {
  return (
    <li
      className="row-line"
      style={{ display: "grid", gridTemplateColumns: "24px minmax(0, 1fr) auto", alignItems: "center", gap: 12, minHeight: 48 }}
    >
      <span className="t-label c-faint">{index}</span>
      <span className={`t-body${state === "todo" ? " c-faint" : ""}`}>{label}</span>
      <span>{state === "done" && <Tag kind="done">DONE</Tag>}</span>
    </li>
  );
}

export function Progress({ doc, options, job, onInterrupt }: { doc: Doc | null; options: JobOptions; job: RunningJob; onInterrupt: () => void }) {
  const total = job.pages.length;
  const current = job.pages[Math.min(job.done, total - 1)];
  const prev = job.pages[Math.max(0, job.done - 1)];
  const percent = Math.round((job.done / total) * 100);
  const name = doc?.file.name ?? "示範.pdf";

  return (
    <main className="main">
      <div className="hero">
        <div style={{ display: "flex", flexDirection: "column", gap: 8, minWidth: 0 }}>
          <span className="t-label c-faint wrap-any">
            {name} · {profileName(options.profile)} · {MODEL_NAME}
          </span>
          <div style={{ display: "flex", alignItems: "baseline", gap: 16, flexWrap: "wrap" }}>
            <span className="t-display">{percent}%</span>
            <span className="t-focus">正在翻第 {current} 頁</span>
          </div>
        </div>
        <div className="stats" style={{ textAlign: "right" }}>
          <ReadoutRight label="已用" value={clock(DEMO_ANALYSIS_SECONDS + job.done * SEC_PER_PAGE)} />
          <ReadoutRight label="剩下約" value={clock((total - job.done) * SEC_PER_PAGE + 20)} />
          <ReadoutRight label="每頁" value={`${SEC_PER_PAGE} 秒`} />
        </div>
      </div>

      <PageStrip
        total={total}
        height={160}
        label={`共 ${total} 頁，已翻好 ${job.done} 頁，正在翻第 ${current} 頁`}
        bar={(i) => {
          if (i <= job.done) return { height: 160, background: "var(--ink)" };
          if (i === job.done + 1) return { width: 2, height: 96, background: "var(--ink)", boxShadow: "var(--glow-ink)" };
          return { height: 24, background: "var(--line-strong)" };
        }}
      />

      <div className="columns">
        <div className="col-main">
          <Section>
            <SectionTitle>剛翻好的段落</SectionTitle>
            <div style={{ display: "flex", flexDirection: "column", maskImage: "linear-gradient(to bottom, transparent 0, #000 24px)" }}>
              {DEMO_PARAGRAPHS.map((p, i) => (
                <div
                  key={i}
                  className={i < DEMO_PARAGRAPHS.length - 1 ? "row-line-bottom" : undefined}
                  style={{ display: "grid", gridTemplateColumns: "48px minmax(0, 1fr) minmax(0, 1fr)", gap: 24, padding: "16px 0" }}
                >
                  <span className="t-label c-faint" style={{ lineHeight: "22px" }}>
                    P.{i === 0 ? prev : current}
                  </span>
                  <p lang="en" className="t-body c-muted">
                    {p.en}
                  </p>
                  {p.zh === null ? (
                    <p className="t-body c-faint">翻譯中…</p>
                  ) : (
                    <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                      <p className="t-body">{p.zh}</p>
                      {p.fixed && (
                        <div style={{ display: "flex", flexWrap: "wrap", alignItems: "center", gap: "0 12px" }}>
                          <span className="t-label">已改</span>
                          <span className="t-caption c-muted">
                            {p.fixed.from} 換成 {p.fixed.to}
                          </span>
                          <button type="button" className="btn-text secondary">
                            復原
                          </button>
                        </div>
                      )}
                    </div>
                  )}
                </div>
              ))}
            </div>
          </Section>
        </div>

        <aside className="col-side">
          <Section gap={0}>
            <h2 className="t-label" style={{ marginBottom: 8 }}>
              步驟
            </h2>
            <ol style={{ margin: 0, padding: 0, listStyle: "none", display: "flex", flexDirection: "column" }}>
              <Step index="01" label="分析版面、辨識圖表與公式" state="done" />
              <Step index="02" label="套用術語表" state="done" />
              <li
                className="row-line"
                style={{ display: "grid", gridTemplateColumns: "24px minmax(0, 1fr) auto", alignItems: "center", gap: 12, minHeight: 48 }}
              >
                <span className="t-label c-faint">03</span>
                <span className="t-body">翻譯段落並填回原位</span>
                <Tag kind="outline">
                  {job.done} / {total}
                </Tag>
              </li>
              <Step index="04" label={options.dual === "none" ? "整理輸出檔" : "組出對照版"} state="todo" />
            </ol>
          </Section>

          <Section gap={12}>
            <SectionTitle>到目前為止</SectionTitle>
            <div style={{ display: "flex", justifyContent: "space-between", gap: 16 }}>
              <span className="t-body c-muted">大陸用語修正</span>
              <span className="t-data">{Math.round(job.done * 0.12)} 處</span>
            </div>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 16 }}>
              <span className="t-body c-muted">改用簡單指令重翻</span>
              <span style={{ display: "flex", alignItems: "center", gap: 8 }}>
                {job.done >= 40 && <Tag kind="due">DUE</Tag>}
                <span className="t-data">{Math.floor(job.done / 40)} 段</span>
              </span>
            </div>
            <p className="t-caption c-muted">模型回傳的格式不對時，那一段會用簡單指令重翻，不帶術語表。完成後會列出這些段落讓你檢查。</p>
          </Section>

          <Section gap={4}>
            <div>
              <button type="button" className="btn-text secondary" onClick={onInterrupt}>
                中斷翻譯
              </button>
            </div>
            <p className="t-caption c-muted">已翻好的段落有快取。中斷後再開始同一份檔案，會從第 {current} 頁接著翻。</p>
          </Section>
        </aside>
      </div>
    </main>
  );
}

function ReadoutRight({ label, value }: { label: string; value: string }) {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 4, textAlign: "right" }}>
      <span className="t-label c-faint">{label}</span>
      <span className="t-data">{value}</span>
    </div>
  );
}
