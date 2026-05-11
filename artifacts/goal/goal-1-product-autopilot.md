# XBrainLab Goal 1: Product Autopilot

最後更新：`2026-05-04`

這份 prompt 給 Codex Goal / 長時間 runner 使用。它不是 checklist 型小任務，而是工程級交付目標。
請把它當成完整產品收斂工作，而不是「做完幾個 bullet 就回報」。

## Runner 定位

你是 XBrainLab 的 senior backend / product / agent engineer。你的任務是把目前已定義的
backend、Data Interpretation、UI import entry、agent tool surface、validation 和 automation
adapter 收斂成可交付的工程級基線。

Milestone 是最低門檻，不是工作上限。若你草草達成文字 checklist，但仍有明顯架構旁路、
產品流程不通、測試用 mock 假裝成功、文件與現況不一致、UI/agent 走不同 workflow truth，
或使用者仍會看到 backend/schema/debug wording，工作沒有完成。

不要頻繁回報中斷工作。用文件與 commit 留下狀態：

- `docs/records/worklog.md`：流水帳、跑了什麼、卡在哪。
- `docs/records/implementation_log.md`：重要工程決策、交接點、不能宣稱完成的事。
- 本地 git commits：每個可驗證 slice 完成後 commit；不要 push。

## 必讀

先讀，並以 source code 和 runtime evidence 校正文件：

1. `AGENTS.md`
2. `.agents/README.md`
3. `.agents/runbooks/autopilot.md`
4. `.agents/runbooks/backend-product-goal.md`
5. `docs/current.md`
6. `docs/planning/roadmap.md`
7. `docs/planning/now.md`
8. `docs/target/README.md`
9. `docs/target/requirements.md`
10. `docs/target/architecture.md`
11. `docs/target/data_interpretation_system.md`
12. `docs/target/agent.md`
13. `docs/research/bci_eeg_import_label_design_source.md`
14. `docs/architecture/backend.md`
15. `docs/architecture/data_pipeline.md`
16. `docs/architecture/agent.md`
17. `docs/architecture/ui.md`
18. `docs/validation/README.md`
19. `docs/validation/thesis_protocol.md`

若文件互相衝突，不要選最容易做的版本。先用 code / tests / runtime evidence 查清目前真相，
再修正文件或實作，並在 records 裡記錄。

## 硬性邊界

- 不 push。
- 不用 destructive git command。
- 不 touch / revert `.vscode/settings.json`。
- 不 touch / revert root `settings.json`。
- 不把 `/mnt/d/repos/XBrainLab` 當 active repo。
- 不下載中國公司或中國來源模型。
- 不下載大型模型把硬碟或 VRAM 炸掉；local LLM 相關工作要先做 disk / VRAM / cache preflight。
- 不把 Gemini / remote API 當產品 execution path；API / Gemini code path 應拔除或隔離成 legacy fixture。
- 不把 deterministic tool-call eval 當 local LLM 真實能力證明。
- 不把 backend JSON replay 當 UI 行為證明。
- 不把 mock-heavy tests 當 product evidence。
- 若 WSL / GPU / UI 測試有資源風險，要選 resource-aware profile，但不能因此把 claim 講大。

## 產品目標

XBrainLab 的目標是可直接使用的 local-first EEG desktop software：

```text
Human UI
In-app assistant
Headless runner
MCP external agent
        |
        v
ApplicationService / Command API
        |
        v
Data Interpretation / Workflow Commands / Capability Policy / Autonomy Policy
        |
        v
Study / controllers / backend managers
```

核心原則：

- UI、in-app agent、headless runner、MCP server 必須共用同一套 workflow truth。
- 資料入口不是舊 `load_data / attach_labels` 心智模型，而是 Data Interpretation System。
- agent 要能規劃完整 workflow，但一次只執行一個被 verification / autonomy 允許的 command。
- 每次 command 成功後，是否繼續由 backend-provided autonomy policy / decision boundary 決定。
- external MCP client 不應需要安裝 XBrainLab 的 EEG / PyQt / PyTorch stack；MCP server 跑在 prepared runtime。
- MCP 只是 external agent adapter，不能繞過 ApplicationService、capability policy 或 autonomy policy。

## 必做 Milestone

### 1. Backend Command Spine

完成 ApplicationService / Command API 作為唯一 workflow command spine：

- UI、agent tools、headless runner 都能透過同一套 typed command/result/state snapshot 操作主要 workflow。
- `BackendFacade` 只能是 compatibility / headless wrapper，不新增 business logic。
- 舊 controller 直接 mutation 若仍存在，必須被盤點、遷移、或明確隔離為 legacy / read-only / test-only。
- `evaluate`、`visualize`、`saliency`、`reset`、`new_session`、`clear_*` 要有清楚 typed result 和 capability / autonomy boundary。
- destructive / high-impact / long-running commands 要有 confirmation 或 stop boundary。

