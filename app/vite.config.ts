import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

// base: "./" 讓打包後的 Electron 用 file:// 載入時，資源路徑仍正確
export default defineConfig({
  base: "./",
  plugins: [react()],
  // 本機 App 從硬碟載入，單一檔案大一點沒關係（主要是 PDF.js 和中文字型）
  build: { outDir: "dist", emptyOutDir: true, chunkSizeWarningLimit: 2000 },
});
