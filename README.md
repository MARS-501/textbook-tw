# textbook-tw

把英文 PDF 簡報與原文教科書翻成**台灣繁體中文**，並**保留原本的版面、圖表與公式**。
翻譯全部在自己的電腦上用本地模型完成，不需要把檔案上傳到任何雲端服務。

> 🚧 開發中。目前可以用指令列翻譯（含術語表），網頁介面還在開發，進度見下方「開發階段」。

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
| `--no-glossary` | 不使用術語表 |

預設值在 `config/default.toml`；想改成自己的預設，可以建立 `config/local.toml` 只寫要改的項目（不會上傳 GitHub）。

翻譯中途按 Ctrl+C 中斷也沒關係，已翻好的段落有快取，重跑時會跳過。

## 術語表

第一次翻譯某份 PDF 時，程式會掃描全文，從國家教育研究院的名詞庫挑出文中出現的術語，存成 `glossary/books/<檔名>.csv`。之後翻譯同一份 PDF（包括只翻部分頁面）都用這份術語表，全書譯名一致。

用 Excel 打開這個檔案就能修改：

| 欄位 | 說明 |
|---|---|
| `source` | 英文術語 |
| `target` | 採用的譯名。**改這欄**就能換譯名；清空代表不使用 |
| `status` | `待確認`：名詞庫譯名不一致，沒有自動採用，請從 `alternatives` 挑一個填進 `target`<br>`名詞庫譯名不同`：已採用科目設定裡優先的名詞庫，其他名詞庫的譯法列在 `alternatives` |
| `count` | 在這份文件出現的次數 |
| `origin` | 譯名來自哪個名詞庫 |
| `alternatives` | 其他候選譯名 |

所有文件共用的修正寫在 `glossary/my_terms.csv`（`source,target,note`），優先權最高。

科目設定（`--profile`）決定名詞庫的優先順序，會影響譯名，例如 drag coefficient 在「力學」名詞庫是「曳力係數」，在「航空太空」是「阻力係數」。

```bash
uv run textbook-tw profiles                                         # 列出科目設定
uv run textbook-tw glossary scan 課本.pdf --profile aerospace --force  # 換科目重建術語表（會覆蓋你的修改）
uv run textbook-tw glossary update                                  # 重新下載名詞庫
```

挑選規則：多字詞組（Mach number、angle of attack）都收；單一單字大多是一般用字（名詞庫裡 can→罐、figure→數字），所以只收英文裡少見、而且多個名詞庫譯名一致的字（fuselage→機身）。

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
- [x] 2. 術語系統：名詞庫下載與清理、科目設定、文件專屬術語表
- [ ] 3. 翻譯閘道與模型評比：簡轉繁、大陸用語檢查、比較模型
- [ ] 4. 網頁介面：拖放檔案、選科目與輸出格式、看進度
- [ ] 5. 收尾：安裝說明、自動測試

設計細節見 [docs/architecture.md](docs/architecture.md)。

## 授權

本專案以 [GNU AGPL-3.0](LICENSE) 授權釋出，因為所使用的 BabelDOC 採用相同授權。

術語資料來源：國家教育研究院「學術名詞」資料集，依[政府資料開放授權條款-第1版](https://data.gov.tw/license)使用。
