# Repository 與 owners

從行為的 owner 開始找，不要只看距離最近的 widget 或 helper。

| 區域 | 主要位置 | 責任 |
| --- | --- | --- |
| Desktop UI | `XBrainLab/ui/` | 可見 workflow、dialogs、panels 與 presentation state |
| 產品 command boundary | `XBrainLab/backend/application/` | Admission、mutation、capability、results 與 publication |
| EEG／domain logic | `XBrainLab/backend/` | Data interpretation、preprocessing、datasets、training 與 analysis |
| 本機 Assistant | `XBrainLab/llm/` 加上 `XBrainLab/ui/components/` 的 Assistant adapters | Prompt、本機 runtime、verification、tool execution 與 UI handoff |
| Tests | `tests/` | Observable behavior、state transition 與 integration boundary |
| 開發工具 | `scripts/dev/` | Validation、evidence capture 與 repository maintenance |
| 使用者文件 | `user_docs/` | Task-oriented desktop guidance 與 bounded dataset examples |
| 工程文件 | `docs/` | Current、architecture、target、validation、decisions 與 planning |

## Ownership 規則

`ApplicationService / Command API` 是產品的 command spine。UI panels、Assistant 與 scripts 不得
建立另一套 workflow state machine，或第二套 capability／error rules。

Owner 是能決定 admission、authoritative mutation／publication、confirmation 或 asynchronous
lifecycle 的 component。DTO、parser、renderer 與 pure function 不會因為承載資料就成為 owner。

## 選擇正確文件

- 宣稱產品事實前讀[目前狀態](../current.md)。
- 修改 boundary 前讀[目前架構](../architecture/README.md)的相關頁面。
- [目標架構](../target/README.md)只描述已核准的未來方向。
- 選擇 evidence 或 handoff claim 前讀[驗證契約](../validation/README.md)。
- 讀 [Now](../planning/now.md)，避免與 active product slice 衝突。

Source 與文件不一致時，先確認 runtime／source 行為，再修正既有 authority；不要新增另一份摘要頁。
