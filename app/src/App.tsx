import { useEffect, useState } from "react";
import { ollamaStatus, type OllamaStatus } from "./bridge";
import { Header } from "./components/Header";
import { DEMO_ANALYSIS_SECONDS, DEMO_MS_PER_PAGE } from "./demo";
import { parsePages } from "./lib/pages";
import { DEFAULT_OPTIONS, SEC_PER_PAGE, type Doc, type JobOptions, type Screen } from "./model";
import { Done, type FinishedJob } from "./screens/Done";
import { Glossary, initialPicks, type Picks } from "./screens/Glossary";
import { NewTranslation } from "./screens/NewTranslation";
import { Progress, type RunningJob } from "./screens/Progress";
import { Settings, type Theme } from "./screens/Settings";

const OPTIONS_KEY = "textbook-tw.options";
const THEME_KEY = "textbook-tw.theme";

function loadStored<T>(key: string, fallback: T): T {
  try {
    const raw = localStorage.getItem(key);
    return raw ? { ...fallback, ...JSON.parse(raw) } : fallback;
  } catch {
    return fallback;
  }
}

function store(key: string, value: unknown) {
  try {
    localStorage.setItem(key, JSON.stringify(value));
  } catch {
    // 存不了就只影響下次的預設值
  }
}

export function App() {
  const [screen, setScreen] = useState<Screen>("new");
  const [doc, setDoc] = useState<Doc | null>(null);
  const [options, setOptions] = useState<JobOptions>(() => loadStored(OPTIONS_KEY, DEFAULT_OPTIONS));
  const [picks, setPicks] = useState<Picks>(initialPicks);
  const [job, setJob] = useState<RunningJob | null>(null);
  const [result, setResult] = useState<FinishedJob | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [ollama, setOllama] = useState<OllamaStatus | null>(null);
  const [theme, setTheme] = useState<Theme>(() => loadStored(THEME_KEY, { theme: "dark" as Theme }).theme);

  // 換畫面時回到頂端
  useEffect(() => {
    window.scrollTo(0, 0);
  }, [screen]);

  useEffect(() => {
    document.documentElement.dataset.theme = theme;
    store(THEME_KEY, { theme });
  }, [theme]);

  // 每 5 秒更新一次 Ollama 狀態
  useEffect(() => {
    let alive = true;
    const poll = () => ollamaStatus().then((s) => alive && setOllama(s));
    poll();
    const timer = window.setInterval(poll, 5000);
    return () => {
      alive = false;
      window.clearInterval(timer);
    };
  }, []);

  // 示範：模擬翻譯進度（接上後端後改成接收真實進度）
  const running = job !== null && job.done < job.pages.length;
  useEffect(() => {
    if (!running) return;
    const timer = window.setInterval(() => {
      setJob((j) => (j ? { ...j, done: j.done + 1 } : j));
    }, DEMO_MS_PER_PAGE);
    return () => window.clearInterval(timer);
  }, [running]);

  useEffect(() => {
    if (!job || job.done < job.pages.length) return;
    setResult({
      doc,
      options,
      pages: job.pages,
      seconds: DEMO_ANALYSIS_SECONDS + job.pages.length * SEC_PER_PAGE,
      finishedAt: new Date(),
    });
    setJob(null);
    setScreen("done");
  }, [job, doc, options]);

  function startJob() {
    const total = doc?.pageCount ?? 120;
    const pages = parsePages(options.pages, total) ?? [];
    setNotice(null);
    setJob({ pages, done: 0 });
    setScreen("progress");
  }

  function navigate(target: Screen) {
    setScreen(target === "new" && job ? "progress" : target);
  }

  return (
    <div className="page">
      <Header current={screen} onNavigate={navigate} ollama={ollama} />
      {screen === "new" && (
        <NewTranslation
          doc={doc}
          onDoc={(d) => {
            setDoc(d);
            setPicks(initialPicks());
          }}
          options={options}
          onOptions={setOptions}
          ollama={ollama}
          notice={notice}
          onStart={() => setScreen("glossary")}
          onSaveDefault={() => store(OPTIONS_KEY, { ...options, pages: "", outputDir: null })}
          onOpenRecent={() => setScreen("done")}
        />
      )}
      {screen === "glossary" && <Glossary doc={doc} options={options} picks={picks} onPicks={setPicks} onApply={startJob} />}
      {screen === "progress" && job && (
        <Progress
          doc={doc}
          options={options}
          job={job}
          onInterrupt={() => {
            const next = job.pages[Math.min(job.done, job.pages.length - 1)];
            setNotice(`已中斷。再開始同一份檔案，會從第 ${next} 頁接著翻。`);
            setJob(null);
            setScreen("new");
          }}
        />
      )}
      {screen === "done" && <Done result={result} onNext={() => setScreen("new")} onEditGlossary={() => setScreen("glossary")} />}
      {screen === "settings" && <Settings theme={theme} onTheme={setTheme} />}
    </div>
  );
}
