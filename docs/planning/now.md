# XBrainLab Now

最後更新：`2026-08-30`

## 目前焦點：Assistant stage projection 與 notch Nyquist precondition

唯一 active slice 是 `fix/assistant-clarification-capture-v1`，以
`971309d8a65d61abb0b379b1827e8a231f39afa5` 為起點。此 slice 收斂兩個已核准、彼此獨立但都
由既有 owner 表達的產品契約；不重做 Assistant 架構。

### 問題與證據

- `select_channels` 的 Assistant publication 目前仍在 `preprocessed`，但核准 workflow 是只在
  `data_loaded` 提供；`set_montage` 保持在 `data_loaded`、`preprocessed`，在 epoch 後消失。
- Notch filter 的 model schema、stage publication 與 DSP command mapping 都已存在，但 100 Hz
  recording 上要求 50/60 Hz 的 notch 會晚到 MNE/DSP 層才失敗。Assistant 必須收到可信、可採取
  行動的 backend precondition result，而不是 generic runtime failure。

### Outcome

- `select_channels` 只在 `data_loaded` 對模型發布；`set_montage` 維持 `data_loaded` 與
  `preprocessed`。兩者都在 epoch 成功後不再發布。
- `apply_notch_filter` 的 schema、published stages（`data_loaded`、`preprocessed`）與 DSP 行為不變。
  既有 preprocess command owner 在 MNE prepare 前，從本次 `source_data` 的最低可靠 sampling rate
  檢查 `freq < sfreq / 2`。違反時回 typed `PreconditionError`：訊息包含 requested frequency、sampling
  rate、Nyquist 與下一步；若 data 曾 resample，說明 reset → notch → resample。資料、history、processor
  與 commit 必須保持不變。

### Scope 與 non-goals

- 只修改既有 `STAGE_CONFIG` 和既有 preprocessing command owner；沿用
  `ApplicationService → ToolCommandResult → existing presentation`。
- 不改 UI 檔案、prompt、model、tool schema、bandpass/resample、DSP implementation、tool surface、
  auto-reorder、receipt、router 或新的 owner/state machine。
- sampling rate 無法可靠取得時，不猜測也不阻擋，維持既有 execution path。

### TDD 與 focused validation

1. 先讓 stage exact-set 與 real `ContextAssembler` publication 測試證明現況錯誤：`data_loaded`
   有 `select_channels`、`preprocessed` 沒有；`set_montage` 僅於 epoch 前存在。
2. 以 100 Hz source data 讓 50/60 Hz notch 的 ApplicationService/PreprocessCommandService 測試先 red：
   必須得到 `PreconditionError`、preserve state/history、且 processor/commit 未被呼叫；低於 Nyquist
   的 notch 仍走既有 prepare/commit。
3. 驗證 typed result 的 controller-visible summary 有 requested frequency、sampling rate、Nyquist
   與 actionable guidance，且不退回 status-bar-only 或 generic `try again` copy。
4. 最小實作後重跑同一組測試、directly affected adjacent tests、touched Python Ruff 與
   `git diff --check`。

### Stop condition 與 UI copy approval

若需要改 GUI/backend capability、prompt heuristic、schema、DSP 行為、添加 owner/module/state machine，或
生產改動超過兩個檔案／net 100 LOC，停止並回報。UI copy approval：已核准使用既有 Assistant terminal
presentation 顯示 backend typed precondition message；本 slice 不改任何 UI 檔案或 layout。
