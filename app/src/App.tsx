import { useEffect, useRef, useState } from "react";
import {
  applyGlossary,
  cancelJob,
  cancelResolve,
  glossaryReview,
  hasBackend,
  ollamaStatus,
  onJobEvent,
  onResolveEvent,
  resolveGlossary,
  startJob,
  type GlossaryReview,
  type JobEvent,
  type OllamaStatus,
  type ReviewTerm,
} from "./bridge";
import { Header } from "./components/Header";
import {
  DEMO_FIXES,
  DEMO_KEEP,
  DEMO_MS_PER_PAGE,
  DEMO_PARAGRAPHS,
  DEMO_RECENT,
  DEMO_RESOLVE_MS_PER_BATCH,
  DEMO_RESOLVE_TOTAL,
  DEMO_TOTAL_TERMS,
  demoReview,
} from "./demo";
import { defaultOutputDir, joinPath } from "./lib/format";
import { parsePages } from "./lib/pages";
import {
  DEFAULT_OPTIONS,
  plannedOutputs,
  profileName,
  SEC_PER_PAGE,
  type Doc,
  type FinishedJob,
  type JobOptions,
  type JobView,
  type Screen,
} from "./model";
import { Done } from "./screens/Done";
import { Glossary, initialPicks, targetOf, type Picks, type ResolveState } from "./screens/Glossary";
import { NewTranslation } from "./screens/NewTranslation";
import { Progress } from "./screens/Progress";
import { Settings, type Theme } from "./screens/Settings";

const OPTIONS_KEY = "textbook-tw.options";
const THEME_KEY = "textbook-tw.theme";
const HISTORY_KEY = "textbook-tw.history";
const HISTORY_SIZE = 10;
const TRANSLATE_STAGE = "Translate Paragraphs"; // BabelDOC 翻譯段落的階段名稱
const RECENT_PARAGRAPHS = 3;

function loadJson<T>(key: string, fallback: T): T {
  try {
    const raw = localStorage.getItem(key);
    return raw ? (JSON.parse(raw) as T) : fallback;
  } catch {
    return fallback;
  }
}

function store(key: string, value: unknown) {
  try {
    localStorage.setItem(key, JSON.stringify(value));
  } catch {
    // 存不了只影響下次的預設值與紀錄
  }
}

/** 翻譯中的原始狀態；畫面用的 JobView 由它算出來。 */
interface LiveJob {
  pages: number[];
  startedAt: number;
  percent: number;
  stage: string;
  stageCurrent: number;
  stageTotal: number;
  pastTranslate: boolean;
  paragraphs: JobView["paragraphs"];
  fallbacks: number;
  error: string | null;
  demo: boolean;
}

function newJob(pages: number[], demo: boolean): LiveJob {
  return {
    pages,
    startedAt: Date.now(),
    percent: 0,
    stage: "",
    stageCurrent: 0,
    stageTotal: 0,
    pastTranslate: false,
    paragraphs: [],
    fallbacks: 0,
    error: null,
    demo,
  };
}

function toView(job: LiveJob, now: number): JobView {
  const n = job.pages.length;
  const translating = job.stage === TRANSLATE_STAGE;
  const step = translating ? 2 : job.pastTranslate ? 3 : 0;
  const pagesDone =
    step === 3 ? n : translating && job.stageTotal > 0 ? Math.floor((job.stageCurrent / job.stageTotal) * n) : 0;
  const elapsed = job.demo ? pagesDone * SEC_PER_PAGE : (now - job.startedAt) / 1000;
  return {
    pages: job.pages,
    pagesDone,
    percent: job.percent,
    step,
    elapsed,
    remaining: job.error === null && job.percent >= 2 ? (elapsed * (100 - job.percent)) / job.percent : null,
    perPage: pagesDone > 0 ? elapsed / pagesDone : null,
    paragraphs: job.paragraphs,
    fallbacks: job.fallbacks,
    fixes: job.demo ? Math.round(pagesDone * 0.12) : null, // 大陸用語修正還沒做
    error: job.error,
  };
}

/** 模型判斷完換上新清單時，保留使用者在判斷期間自己改過的選擇。 */
function mergePicks(before: ReviewTerm[], picks: Picks, after: ReviewTerm[]): Picks {
  const next = initialPicks(after);
  for (const old of before) {
    const pick = picks[old.source];
    if (pick === undefined || pick === old.pick) continue;
    const term = after.find((t) => t.source === old.source);
    const target = targetOf(old, pick);
    if (!term || target === null) continue;
    const index = term.options.findIndex((o) => o.zh === target);
    if (index >= 0) next[term.source] = index;
    else if (target === "") next[term.source] = pick; // 不套用
  }
  return next;
}

