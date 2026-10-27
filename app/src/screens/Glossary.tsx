import { useState } from "react";
import { PICK_NONE, PICK_PER_PARAGRAPH, PICK_SKIP, type ReviewTerm } from "../bridge";
import { Notice, Section, SectionTitle, Tag } from "../components/ui";

// 英文 → 選第幾個譯名；或 PICK_NONE（還沒選）、PICK_PER_PARAGRAPH（依段落）、PICK_SKIP（不套用）
export type Picks = Record<string, number>;

export function initialPicks(review: ReviewTerm[]): Picks {
  return Object.fromEntries(review.map((t) => [t.source, t.pick]));
}

/** 選的結果寫成術語表的 target：依段落選的用「｜」串起來，不套用是空字串。 */
export function targetOf(term: ReviewTerm, pick: number): string | null {
  if (pick >= 0) return term.options[pick].zh;
  if (pick === PICK_PER_PARAGRAPH) return term.paragraph.map((i) => term.options[i].zh).join("｜");
  if (pick === PICK_SKIP) return "";
  return null;
}

/** 模型判斷術語的狀態：null 代表還沒開始或不需要。 */
export type ResolveState =
  | { phase: "running"; done: number; total: number }
  | { phase: "stopped"; pending: number } // 使用者停掉了，或 Ollama 沒開
  | { phase: "failed"; message: string };

const MIN_SHOWN = 6;
const SECONDS_PER_TERM = 1; // 實測：qwen3.5:4b 每批 8 個詞約 7.5 秒

/** 先列出必須選的（還沒選），不足 6 個再補其他詞，其餘收起來。 */
function splitShown(review: ReviewTerm[], picks: Picks): [ReviewTerm[], ReviewTerm[]] {
  const required = review.filter((t) => (picks[t.source] ?? t.pick) === PICK_NONE);
  const others = review.filter((t) => (picks[t.source] ?? t.pick) !== PICK_NONE);
  const fill = Math.max(0, MIN_SHOWN - required.length);
  return [[...required, ...others.slice(0, fill)], others.slice(fill)];
}

function TermRow({ term, pick, onPick }: { term: ReviewTerm; pick: number; onPick: (index: number) => void }) {
  const fromModel = term.note !== "";
  return (
    <div role="group" aria-label={term.source} className="row-line-bottom" style={{ display: "flex", flexWrap: "wrap", gap: "8px 32px", padding: "20px 0" }}>
      <div style={{ flex: "1 1 260px", minWidth: 0, display: "flex", flexDirection: "column", gap: 6 }}>
        <div style={{ display: "flex", alignItems: "baseline", gap: 12, flexWrap: "wrap" }}>
          <span className="t-heading">{term.source}</span>
          <span className="t-label c-faint">
            {term.page > 0 ? `p.${term.page} 等 ${term.count} 處` : `${term.count} 處`}
          </span>
        </div>
        <span lang="en" className="t-body c-muted">
          {term.context}
        </span>
        {fromModel && (
          <span style={{ display: "flex", alignItems: "baseline", gap: 8, flexWrap: "wrap" }}>
            <Tag kind="outline">{term.status}</Tag>
            <span className="t-caption c-muted">{term.note}</span>
          </span>
        )}
      </div>
      <div role="radiogroup" aria-label={`${term.source} 的譯名`} style={{ flex: "1 1 320px", display: "flex", flexWrap: "wrap", gap: "0 24px", alignContent: "flex-start" }}>
        {term.options.map((o, i) => (
          <button key={o.zh} type="button" role="radio" aria-checked={pick === i} className="seg" onClick={() => onPick(i)} style={{ gap: 8 }}>
            <span className="t-body">{o.zh}</span>
            <span className="t-label c-faint">{o.src}</span>
          </button>
        ))}
        {term.paragraph.length > 1 && (
          <button type="button" role="radio" aria-checked={pick === PICK_PER_PARAGRAPH} className="seg" onClick={() => onPick(PICK_PER_PARAGRAPH)} style={{ gap: 8 }}>
            <span className="t-body">依段落：{term.paragraph.map((i) => term.options[i].zh).join("／")}</span>
          </button>
        )}
        <button type="button" role="radio" aria-checked={pick === PICK_SKIP} className="seg" onClick={() => onPick(PICK_SKIP)} style={{ gap: 8 }}>
          <span className="t-body c-muted">不套用</span>
        </button>
      </div>
    </div>
  );
}

