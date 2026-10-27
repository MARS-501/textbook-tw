// Electron 主程序：視窗、原生對話框、檔案讀取、Ollama 狀態，以及呼叫 Python 後端。
// 介面（renderer）只能透過 preload.cjs 開放的函式呼叫這裡。

const { app, BrowserWindow, dialog, ipcMain, shell } = require("electron");
const { execFile, spawn } = require("node:child_process");
const fs = require("node:fs/promises");
const path = require("node:path");
const readline = require("node:readline");

const OLLAMA_URL = "http://127.0.0.1:11434";
const DEV_URL = process.env.VITE_DEV_SERVER_URL;
// 開發階段：Python 專案就在 app/ 的上一層，用 uv 執行；打包後改成內附的執行檔
const PROJECT_ROOT = path.resolve(__dirname, "..", "..");

function createWindow() {
  const win = new BrowserWindow({
    width: 1440,
    height: 1000,
    minWidth: 960,
    minHeight: 640,
    backgroundColor: "#000000",
    autoHideMenuBar: true,
    title: "textbook-tw",
    icon: path.join(__dirname, "..", "build", "icon.ico"),
    webPreferences: {
      preload: path.join(__dirname, "preload.cjs"),
      contextIsolation: true,
      sandbox: true,
    },
  });
  // 外部連結用系統瀏覽器開，不在 App 視窗裡換頁
  win.webContents.setWindowOpenHandler(({ url }) => {
    if (url.startsWith("https://")) shell.openExternal(url);
    return { action: "deny" };
  });
  // 開發用自我檢查：載入後印出畫面文字就結束，確認正式版畫得出來
  if (process.env.TEXTBOOK_TW_SMOKE_TEST) {
    win.webContents.once("did-finish-load", () => {
      setTimeout(async () => {
        const text = await win.webContents.executeJavaScript("document.body.innerText.slice(0, 300)");
        process.stdout.write(`${JSON.stringify({ smokeTest: text })}\n`);
        app.quit();
      }, 2000);
    });
  }
  if (DEV_URL) {
    win.loadURL(DEV_URL);
  } else {
    win.loadFile(path.join(__dirname, "..", "dist", "index.html"));
  }
}

async function fileInfo(filePath) {
  const stat = await fs.stat(filePath);
  return { path: filePath, name: path.basename(filePath), size: stat.size };
}

function isPdf(filePath) {
  return typeof filePath === "string" && filePath.toLowerCase().endsWith(".pdf");
}

ipcMain.handle("pdf:pick", async (event) => {
  const result = await dialog.showOpenDialog(BrowserWindow.fromWebContents(event.sender), {
    title: "選擇要翻譯的 PDF",
    properties: ["openFile"],
    filters: [{ name: "PDF", extensions: ["pdf"] }],
  });
  return result.canceled ? null : fileInfo(result.filePaths[0]);
});

ipcMain.handle("pdf:info", async (_event, filePath) => (isPdf(filePath) ? fileInfo(filePath) : null));

ipcMain.handle("pdf:read", async (_event, filePath) => {
  if (!isPdf(filePath)) throw new Error("只能讀取 PDF");
  return new Uint8Array(await fs.readFile(filePath));
});

ipcMain.handle("folder:pick", async (event, defaultPath) => {
  const result = await dialog.showOpenDialog(BrowserWindow.fromWebContents(event.sender), {
    title: "選擇輸出位置",
    defaultPath,
    properties: ["openDirectory", "createDirectory"],
  });
  return result.canceled ? null : result.filePaths[0];
});

ipcMain.handle("path:open", async (_event, target) => {
  // shell.openPath 成功時回傳空字串，失敗時回傳錯誤說明
  return shell.openPath(target);
});

ipcMain.handle("path:reveal", async (_event, target) => {
  shell.showItemInFolder(target);
});

function gpuTotalMiB() {
  return new Promise((resolve) => {
    execFile(
      "nvidia-smi",
      ["--query-gpu=memory.total", "--format=csv,noheader,nounits"],
      { timeout: 3000, windowsHide: true },
      (error, stdout) => resolve(error ? null : Number.parseInt(stdout.trim().split(/\r?\n/)[0], 10) || null),
    );
  });
}

ipcMain.handle("ollama:status", async () => {
  try {
    const version = await fetch(`${OLLAMA_URL}/api/version`, { signal: AbortSignal.timeout(2000) });
    const ps = await fetch(`${OLLAMA_URL}/api/ps`, { signal: AbortSignal.timeout(2000) });
    const loaded = (await ps.json()).models ?? [];
    return {
      live: version.ok,
      version: (await version.json()).version,
      loaded: loaded.map((m) => ({ name: m.name, sizeVram: m.size_vram, size: m.size })),
      gpuTotalBytes: ((await gpuTotalMiB()) ?? 0) * 1024 * 1024 || null,
    };
  } catch {
    return { live: false, version: null, loaded: [], gpuTotalBytes: null };
  }
});

// ---- Python 後端 ----------------------------------------------------------

function spawnBackend(args) {
  return spawn("uv", ["run", "--quiet", "--project", PROJECT_ROOT, "textbook-tw", "app", ...args], {
    cwd: PROJECT_ROOT,
    windowsHide: true,
    env: { ...process.env, PYTHONIOENCODING: "utf-8", PYTHONUNBUFFERED: "1" },
  });
}

function stderrTail(chunks) {
  return Buffer.concat(chunks).toString("utf8").trim().split(/\r?\n/).slice(-6).join("\n");
}

