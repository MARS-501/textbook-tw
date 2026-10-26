# textbook-tw

把英文 PDF 簡報與原文教科書翻成**台灣繁體中文**，並**保留原本的版面、圖表與公式**。
翻譯全部在自己的電腦上用本地模型完成，不需要把檔案上傳到任何雲端服務。

> 🚧 開發中。目前可以用指令列翻譯，術語表與網頁介面還在開發，進度見下方「開發階段」。

## 功能（規劃）

- **保留版面**：以 [BabelDOC](https://github.com/funstory-ai/BabelDOC) 為版面引擎，圖片、圖表、公式不動，譯文填回原位置
- **中英對照**：可選擇輸出
  - 左右並排（左原文、右譯文）
  - 交替頁（原文頁、譯文頁輪流）
  - 兩種都輸出
  - 另有純譯文版
- **本地模型**：透過 [Ollama](https://ollama.com) 執行，預設 Qwen3.5-4B，6GB 顯卡可用
- **專業術語**：內建國家教育研究院學術名詞（航空太空、力學、數學、機械工程等），依科目決定優先順序，全書譯名一致
- **台灣用語**：自動把簡體字與大陸用語修正為台灣繁體用語

## 安裝

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
| `--profile fluid-mechanics／aerospace／engineering-math` | 科目設定 |
| `--font auto／serif／sans-serif` | 譯文字型；`auto` 時投影片用黑體 |
| `--translated-first` | 對照版譯文放前面 |
| `--no-mono` | 不輸出純譯文版 |

預設值在 `config/default.toml`；想改成自己的預設，可以建立 `config/local.toml` 只寫要改的項目（不會上傳 GitHub）。

翻譯中途按 Ctrl+C 中斷也沒關係，已翻好的段落有快取，重跑時會跳過。

## 資料夾說明

| 資料夾 | 用途 | 上傳 GitHub |
|---|---|---|
| `input/slides/` | 放要翻譯的**簡報** PDF | ❌ |
| `input/textbooks/` | 放要翻譯的**教科書** PDF | ❌ |
| `output/` | 翻譯結果 | ❌ |
| `config/` | 預設設定與科目設定（流體力學、航太、工程數學） | ✅ |
| `glossary/` | 術語來源清單與你的修正表 `my_terms.csv` | ✅（原始名詞庫不上傳） |
| `src/textbook_tw/` | 程式碼 | ✅ |
| `eval/` | 模型評比（測試段落不上傳） | ✅ |
| `docs/` | 設計文件 | ✅ |

所有 PDF 都不會上傳到 GitHub（見 `.gitignore`），因為教科書與其譯本受著作權保護。

## 開發階段

- [x] 0. 環境：Python 3.12、Ollama、GitHub repo
- [x] 1. 最小可用：指令列翻譯一份 PDF，輸出純譯文版與對照版
- [ ] 2. 術語系統：名詞庫下載與清理、科目設定、文件專屬術語表
- [ ] 3. 翻譯閘道與模型評比：簡轉繁、大陸用語檢查、比較模型
- [ ] 4. 網頁介面：拖放檔案、選科目與輸出格式、看進度
- [ ] 5. 收尾：安裝說明、自動測試

設計細節見 [docs/architecture.md](docs/architecture.md)。

## 授權

本專案以 [GNU AGPL-3.0](LICENSE) 授權釋出，因為所使用的 BabelDOC 採用相同授權。

術語資料來源：國家教育研究院「學術名詞」資料集，依[政府資料開放授權條款-第1版](https://data.gov.tw/license)使用。
