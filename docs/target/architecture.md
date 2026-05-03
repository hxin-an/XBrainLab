# Target Architecture

最後更新：`2026-05-04`

這份文件描述理想架構。它是目標，不代表目前已完成。

## 目標圖

```text
PyQt UI panels
Assistant tools
Headless scripts
MCP server
  |
  v
Application Service / Command API
  |
  v
Study / Domain State
  |
  +-- DataManager
  +-- TrainingManager
  +-- Evaluation / Visualization services
  |
  v
Infrastructure
  +-- MNE / file loaders / BIDS metadata readers
  +-- PyTorch models
  +-- filesystem
  +-- runtime diagnostics
```

## Application Service / Command API

Application Service 是 UI、agent tools、scripts、MCP external agents 共用的 workflow command layer。

它不是新的大型 framework，也不是單純把 `BackendFacade` 改名。它的責任是承接軟體能力面。
資料入口的目標心智模型不是舊式 `load_data` / `attach_labels`，而是 Data Interpretation flow：

- `scan_source(source_path, source_hint)`
- `preview_interpretation(scan_id, choices)`
- `validate_interpretation(candidate_id)`
- `apply_interpretation(candidate_id, confirmed)`
- `save_interpretation_recipe(interpretation_id)`
- `apply_preprocess(config)`
- `generate_dataset(config)`
- `configure_training(config)`
- `start_training()`
- `stop_training()`
- `evaluate_model(config)`
- `get_current_state()`

每個 command 應該有：

- 明確 input schema。
- 明確 output / result object。
- 可分類 error。
- 對 domain state 的受控 side effect。
- 可被 UI、agent、script、MCP adapter 共用的測試。

Command API 也應提供 backend-controlled capability policy：

- 目前哪些 command 可執行。
- 哪些 command 被阻擋，以及原因。
- 哪些 command 需要使用者確認。
- command 對應的 target resource，例如 dataset、training job、model result。

這個 policy 應由 Application Service / backend state 產生，而不是交給 agent 自己從全部 tool list 中猜。

Command API 也應提供 autonomy policy / decision boundary。Capability policy 只回答
「能不能執行」；autonomy policy 回答「agent 能不能自動執行、執行後能不能繼續」。

每個 command 的 result 應至少能表達：

- `capability_decision`：backend state 是否允許 command。
- `autonomy_decision`：`allow_auto`、`confirm`、`ask_user`、`stop`、`repair`、`block`。
- `decision_boundary`：semantic、high-impact、long-running、destructive、blocked、
  missing-input、resource-lock 等。
- `continue_allowed_after_success`：成功後 agent 是否可繼續下一個 command。
- `required_confirmation`：若需要使用者確認，要確認什麼語意或高影響操作。

因此 command allowed 不代表 agent allowed auto-run。`start_training`、`reset_session`、
`apply_interpretation`、`select_split_strategy` 等高影響 command 必須被 autonomy policy
明確約束。

Data Interpretation command 的 target resource 是資料來源、候選資料解讀、已套用資料解讀和
import recipe。舊的 file loader / label loader 可以作為底層能力存在，但不應成為 UI、agent、headless script 或 MCP external agent 的主要 workflow command。

Data Interpretation 也應承接 subject / session / task / run metadata。這些欄位不能被視為
UI 表格裝飾，因為它們會影響 subject-wise / session-wise split、training report、saliency
解釋和 thesis evidence。

目標 workflow 不能只靠單一 stage 字串描述，但目前目標也不是同時開多個 active dataset。XBrainLab 應先維持一個 active dataset pipeline，並支援同一 dataset 上的多個 training run / evaluation / visualization result。

多 run / 多 result 不等於任意並行。Command API 必須對每個 target resource 檢查前置條件：沒有 loaded data 不能 preprocess，沒有 dataset 不能 training，沒有 trained result 不能 saliency / model-based visualization。epoch / dataset 形成後，載入新資料或開新 dataset 應是 reset / new session / fork 類高風險 command，不應作為一般 available command。

## UI 的目標角色

UI 應該是 command API 的 human-facing adapter。

它負責：

- 收集使用者輸入。
- 呈現 state、progress、error。
- 提供可預期的 navigation 和 feedback。
- 透過 Qt event / observer bridge 安全刷新。

它不應該長期直接承載 workflow business logic。

## Controller 的目標角色

目前 controllers 仍包含不少 workflow logic。目標狀態下：

- controller 應逐步變成 adapter。
- business workflow 下沉到 service / command。
- observer event 保留，但 event payload 和 lifecycle 要明確。
- UI 依賴 controller method 的範圍要先盤點，不能直接大改。