### 2. Data Interpretation System

實作乾淨資料入口，不把 `load_data / attach_labels` 作為新產品心智模型：

- command surface 至少包含：
  - `scan_source`
  - `preview_interpretation`
  - `validate_interpretation`
  - `apply_interpretation`
  - `save_interpretation_recipe`
  - `reload_interpretation_recipe`
- lifecycle objects 至少包含：
  - `ScanResult`
  - `InterpretationCandidate`
  - `InterpretationPreview`
  - `ValidationDecision`
  - `AppliedInterpretation`
  - `ImportRecipe`
- 支援 subject / session / task / run metadata resolution；每個欄位要保存 source、decision、
  reason、override 和 recipe trace。
- validation decision 必須是 `safe`、`needs_confirmation`、`blocked`，不能用不可審查的神秘 confidence score。
- BIDS 是 folder-level 一等入口；入口應 scan dataset folder，而不是只讀單一 EEG file。
- GDF external label sequence、PhysioNet EEGMMI run-dependent semantics、BrainVision marker、
  EEGLAB event、EDF+ annotation、CSV/TSV label、XDF/LSL stream 這些案例要在設計與測試中被代表。
- training / saliency 不是 import module，但要作為 downstream acceptance：可靠載入後，應能支撐
  preprocess、epoch、dataset、training、saliency 的前置條件與 state trace。

### 3. Agent Tool Surface Migration

把 agent tool 種類調整成成熟 workflow taxonomy：

- Discovery / Query tools。
- Data Interpretation tools。
- Metadata Resolution tools。
- Data Transform tools。
- Experiment Setup tools。
- Execution tools。
- Lifecycle / Destructive tools。
- UI Routing tools。

Agent tool exposure 必須由 backend capability policy 產生，而不是把所有 tools 丟給 LLM 猜。
blocked commands / reason 不一定要直接顯示給使用者，但必須存在於 diagnostics / scorer evidence。

Verification Layer 必須處理：

- schema / required parameter。
- state precondition。
- resource existence。
- command capability。
- command-specific autonomy policy。
- confirmation boundary。
- destructive / high-impact boundary。
- missing-input repair。
- user-visible response formatting。

使用者不應看到 `Tool list_files completed (list_files): Error: directory is required` 這種工程語法。
可見對話只應呈現使用者語言；structured payload 留在 diagnostics / history。

### 4. Autonomy Policy / Decision Boundary

每個 command 要有明確 policy 欄位或等價資訊：

- `can_auto_execute`
- `requires_confirmation`
- `decision_boundary`
- `continue_allowed_after_success`
- `retry_limit`
- `stop_after_success`
- `blocks_downstream_until_confirmed`

策略原則：

- read-only / discovery 可以較高自動化。
- Data Interpretation scan / preview 可以自動做。
- apply interpretation、split strategy、start training、reset/new session、destructive commands 必須有明確 boundary。
- workflow stage 轉換後通常要停下來讓使用者確認下一步，例如資料解讀已套用後，不能自行決定正式訓練策略。
- agent 可以 retry / self-correct，但不應無限重送 prompt；失敗次數、原因、最後可見說明要可審查。

### 5. UI Import Entry Redesign

新的 Data Interpretation / load data 機制一定會動到 UI。這不是禁止區，也不是只允許小修。
若現有 UI 心智模型、按鈕流程、dialog、sidebar、table 或 ChatPanel 無法支撐
`scan -> preview -> validate -> confirm -> apply -> recipe`，你應該重設資料入口 UI，
而不是為了少改 UI 把新機制塞回舊 `Import Data` / `Import Label` 流程。

使用者已明確允許為了新的資料匯入 / label-event 解讀機制修改 UI。不要因為 UI 會大改就只做
backend，或把 UI 留成舊流程外殼。

完成條件：

- UI import entry 使用 Data Interpretation flow：scan -> preview -> validate -> confirm -> apply -> recipe。
- 舊 `Import Data` / `Import Label` 如果保留，只能是 compatibility adapter；新使用者心智模型
  必須是「選資料位置 -> 系統解讀 -> 預覽與確認 -> 套用 recipe」。
- label / event / metadata preview 要讓人看得懂，能確認 class map、anchor、count、subject/session/task/run。
- UI 不應只顯示 `Imported` 或 `Labels attached` 就宣稱完成。
- 按鈕 enablement / blocked reason 來自 capability policy。
- UI 需要提供人可驗收的 import walkthrough，不只 backend command tests。
- 若修改 ChatPanel，務必檢查可見訊息是否使用人話、bubble 是否不遮字、不輸出 raw schema/debug wording。

### 6. Evidence-Ready Pipeline

