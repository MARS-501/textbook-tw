import type { ReactNode } from "react";
import { Notice, PageStrip, Section, SectionTitle, Tag } from "../components/ui";
import { clock } from "../lib/format";
import { MODEL_NAME, profileName, type JobOptions, type JobView } from "../model";

const STEPS = ["分析版面、辨識圖表與公式", "套用術語表", "翻譯段落並填回原位"];

function StepRow({ index, label, state, right }: { index: number; label: string; state: "done" | "active" | "todo"; right?: ReactNode }) {
  return (
    <li className="row-line" style={{ display: "grid", gridTemplateColumns: "24px minmax(0, 1fr) auto", alignItems: "center", gap: 12, minHeight: 48 }}>
      <span className="t-label c-faint">{String(index + 1).padStart(2, "0")}</span>
      <span className={`t-body${state === "todo" ? " c-faint" : ""}`}>{label}</span>
      <span>{state === "done" ? <Tag kind="done">DONE</Tag> : right}</span>
    </li>
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

export function Progress({
  fileName,
  options,
  view,
  onInterrupt,
  onBack,
}: {
  fileName: string;
  options: JobOptions;
  view: JobView;
  onInterrupt: () => void;
  onBack: () => void;
}) {
  const total = view.pages.length;
  const index = Math.min(view.pagesDone, total - 1);
  const current = view.pages[Math.max(0, index)];
  const translating = view.step === 2;
  const headline =
    view.error !== null
      ? "翻譯停下來了"
      : view.step < 2
        ? "正在分析版面"
        : view.step === 3
          ? options.dual === "none"
            ? "正在整理輸出檔"
            : "正在組出對照版"
          : `正在翻第 ${current} 頁`;
  const lastStep = options.dual === "none" ? "整理輸出檔" : "組出對照版";

  return (
    <main className="main">
      <div className="hero">
        <div style={{ display: "flex", flexDirection: "column", gap: 8, minWidth: 0 }}>
          <span className="t-label c-faint wrap-any">
            {fileName} · {profileName(options.profile)} · {MODEL_NAME}
          </span>
          <div style={{ display: "flex", alignItems: "baseline", gap: 16, flexWrap: "wrap" }}>
            <span className="t-display">{Math.round(view.percent)}%</span>
            <span className="t-focus">{headline}</span>
          </div>
        </div>
        <div className="stats" style={{ textAlign: "right" }}>
          <ReadoutRight label="已用" value={clock(view.elapsed)} />
          <ReadoutRight label="剩下約" value={view.remaining === null ? "—" : clock(view.remaining)} />
          <ReadoutRight label="每頁" value={view.perPage === null ? "—" : `${Math.round(view.perPage)} 秒`} />
        </div>
      </div>

      {view.error !== null && (
        <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
          <Notice kind="err">{view.error}</Notice>
          <div>
            <button type="button" className="btn-text secondary" onClick={onBack}>
              回到設定
            </button>
          </div>
        </div>
      )}

      <PageStrip
        total={total}
        height={160}
        label={`共 ${total} 頁，已翻好約 ${view.pagesDone} 頁`}
        bar={(i) => {
          if (i <= view.pagesDone) return { height: 160, background: "var(--ink)" };
          if (translating && i === view.pagesDone + 1) return { width: 2, height: 96, background: "var(--ink)", boxShadow: "var(--glow-ink)" };
          return { height: 24, background: "var(--line-strong)" };
        }}
      />

      <div className="columns">
        <div className="col-main">
          <Section>
            <SectionTitle>剛翻好的段落</SectionTitle>
            {view.paragraphs.length === 0 ? (
              <p className="t-body c-faint">{view.step < 2 ? "版面分析完就會開始翻譯段落。" : "第一批段落翻好後會出現在這裡。"}</p>
            ) : (
              <div style={{ display: "flex", flexDirection: "column", maskImage: "linear-gradient(to bottom, transparent 0, #000 24px)" }}>
                {view.paragraphs.map((p, i) => (
                  <div
                    key={`${i}-${p.en.slice(0, 24)}`}
                    className={i < view.paragraphs.length - 1 ? "row-line-bottom" : undefined}
                    style={{ display: "grid", gridTemplateColumns: "minmax(0, 1fr) minmax(0, 1fr)", gap: 24, padding: "16px 0" }}
                  >
                    <p lang="en" className="t-body c-muted wrap-any">
                      {p.en}
                    </p>
                    {p.zh === null ? (
                      <p className="t-body c-faint">翻譯中…</p>
                    ) : (
                      <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                        <p className="t-body wrap-any">{p.zh}</p>
                        {p.fixed && (
                          <div style={{ display: "flex", flexWrap: "wrap", alignItems: "center", gap: "0 12px" }}>
                            <span className="t-label">已改</span>
                            <span className="t-caption c-muted">
                              {p.fixed.from} 換成 {p.fixed.to}
                            </span>
                          </div>
                        )}
                      </div>
                    )}
                  </div>
                ))}
              </div>
            )}
          </Section>
        </div>

        <aside className="col-side">
          <Section gap={0}>
            <h2 className="t-label" style={{ marginBottom: 8 }}>
              步驟
            </h2>
            <ol style={{ margin: 0, padding: 0, listStyle: "none", display: "flex", flexDirection: "column" }}>
              {STEPS.map((label, i) => (
                <StepRow
                  key={label}
                  index={i}
                  label={label}
                  state={view.step > i ? "done" : view.step === i ? "active" : "todo"}
                  right={
                    i === 2 && translating ? (
                      <Tag kind="outline">
                        {view.pagesDone} / {total}
                      </Tag>
                    ) : undefined
                  }
                />
              ))}
              <StepRow index={3} label={lastStep} state={view.step === 3 ? "active" : "todo"} />
            </ol>
          </Section>

          <Section gap={12}>
            <SectionTitle>到目前為止</SectionTitle>
            {view.fixes !== null && (
              <div style={{ display: "flex", justifyContent: "space-between", gap: 16 }}>
                <span className="t-body c-muted">大陸用語修正</span>
                <span className="t-data">{view.fixes} 處</span>
              </div>
            )}
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 16 }}>
              <span className="t-body c-muted">改用簡單指令重翻</span>
              <span style={{ display: "flex", alignItems: "center", gap: 8 }}>
                {view.fallbacks > 0 && <Tag kind="due">DUE</Tag>}
                <span className="t-data">{view.fallbacks} 段</span>
              </span>
            </div>
            <p className="t-caption c-muted">模型回傳的格式不對時，那一段會用簡單指令重翻，不帶術語表。完成後會告訴你有幾段要檢查。</p>
          </Section>

          {view.error === null && (
            <Section gap={4}>
              <div>
                <button type="button" className="btn-text secondary" onClick={onInterrupt}>
                  中斷翻譯
                </button>
              </div>
              <p className="t-caption c-muted">已翻好的段落有快取。中斷後再開始同一份檔案，翻過的段落會直接沿用，很快就跑到這裡。</p>
            </Section>
          )}
        </aside>
      </div>
    </main>
  );
}