function describe(props: GlossaryProps, list: ReviewTerm[], left: number): string {
  const { review, resolve } = props;
  if (props.error) return "掃描術語時出錯了。";
  if (review === null) return "正在掃描全書，從名詞庫找出文中用到的專業術語。第一次掃描一本書約需十幾秒。";
  if (resolve?.phase === "running") {
    const minutes = Math.max(1, Math.round(((resolve.total - resolve.done) * SECONDS_PER_TERM) / 60));
    return `掃描全書後找到 ${props.total} 個專業術語。模型正在讀這份文件，依上下文替 ${resolve.total} 個詞挑譯名，大約還要 ${minutes} 分鐘。`;
  }
  const suggested = list.filter((t) => t.status === "模型建議").length;
  const perParagraph = list.filter((t) => t.status === "依段落").length;
  const parts = [`掃描全書後找到 ${props.total} 個專業術語`];
  if (suggested > 0) parts.push(`模型依這份文件的上下文替 ${suggested} 個詞選了譯名`);
  if (perParagraph > 0) parts.push(`${perParagraph} 個詞在文中有不同意思，翻譯時依段落挑`);
  if (left > 0) parts.push(`${left} 個要你選`);
  return `${parts.join("，")}。選好的譯名會存成這本書的術語表，以後翻同一本的其他章節會沿用。`;
}

export interface GlossaryProps {
  meta: string;
  total: number;
  review: ReviewTerm[] | null; // null = 掃描中
  error: string | null;
  picks: Picks;
  onPicks: (next: Picks) => void;
  myTerms: [string, string][];
  onAddMyTerm: (source: string, target: string) => void;
  busy: boolean; // 正在寫入術語表、啟動翻譯
  resolve: ResolveState | null;
  onResolve: () => void; // 讓模型依上下文判斷（重新開始）
  onStopResolve: () => void;
  onApply: () => void;
  onSkip: () => void;
  onRetry: () => void;
  fixes: { cn: string; tw: string; en: string }[] | null; // 大陸用語修正：功能還沒做時為 null
  keep: { name: string; pages: string }[] | null; // 保留原文的名稱：功能還沒做時為 null
}

