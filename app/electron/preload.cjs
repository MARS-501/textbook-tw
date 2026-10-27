// 介面能呼叫的原生功能，只開放這幾個。
const { contextBridge, ipcRenderer, webUtils } = require("electron");

contextBridge.exposeInMainWorld("textbookTw", {
  pickPdf: () => ipcRenderer.invoke("pdf:pick"),
  pdfInfo: (filePath) => ipcRenderer.invoke("pdf:info", filePath),
  readPdf: (filePath) => ipcRenderer.invoke("pdf:read", filePath),
  pickFolder: (defaultPath) => ipcRenderer.invoke("folder:pick", defaultPath),
  openPath: (target) => ipcRenderer.invoke("path:open", target),
  revealPath: (target) => ipcRenderer.invoke("path:reveal", target),
  ollamaStatus: () => ipcRenderer.invoke("ollama:status"),
  // 拖放進來的檔案取得實際路徑（Electron 32 起 File.path 已移除）
  pathForFile: (file) => webUtils.getPathForFile(file),

  // Python 後端
  glossaryReview: (pdfPath, profile) => ipcRenderer.invoke("backend:glossary", pdfPath, profile),
  applyGlossary: (pdfPath, payload) => ipcRenderer.invoke("backend:apply", pdfPath, payload),
  resolveGlossary: (pdfPath, profile) => ipcRenderer.invoke("backend:resolve", pdfPath, profile),
  cancelResolve: () => ipcRenderer.invoke("backend:resolve-cancel"),
  onResolveEvent: (callback) => {
    const listener = (_event, payload) => callback(payload);
    ipcRenderer.on("resolve:event", listener);
    return () => ipcRenderer.removeListener("resolve:event", listener);
  },
  startJob: (spec) => ipcRenderer.invoke("job:start", spec),
  cancelJob: () => ipcRenderer.invoke("job:cancel"),
  onJobEvent: (callback) => {
    const listener = (_event, payload) => callback(payload);
    ipcRenderer.on("job:event", listener);
    return () => ipcRenderer.removeListener("job:event", listener);
  },
});