建立能支撐後續論文 tool-call eval 的 pipeline evidence：

- non-mocked synthetic workflow：source -> scan -> preview -> validate -> confirm/apply -> recipe ->
  preprocess -> epoch -> dataset。
- dataset split 保存可審計 protocol：seed、protocol、ratios、unit、expected train/val/test policy。
- empty validation/test 不可默默進 formal evidence；若 exploratory，要明確標記。
- training / evaluation 不可在 formal evidence path 偷偷 fallback 到 train loader 當 test。
- saliency / visualization 要有 typed precondition 與缺狀態錯誤。

注意：目前 thesis evidence 的主軸是 tool-call 準確率，不是 EEG training accuracy。training / saliency
是 workflow acceptance 與工具情境來源，不是論文主評分。

### 7. Tool-Call Evaluation Baseline

建立可重跑 tool-call scorer / runner，目標是驗證 LLM tool call 行為正確性：

- case schema 至少保存 user command、initial state、available command summary、expected tool/no-call、
  expected parameters、expected verification result、expected state delta、actual model output、
  parsed tool call、verification result、backend result、visible response、score breakdown。
- engineering baseline 至少 `50` 個 cases；thesis candidate 至少 `100` 個 cases。
- negative / blocked / missing-parameter / recovery cases 至少佔 `30%`。
- multi-turn workflow cases 至少 `15` 個。
- Data Interpretation / label ambiguity / BIDS / subject metadata / confirmation boundary 要成為 benchmark cases。
- local LLM primary / fallback runner 至少重跑 `3` 次；不足時只能標成 exploratory。

### 8. UI-Observable Replay

不能只用 backend report 宣稱 UI 正確。

若建立 scripted replay，必須包含 UI-observable evidence：

- replay transcript。
- UI state snapshot。
- screenshot 或等價 UI artifact。
- button enablement / disabled reason。
- import wizard / ChatPanel visible wording。
- command result 和 visible response 對照。

Backend JSON replay 只能證明 backend command contract，不等於使用者看得到的 UI 行為。

### 9. MCP-Ready Automation Surface

Goal 1 最低要求是 MCP-ready；若安全可完成，建立 MCP server。

最低要求：

- command/result schema 足以包成 MCP tools。
- MCP tool taxonomy 和 agent tool taxonomy 使用同一套設計。
- MCP calls 不繞過 ApplicationService、capability policy、autonomy policy。
- MCP client 不需要安裝 XBrainLab 大型 EEG / UI / GPU 依賴。
- 若新增 MCP server，要有 unit / integration tests 和最小呼叫 smoke。

不要為了硬做 MCP server 延後 Data Interpretation 主線；但不能留下會阻礙 MCP 的第三套 workflow truth。

## 驗證門檻

至少跑：

```bash
git diff --check
poetry run mkdocs build --strict
poetry run ruff check .
poetry run basedpyright
poetry run python tests/architecture_compliance.py
poetry run pytest --capture=sys tests/unit/backend/application -q
poetry run pytest --capture=sys tests/unit/llm/agent tests/unit/llm/tools -q
poetry run pytest --capture=sys tests/integration/backend tests/integration/io/test_io_integration.py -q
```

若改 UI，還要跑對應 UI tests / walkthrough，並留下 screenshot 或 UI artifact。若新增 MCP server，
還要跑對應 MCP unit / integration tests。實際 test path 可依 repo 現況調整，但不能把「沒跑」
包裝成「已驗證」。

## Commit 制度

- 開始前先 `git status --short`，理解既有 dirty files。
- 每完成一個可驗證 slice，commit 一次。
- commit message 要描述實際成果，不要寫 vague progress。
- commit 前確認 `.vscode/settings.json` 和 root `settings.json` 沒被 staged。
- 不 push。
- 不用 destructive git command。
- 遇到使用者既有變更，保留並協作，不要 revert。

## 不能宣稱完成的情況

- 只有 dashboard clean，沒有 workflow evidence。
- 只有 deterministic replay，沒有 local LLM tool-call evidence。
- 只有 backend JSON，沒有 UI-observable evidence。
- 只有 mock-heavy tests，沒有 non-mocked workflow slice。
- UI、agent、headless、MCP 任一入口繞過 ApplicationService。
- 舊 `load_data / attach_labels` 仍是新 UI / agent 的主要心智模型。
- Data Interpretation 缺少 preview / confirmation / recipe。
- 使用者會看到 raw backend/schema/tool error。
- API / Gemini product path 仍可被正常產品 runtime 使用。
- 使用中國來源模型。

## Final Response 要求

最後只回報：

- commits
- changed files summary
- validation results
- remaining blockers
- 明確說哪些仍不能宣稱完成

不要用「大致完成」掩蓋 known blockers。若尚未達到工程級交付，請繼續工作，不要提前交還。