## BackendFacade 的目標角色

`BackendFacade` 可以保留，但不應成為第二套 backend。

比較好的角色是：

- assistant / script 的 high-level wrapper。
- command API 的便利入口。
- 不自己重做 workflow logic。
- 不讓 UI 和 agent 行為分裂。

## Automation Adapters / MCP

headless path 仍有意義，但它不應被理解成產品主要使用介面。比較好的定位是 automation
adapter：

| Adapter | 主要用途 |
| --- | --- |
| CLI / headless runner | CI、tests、thesis eval、batch processing、artifact generation。 |
| MCP server | 讓外部 agent 操作 XBrainLab，而不需要在 agent client 端安裝完整 EEG / PyQt / PyTorch stack。 |

MCP server 應該跑在 XBrainLab 已準備好的 runtime 裡，對外暴露穩定 tool schema。外部 agent
透過 MCP 呼叫 tools；MCP server 再把 calls 轉成 `ApplicationService / Command API`。
目前 Goal 1 的最低 MCP-ready adapter 是 `XBrainLab.backend.application.automation`：
它從同一組 typed command dataclass 產生 JSON schema / MCP-shaped tool specs，並把 JSON
payload 轉回 `ApplicationService.execute()` 可執行的 command；adapter 本身不得直接碰
controller internals。

MCP 不應該：

- 直接打 controller internals。
- 繞過 Data Interpretation validation。
- 繞過 capability policy 或 autonomy policy。
- 重新定義一套和 UI / in-app assistant 不同的 workflow truth。
- 要求外部 agent client 自己安裝 MNE、PyTorch、PyQt 或 XBrainLab 的大型依賴。

MCP exposed tools 應沿用成熟 workflow taxonomy，例如：

- Discovery / Query：`get_state`、`explain_validation_state`。
- Data Interpretation：`scan_source`、`preview_interpretation`、`validate_interpretation`、
  `apply_interpretation`、`save_recipe`、`reload_recipe`。
- Metadata Resolution：`preview_subject_map`、`confirm_subject_map`、`confirm_class_map`、
  `confirm_event_roles`。
- Data Transform：`apply_preprocess`、`create_epoch`、`generate_dataset`。
- Experiment Setup / Execution：`configure_training`、`start_training`、`run_evaluation`、
  `run_saliency`。
- Lifecycle：`reset_session`、`new_session`、`clear_dataset`。

如果 MCP call 觸發 decision boundary，MCP result 必須回傳同樣的 `autonomy_decision`、
`decision_boundary`、`required_confirmation` 和 user-facing explanation。外部 agent 不能因為
跑在 app 外面就獲得更高權限。

## Agent tools 的目標角色

agent tools 應包 command input / output，不應直接操作零散 controller internals。

理想上：

```text
Agent tool: scan_data_source(source_path)
  -> ScanSourceCommand(source_path, source_hint="auto")
  -> interpretation preview / validation decision
  -> command result
  -> structured response for assistant
```

UI button 也應走同一條能力面：

```text
UI Dataset import wizard
  -> scan / preview / validate / confirm / apply DataInterpretation
  -> command result
  -> UI refresh event
```

agent tool 類型要重新設計成 workflow intent taxonomy，而不是沿用舊 `dataset / preprocess /
training` 粗分類。目標 taxonomy 至少包含：

- Discovery / Query。
- Data Interpretation。
- Metadata Resolution。
- Data Transform。
- Experiment Setup。
- Execution。
- Lifecycle / Destructive。
- UI Routing。

這個 taxonomy 要反映 side effect、decision boundary、confirmation rule 和 scorer 欄位。
舊模組分類可以留在 source code 內部，但不能作為 agent 對外 tool contract。

## 開工原則

後端重構前先做全盤架構複盤。實作順序可由 runner 自行安排，但交付不能停在半成品，也不能讓
UI、agent 和 backend 留下多套資料解讀 truth。

重構時至少要處理：

1. 盤點每個 controller 內的 workflow logic。
2. 找出 UI 已依賴的 controller method 和 event。
3. 把資料入口收斂到 Data Interpretation command surface。
4. 補 command-specific autonomy policy / decision boundary。
5. 讓 UI 和 headless path 共用同一條 scan / preview / validate / apply / recipe flow。
6. 讓 MCP server 作為 external agent adapter，共用同一套 command taxonomy。
7. 補 non-mocked command / integration tests。
8. 清掉或隔離會讓新 UI / agent / MCP 走回舊 `load_data` / `attach_labels` 心智模型的路徑。
