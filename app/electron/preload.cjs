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
});
