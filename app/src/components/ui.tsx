import type { CSSProperties, ReactNode } from "react";

/** 區段標題：頂端髮絲線＋（編號）＋名稱，右側可放讀數。 */
export function SectionTitle({ index, children, right }: { index?: string; children: ReactNode; right?: ReactNode }) {
  const title = (
    <h2 className="t-label" style={{ display: "flex", gap: 12 }}>
      {index && <span className="c-faint">{index}</span>}
      <span>{children}</span>
    </h2>
  );
  if (!right) return title;
  return (
    <div style={{ display: "flex", flexWrap: "wrap", justifyContent: "space-between", alignItems: "baseline", gap: "8px 24px" }}>
      {title}
      <span className="t-label c-faint">{right}</span>
    </div>
  );
}

export function Section({ gap = 16, children, style }: { gap?: number; children: ReactNode; style?: CSSProperties }) {
  return (
    <section className="section" style={{ gap, ...style }}>
      {children}
    </section>
  );
}

/** 小讀數：標籤在上、數值在下。 */
export function Stat({ label, value, align = "left" }: { label: string; value: ReactNode; align?: "left" | "right" }) {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 4, textAlign: align }}>
      <span className="t-label c-faint">{label}</span>
      <span className="t-data">{value}</span>
    </div>
  );
}

export function Tag({ kind, children }: { kind: "done" | "due" | "err" | "outline"; children: ReactNode }) {
  return <span className={`tag ${kind}`}>{children}</span>;
}

/** 狀態標籤＋說明文字（DUE、ERR 一定附文字）。 */
export function Notice({ kind, children }: { kind: "due" | "err"; children: ReactNode }) {
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
      <Tag kind={kind}>{kind === "due" ? "DUE" : "ERR"}</Tag>
      <span className="t-caption">{children}</span>
    </div>
  );
}

export function Switch({
  checked,
  onChange,
  disabled,
  labelledBy,
}: {
  checked: boolean;
  onChange: (next: boolean) => void;
  disabled?: boolean;
  labelledBy: string;
}) {
  return (
    <button
      type="button"
      className="switch"
      role="switch"
      aria-checked={checked}
      aria-labelledby={labelledBy}
      disabled={disabled}
      onClick={() => onChange(!checked)}
    >
      <span className="switch-track">
        <span className="switch-knob" />
      </span>
    </button>
  );
}

/** 開關列：左邊名稱與說明，右邊開關。 */
export function SwitchRow(props: {
  id: string;
  label: string;
  hint: string;
  checked: boolean;
  disabled?: boolean;
  onChange: (next: boolean) => void;
}) {
  return (
    <div className="row-line-bottom" style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 16, minHeight: 48 }}>
      <div style={{ display: "flex", flexDirection: "column", gap: 2 }}>
        <span id={props.id} className={`t-body${props.disabled ? " c-faint" : ""}`}>
          {props.label}
        </span>
        <span className="t-caption c-muted">{props.hint}</span>
      </div>
      <Switch checked={props.checked} disabled={props.disabled} onChange={props.onChange} labelledBy={props.id} />
    </div>
  );
}

/** 底線式單選（分段切換）。 */
export function Segmented<T extends string>({
  label,
  labelledBy,
  options,
  value,
  onChange,
}: {
  label?: string;
  labelledBy?: string;
  options: { value: T; label: ReactNode }[];
  value: T;
  onChange: (next: T) => void;
}) {
  return (
    <div className="seg-group" role="radiogroup" aria-label={label} aria-labelledby={labelledBy}>
      {options.map((o) => (
        <button
          key={o.value}
          type="button"
          role="radio"
          aria-checked={value === o.value}
          className="seg t-label"
          onClick={() => onChange(o.value)}
        >
          {o.label}
        </button>
      ))}
    </div>
  );
}

/** 全書頁面條：每頁一條直線，形狀由 bar(頁碼) 決定。 */
export function PageStrip({
  total,
  height,
  bar,
  marks,
  label,
}: {
  total: number;
  height: number;
  bar: (page: number) => CSSProperties;
  marks?: (page: number) => CSSProperties;
  label: string;
}) {
  const pages = Array.from({ length: total }, (_, i) => i + 1);
  const ticks = total >= 8 ? [1, ...[1, 2, 3].map((q) => Math.round((total * q) / 4)), total] : [1, total];
  return (
    <div role="img" aria-label={label} style={{ display: "flex", flexDirection: "column", gap: 8 }}>
      <div style={{ height, display: "flex", justifyContent: "space-between", alignItems: "flex-end" }}>
        {pages.map((p) => (
          <span key={p} style={{ display: "block", width: 1, ...bar(p) }} />
        ))}
      </div>
      {marks && (
        <div style={{ height: 6, display: "flex", justifyContent: "space-between" }}>
          {pages.map((p) => (
            <span key={p} style={{ display: "block", width: 1, height: 6, ...marks(p) }} />
          ))}
        </div>
      )}
      <div aria-hidden="true" className="t-label c-faint" style={{ display: "flex", justifyContent: "space-between" }}>
        {ticks.map((t, i) => (
          <span key={i}>{t}</span>
        ))}
      </div>
    </div>
  );
}

/** 對照版的小圖示：空框是原文頁，實心是譯文頁。 */
export function DualIcon({ mode, translatedFirst }: { mode: "side_by_side" | "alternating" | "both" | "none"; translatedFirst: boolean }) {
  const original: CSSProperties = { display: "block", width: 9, height: 13, border: "1px solid currentColor" };
  const translated: CSSProperties = { display: "block", width: 9, height: 13, background: "currentColor" };
  const pair = translatedFirst ? [translated, original] : [original, translated];
  const side = (
    <span style={{ display: "flex" }}>
      {pair.map((s, i) => (
        <span key={i} style={s} />
      ))}
    </span>
  );
  const alt = (
    <span style={{ display: "flex", gap: 3 }}>
      {[...pair, ...pair].map((s, i) => (
        <span key={i} style={s} />
      ))}
    </span>
  );
  if (mode === "none") return null;
  return (
    <span aria-hidden="true" style={{ display: "flex", gap: 6, height: 16, alignItems: "center" }}>
      {(mode === "side_by_side" || mode === "both") && side}
      {(mode === "alternating" || mode === "both") && alt}
    </span>
  );
}
