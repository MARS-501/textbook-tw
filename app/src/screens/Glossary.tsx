import { useState } from "react";
import { Notice, Section, SectionTitle } from "../components/ui";
import { DEMO_FIXES, DEMO_KEEP, DEMO_TERMS, DEMO_TERMS_PRESET, type TermChoice } from "../demo";
import { profileName, type Doc, type JobOptions } from "../model";

const FOUND_TERMS = 312; // 示範：掃描全書找到的術語數

export type Picks = Record<string, number>;

export function initialPicks(): Picks {
  const picks: Picks = {};
  for (const t of [...DEMO_TERMS, ...DEMO_TERMS_PRESET]) picks[t.id] = t.suggest;
  return picks;
}

function TermRow({ term, pick, onPick }: { term: TermChoice; pick: number; onPick: (index: number) => void }) {
  return (
    <div role="group" aria-label={term.term} className="row-line-bottom" style={{ display: "flex", flexWrap: "wrap", gap: "8px 32px", padding: "20px 0" }}>
      <div style={{ flex: "1 1 260px", minWidth: 0, display: "flex", flexDirection: "column", gap: 6 }}>
        <div style={{ display: "flex", alignItems: "baseline", gap: 12, flexWrap: "wrap" }}>
          <span className="t-heading">{term.term}</span>
          <span className="t-label c-faint">{term.where}</span>
        </div>
        <span lang="en" className="t-body c-muted">
          {term.context}
        </span>
      </div>
      <div role="radiogroup" aria-label={`${term.term} 的譯名`} style={{ flex: "1 1 320px", display: "flex", flexWrap: "wrap", gap: "0 24px", alignContent: "flex-start" }}>
        {term.options.map((o, i) => (
          <button key={o.zh} type="button" role="radio" aria-checked={pick === i} className="seg" onClick={() => onPick(i)} style={{ gap: 8 }}>
            <span className="t-body">{o.zh}</span>
            <span className="t-label c-faint">{o.src}</span>
          </button>
        ))}
      </div>
    </div>
  );
}

export function Glossary({
  doc,
  options,
  picks,
  onPicks,
  onApply,
}: {
  doc: Doc | null;
  options: JobOptions;
  picks: Picks;
  onPicks: (next: Picks) => void;
  onApply: () => void;
}) {
  const [showAll, setShowAll] = useState(false);
  const [source, setSource] = useState("");
  const [target, setTarget] = useState("");
  const [addError, setAddError] = useState<string | null>(null);
  const [added, setAdded] = useState<{ source: string; target: string }[]>([]);

  const allTerms = [...DEMO_TERMS, ...DEMO_TERMS_PRESET];
  const shown = showAll ? allTerms : DEMO_TERMS;
  const left = allTerms.filter((t) => picks[t.id] < 0).length;
  const ready = left === 0;

  function addTerm() {
    if (!source.trim() || !target.trim()) {
      setAddError("英文和譯名都要填。");
      return;
    }
    setAdded([...added, { source: source.trim(), target: target.trim() }]);
    setSource("");
    setTarget("");
    setAddError(null);
  }

  const meta = doc ? `${doc.file.name} · ${doc.pageCount} 頁 · ${profileName(options.profile)}` : `示範 · ${profileName(options.profile)}`;

  return (
    <main className="main">
      <div className="hero">
        <div style={{ display: "flex", flexDirection: "column", gap: 8, maxWidth: 640 }}>
          <span className="t-label c-faint wrap-any">{meta}</span>
          <h1 className="t-title">術語確認</h1>
          <p className="t-body c-muted">
            掃描全書後找到 {FOUND_TERMS} 個專業術語，其中 {allTerms.length} 個在不同名詞庫有不同譯名。選好的譯名會存成這本書的術語表，以後翻同一本的其他章節會沿用。
          </p>
        </div>
        <div style={{ display: "flex", flexDirection: "column", gap: 8, textAlign: "right" }}>
          <span className="t-display">{left}</span>
          <span className="t-label c-faint">個詞還沒選</span>
        </div>
      </div>

      <div className="columns">
        <div className="col-main">
          <Section gap={4}>
            <SectionTitle index="01" right={`${shown.length} / ${allTerms.length}`}>
              有多個譯名的詞
            </SectionTitle>
            {shown.map((t) => (
              <TermRow key={t.id} term={t} pick={picks[t.id]} onPick={(i) => onPicks({ ...picks, [t.id]: i })} />
            ))}
            <div style={{ display: "flex", flexWrap: "wrap", alignItems: "center", gap: "0 24px" }}>
              <button type="button" className="btn-text secondary" onClick={() => setShowAll(!showAll)}>
                {showAll ? "收起" : `顯示其餘 ${DEMO_TERMS_PRESET.length} 個`}
              </button>
              {!showAll && <span className="t-caption c-faint">其餘 {DEMO_TERMS_PRESET.length} 個都已依科目的名詞庫順序選好。</span>}
            </div>
          </Section>

          <Section gap={4}>
            <SectionTitle index="02">大陸用語修正</SectionTitle>
            <p className="t-caption c-muted" style={{ margin: "8px 0" }}>
              小模型常寫出大陸用語。翻完後，左邊的詞會自動換成右邊的台灣用語。
            </p>
            {DEMO_FIXES.map((f) => (
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
            {added.map((a) => (
              <div key={a.source} className="row-line" style={{ display: "flex", justifyContent: "space-between", gap: 12, minHeight: 40, alignItems: "center" }}>
                <span className="t-data">{a.source}</span>
                <span className="t-body">{a.target}</span>
              </div>
            ))}
            <p className="t-caption c-muted">存進 my_terms.csv。你的修正優先於所有名詞庫，每本書都會用。</p>
          </Section>

          <Section gap={4}>
            <SectionTitle>保留原文的名稱</SectionTitle>
            <p className="t-caption c-muted" style={{ margin: "8px 0" }}>
              機構、人名和代號不翻譯，避免小模型自己編出中文名稱。
            </p>
            {DEMO_KEEP.map((k) => (
              <div key={k.name} className="row-line" style={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 12, minHeight: 48 }}>
                <span className="t-data wrap-any">{k.name}</span>
                <span className="t-label c-faint" style={{ flex: "none" }}>
                  {k.pages}
                </span>
              </div>
            ))}
          </Section>
        </aside>
      </div>

      <div className="row-line" style={{ display: "flex", flexWrap: "wrap", alignItems: "center", gap: "8px 24px", paddingTop: 24 }}>
        <button type="button" className="btn-primary" disabled={!ready} onClick={onApply}>
          套用並開始翻譯
        </button>
        <button type="button" className="btn-text secondary" onClick={onApply}>
          略過，照科目建議
        </button>
        <span className="t-caption c-faint">
          {ready ? "會寫入這本書的術語表，各章沿用。" : `還有 ${left} 個詞沒選。選好才能套用，或略過讓科目決定。`}
        </span>
      </div>
    </main>
  );
}