function applyEvent(job: LiveJob, event: JobEvent): LiveJob {
  switch (event.type) {
    case "start":
      return { ...job, pages: event.pages };
    case "progress": {
      const pastTranslate = job.pastTranslate || (job.stage === TRANSLATE_STAGE && event.stage !== TRANSLATE_STAGE);
      return { ...job, percent: event.percent, stage: event.stage, stageCurrent: event.current, stageTotal: event.total, pastTranslate };
    }
    case "paragraphs":
      return { ...job, paragraphs: [...job.paragraphs, ...event.items].slice(-RECENT_PARAGRAPHS) };
    case "fallback":
      return { ...job, fallbacks: event.count };
    case "error":
      return { ...job, error: event.message };
    default:
      return job;
  }
}

export function App() {
  const [screen, setScreen] = useState<Screen>("new");
  const [doc, setDoc] = useState<Doc | null>(null);
  const [options, setOptions] = useState<JobOptions>(() => ({ ...DEFAULT_OPTIONS, ...loadJson(OPTIONS_KEY, {}) }));
  const [ollama, setOllama] = useState<OllamaStatus | null>(null);
  const [theme, setTheme] = useState<Theme>(() => loadJson<{ theme: Theme }>(THEME_KEY, { theme: "dark" }).theme);

  // 術語確認
  const [review, setReview] = useState<ReviewTerm[] | null>(null);
  const [reviewTotal, setReviewTotal] = useState(0);
  const [reviewError, setReviewError] = useState<string | null>(null);
  const [reviewKey, setReviewKey] = useState<string | null>(null);
  const [picks, setPicks] = useState<Picks>({});
  const [myTerms, setMyTerms] = useState<[string, string][]>([]);
  const [busy, setBusy] = useState(false);
  const [resolve, setResolve] = useState<ResolveState | null>(null);

  // 翻譯
  const [job, setJob] = useState<LiveJob | null>(null);
  const [now, setNow] = useState(Date.now());
  const [notice, setNotice] = useState<string | null>(null);
  const [history, setHistory] = useState<FinishedJob[]>(() => loadJson(HISTORY_KEY, []));
  const [viewing, setViewing] = useState<FinishedJob | null>(null);

  // 事件處理器需要最新的 doc、options 與術語確認的狀態
  const latest = useRef({ doc, options, review, picks, reviewKey });
  latest.current = { doc, options, review, picks, reviewKey };

  useEffect(() => {
    window.scrollTo(0, 0);
  }, [screen]);

  useEffect(() => {
    document.documentElement.dataset.theme = theme;
    store(THEME_KEY, { theme });
  }, [theme]);

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

  // 翻譯中每秒更新已用時間
  const ticking = job !== null && job.error === null;
  useEffect(() => {
    if (!ticking) return;
    const timer = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(timer);
  }, [ticking]);

  function finish(result: FinishedJob) {
    setJob(null);
    setViewing(result);
    if (!result.demo) {
      setHistory((h) => {
        const next = [result, ...h].slice(0, HISTORY_SIZE);
        store(HISTORY_KEY, next);
        return next;
      });
    }
    setScreen("done");
  }

  // 真實翻譯：接收 Python 後端的事件
  useEffect(
    () =>
      onJobEvent((event) => {
        if (event.type === "done") {
          const { doc: d, options: o } = latest.current;
          finish({
            fileName: d?.file.name ?? "",
            totalPages: d?.pageCount ?? event.pages.length,
            options: o,
            pages: event.pages,
            seconds: event.seconds,
            finishedAt: new Date().toISOString(),
            fallbacks: event.fallbacks,
            outputs: event.outputs,
            perParagraph: event.per_paragraph,
            demo: false,
          });
        } else if (event.type === "cancelled") {
          setJob(null);
          setNotice("已中斷。再開始同一份檔案時，翻過的段落會直接沿用。");
          setScreen("new");
        } else {
          setJob((j) => (j ? applyEvent(j, event) : j));
        }
      }),
    [],
  );

  // 模型判斷術語譯名的進度
  useEffect(
    () =>
      onResolveEvent((event) =>
        setResolve((r) => (r?.phase === "running" ? { phase: "running", done: event.done, total: event.total } : r)),
      ),
    [],
  );

  // 示範：模擬模型判斷術語
  const demoResolving = !hasBackend && resolve?.phase === "running";
  useEffect(() => {
    if (!demoResolving) return;
    const timer = window.setInterval(() => {
      setResolve((r) => {
        if (r?.phase !== "running") return r;
        const done = Math.min(r.total, r.done + 8);
        return done >= r.total ? null : { ...r, done };
      });
    }, DEMO_RESOLVE_MS_PER_BATCH);
    return () => window.clearInterval(timer);
  }, [demoResolving]);

  // 示範：模擬翻譯進度
  const demoRunning = job !== null && job.demo && job.stageCurrent < job.pages.length;
  useEffect(() => {
    if (!demoRunning) return;
    const timer = window.setInterval(() => {
      setJob((j) => {
        if (!j) return j;
        const done = j.stageCurrent + 1;
        const paragraphs = DEMO_PARAGRAPHS.map((p) => ({ en: p.en, zh: p.zh, fixed: p.fixed }));
        return { ...j, stage: TRANSLATE_STAGE, stageCurrent: done, stageTotal: j.pages.length, percent: (done / j.pages.length) * 100, paragraphs };
      });
    }, DEMO_MS_PER_PAGE);
    return () => window.clearInterval(timer);
  }, [demoRunning]);

  useEffect(() => {
    if (!job || !job.demo || job.stageCurrent < job.pages.length) return;
    const name = doc?.file.name ?? "示範.pdf";
    const outDir = options.outputDir ?? (doc ? defaultOutputDir(doc.file.path, doc.file.name) : null) ?? "";
    finish({
      fileName: name,
      totalPages: doc?.pageCount ?? job.pages.length,
      options,
      pages: job.pages,
      seconds: 74 + job.pages.length * SEC_PER_PAGE,
      finishedAt: new Date().toISOString(),
      fallbacks: 0,
      outputs: plannedOutputs(name, options, job.pages, doc?.pageCount ?? job.pages.length)
        .sort((a, b) => ["side_by_side", "alternating", "mono"].indexOf(a.kind) - ["side_by_side", "alternating", "mono"].indexOf(b.kind))
        .map((o) => ({ kind: o.kind, path: joinPath(outDir, o.file), size: null })),
      demo: true,
    });
  }, [job, doc, options]);

  function showReview(result: GlossaryReview) {
    setReview(result.review);
    setReviewTotal(result.total);
    setPicks(initialPicks(result.review));
  }

  async function loadReview(force = false) {
    setScreen("glossary");
    if (!hasBackend) {
      const demo = demoReview();
      setReview(demo);
      setReviewTotal(DEMO_TOTAL_TERMS);
      setPicks(initialPicks(demo));
      if (review === null) setResolve({ phase: "running", done: 0, total: DEMO_RESOLVE_TOTAL });
      return;
    }
    if (!doc?.file.path) {
      setReview(null);
      setReviewError("先在「翻譯」選一個 PDF。");
      return;
    }
    const key = `${doc.file.path}|${options.profile}`;
    if (!force && key === reviewKey && review !== null) return;
    if (resolve?.phase === "running") await cancelResolve();
    setReview(null);
    setReviewError(null);
    setResolve(null);
    setReviewKey(key);
    try {
      const result = await glossaryReview(doc.file.path, options.profile);
      showReview(result);
      // 還沒讓模型依上下文判斷過：Ollama 有開就自動開始
      if (!result.resolved && result.pending > 0) {
        // 狀態還沒查到時也試試看；連不到會顯示錯誤與「再試一次」
        if (ollama?.live !== false) void runResolve(key, doc.file.path, options.profile, result.pending);
        else setResolve({ phase: "stopped", pending: result.pending });
      }
    } catch (e) {
      setReviewError(e instanceof Error ? e.message : String(e));
    }
  }

  async function runResolve(key: string, pdfPath: string, profile: string, pending: number) {
    setResolve({ phase: "running", done: 0, total: pending });
    try {
      const result = await resolveGlossary(pdfPath, profile);
      if (latest.current.reviewKey !== key) return; // 已經換了檔案或科目
      if (result === null) {
        // 被停掉：已判斷完的批次有存檔，重新讀一次
        const partial = await glossaryReview(pdfPath, profile);
        showReview(partial);
        setResolve(partial.pending > 0 ? { phase: "stopped", pending: partial.pending } : null);
        return;
      }
      const { review: before, picks: chosen } = latest.current;
      setReview(result.review);
      setReviewTotal(result.total);
      setPicks(mergePicks(before ?? [], chosen, result.review));
      setResolve(null);
    } catch (e) {
      if (latest.current.reviewKey === key) setResolve({ phase: "failed", message: e instanceof Error ? e.message : String(e) });
    }
  }

  function startResolve() {
    if (!hasBackend) return setResolve({ phase: "running", done: 0, total: DEMO_RESOLVE_TOTAL });
    if (!doc?.file.path || !reviewKey) return;
    const pending = resolve?.phase === "stopped" ? resolve.pending : (review?.length ?? 0);
    void runResolve(reviewKey, doc.file.path, options.profile, pending);
  }

  function stopResolve() {
    if (!hasBackend) return setResolve({ phase: "stopped", pending: 9 });
    void cancelResolve();
  }

  async function begin(useChoices: boolean) {
    const total = doc?.pageCount ?? 120;
    const pages = parsePages(options.pages, total) ?? [];
    setNotice(null);
    if (!hasBackend || !doc?.file.path) {
      setJob(newJob(pages, true));
      setScreen("progress");
      return;
    }
    setBusy(true);
    try {
      const choices: Record<string, string> = {};
      if (useChoices) {
        for (const t of review ?? []) {
          const pick = picks[t.source] ?? t.pick;
          const target = targetOf(t, pick);
          if (pick !== t.pick && target !== null) choices[t.source] = target;
        }
      }
      if (Object.keys(choices).length > 0 || myTerms.length > 0) {
        await applyGlossary(doc.file.path, { choices, my_terms: myTerms });
        setMyTerms([]);
      }
      setJob(newJob(pages, false));
      setScreen("progress");
      await startJob({
        pdf: doc.file.path,
        pages: options.pages,
        profile: options.profile,
        dual: options.dual,
        font: options.font,
        mono: options.mono,
        translatedFirst: options.translatedFirst,
        outDir: options.outputDir ?? defaultOutputDir(doc.file.path, doc.file.name),
      });
    } catch (e) {
      const message = e instanceof Error ? e.message : String(e);
      setJob((j) => (j ? { ...j, error: message } : j));
      if (screen === "glossary") setReviewError(message);
    } finally {
      setBusy(false);
    }
  }

  function interrupt() {
    if (!job) return;
    if (job.demo) {
      setJob(null);
      setNotice("已中斷（示範）。");
      setScreen("new");
    } else {
      cancelJob();
    }
  }

  function navigate(target: Screen) {
    if (target === "new" && job) return setScreen("progress");
    if (target === "glossary") return void loadReview();
    if (target === "done") setViewing((v) => v ?? history[0] ?? null);
    setScreen(target);
  }

  const meta = doc ? `${doc.file.name} · ${doc.pageCount} 頁 · ${profileName(options.profile)}` : `示範 · ${profileName(options.profile)}`;
  const recent: FinishedJob[] = hasBackend
    ? history
    : DEMO_RECENT.map((r, i) => ({
        fileName: r.name,
        totalPages: 0,
        options,
        pages: Array.from({ length: Number(r.meta.split(" ")[0]) }, (_, k) => k + 1),
        seconds: 0,
        finishedAt: new Date(Date.now() - i * 3600_000).toISOString(),
        fallbacks: 0,
        outputs: [],
        demo: true,
      }));

  return (
    <div className="page">
      <Header current={screen} onNavigate={navigate} ollama={ollama} />
      {screen === "new" && (
        <NewTranslation
          doc={doc}
          onDoc={(d) => {
            if (resolve?.phase === "running") void cancelResolve();
            setDoc(d);
            setReviewKey(null);
            setResolve(null);
          }}
          options={options}
          onOptions={setOptions}
          ollama={ollama}
          notice={notice}
          onStart={() => loadReview()}
          onSaveDefault={() => store(OPTIONS_KEY, { ...options, pages: "", outputDir: null })}
          recent={recent}
          onOpenRecent={(r) => {
            setViewing(r);
            setScreen("done");
          }}
        />
      )}
      {screen === "glossary" && (
        <Glossary
          meta={meta}
          total={reviewTotal}
          review={review}
          error={reviewError}
          picks={picks}
          onPicks={setPicks}
          myTerms={myTerms}
          onAddMyTerm={(s, t) => setMyTerms((list) => [...list.filter(([x]) => x.toLowerCase() !== s.toLowerCase()), [s, t]])}
          busy={busy}
          resolve={resolve}
          onResolve={startResolve}
          onStopResolve={stopResolve}
          onApply={() => begin(true)}
          onSkip={() => begin(false)}
          onRetry={() => (doc ? loadReview(true) : setScreen("new"))}
          fixes={hasBackend ? null : DEMO_FIXES}
          keep={hasBackend ? null : DEMO_KEEP}
        />
      )}
      {screen === "progress" && job && (
        <Progress
          fileName={doc?.file.name ?? "示範.pdf"}
          options={options}
          view={toView(job, now)}
          onInterrupt={interrupt}
          onBack={() => {
            setJob(null);
            setScreen("new");
          }}
        />
      )}
      {screen === "done" && <Done result={viewing} onNext={() => setScreen("new")} onEditGlossary={() => loadReview()} />}
      {screen === "settings" && <Settings theme={theme} onTheme={setTheme} />}
    </div>
  );
}
