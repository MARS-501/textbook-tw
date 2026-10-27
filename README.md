# textbook-tw

把英文 PDF 簡報與原文教科書翻成**台灣繁體中文**，並**保留原本的版面、圖表與公式**。
翻譯全部在自己的電腦上用本地模型完成，不需要把檔案上傳到任何雲端服務。

> 🚧 開發中（v0.1.0 預覽版）。可以用 Windows 桌面 App 或指令列翻譯，進度見下方「開發階段」。

## 功能（規劃）

- **保留版面**：以 [BabelDOC](https://github.com/funstory-ai/BabelDOC) 為版面引擎，圖片、圖表、公式不動，譯文填回原位置
- **中英對照**：可選擇輸出
  - 左右並排（左原文、右譯文）
  - 交替頁（原文頁、譯文頁輪流）
  - 兩種都輸出
  - 另有純譯文版
- **本地模型**：透過 [Ollama](https://ollama.com) 執行，預設 Qwen3.5-4B，6GB 顯卡可用
- **專業術語**：內建國家教育研究院學術名詞（航空太空、力學、數學、機械工程、材料科學、統計學等），由本地模型依文件上下文挑譯名，全書譯名一致
- **台灣用語**：自動把簡體字與大陸用語修正為台灣繁體用語

## 安裝

### Windows 安裝版（建議）

1. 到 [Releases](https://github.com/MARS-501/textbook-tw/releases) 下載最新的 `textbook-tw-Setup-<版本>.exe`，執行後照安裝精靈的步驟走：
   - 可以選擇只裝給自己或所有使用者、安裝位置
   - 會建立桌面與開始功能表捷徑
   - 可從「設定 › 應用程式」解除安裝
2. 安裝 [Ollama](https://ollama.com)，並下載模型：`ollama pull qwen3.5:4b`（約 3.3GB）
3. 開啟 textbook-tw，右上角顯示「OLLAMA · LIVE」就能開始翻譯

說明：
- 安裝版已內附 Python 與所有套件，不需要另外安裝。
- 第一次翻譯時，BabelDOC 會下載版面辨識模型與中文字型，需要網路。
- 術語表、下載的名詞庫、你的修正表放在 `%APPDATA%\textbook-tw`。
- 安裝檔沒有數位簽章，Windows 可能顯示「Windows 已保護您的電腦」。按「其他資訊 › 仍要執行」即可。

### 從原始碼執行

需要 Windows／macOS／Linux，以及：

1. [uv](https://docs.astral.sh/uv/)（Python 套件管理工具，會自動安裝 Python 3.12）
2. [Ollama](https://ollama.com)，並下載模型：`ollama pull qwen3.5:4b`（約 3.3GB，6GB 顯卡可全部放進顯示記憶體）

```bash
git clone https://github.com/MARS-501/textbook-tw.git
cd textbook-tw
uv sync
```

第一次翻譯時，BabelDOC 會自動下載版面辨識模型與中文字型。

## 使用方式

把 PDF 放進 `input/` 底下，然後：

```bash
uv run textbook-tw translate input/slides/講義.pdf
uv run textbook-tw translate input/textbooks/課本.pdf --pages 1-20 --dual alternating
```

結果會放在 `output/<檔名>/`：

| 檔案 | 內容 |
|---|---|
| `<檔名>.譯文.pdf` | 純譯文版 |
| `<檔名>.對照-並排.pdf` | 每頁左原文、右譯文 |
| `<檔名>.對照-交替.pdf` | 原文頁、譯文頁輪流 |

常用選項：

| 選項 | 說明 |
|---|---|
| `--pages 1-5,8` | 只翻部分頁面（檔名會加上頁碼，不會蓋掉整份的結果） |
| `--dual side_by_side／alternating／both／none` | 對照版格式，預設 `both` |
| `--profile fluid-mechanics／aerospace／engineering-math／materials` | 科目設定 |
| `--font auto／serif／sans-serif` | 譯文字型；`auto` 時投影片用黑體 |
| `--translated-first` | 對照版譯文放前面 |
| `--no-mono` | 不輸出純譯文版 |
| `--no-glossary` | 不使用術語表 |

預設值在 `config/default.toml`；想改成自己的預設，可以建立 `config/local.toml` 只寫要改的項目（不會上傳 GitHub）。

翻譯中途按 Ctrl+C 中斷也沒關係，已翻好的段落有快取，重跑時會跳過。

BabelDOC 把每個中文字寫成獨立的文字物件，閱讀器開起來很卡；翻譯完成後會自動合併（畫面不變）。之前翻好的檔案可以這樣處理，不用重翻：

```bash
uv run textbook-tw optimize output/
```

## 桌面 App（從原始碼執行）

`app/` 是 Electron 桌面介面，會呼叫上面的 Python 程式翻譯（需要 [Node.js](https://nodejs.org) 與 uv）：

```bash
npm --prefix app install
npm --prefix app run dev
```

Windows PowerShell 若擋住 `npm`，改打 `npm.cmd`。只想看介面、不翻譯的話，`npm --prefix app run dev:web` 會在瀏覽器開啟示範模式。

製作 Windows 安裝檔：

```bash
npm --prefix app run dist
```

這個指令依序做三件事：
1. 用 uv 下載獨立的 Python 3.12，照 `uv.lock` 裝好套件。
2. 連同程式碼放進 `app/.stage/`。
3. 用 electron-builder 產生 `app/release/textbook-tw-Setup-<版本>.exe`（NSIS 安裝精靈）。

## 術語表

第一次翻譯某份 PDF 時，程式會掃描全文，從國家教育研究院的名詞庫挑出文中出現的術語，存成 `glossary/books/<檔名>.csv`。之後翻譯同一份 PDF（包括只翻部分頁面）都用這份術語表，全書譯名一致。

論文和課本常常跨領域（複合材料論文裡有材料、力學、統計用語），所以掃描後會讓本地模型**依這份文件的上下文挑譯名**：名詞庫譯名不一致的詞，連同它在文中的幾段原文與各名詞庫的候選，交給模型判斷。一本書只做一次；論文約 2 分鐘，120 頁課本約 8 分鐘。桌面 App 會在術語確認畫面顯示進度與模型的理由，可以停止或修改。

用 Excel 打開這個檔案就能修改：

| 欄位 | 說明 |
|---|---|
| `source` | 英文術語 |
| `target` | 採用的譯名。**改這欄**就能換譯名；清空代表不使用。<br>寫成 `剪力｜剪切`（全形直線隔開）代表翻譯時依每一段的意思挑一個 |
| `status` | `模型建議`：模型依上下文選的，理由在 `note`<br>`依段落`：文中有不同意思，翻譯時每段從 `target` 列的譯名挑<br>`不套用`：模型判斷這裡只是一般用語或候選都不合適，翻譯時自行處理<br>`待確認`：名詞庫譯名不一致、還沒判斷，請從 `alternatives` 挑一個填進 `target`<br>`名詞庫譯名不同`：還沒判斷，暫用科目設定裡優先的名詞庫 |
| `count` | 在這份文件出現的次數 |
| `origin` | 譯名來自哪些名詞庫 |
| `alternatives` | 其他候選譯名 |
| `note` | 模型選這個譯名的理由 |

所有文件共用的修正寫在 `glossary/my_terms.csv`（`source,target,note`），優先權最高。

科目設定（`--profile`）決定名詞庫的優先順序。有模型判斷上下文時，這個順序只在難分高下時參考；沒判斷過的詞照這個順序選，例如 drag coefficient 在「力學」名詞庫是「曳力係數」，在「航空太空」是「阻力係數」。大陸用語（方差、置信、模量…）不會列為候選。

```bash
uv run textbook-tw profiles                                         # 列出科目設定
uv run textbook-tw glossary scan 課本.pdf --profile aerospace --force  # 換科目重建術語表並讓模型判斷（會覆蓋你的修改）
uv run textbook-tw glossary resolve 課本.pdf                         # 只讓模型判斷還沒判斷過的詞（--all 全部重判）
uv run textbook-tw glossary update                                  # 重新下載名詞庫
```

挑選規則：多字詞組（Mach number、angle of attack）都收；單一單字大多是一般用字（名詞庫裡 can→罐、figure→數字），所以只收英文裡少見、而且多個名詞庫譯名一致的字（fuselage→機身）。

## 資料夾說明

| 資料夾 | 用途 | 上傳 GitHub |
|---|---|---|
| `input/slides/` | 放要翻譯的**簡報** PDF | ❌ |
| `input/textbooks/` | 放要翻譯的**教科書** PDF | ❌ |
| `output/` | 翻譯結果 | ❌ |
| `config/` | 預設設定與科目設定（流體力學、航太、工程數學、材料與結構） | ✅ |
| `glossary/` | 術語來源清單與你的修正表 `my_terms.csv` | ✅（原始名詞庫不上傳） |
| `src/textbook_tw/` | 程式碼 | ✅ |
| `eval/` | 模型評比（測試段落不上傳） | ✅ |
| `docs/` | 設計文件 | ✅ |

所有 PDF 都不會上傳到 GitHub（見 `.gitignore`），因為教科書與其譯本受著作權保護。

## 開發階段

- [x] 0. 環境：Python 3.12、Ollama、GitHub repo
- [x] 1. 最小可用：指令列翻譯一份 PDF，輸出純譯文版與對照版
- [x] 2. 術語系統：名詞庫下載與清理、科目設定、文件專屬術語表
- [ ] 3. 翻譯閘道與模型評比：簡轉繁、大陸用語檢查、比較模型
- [x] 4. 桌面介面：拖放檔案、選科目與輸出格式、術語確認、看進度、Windows 安裝檔
- [ ] 5. 收尾：安裝說明、自動測試

設計細節見 [docs/architecture.md](docs/architecture.md)。

## 授權

本專案以 [GNU AGPL-3.0](LICENSE) 授權釋出，因為所使用的 BabelDOC 採用相同授權。

術語資料來源：國家教育研究院「學術名詞」資料集，依[政府資料開放授權條款-第1版](https://data.gov.tw/license)使用。
