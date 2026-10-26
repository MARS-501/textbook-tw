// Electron 主程序：視窗、原生對話框、檔案讀取、Ollama 狀態。
// 介面（renderer）只能透過 preload.cjs 開放的函式呼叫這裡。

const { app, BrowserWindow, dialog, ipcMain, shell } = require("electron");
const { execFile } = require("node:child_process");
const fs = require("node:fs/promises");
const path = require("node:path");

const OLLAMA_URL = "http://127.0.0.1:11434";
const DEV_URL = process.env.VITE_DEV_SERVER_URL;

function createWindow() {
  const win = new BrowserWindow({
    width: 1440,
    height: 1000,
    minWidth: 960,
    minHeight: 640,
    backgroundColor: "#000000",
    autoHideMenuBar: true,
    title: "textbook-tw",
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

app.whenReady().then(() => {
  createWindow();
  app.on("activate", () => {
    if (BrowserWindow.getAllWindows().length === 0) createWindow();
  });
});

app.on("window-all-closed", () => {
  if (process.platform !== "darwin") app.quit();
});