export function Glossary(props: GlossaryProps) {
  const { review, picks } = props;
  const [showAll, setShowAll] = useState(false);
  const [source, setSource] = useState("");
  const [target, setTarget] = useState("");
  const [addError, setAddError] = useState<string | null>(null);

  function addTerm() {
    if (!source.trim() || !target.trim()) {
      setAddError("英文和譯名都要填。");
      return;
    }
    props.onAddMyTerm(source.trim(), target.trim());
    setSource("");
    setTarget("");
    setAddError(null);
  }

  const list = review ?? [];
  const [shown, hidden] = splitShown(list, picks);
  const visible = showAll ? [...shown, ...hidden] : shown;
  const left = list.filter((t) => (picks[t.source] ?? t.pick) === PICK_NONE).length;
  const resolving = props.resolve?.phase === "running";
  const ready = review !== null && left === 0 && !resolving;
  const description = describe(props, list, left);

  return (
    <main className="main">
      <div className="hero">
        <div style={{ display: "flex", flexDirection: "column", gap: 8, maxWidth: 640 }}>
          <span className="t-label c-faint wrap-any">{props.meta}</span>
          <h1 className="t-title">術語確認</h1>
          <p className="t-body c-muted">{description}</p>
        </div>
        <div style={{ display: "flex", flexDirection: "column", gap: 8, textAlign: "right" }}>
          <span className="t-display">{review === null ? "—" : left}</span>
          <span className="t-label c-faint">個詞還沒選</span>
        </div>
      </div>

      {props.error && (
        <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
          <Notice kind="err">{props.error}</Notice>
          <div>
            <button type="button" className="btn-text secondary" onClick={props.onRetry}>
              再掃描一次
            </button>
          </div>
        </div>
      )}

      {props.resolve?.phase === "running" && (
        <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
          <div
            role="progressbar"
            aria-label="模型判斷術語譯名"
            aria-valuemin={0}
            aria-valuemax={props.resolve.total}
            aria-valuenow={props.resolve.done}
            style={{ height: 2, background: "var(--line)" }}
          >
            <div style={{ height: 2, width: `${props.resolve.total ? (props.resolve.done / props.resolve.total) * 100 : 0}%`, background: "var(--ink)" }} />
          </div>
          <div style={{ display: "flex", flexWrap: "wrap", alignItems: "center", gap: "0 24px" }}>
            <span className="t-data">
              {props.resolve.done} / {props.resolve.total}
            </span>
            <span className="t-caption c-muted">判斷完會更新下面的選擇；你先改過的會保留。</span>
            <button type="button" className="btn-text secondary" onClick={props.onStopResolve}>
              停止判斷
            </button>
          </div>
        </div>
      )}
      {props.resolve?.phase === "stopped" && (
        <div style={{ display: "flex", flexWrap: "wrap", alignItems: "center", gap: "8px 24px" }}>
          <Notice kind="due">還有 {props.resolve.pending} 個詞沒讓模型依上下文判斷，目前用科目的名詞庫順序。</Notice>
          <button type="button" className="btn-text secondary" onClick={props.onResolve}>
            讓模型判斷
          </button>
        </div>
      )}
      {props.resolve?.phase === "failed" && (
        <div style={{ display: "flex", flexWrap: "wrap", alignItems: "center", gap: "8px 24px" }}>
          <Notice kind="err">模型判斷術語時出錯：{props.resolve.message}</Notice>
          <button type="button" className="btn-text secondary" onClick={props.onResolve}>
            再試一次
          </button>
        </div>
      )}

      <div className="columns">
        <div className="col-main">
          <Section gap={4}>
            <SectionTitle index="01" right={review ? `${visible.length} / ${list.length}` : "掃描中…"}>
              需要看一下的詞
            </SectionTitle>
            {visible.map((t) => (
              <TermRow key={t.source} term={t} pick={picks[t.source] ?? t.pick} onPick={(i) => props.onPicks({ ...picks, [t.source]: i })} />
            ))}
            {review !== null && list.length === 0 && <p className="t-body c-muted" style={{ padding: "20px 0" }}>這份文件沒有需要選的詞。</p>}
            {hidden.length > 0 && (
              <div style={{ display: "flex", flexWrap: "wrap", alignItems: "center", gap: "0 24px" }}>
                <button type="button" className="btn-text secondary" onClick={() => setShowAll(!showAll)}>
                  {showAll ? "收起" : `顯示其餘 ${hidden.length} 個`}
                </button>
                {!showAll && <span className="t-caption c-faint">其餘 {hidden.length} 個都已選好（模型建議或科目的名詞庫順序）。</span>}
              </div>
            )}
          </Section>

          {props.fixes && (
            <Section gap={4}>
              <SectionTitle index="02">大陸用語修正</SectionTitle>
              <p className="t-caption c-muted" style={{ margin: "8px 0" }}>
                小模型常寫出大陸用語。翻完後，左邊的詞會自動換成右邊的台灣用語。
              </p>
              {props.fixes.map((f) => (
                <div
                  key={f.cn}
                  className="row-line"
                  style={{ display: "grid", gridTemplateColumns: "minmax(0, 1fr) 24px minmax(0, 1fr) minmax(0, 1fr)", alignItems: "center", gap: 16, minHeight: 48 }}
                >
                  <span className="t-body c-faint" style={{ textDecoration: "line-through" }}>
                    {f.cn}
                  </span>
                  <svg aria-hidden="true" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="var(--ink-muted)" strokeWidth="1.5" strokeLinecap="square">
                    <path d="M4 12h15M13 6l6 6-6 6" />
                  </svg>
                  <span className="t-body">{f.tw}</span>
                  <span lang="en" className="t-label c-faint" style={{ textAlign: "right" }}>
                    {f.en}
                  </span>
                </div>
              ))}
            </Section>
          )}
        </div>

        <aside className="col-side">
          <Section gap={12}>
            <SectionTitle>加一條我的譯名</SectionTitle>
            <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
              <label htmlFor="src" className="t-label c-faint">
                英文
              </label>
              <input id="src" className="input-line" type="text" placeholder="airfoil" value={source} onChange={(e) => setSource(e.target.value)} />
            </div>
            <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
              <label htmlFor="dst" className="t-label c-faint">
                譯名
              </label>
              <input
                id="dst"
                className="input-line zh"
                type="text"
                placeholder="翼型"
                value={target}
                onChange={(e) => setTarget(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && addTerm()}
              />
            </div>
            <div>
              <button type="button" className="btn-text" onClick={addTerm}>
                加入修正表
              </button>
            </div>
            {addError && <Notice kind="err">{addError}</Notice>}
            {props.myTerms.map(([s, t]) => (
              <div key={s} className="row-line" style={{ display: "flex", justifyContent: "space-between", gap: 12, minHeight: 40, alignItems: "center" }}>
                <span className="t-data">{s}</span>
                <span className="t-body">{t}</span>
              </div>
            ))}
            <p className="t-caption c-muted">
              {props.myTerms.length > 0
                ? "開始翻譯時存進 my_terms.csv。你的修正優先於所有名詞庫，每本書都會用。"
                : "存進 my_terms.csv。你的修正優先於所有名詞庫，每本書都會用。"}
            </p>
          </Section>

          {props.keep && (
            <Section gap={4}>
              <SectionTitle>保留原文的名稱</SectionTitle>
              <p className="t-caption c-muted" style={{ margin: "8px 0" }}>
                機構、人名和代號不翻譯，避免小模型自己編出中文名稱。
              </p>
              {props.keep.map((k) => (
                <div key={k.name} className="row-line" style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 12, minHeight: 48 }}>
                  <span className="t-data wrap-any">{k.name}</span>
                  <span className="t-label c-faint" style={{ flex: "none" }}>
                    {k.pages}
                  </span>
                </div>
              ))}
            </Section>
          )}
        </aside>
      </div>

      <div className="row-line" style={{ display: "flex", flexWrap: "wrap", alignItems: "center", gap: "8px 24px", paddingTop: 24 }}>
        <button type="button" className="btn-primary" disabled={!ready || props.busy} onClick={props.onApply}>
          {props.busy ? "準備中…" : resolving ? "模型判斷中…" : "套用並開始翻譯"}
        </button>
        <button type="button" className="btn-text secondary" disabled={review === null || props.busy || resolving} onClick={props.onSkip}>
          略過，照目前的選擇
        </button>
        <span className="t-caption c-faint">
          {review === null
            ? "掃描完成後就能開始。"
            : resolving
              ? "模型判斷完就能開始；也可以先停止判斷。"
              : ready
                ? "會寫入這本書的術語表，各章沿用。"
                : `還有 ${left} 個詞沒選。選好才能套用，或略過、這些詞翻譯時不套用術語表。`}
        </span>
      </div>
    </main>
  );
}
