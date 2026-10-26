import { Section, SectionTitle, Segmented } from "../components/ui";

export type Theme = "dark" | "light";

// 設定畫面還沒有設計稿；先放外觀切換，方便檢查淺色主題
export function Settings({ theme, onTheme }: { theme: Theme; onTheme: (t: Theme) => void }) {
  return (
    <main className="main">
      <div style={{ display: "flex", flexDirection: "column", gap: 8, maxWidth: 640 }}>
        <h1 className="t-title">設定</h1>
        <p className="t-body c-muted">這個畫面還沒有設計稿。模型、輸出預設、科目設定會放在這裡。</p>
      </div>
      <Section style={{ maxWidth: 560 }}>
        <SectionTitle index="01">外觀</SectionTitle>
        <Segmented
          label="外觀"
          value={theme}
          onChange={onTheme}
          options={[
            { value: "dark", label: "深色" },
            { value: "light", label: "淺色" },
          ]}
        />
      </Section>
    </main>
  );
}
