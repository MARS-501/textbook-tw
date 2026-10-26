import type { OllamaStatus } from "../bridge";
import type { Screen } from "../model";

const NAV: { screen: Screen; label: string }[] = [
  { screen: "new", label: "翻譯" },
  { screen: "glossary", label: "術語表" },
  { screen: "done", label: "紀錄" },
  { screen: "settings", label: "設定" },
];

export function Header({
  current,
  onNavigate,
  ollama,
}: {
  current: Screen;
  onNavigate: (screen: Screen) => void;
  ollama: OllamaStatus | null;
}) {
  // 「翻譯中」屬於「翻譯」分頁
  const active = current === "progress" ? "new" : current;
  const live = ollama?.live ?? false;
  return (
    <header className="header">
      <div style={{ display: "flex", alignItems: "center", gap: 32, flexWrap: "wrap" }}>
        <span className="t-heading" style={{ lineHeight: "48px", letterSpacing: "-0.01em" }}>
          textbook-tw
        </span>
        <nav aria-label="頁面" style={{ display: "flex", gap: 24 }}>
          {NAV.map((item) => (
            <a
              key={item.screen}
              href="#"
              className="nav-link t-label"
              aria-current={active === item.screen ? "page" : undefined}
              onClick={(e) => {
                e.preventDefault();
                onNavigate(item.screen);
              }}
            >
              {item.label}
            </a>
          ))}
        </nav>
      </div>
      <div className="t-label c-faint" style={{ display: "flex", alignItems: "center", gap: 4, lineHeight: "48px" }}>
        <span aria-hidden="true" className={`led${live ? " live" : ""}`} />
        <span>{ollama === null ? "OLLAMA · …" : live ? "OLLAMA · LIVE" : "OLLAMA · OFF"}</span>
      </div>
    </header>
  );
}