/** 執行一次後端指令，回傳它輸出的 JSON。 */
function runBackend(args, input) {
  return new Promise((resolve, reject) => {
    const child = spawnBackend(args);
    const out = [];
    const err = [];
    child.stdout.on("data", (d) => out.push(d));
    child.stderr.on("data", (d) => err.push(d));
    child.on("error", (e) => reject(new Error(`無法啟動 Python 後端（${e.message}）。請確認已安裝 uv。`)));
    child.on("close", (code) => {
      const lines = Buffer.concat(out).toString("utf8").trim().split(/\r?\n/).filter(Boolean);
      if (code === 0 && lines.length > 0) {
        try {
          return resolve(JSON.parse(lines[lines.length - 1]));
        } catch {
          // 落到下面的錯誤
        }
      }
      reject(new Error(stderrTail(err) || `後端結束代碼 ${code}`));
    });
    if (input !== undefined) child.stdin.end(JSON.stringify(input));
    else child.stdin.end();
  });
}

ipcMain.handle("backend:glossary", (_event, pdfPath, profile) =>
  runBackend(["glossary", pdfPath, "--profile", profile]),
);

ipcMain.handle("backend:apply", (_event, pdfPath, payload) => runBackend(["apply", pdfPath], payload));

function killTree(child) {
  // BabelDOC 可能再開子程序，Windows 要用 taskkill /T 才會整棵結束
  if (process.platform === "win32") execFile("taskkill", ["/pid", String(child.pid), "/T", "/F"], { windowsHide: true });
  else child.kill("SIGTERM");
}

let resolving = null; // 模型判斷術語譯名的程序：{ child, cancelled }

// 模型依上下文判斷術語譯名：進度用 resolve:event 傳給介面，完成時回傳新的確認清單；中斷時回傳 null
ipcMain.handle("backend:resolve", (event, pdfPath, profile) => {
  if (resolving) {
    resolving.cancelled = true;
    killTree(resolving.child);
  }
  return new Promise((resolve, reject) => {
    const child = spawnBackend(["resolve", pdfPath, "--profile", profile]);
    const current = { child, cancelled: false };
    resolving = current;
    const err = [];
    let result = null;
    let failure = null;
    child.stderr.on("data", (d) => {
      err.push(d);
      if (err.length > 200) err.shift();
    });
    readline.createInterface({ input: child.stdout }).on("line", (line) => {
      let payload;
      try {
        payload = JSON.parse(line);
      } catch {
        return; // 不是 JSON 的輸出略過
      }
      if (payload.type === "progress" && !event.sender.isDestroyed()) event.sender.send("resolve:event", payload);
      else if (payload.type === "done") result = payload;
      else if (payload.type === "error") failure = payload.message;
    });
    child.on("error", (e) => reject(new Error(`無法啟動 Python 後端（${e.message}）。請確認已安裝 uv。`)));
    child.on("close", (code) => {
      if (resolving === current) resolving = null;
      if (result) resolve(result);
      else if (current.cancelled) resolve(null);
      else reject(new Error(failure || stderrTail(err) || `後端結束代碼 ${code}`));
    });
  });
});

ipcMain.handle("backend:resolve-cancel", () => {
  if (!resolving) return;
  resolving.cancelled = true;
  killTree(resolving.child);
});

let job = null; // 目前的翻譯程序：{ child, cancelled }

ipcMain.handle("job:start", (event, spec) => {
  if (job) throw new Error("已經有翻譯在進行");
  const args = ["translate", spec.pdf, "--profile", spec.profile, "--dual", spec.dual, "--font", spec.font];
  if (spec.pages.trim()) args.push("--pages", spec.pages.trim());
  if (!spec.mono) args.push("--no-mono");
  if (spec.translatedFirst) args.push("--translated-first");
  if (spec.outDir) args.push("--out-dir", spec.outDir);

  const sender = event.sender;
  const send = (payload) => {
    if (!sender.isDestroyed()) sender.send("job:event", payload);
  };
  const child = spawnBackend(args);
  const current = { child, cancelled: false, finished: false };
  job = current;
  const err = [];
  child.stderr.on("data", (d) => {
    err.push(d);
    if (err.length > 200) err.shift();
  });
  readline.createInterface({ input: child.stdout }).on("line", (line) => {
    try {
      const payload = JSON.parse(line);
      if (payload.type === "done" || payload.type === "error") current.finished = true;
      send(payload);
    } catch {
      // 不是 JSON 的輸出（BabelDOC 的除錯訊息）略過
    }
  });
  child.on("error", (e) => {
    current.finished = true;
    send({ type: "error", message: `無法啟動 Python 後端（${e.message}）。請確認已安裝 uv。` });
  });
  child.on("close", (code) => {
    if (job === current) job = null;
    if (current.cancelled) send({ type: "cancelled" });
    else if (!current.finished) send({ type: "error", message: stderrTail(err) || `翻譯程序意外結束（代碼 ${code}）` });
  });
});

ipcMain.handle("job:cancel", () => {
  if (!job) return;
  job.cancelled = true;
  killTree(job.child);
});

app.on("before-quit", () => {
  if (job) killTree(job.child);
  if (resolving) killTree(resolving.child);
});

// 讓工作列把視窗與桌面捷徑視為同一個 App（顯示同一個圖示）
app.setAppUserModelId("tw.textbook.app");

app.whenReady().then(() => {
  createWindow();
  app.on("activate", () => {
    if (BrowserWindow.getAllWindows().length === 0) createWindow();
  });
});

app.on("window-all-closed", () => {
  if (process.platform !== "darwin") app.quit();
});
