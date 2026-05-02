# Target Architecture

最後更新：`2026-05-01`

這份文件描述理想架構。它是目標，不代表目前已完成。

## 目標圖

```text
PyQt UI panels
Assistant tools
Headless scripts
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
  +-- MNE / file loaders
  +-- PyTorch models
  +-- filesystem
  +-- runtime diagnostics
```

## Application Service / Command API

Application Service 是 UI、agent tools、scripts 共用的 workflow command layer。

它不是新的大型 framework，也不是單純把 `BackendFacade` 改名。它的責任是承接軟體能力面：

- `load_data(files)`
- `attach_labels(mapping)`
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
- 可被 UI、agent、script 共用的測試。

Command API 也應提供 backend-controlled capability policy：

- 目前哪些 command 可執行。
- 哪些 command 被阻擋，以及原因。
- 哪些 command 需要使用者確認。
- command 對應的 target resource，例如 dataset、training job、model result。

這個 policy 應由 Application Service / backend state 產生，而不是交給 agent 自己從全部 tool list 中猜。

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

## Agent tools 的目標角色

agent tools 應包 command input / output，不應直接操作零散 controller internals。

理想上：

```text
Agent tool: load_data(files)
  -> LoadDataCommand(files)
  -> command result
  -> structured response for assistant
```

UI button 也應走同一條能力面：

```text
UI Dataset import button
  -> LoadDataCommand(files)
  -> command result
  -> UI refresh event
```

## 開工原則

後端重構前先做全盤架構複盤。

重構順序應該是：

1. 盤點每個 controller 內的 workflow logic。
2. 找出 UI 已依賴的 controller method 和 event。
3. 選一條低風險 workflow 建立 command。
4. 讓 UI 和 headless path 共用 command。
5. 補 non-mocked command / integration tests。
6. 再逐步擴大到 data、training、evaluation、agent tools。

不建議一次大改 `Study`、controller、facade 和 agent tools。
