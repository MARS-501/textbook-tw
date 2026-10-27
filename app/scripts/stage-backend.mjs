// 準備安裝版要附的 Python 後端（electron-builder 再把它們放進 resources/）：
//   app/.stage/python   獨立的 Python 3.12（uv 下載的 python-build-standalone）與所有套件，
//                       使用者電腦上不需要另外安裝 Python 或 uv
//   app/.stage/backend  textbook_tw 程式碼、config/、glossary/sources.toml
// 執行：npm --prefix app run stage（npm run dist 會先跑這一步）

import { execFileSync } from "node:child_process";
import { cpSync, existsSync, mkdirSync, readdirSync, renameSync, rmSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const APP = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const ROOT = path.resolve(APP, "..");
const STAGE = path.join(APP, ".stage");
const PYTHON_VERSION = "3.12";

function run(command, args) {
  console.log(`> ${command} ${args.join(" ")}`);
  execFileSync(command, args, { cwd: ROOT, stdio: "inherit" });
}

rmSync(STAGE, { recursive: true, force: true });
mkdirSync(STAGE, { recursive: true });

// 1. 獨立的 Python
const installs = path.join(STAGE, "python-installs");
run("uv", ["python", "install", PYTHON_VERSION, "--install-dir", installs, "--no-bin"]);
const found = readdirSync(installs).find((d) => d.startsWith(`cpython-${PYTHON_VERSION}.`) && d.includes("windows"));
if (!found) throw new Error(`uv 沒有裝好 Python ${PYTHON_VERSION}`);
const python = path.join(STAGE, "python");
renameSync(path.join(installs, found), python);
rmSync(installs, { recursive: true, force: true });
// 用不到、又佔空間的標準函式庫部分
for (const part of ["test", "idlelib", "tkinter", "turtledemo"]) {
  rmSync(path.join(python, "Lib", part), { recursive: true, force: true });
}
const pythonExe = path.join(python, "python.exe");

// 2. 套件：版本照 uv.lock，直接裝進這個 Python（不是虛擬環境，搬到哪都能用）
const requirements = path.join(STAGE, "requirements.txt");
run("uv", ["export", "--frozen", "--no-dev", "--no-hashes", "--no-emit-project", "--format", "requirements.txt", "--output-file", requirements]);
run("uv", [
  "pip", "install",
  "--python", pythonExe,
  "--break-system-packages",
  "--compile-bytecode", // 先編好 .pyc：安裝在 Program Files 時執行中不能寫入
  "--link-mode", "copy",
  "-r", requirements,
]); // prettier-ignore

// 3. 程式碼與設定
const backend = path.join(STAGE, "backend");
const skipCache = (p) => !p.includes("__pycache__");
cpSync(path.join(ROOT, "src", "textbook_tw"), path.join(backend, "src", "textbook_tw"), { recursive: true, filter: skipCache });
cpSync(path.join(ROOT, "config"), path.join(backend, "config"), { recursive: true, filter: (p) => !p.endsWith("local.toml") });
mkdirSync(path.join(backend, "glossary"), { recursive: true });
cpSync(path.join(ROOT, "glossary", "sources.toml"), path.join(backend, "glossary", "sources.toml"));
cpSync(path.join(ROOT, "LICENSE"), path.join(backend, "LICENSE"));
run(pythonExe, ["-m", "compileall", "-q", path.join(backend, "src")]);

// 4. 確認裝好的 Python 能載入後端
run(pythonExe, ["-c", `import sys; sys.path.insert(0, r"${path.join(backend, "src")}"); import textbook_tw.pipeline, babeldoc; print("backend ok")`]);
if (!existsSync(pythonExe)) throw new Error("沒有產生 python.exe");
