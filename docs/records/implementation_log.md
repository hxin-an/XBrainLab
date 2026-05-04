# XBrainLab Implementation Log

這份文件記錄接手後的重要實作與整理工作。

它不是 changelog，也不是每日流水帳。它的目的是讓之後的人知道：

- 當時解決了什麼問題
- 為什麼這樣改
- 改到哪些區域
- 有什麼驗證證據
- 還留下什麼風險

新 entry 插在本格式說明下方，最新在上。

## Entry 格式

```md
## YYYY-MM-DD 主題

### 背景

### 變更

### 影響範圍

### 驗證

### 剩餘風險
```

## 2026-05-04 Post-load label import target context

### 背景

`Add Labels to Loaded Data` 已是 service-backed compatibility path，成功後也會更新 applied
interpretation recipe trace。但 dialog 本身仍像舊式 label file picker：使用者在選 label files
和 mapping code 時，看不到 labels 會套到哪些 loaded EEG files，也看不到這會影響 recipe trace。

### 變更

- `ImportLabelDialog` 新增可選 `target_files` 參數。
- Dialog title 改為 `Add Labels to Loaded Data`。
- Dialog 上方新增 target summary：
  - 顯示 selected target count。
  - 顯示最多前三個 target EEG file name。
- Dialog 新增 recipe-impact note，說明成功 import 會在 active data interpretation 時更新 import
  recipe trace。
- `DatasetActionHandler.import_label()` 會把 `_get_target_files_for_import()` 選出的 target
  files 傳給 dialog。

### 影響範圍

- Post-load label import dialog。
- Dataset action handler。
- Import-label UI tests。
- Current / planning / validation / records docs。

### 驗證

- TDD red:
  - focused tests first failed because `ImportLabelDialog` did not accept `target_files` and
    `DatasetActionHandler.import_label()` still instantiated it without target context.
- UI regression:
  - `scripts/dev/run_ui_pytest.sh tests/unit/ui/dataset/test_import_label.py::test_import_label_dialog_shows_target_context tests/unit/ui/test_ui_misc.py::TestDatasetActionHandler::test_import_label_passes_target_context_to_dialog -q`
  - `2 passed`
  - `scripts/dev/run_ui_pytest.sh tests/unit/ui/dataset/test_import_label.py tests/unit/ui/test_ui_misc.py::TestDatasetActionHandler tests/unit/ui/test_ui_misc.py::TestImportLabelDialog -q`
  - `83 passed`
- static:
  - targeted `ruff` -> pass
  - targeted `ruff format --check` -> pass
  - production touched-file `basedpyright` -> `0 errors, 0 warnings, 0 notes`
  - `poetry run mkdocs build --strict` -> pass with existing MkDocs Material warning
  - `poetry run python tests/architecture_compliance.py` -> `Architecture compliant!`
  - `git diff --check` -> pass

### 剩餘風險

- This makes the compatibility label flow more user-facing.
- It is not a full embedded Data Interpretation label wizard and does not solve raw-event-anchor
  alignment, Windows launcher human click-through, interactive desktop 3D, MCP Inspector GUI, or
  thesis-ready local LLM evidence.

## 2026-05-04 Data Interpretation label carrier matched-EEG UI

### 背景

Backend 已能用 reviewed label carrier plan 做安全多檔 mapping，但 import wizard 的 label
carrier table 仍只顯示 carrier、format、label field、anchor、time model 和 granularity。
使用者看不到每個 label carrier 實際會對到哪個 EEG file，這會讓多檔 import review 仍偏向
backend JSON，而不是成熟使用者流程。

### 變更

- `DataInterpretationPreviewDialog` label carrier table 新增 `Matched EEG` 欄位。
- match 顯示規則：
  - 單一 EEG + 單一 carrier：顯示該 EEG 檔名，保留既有 backend direct apply 行為。
  - 多 EEG：用 normalized stem 唯一 match 時顯示 EEG 檔名。
  - 無法唯一 match：顯示 `Needs review`。
- `_label_carrier_choices()` 欄位 index 已更新，新增欄位後仍正確回傳 label field、anchor、
  time model 和 granularity。
- `capture_data_interpretation_replay.py` 更新填欄 index，刷新 UI-observable replay artifact。

### 影響範圍

- Data Interpretation preview dialog。
- Data Interpretation replay script / artifacts。
- UI dialog tests。
- Current / planning / validation / records docs。

### 驗證

- TDD red:
  - `test_data_interpretation_preview_dialog_returns_label_carrier_review` first failed because
    column 1 still showed `MAT` instead of matched EEG file.
- UI tests:
  - `scripts/dev/run_ui_pytest.sh tests/unit/ui/dialogs/dataset/test_data_interpretation_preview_dialog.py -q`
  - `6 passed`
  - `scripts/dev/run_ui_pytest.sh tests/unit/ui/dialogs/dataset/test_data_interpretation_preview_dialog.py tests/unit/ui/test_ui_misc.py::TestDatasetActionHandler -q`
  - `52 passed`
- replay:
  - `timeout 180s env QT_QPA_PLATFORM=offscreen poetry run python scripts/dev/capture_data_interpretation_replay.py`
  - exit `0`
  - `artifacts/ui/data-interpretation-replay.json` label carrier row shows
    `product_replay_events.tsv -> product_replay_raw.fif`
  - replay still records reviewed `trial_type` / `onset` / `seconds` / `trial` choices and
    `label_apply.status=applied`.
- static:
  - targeted `ruff` -> pass
  - targeted `ruff format --check` -> pass
  - targeted `basedpyright` -> `0 errors, 0 warnings, 0 notes`
  - `poetry run mkdocs build --strict` -> pass with existing MkDocs Material warning
  - `poetry run python tests/architecture_compliance.py` -> `Architecture compliant!`
  - `git diff --check` -> pass

### 剩餘風險

- This improves label carrier mapping visibility in the import wizard.
- It is not a complete embedded post-load label import wizard and does not solve
  raw-event-anchor-specific GDF / MAT alignment, Windows launcher human click-through,
  interactive desktop 3D, MCP Inspector GUI, or thesis-ready local LLM evidence.

## 2026-05-04 Data Interpretation multi-file sequence label mapping

### 背景

Timestamp label carriers 已補上 safe stem-matched multi-file mapping，但 MAT / TXT trial-order
sequence labels 仍只支援單檔。BCI Competition / GDF external labels 類資料常見一個 EEG file
搭配一個 MAT labels file，若每個 file pair 已在 wizard review 後唯一對應，仍不應被擋在
單檔限制。

### 變更

- `_apply_interpretation_label_carriers()` 的 multi-file mapping 現在不只限 timestamp mode。
- sequence mode 多檔成功條件：
  - 每個 loaded EEG file 都有唯一 normalized stem match。
  - 每個 reviewed MAT / TXT carrier 都被使用。
  - class map 已確認，time model 是 `trial_order`，granularity 是 `trial`。
- sequence mode 多檔實作：
  - 逐一讀取每個 carrier 的 reviewed label field。
  - 每個 target file 單獨呼叫 `dataset.apply_labels_legacy([target], labels_for_target, ...)`。
  - 不把不同檔案的 sequence labels 串接後再分配。
- ambiguous 多檔情境，例如兩個 raw files 只有一個 generic `labels.mat`，仍 skipped，不呼叫
  label mutation path。

### 影響範圍

- `ApplicationService.apply_interpretation` reviewed label apply path。
- Data Interpretation recipe label import record。
- Backend application tests。
- Current / planning / validation / records docs。

### 驗證

- TDD red:
  - `test_apply_interpretation_applies_reviewed_sequence_label_carriers_by_stem` first failed with
    `label_apply.status=skipped`.
- focused:
  - `poetry run pytest --capture=sys tests/unit/backend/application/test_application_service.py::test_apply_interpretation_applies_reviewed_sequence_label_carriers_by_stem tests/unit/backend/application/test_application_service.py::test_apply_interpretation_skips_ambiguous_multi_file_sequence_labels -q`
  - `2 passed`
- regression:
  - `poetry run pytest --capture=sys tests/unit/backend/application/test_application_service.py tests/unit/backend/application/test_automation.py tests/unit/llm/tools/test_application_surface.py -q`
  - `65 passed`
- static:
  - targeted `ruff` -> pass
  - targeted `ruff format --check` -> pass
  - targeted `basedpyright` -> `0 errors, 0 warnings, 0 notes`
  - `poetry run mkdocs build --strict` -> pass with existing MkDocs Material warning
  - `poetry run python tests/architecture_compliance.py` -> `Architecture compliant!`
  - `git diff --check` -> pass

### 剩餘風險

- This supports safe stem-matched MAT / TXT trial-order carriers only.
- It does not support raw-event-anchor-specific GDF / MAT alignment, generic label
  disambiguation, embedded label wizard UI, Windows launcher human click-through, interactive
  desktop 3D, MCP Inspector GUI, or thesis-ready local LLM evidence.

## 2026-05-04 Data Interpretation multi-file timestamp label mapping

### 背景

Reviewed timestamp label apply 已支撐單一 EEG + 單一 CSV / TSV / BIDS events carrier，但
`apply_interpretation` 遇到多個 reviewed carriers 或多個 loaded EEG files 會直接 skip。這使
BIDS-style per-run `*_events.tsv` 無法在 Data Interpretation 主線中一次套到多個 raw files。

### 變更

- `_apply_interpretation_label_carriers()` 保留單檔 direct mapping 行為。
- 多檔 timestamp mode 現在會建立 reviewed file mapping：
  - 每個 loaded EEG file 取 normalized stem。
  - 每個 reviewed CSV / TSV / BIDS events carrier 取 normalized stem。
  - suffix normalization 會移除 `_events`、`_raw`、`_labels`、`_label`、`_eeg` 等常見尾綴。
  - 每個 raw file 必須唯一對應一個 carrier，且所有 carriers 都要被使用。
- mapping 成功時一次呼叫既有 `dataset.apply_labels_batch()`，並保留 `LabelImportPlan`
  / recipe trace record。
- ambiguous 多檔情境，例如兩個 raw files 只有一個 generic `events.tsv`，仍會 skipped 並
  回傳 reason，不會自動把同一 labels 套到多個檔案。

### 影響範圍

- `ApplicationService.apply_interpretation` reviewed label apply path。
- Data Interpretation recipe label import record。
- Backend application tests。
- Current / planning / validation / records docs。

### 驗證

- TDD red:
  - `test_apply_interpretation_applies_reviewed_timestamp_label_carriers_by_stem` first failed with
    `label_apply.status=skipped`.
- focused:
  - `poetry run pytest --capture=sys tests/unit/backend/application/test_application_service.py::test_apply_interpretation_applies_reviewed_timestamp_label_carriers_by_stem tests/unit/backend/application/test_application_service.py::test_apply_interpretation_skips_ambiguous_multi_file_timestamp_labels tests/unit/backend/application/test_application_service.py::test_apply_interpretation_applies_reviewed_timestamp_label_carrier tests/unit/backend/application/test_application_service.py::test_apply_interpretation_applies_reviewed_mat_sequence_label_carrier -q`
  - `4 passed`
- regression:
  - `poetry run pytest --capture=sys tests/unit/backend/application/test_application_service.py tests/unit/backend/application/test_automation.py tests/unit/llm/tools/test_application_surface.py -q`
  - `63 passed`
- static:
  - targeted `ruff` -> pass
  - targeted `ruff format --check` -> pass
  - targeted `basedpyright` -> `0 errors, 0 warnings, 0 notes`
  - `poetry run mkdocs build --strict` -> pass with existing MkDocs Material warning
  - `poetry run python tests/architecture_compliance.py` -> `Architecture compliant!`
  - `git diff --check` -> pass

### 剩餘風險

- This supports safe stem-matched timestamp carriers only.
- It does not support generic folder-level events disambiguation, multi-file MAT / TXT sequence
  mapping, raw-event-anchor-specific GDF / MAT alignment, embedded label wizard UI,
  Windows launcher human click-through, interactive desktop 3D, MCP Inspector GUI, or
  thesis-ready local LLM evidence.

## 2026-05-04 Data Interpretation shared state snapshot propagation

### 背景

Data Interpretation recipe / wizard 已保存 label carrier plan、format capability boundaries、
event roles 和 class map，但 shared `ApplicationStateSnapshot.interpretation` 仍只暴露舊的
label carrier path list 和 label import summary。這會讓 `query_state`、agent、headless
automation 和 MCP-shaped envelope 看不到 UI / recipe 已確認的 import truth。

### 變更

- `InterpretationStateSnapshot` 新增：
  - `label_carrier_plan`
  - `format_capabilities`
  - `event_roles`
  - `class_map`
- `ApplicationService._interpretation_snapshot()` 依序從 applied interpretation、candidate、
  preview / scan state 建立這些欄位。
- 補 backend public behavior test，覆蓋 `ApplyInterpretationCommand` result state 和
  `QueryStateCommand(query="state")` diagnostics。
- 補 automation test，覆蓋 `execute_automation_payload()` serialized state envelope。
- 補 agent surface test，覆蓋 ApplicationService-backed `query_state` tool result。

### 影響範圍

- Backend application state contract。
- `query_state` command diagnostics。
- Headless / MCP automation envelope。
- Agent ApplicationService-backed tool surface。
- Current / planning / validation / records docs。

### 驗證

- TDD red:
  - `test_data_interpretation_state_snapshot_preserves_import_review_truth` first failed because
    `InterpretationStateSnapshot` had no `label_carrier_plan` attribute.
- targeted:
  - `poetry run pytest --capture=sys tests/unit/backend/application/test_application_service.py::test_data_interpretation_state_snapshot_preserves_import_review_truth tests/unit/backend/application/test_automation.py::test_execute_automation_payload_state_contains_interpretation_review_truth tests/unit/llm/tools/test_application_surface.py::test_query_state_tool_surfaces_interpretation_review_truth -q`
  - `3 passed`
- regression:
  - `poetry run pytest --capture=sys tests/unit/backend/application/test_application_service.py tests/unit/backend/application/test_automation.py tests/unit/llm/tools/test_application_surface.py -q`
  - `61 passed`
- static:
  - targeted `ruff` -> pass
  - targeted `ruff format --check` -> pass
  - targeted `basedpyright` -> `0 errors, 0 warnings, 0 notes`
  - `poetry run mkdocs build --strict` -> pass with existing MkDocs Material warning
  - `poetry run python tests/architecture_compliance.py` -> `Architecture compliant!`
  - `git diff --check` -> pass

### 剩餘風險

- This is state propagation, not a new UI workflow.
- It does not implement mature embedded label import wizard, multi-file label mapping,
  raw-event-anchor-specific MAT / GDF alignment, Windows launcher human click-through,
  interactive desktop 3D, MCP Inspector GUI, or thesis-ready local LLM evidence.

## 2026-05-04 Usage-refresh handoff after import label apply

### 背景

使用者要求因用量即將刷新先建立交接紀錄。既有 usage-refresh handoff 仍停在
`f9f0956 assistant: capture training completion walkthrough`，但 repo 已前進到 Data
Interpretation label carrier review、format capability boundaries、timestamp label apply 和
MAT / TXT sequence label apply。

### 變更

- 刷新 `artifacts/goal/handoff-2026-05-04-usage-refresh.md`：
  - latest commits 更新到 `0da24db`。
  - 保存 protected dirty files：`.vscode/settings.json` 和 root `settings.json`。
  - 記錄最新 validation、evidence highlights、不要重做的 slices、仍不能宣稱完成的 blockers。
- 刷新 `artifacts/goal/continuation-2026-05-04-product-completion.md`：
  - latest completed product slice 改成 reviewed MAT / TXT sequence label apply。
  - immediate resume plan 改成補 shared state snapshot 的 import truth。
  - 建議下一手 TDD：`ApplicationStateSnapshot.interpretation` / automation / `query_state`
    應包含 `label_carrier_plan` 和 `format_capabilities`。

### 影響範圍

- Handoff / continuation artifacts。
- Records docs。
- 沒有 product code change。

### 驗證

- `git status --short` 顯示當下既有 dirty files 只有：
  - `.vscode/settings.json`
  - root `settings.json`
- `git diff --check` -> pass。
- `poetry run mkdocs build --strict` -> pass with existing MkDocs Material warning。

### 剩餘風險

- Goal 不能標 complete。
- 下一輪仍需實作 shared state snapshot propagation，並繼續補 embedded label import wizard、
  multi-file label mapping、raw-event-anchor-specific MAT / GDF alignment、Windows launcher
  human click-through、interactive desktop 3D、MCP Inspector / release config 和 thesis-ready
  local LLM evidence。

## 2026-05-04 ChatPanel multi-turn compact tool history

### 背景

ChatPanel 已有 one-turn local response 和 one-turn `query_state` tool-command evidence，但
multi-turn capture 暴露真產品問題：第一次 tool call 成功後，controller 把完整 ApplicationService
state/raw result 寫回 conversation history。第二輪 prompt 膨脹到約 `10.7k` input tokens，
Phi-4 mini local backend timeout，使用者只會看到 timeout error。

### 變更

- 新增 `scripts/dev/capture_chatpanel_local_workflow_walkthrough.py`：
  - 強制 HF / Transformers offline。
  - 開真 `MainWindow` / `ChatPanel`。
  - turn 1 要求 state query tool。
  - turn 2 在同一 conversation 中送 no-tool follow-up。
  - 保存 ready / turn screenshots、visible transcript、executed tools、UI idle state。
- `LLMController._format_tool_output()` 對 `ToolCommandResult` 改用 compact payload：
  - 保留 `ok`、tool / command name、message、error type、blocked reason。
  - 保留 compact capability。
  - 保留 compact `state_summary`。
  - 只保留 small diagnostics keys。
  - 不再把 full `state` / `raw_result` 餵回下一輪 LLM。
- 新增 controller regression，確保 compact tool history 不含 raw state/raw result。

### 影響範圍

- Local-model multi-turn ChatPanel behavior。
- Agent controller conversation history。
- UI workflow artifact scripts。
- Validation / current / planning / records docs。

### 驗證

- failing diagnosis:
  - first multi-turn attempt after `query_state` produced turn 2 timeout with about `10.7k` input tokens。
- passing walkthrough:
  - `timeout 520s env QT_QPA_PLATFORM=offscreen poetry run python scripts/dev/capture_chatpanel_local_workflow_walkthrough.py --output-dir artifacts/ui/chatpanel-local-workflow --timeout-seconds 480`
  - status `passed`
  - turn 1 executed `query_state`
  - turn 2 completed in the same conversation with about `2.46k` input tokens
  - visible transcript contains no raw tool/debug syntax
  - UI returned idle
- tests:
  - `poetry run pytest --capture=sys tests/unit/llm/agent/test_controller.py::TestPipelineGate::test_tool_output_history_uses_compact_state_summary tests/unit/llm/agent/test_controller.py::TestPipelineGate::test_allowed_tool_executes -q`
  - `2 passed`
  - `poetry run pytest --capture=sys tests/unit/scripts/test_capture_chatpanel_local_workflow_walkthrough.py -q`
  - `1 passed`
- focused static checks:
  - touched controller / workflow script files passed `ruff`
  - touched controller / workflow script files passed `basedpyright`

### 剩餘風險

- 這只證明 basic two-turn continuity，不是長時間 autonomous tool-command chain。
- ChatPanel 仍需要真 import / preprocess / epoch / train 操作 walkthrough，才能支撐產品完成宣稱。

## 2026-05-04 Windows launcher automated command walkthrough

### 背景

Launcher 先前已有 `.cmd` / PowerShell baseline 和 WSL startup smoke，但缺少可重跑 artifact
證明 Desktop `.cmd`、PowerShell launcher、`wsl.exe` bridge、launcher log 和 `run.py` startup
確實串在同一條 Windows launcher path。真人 click-through 仍需要使用者在 Windows 桌面上執行，
但 automated evidence 可以先縮小「是不是 stale shortcut / launcher 無法進 WSL」這類風險。

### 變更

- `scripts/launchers/xbrainlab_wsl_launcher.ps1` 新增
  `XBRAINLAB_LAUNCHER_SMOKE=startup`：
  - 透過原本 `Invoke-WslWithLiveLog` path 進 WSL。
  - `cd` active repo。
  - bounded 執行 `run.py --model local` startup smoke。
  - `timeout` 後把 GUI keep-running 視為 bounded smoke success。
- 新增 `scripts/dev/capture_windows_launcher_walkthrough.py`：
  - Windows `cmd.exe` 執行 Desktop `XBrainLab.cmd` smoke。
  - PowerShell 執行 `wsl` smoke，確認 stdout / stderr mirror。
  - PowerShell 執行 `startup` smoke，確認 launcher path 看到 `MainWindow initialized`。
  - 保存 JSON / Markdown artifact。
- 新增 `tests/unit/scripts/test_capture_windows_launcher_walkthrough.py`，覆蓋 log path parsing 和
  artifact claim boundary rendering。

### 影響範圍

- Windows launcher PowerShell script。
- Dev validation artifact script。
- Launcher artifacts。
- Validation / current / planning / records docs。

### 驗證

- walkthrough:
  - `timeout 180s poetry run python scripts/dev/capture_windows_launcher_walkthrough.py --output-dir artifacts/launcher --startup-timeout 150`
  - wrote `artifacts/launcher/windows-launcher-walkthrough.json`
  - wrote `artifacts/launcher/windows-launcher-walkthrough.md`
- artifact summary:
  - status `passed`
  - Desktop command points to active WSL repo
  - WSL stdout / stderr markers observed
  - startup smoke saw `MainWindow initialized`
  - launcher log exists under `/mnt/c/Users/Administrator/AppData/Local/XBrainLab/logs/`
- tests:
  - `poetry run pytest --capture=sys tests/unit/scripts/test_capture_windows_launcher_walkthrough.py -q`
  - `2 passed`
- focused static checks:
  - `poetry run ruff check scripts/dev/capture_windows_launcher_walkthrough.py tests/unit/scripts/test_capture_windows_launcher_walkthrough.py`
  - pass
  - `poetry run basedpyright scripts/dev/capture_windows_launcher_walkthrough.py tests/unit/scripts/test_capture_windows_launcher_walkthrough.py`
  - `0 errors, 0 warnings, 0 notes`

### 剩餘風險

- 這不是真人 Windows Desktop click-through。
- 尚未驗證真 WSLg 多螢幕 placement、packaged installer behavior 或 release shortcut
  registration。

## 2026-05-04 Data Interpretation reviewed MAT/TXT sequence label apply

### 背景

Timestamp CSV / TSV / BIDS events labels 已能在 `apply_interpretation` 期間自動套用，但 GDF
external MAT labels 的常見情境還有 trial-order sequence。若已經在 wizard 確認 MAT variable、
trial-order alignment 和 class map，仍只保存 recipe plan 會讓 supervised workflow 不完整。

### 變更

- `_apply_interpretation_label_carriers()` 新增 sequence auto-apply path。
- 條件刻意收窄：
  - 單一 loaded EEG file。
  - 單一 reviewed MAT / TXT label carrier。
  - `time_model == "trial_order"`。
  - `granularity == "trial"`。
  - `class_map` 已確認。
- 成功後呼叫既有 `dataset.apply_labels_legacy()`，不新增第二套 label mutation。
- recipe trace 透過 `_record_label_import_for_recipe()` 寫入 `label_import:legacy:<n>`。

### 驗證

- TDD red:
  - MAT sequence test first failed with `label_apply.status=skipped`。
- tests:
  - `poetry run pytest --capture=sys tests/unit/backend/application/test_application_service.py::test_apply_interpretation_applies_reviewed_mat_sequence_label_carrier tests/unit/backend/application/test_application_service.py::test_apply_interpretation_applies_reviewed_timestamp_label_carrier -q`
  - `2 passed`

### 剩餘風險

- This does not infer raw event anchors. GDF/MAT workflows that need a selected raw trigger still
  need explicit anchor-to-raw-event modeling.
- Multi-file label mapping and full embedded label import wizard remain open.

## 2026-05-04 Data Interpretation reviewed timestamp label apply

### 背景

前一個 slice 讓 import wizard 能保存 label carrier plan，但 `apply_interpretation` 還只是載入
EEG source 並保存 recipe；已確認的 external timestamp labels 尚未真正套進 loaded raw data。
這會讓使用者以為 label / anchor 已被套用，但下游 supervised workflow 仍可能只看到原始 event。

### 變更

- `load_label_file()` 新增可選參數：
  - `label_field`
  - `anchor`
- MAT loader：
  - 如果 wizard 選了 MAT variable，使用該 variable。
  - 若 variable 不存在，回傳明確 `ValueError`。
- CSV / TSV / BIDS events loader：
  - 使用 reviewed label column 和 anchor column。
  - 若 label + anchor 都存在，輸出 timestamp mode dicts：`onset`、`label`、`duration`。
- `ApplicationService._handle_apply_interpretation()` 在 apply raw data 後呼叫
  `_apply_interpretation_label_carriers()`。
- 自動套用 labels 只允許 narrow safe path：
  - 單一 loaded EEG file。
  - 單一 reviewed timestamp CSV / TSV / BIDS events carrier。
  - time model 是 `seconds` 或 `relative_time`。
  - carrier 有 selected label field 和 selected anchor。
- 成功套用後：
  - 呼叫既有 `dataset.apply_labels_batch()`。
  - 使用 `_record_label_import_for_recipe()` 更新 `AppliedInterpretation.label_imports`。
  - recipe trace 新增 `label_import:timestamp:<n>`。
  - command diagnostics 新增 `label_apply`。
- 如果 carrier 不符合 narrow path，例如 MAT sequence、多 carrier 或多 loaded file，會 skip 並留下
  reason，不自動猜。

### 影響範圍

- Label loader。
- ApplicationService apply interpretation path。
- Data Interpretation replay artifact。
- Backend application / label loader tests。
- Current / planning / validation / records docs。
- `.basedpyright/baseline.json` 因 targeted basedpyright refresh 減少一個既有 baseline error。

### 驗證

- TDD red:
  - selected MAT / TSV loader tests first failed because `load_label_file()` lacked `label_field`。
  - application test first failed because `apply_interpretation` lacked `label_apply` diagnostics。
- UI replay:
  - `timeout 180s env QT_QPA_PLATFORM=offscreen poetry run python scripts/dev/capture_data_interpretation_replay.py`
  - replay JSON shows:
    - `label_apply.status=applied`
    - timestamp label import record
    - `label_import:timestamp:1` recipe trace
- tests:
  - `poetry run pytest --capture=sys tests/unit/backend/load_data/test_label_loader.py tests/unit/backend/load_data/test_label_loader_coverage.py tests/unit/backend/application/test_application_service.py tests/integration/backend/test_application_service_workflow.py::test_data_interpretation_to_dataset_workflow_is_non_mocked -q`
  - `60 passed`
  - `scripts/dev/run_ui_pytest.sh tests/unit/ui/dialogs/dataset/test_data_interpretation_preview_dialog.py tests/unit/ui/test_ui_misc.py::TestDatasetActionHandler -q`
  - `51 passed`
- focused static checks:
  - touched production/backend files passed `ruff`
  - touched production/backend files passed `basedpyright`

### 剩餘風險

- MAT sequence auto-apply remains intentionally skipped until anchor-to-raw-event mapping is
  represented explicitly.
- Multi-file label carrier mapping is still not automatic.
- Full embedded post-load label import wizard, all-format manual compatibility matrix, human
  Windows click-through, and MCP Inspector GUI validation remain open.

## 2026-05-04 Data Interpretation format capability boundaries

### 背景

Data Interpretation target 要求 GDF external labels、BIDS events、BrainVision、EEGLAB、EDF
annotations、CSV / TSV / MAT labels、XDF / LSL、自建 fallback 都有清楚能力邊界。先前 wizard
只顯示泛泛 warnings，使用者無法分辨「可載入但要確認」、「sidecar context」、「目前 blocked」
這幾種狀態。

### 變更

- `ScanResult` 新增 `format_capabilities`。
- `InterpretationCandidate` / `InterpretationPreview` / `AppliedInterpretation` / `ImportRecipe`
  也保存 `format_capabilities`，讓 UI / recipe / automation 讀同一份 boundary。
- scan 會建立 format-aware capability rows：
  - GDF: needs review，提醒 trial anchor / class map / external label alignment。
  - EDF / BDF: needs review，提醒 annotation role、time unit、class map。
  - EEGLAB `.set`: needs review，提醒 events / urevents / boundary marker。
  - BrainVision `.vhdr`: needs review，提醒 stimulus / response / sync / segment markers。
  - BrainVision `.vmrk`: context sidecar，提示要透過 `.vhdr` source review。
  - MNE FIF: supported，但仍需 review metadata / events。
  - MAT labels: needs review，提醒 MAT variable / anchor / class map。
  - CSV / TSV labels and BIDS `events.tsv`: needs review，提醒 label column / anchor / time model。
  - TXT labels: needs review，提醒 trial-order / anchor alignment。
  - XDF / LSL: blocked，提示 stream selection 尚未在 wizard 中可用。
- 如果 folder 同時有 supported EEG 和 blocked XDF / LSL，scan 仍可走 supported EEG，但會加 warning。
- `DataInterpretationPreviewDialog._details_text()` 新增 `Format capabilities` section，並把
  internal `needs_review` 轉成 visible `needs review`。
- `capture_data_interpretation_replay.py` 會把 `review_notes` 寫進 JSON artifact。

### 影響範圍

- Data Interpretation backend lifecycle objects。
- Data Interpretation preview dialog。
- UI replay artifact。
- Backend application / UI dialog tests。
- Current / planning / validation / records docs。

### 驗證

- TDD red:
  - backend test first failed on missing `format_capabilities`。
  - dialog test first failed on missing `Format capabilities` review notes。
- UI replay:
  - `timeout 180s env QT_QPA_PLATFORM=offscreen poetry run python scripts/dev/capture_data_interpretation_replay.py`
  - replay JSON `review_notes` includes BIDS events `needs review` and MNE FIF `supported`。
- tests:
  - `poetry run pytest --capture=sys tests/unit/backend/application/test_application_service.py tests/integration/backend/test_application_service_workflow.py::test_data_interpretation_to_dataset_workflow_is_non_mocked -q`
  - `34 passed`
  - `scripts/dev/run_ui_pytest.sh tests/unit/ui/dialogs/dataset/test_data_interpretation_preview_dialog.py tests/unit/ui/test_ui_misc.py::TestDatasetActionHandler -q`
  - `51 passed`
- focused static checks:
  - touched production/dialog/backend files passed `ruff`
  - touched production/dialog/backend files passed `basedpyright`

### 剩餘風險

- Capability boundary display is not an XDF stream parser implementation.
- Full all-format manual compatibility matrix, embedded post-load label import wizard, human
  Windows click-through, and MCP Inspector GUI validation remain open.

## 2026-05-04 Data Interpretation label carrier review

### 背景

Data Interpretation wizard 已有 metadata / class-map review，但 label carrier 仍停在「看得到
carrier」和舊 post-load label import compatibility path。對 GDF external labels、BIDS
events、CSV / TSV labels 或 MAT labels 來說，使用者需要在 import wizard 裡審查 label field /
MAT variable、anchor、time model 和 granularity，否則 recipe 仍無法完整說明資料如何被解讀。

### 變更

- `InterpretationCandidate` 新增 `label_carrier_plan`。
- `InterpretationPreview` 新增 `label_carrier_preview`。
- `AppliedInterpretation` / `ImportRecipe` 新增 `label_carrier_plan`，recipe JSON 會保存 reviewed
  label carrier selections。
- `build_interpretation_candidate()` 會為 label carriers 建立 format-aware plan：
  - MAT: 使用 `scipy.io.loadmat()` 列出 public variables，供 MAT variable / anchor review。
  - CSV / TSV 和 BIDS `events.tsv`: 讀 header，將 `trial_type` / `value` / label-like columns
    與 `onset` / `sample` / timestamp-like anchors 分開。
  - TXT: 顯示 trial-order label sequence boundary。
- `PreviewInterpretationCommand(choices=...)` 接受 `label_carrier_choices`：
  - `label_field`
  - `anchor`
  - `time_model`
  - `granularity`
- recipe trace 新增 `choices:label_carriers`。
- `DataInterpretationPreviewDialog` 新增 label carrier review table：
  - carrier
  - format
  - label field / MAT variable
  - anchor
  - time
  - granularity
- `capture_data_interpretation_replay.py` 改用 folder source + synthetic `events.tsv` carrier，並在
  screenshot 前填入 label carrier review choices。

### 影響範圍

- Data Interpretation backend lifecycle objects。
- Data Interpretation preview dialog。
- UI replay artifact。
- Backend application tests。
- UI dialog / Dataset action tests。
- Current / planning / validation / records docs。

### 驗證

- TDD red:
  - backend test first failed on missing `label_carrier_preview`。
  - dialog test first failed on missing `label_carrier_tree`。
- UI replay:
  - `timeout 180s env QT_QPA_PLATFORM=offscreen poetry run python scripts/dev/capture_data_interpretation_replay.py`
  - refreshed `artifacts/ui/data-interpretation-preview.png`
  - refreshed `artifacts/ui/data-interpretation-applied.png`
  - refreshed `artifacts/ui/data-interpretation-replay.json`
- replay JSON:
  - visible `label_carrier_rows` contains `trial_type` / `onset` / `seconds` / `trial`
  - applied interpretation saves the reviewed `label_carrier_plan`
  - recipe trace contains `choices:label_carriers`
- tests:
  - `poetry run pytest --capture=sys tests/unit/backend/application/test_application_service.py tests/integration/backend/test_application_service_workflow.py::test_data_interpretation_to_dataset_workflow_is_non_mocked -q`
  - `33 passed`
  - `scripts/dev/run_ui_pytest.sh tests/unit/ui/dialogs/dataset/test_data_interpretation_preview_dialog.py tests/unit/ui/test_ui_misc.py::TestDatasetActionHandler -q`
  - `50 passed`
- focused static checks:
  - touched production/dialog/backend files passed `ruff`
  - touched production/dialog/backend files passed `basedpyright`

### 剩餘風險

- This is first-pass label carrier review, not a complete embedded post-load label import wizard.
- Full all-format manual compatibility matrix, human Windows launcher click-through, and MCP
  Inspector GUI validation remain open.

## 2026-05-04 Data Interpretation metadata / class-map editor

### 背景

Data Interpretation dialog 已有 import wizard review surface，但使用者只能看 metadata /
class map，不能在同一流程修正不明確欄位。這讓 recipe 仍偏系統推論紀錄，沒有真正承接
metadata override / class map confirmation。

### 變更

- `build_interpretation_candidate()` 支援 `choices`：
  - `metadata_overrides`
  - `class_map`
  - `event_roles`
- metadata override 會產生 `MetadataFieldResolution(source="user_override", decision="safe")`，
  並寫入 `metadata_override:<field>` trace。
- `AppliedInterpretation` 和 `ImportRecipe` 新增 `event_roles` / `class_map`，recipe JSON 會保存
  review 後的 semantic choices。
- `DataInterpretationPreviewDialog`：
  - metadata tree cells 可編輯 subject / session / task / run。
  - class-map rows 可編輯 meaning。
  - `get_result()` 回傳 `choices`，供 apply 前重新建立 candidate。
- Dataset action 在 apply 前偵測 dialog `choices`，並重新執行
  `PreviewInterpretationCommand -> ValidateInterpretationCommand -> ApplyInterpretationCommand`。
- `capture_data_interpretation_replay.py` 會填入 metadata review edits，並在 artifact 記錄
  `review_choices`、reviewed preview / validation 和 apply result。

### 影響範圍

- Data Interpretation backend lifecycle objects。
- Dataset panel import action。
- Data Interpretation preview dialog。
- UI replay artifacts。
- Backend application / UI dialog / Dataset action tests。
- Current / planning / validation / records docs。

### 驗證

- UI replay:
  - `env QT_QPA_PLATFORM=offscreen poetry run python scripts/dev/capture_data_interpretation_replay.py`
  - refreshed `artifacts/ui/data-interpretation-preview.png`
  - refreshed `artifacts/ui/data-interpretation-applied.png`
  - refreshed `artifacts/ui/data-interpretation-replay.json`
- replay JSON:
  - `review_choices.metadata_overrides` contains `S01`、`session-01`、`motor-imagery`
  - reviewed preview contains `source=user_override`
  - recipe trace contains `metadata_override:<field>` and `choices:metadata_overrides`
- tests:
  - `scripts/dev/run_ui_pytest.sh tests/unit/ui/dialogs/dataset/test_data_interpretation_preview_dialog.py tests/unit/ui/test_ui_misc.py::TestDatasetActionHandler -q`
  - `49 passed`
  - `poetry run pytest --capture=sys tests/unit/backend/application -q`
  - `37 passed`
  - `poetry run pytest --capture=sys tests/integration/backend/test_application_service_workflow.py::test_data_interpretation_to_dataset_workflow_is_non_mocked -q`
  - `1 passed`
- focused static checks:
  - touched production/dialog/backend files passed `ruff`
  - touched production/dialog/backend files passed `basedpyright`

### 剩餘風險

- First-pass editor covers metadata cells and class-map row labels, but not format-specific label
  column / MAT variable / anchor event editors.
- Label import remains a compatibility UI after data is loaded; it is not yet embedded inside the
  import wizard.
- 尚未完成真人 Windows launcher click-through 或 MCP Inspector GUI validation。

## 2026-05-04 ChatPanel local tool-command walkthrough

### 背景

ChatPanel 已有真 local-model 一般回覆 walkthrough，但 tool-command prompt 暴露出產品缺口：
local model 會正確呼叫 `query_state`，但 `AgentManager` 把所有 `Tool` sender 回覆都視為內部
diagnostic，導致使用者看不到產品級 summary。stdout log 可以看到 tool execution，但 artifact
沒有保存 executed tool summary，交接可信度不足。

### 變更

- `AgentManager._looks_like_internal_tool_output()` 改為只隱藏 raw/internal `Tool` output：
  - `debug` sender 仍全部隱藏。
  - `Tool` sender 只有在文字以 raw tool markers、JSON、`ApplicationService` 或 `BackendFacade`
    開頭時才視為內部輸出。
  - 已整理成使用者語言的 tool summary 會進入 visible transcript。
- `tests/integration/ui/test_product_walkthrough.py` 補 regression：
  - raw `Tool Output:` 仍不可見。
  - safe tool summary `Workflow state ready...` 必須可見。
- `scripts/dev/capture_chatpanel_local_walkthrough.py` 補 `executed_tools` artifact 欄位，從
  controller metrics completed turns 收集 tool name / success / duration / error。
- `tests/unit/scripts/test_capture_chatpanel_local_walkthrough.py` 補 artifact rendering 和 metrics
  collection coverage。

### 影響範圍

- ChatPanel / AgentManager visible transcript filtering。
- Local ChatPanel walkthrough artifact。
- UI product walkthrough regression。
- Current / planning / validation / records docs。

### 驗證

- true local UI tool-command walkthrough：
  - `timeout 420s env QT_QPA_PLATFORM=offscreen poetry run python scripts/dev/capture_chatpanel_local_walkthrough.py --output-dir artifacts/ui/chatpanel-local-tool --timeout-seconds 360 --prompt "Check what is ready in the current XBrainLab workflow. Use the state query tool if needed, then answer in one short sentence."`
  - artifact status `passed`
  - executed tool `query_state` `ok`
  - visible assistant response `Application state snapshot ready.`
  - UI idle：send button enabled、input enabled、chat / controller processing false
- tests:
  - `scripts/dev/run_ui_pytest.sh tests/integration/ui/test_product_walkthrough.py::test_assistant_product_click_through_layout -q`
  - `1 passed`
  - `scripts/dev/run_ui_pytest.sh tests/integration/ui/test_product_walkthrough.py -q`
  - `3 passed`
  - `poetry run pytest --capture=sys tests/unit/scripts/test_capture_chatpanel_local_walkthrough.py -q`
  - `3 passed`
- static gates:
  - focused `ruff` checks passed
  - focused `basedpyright` checks passed with `0 errors, 0 warnings, 0 notes`

### 剩餘風險

- 這是單步 `query_state` tool-command walkthrough，不是 multi-turn workflow。
- 尚未驗證 Windows Desktop launcher click-through、長時間 assistant 操作、完整 import wizard
  metadata override / label-class map editor、MCP Inspector GUI 或 release config。

## 2026-05-04 Data Interpretation wizard review hardening

### 背景

Data Interpretation 已有 backend command baseline、Dataset panel main entry、recipe save option 和
UI-observable replay，但 preview dialog 仍偏 baseline preview：使用者看得到 metadata table，卻
看不到完整 import flow、source readiness、label/event boundary 和 recipe trace 的 review
structure。

### 變更

- `DataInterpretationPreviewDialog` 改名為 `Interpret Data Source`。
- 新增 visible flow：`Scan -> Preview -> Validate -> Confirm -> Apply -> Save recipe`。
- 新增 source/readiness section：
  - source path。
  - source kind。
  - EEG file count。
  - label/event carrier count。
  - BIDS status。
- 新增 labels/events/recipe trace tree：
  - label carriers。
  - event roles。
  - class map。
  - no-carrier boundary message。
- Review notes 現在整理 warnings、confirmations、blocked reasons、downstream impact 和 recipe trace，
  避免同一 confirmation 重複刷屏。
- needs-confirmation 時 OK button 顯示 `Confirm and Apply`；blocked decision 會 disabled apply 和
  save recipe。
- `scripts/dev/capture_data_interpretation_replay.py` 在 deterministic resize 前清掉 maximized state，
  讓 offscreen replay 可以穩定刷新 screenshot artifact。

### 影響範圍

- Data Interpretation preview / apply dialog。
- Dataset action unit coverage。
- UI-observable Data Interpretation replay artifact。
- Current / planning / validation / records docs。

### 驗證

- replay：
  - `env QT_QPA_PLATFORM=offscreen poetry run python scripts/dev/capture_data_interpretation_replay.py`
  - exit `0`
  - refreshed `artifacts/ui/data-interpretation-preview.png`
  - refreshed `artifacts/ui/data-interpretation-applied.png`
  - refreshed `artifacts/ui/data-interpretation-replay.json`
- replay JSON：
  - dialog title `Interpret Data Source`
  - decision `needs_confirmation`
  - apply button enabled `True`
  - save recipe checked `True`
- tests:
  - `scripts/dev/run_ui_pytest.sh tests/unit/ui/dialogs/dataset/test_data_interpretation_preview_dialog.py tests/unit/ui/test_ui_misc.py::TestDatasetActionHandler -q`
  - `47 passed`
- static gates:
  - `poetry run ruff check XBrainLab/ui/dialogs/dataset/data_interpretation_preview_dialog.py scripts/dev/capture_data_interpretation_replay.py tests/unit/ui/dialogs/dataset/test_data_interpretation_preview_dialog.py tests/unit/ui/test_ui_misc.py`
  - pass
  - `poetry run basedpyright XBrainLab/ui/dialogs/dataset/data_interpretation_preview_dialog.py scripts/dev/capture_data_interpretation_replay.py tests/unit/ui/dialogs/dataset/test_data_interpretation_preview_dialog.py`
  - `0 errors, 0 warnings, 0 notes`

### 剩餘風險

- 這是 wizard review hardening，不是完整 import wizard editor。
- Metadata override UI、label-class map editor、format-specific compatibility matrix、file picker
  click-through 和 label import 內嵌 wizard flow 仍未完成。

## 2026-05-04 ChatPanel true local-model walkthrough

### 背景

之前已有 local runtime preflight / prompt smoke、真 local tool-call eval 和 UI screenshot baseline，
但仍沒有證據顯示「使用者在 ChatPanel 裡送出訊息後，真 local model 會產生可見回覆」。這個缺口
不能用 deterministic eval 或 mocked ChatPanel tests 取代。

### 變更

- 新增 `scripts/dev/capture_chatpanel_local_walkthrough.py`：
  - 強制 `HF_HUB_OFFLINE=1` / `TRANSFORMERS_OFFLINE=1`，避免 walkthrough 觸發下載或 remote path。
  - 啟動真 `MainWindow` / `ChatPanel`，開啟 assistant dock。
  - 從 UI composer 填入 prompt 並按 Send。
  - 經 real `AgentManager -> LLMController -> AgentWorker -> LLMEngine -> LocalBackend` 等待回覆。
  - 保存 ready / response screenshots、visible transcript、button state、runtime summary。
- 新增 `tests/unit/scripts/test_capture_chatpanel_local_walkthrough.py`，覆蓋 Markdown rendering 和
  raw tool/debug syntax detector。

### 影響範圍

- Dev validation scripts。
- UI observable artifacts。
- Validation / current / planning / records docs。

### 驗證

- runtime preflight：
  - `poetry run python scripts/dev/inspect_local_assistant_runtime.py --format markdown`
  - classification `gpu-ready`
  - model `microsoft/Phi-4-mini-instruct`
  - cache `15.34 GB`
- true UI walkthrough：
  - `timeout 420s xvfb-run -a poetry run python scripts/dev/capture_chatpanel_local_walkthrough.py --output-dir artifacts/ui --timeout-seconds 360`
  - wrote `artifacts/ui/chatpanel-local-ready.png`
  - wrote `artifacts/ui/chatpanel-local-response.png`
  - wrote `artifacts/ui/chatpanel-local-walkthrough.json`
  - wrote `artifacts/ui/chatpanel-local-walkthrough.md`
- artifact summary：
  - status `passed`
  - `HF_HUB_OFFLINE=1`
  - `TRANSFORMERS_OFFLINE=1`
  - visible assistant response：
    `EEG preprocessing involves cleaning and organizing the raw EEG data to prepare it for further analysis.`
  - send button `Send`
  - input enabled `True`
  - chat / controller processing `False`
- targeted gate：
  - `poetry run pytest --capture=sys tests/unit/scripts/test_capture_chatpanel_local_walkthrough.py -q`
  - `2 passed`
  - `poetry run ruff check scripts/dev/capture_chatpanel_local_walkthrough.py tests/unit/scripts/test_capture_chatpanel_local_walkthrough.py`
  - pass
  - `poetry run basedpyright scripts/dev/capture_chatpanel_local_walkthrough.py tests/unit/scripts/test_capture_chatpanel_local_walkthrough.py`
  - `0 errors, 0 warnings, 0 notes`

### 剩餘風險

- 這是一輪 true local-model ChatPanel response walkthrough，不是 multi-turn tool-command workflow。
- 尚未驗證 Windows Desktop launcher click-through、長時間 assistant 操作、UI-driven tool execution
  transcript 或完整 import wizard UI。

## 2026-05-04 MCP stdio external-client walkthrough

### 背景

前一個 slice 已把 MCP 從 schema-only 推到可啟動的 stdio server，但仍沒有 external-client
walkthrough artifact。產品完成要求 MCP client 不需要安裝 XBrainLab EEG / PyQt / PyTorch stack，
且 MCP calls 不能繞過 ApplicationService。

### 變更

- 新增 `scripts/dev/capture_mcp_stdio_walkthrough.py`：
  - client 端只使用 Python standard library。
  - 透過 subprocess 啟動 prepared XBrainLab runtime 中的 `scripts/dev/run_mcp_server.py`。
  - 用 MCP stdio JSON-RPC 跑 `initialize`、`tools/list`、`scan_source`、
    `preview_interpretation`、`validate_interpretation`。
  - 保存 client-observable transcript summary 到 `artifacts/mcp/stdio-walkthrough.json` 和
    `artifacts/mcp/stdio-walkthrough.md`。
- 新增 `tests/integration/mcp/test_stdio_walkthrough_artifact.py`，讓 walkthrough artifact 可在 CI /
  local gate 中重生並檢查 dependency boundary、tool listing、taxonomy 和 command statuses。

### 影響範圍

- MCP validation / evidence scripts。
- Integration MCP test suite。
- Current / planning / validation / records docs。

### 驗證

- `poetry run python scripts/dev/capture_mcp_stdio_walkthrough.py --output-dir artifacts/mcp`
  - wrote `artifacts/mcp/stdio-walkthrough.json`
  - wrote `artifacts/mcp/stdio-walkthrough.md`
- artifact summary：
  - initialized `True`
  - tool count `28`
  - `scan_source` taxonomy `data_interpretation`
  - `scan_source` / `preview_interpretation` / `validate_interpretation` status `ok`
  - validation visible text `Interpretation validation: needs_confirmation.`
- `poetry run pytest --capture=sys tests/unit/mcp tests/integration/mcp -q`
  - `7 passed`
- `poetry run ruff check scripts/dev/capture_mcp_stdio_walkthrough.py tests/integration/mcp/test_stdio_walkthrough_artifact.py`
  - pass
- `poetry run basedpyright scripts/dev/capture_mcp_stdio_walkthrough.py tests/integration/mcp/test_stdio_walkthrough_artifact.py`
  - `0 errors, 0 warnings, 0 notes`

### 剩餘風險

- 這是 stdio external-client walkthrough，不是 MCP Inspector GUI click-through。
- 尚未補 Windows release registration / config、HTTP transport、long-running training through MCP
  或 external agent recovery UX。
- 產品 completion 仍受 true ChatPanel multi-turn / tool-command walkthrough、Windows launcher
  click-through 和成熟 import wizard UI 驗收影響。

## 2026-05-04 Local tool-call thesis-candidate 100-case rerun

### 背景

前一輪 local tool-call eval 已從不可用區間提升到 `53 / 54`，但仍不足使用者要求的
`100` thesis candidate cases，也留下 bandpass-only vs standard preprocess 語意 failure。

### 變更

- `scripts/agent/evals/run_tool_call_eval.py` 的 case suite 擴到 `100` cases，覆蓋：
  - Data Interpretation file / folder / BIDS / recipe。
  - metadata choice：subject / session / task / run / event role。
  - missing / relative path、confirmation、blocked / recovery、多輪 workflow。
  - bandpass-only vs standard preprocess、epoch default window、dataset split、query-state、
    visualization / saliency readiness。
- local tool-call guardrails 補齊：
  - `CommandParser` 解析 partial tool-name JSON，以及 command-only JSON with
    `requires_confirmation` / `decision_boundary` metadata。
  - `PlaceholderArgumentValidator` 拒絕 blank / relative source and recipe paths。
  - `tool_call_normalizer` 處理 metadata choice cleanup、bandpass-only demotion、dataset
    split vs training mode、epoch default window、confirmed apply、legacy scan / recipe
    substitutes。
  - local eval prompt 明確寫入 direct tool map、epoch default window 和 visualization /
    saliency no-substitute rule。
  - `LLMController` requested-intent boundary 擋 saliency / visualization 被模型改成 setup /
    UI-route tool。

### 影響範圍

- Agent parser / verifier / controller guardrail。
- Deterministic and local tool-call eval runner / artifacts。
- Tool-call thesis-candidate evidence docs。

### 驗證

- deterministic eval：
  - `poetry run python scripts/agent/evals/run_tool_call_eval.py --repeat-count 2 --output-dir artifacts/agent_evals/deterministic`
  - `100 / 100` pass。
- primary local eval：
  - `timeout 3600s poetry run python scripts/agent/evals/run_local_tool_call_eval.py --model-role primary --repeat-count 3 --max-new-tokens 128 --output-dir artifacts/agent_evals/local_primary`
  - `artifacts/agent_evals/local_primary/local_microsoft_phi_4_mini_instruct.md`
  - `100 / 100` pass (`100.00%`)。
- fallback local eval：
  - `timeout 3600s poetry run python scripts/agent/evals/run_local_tool_call_eval.py --model-role fallback --repeat-count 3 --max-new-tokens 128 --output-dir artifacts/agent_evals/local_fallback`
  - `artifacts/agent_evals/local_fallback/local_microsoft_phi_3.5_mini_instruct.md`
  - `100 / 100` pass (`100.00%`)。
- runtime / resource:
  - primary / fallback 都是 `gpu-ready`。
  - cache `15.34 GB`，no download。
- targeted tests：
  - `poetry run pytest --capture=sys tests/unit/llm/test_parser.py tests/unit/llm/agent/test_tool_call_normalizer.py tests/unit/llm/agent/test_verification_layer.py tests/unit/llm/agent/test_intent.py tests/unit/scripts/test_run_local_tool_call_eval.py tests/unit/llm/agent/test_controller.py -q`
  - `166 passed`
  - targeted `poetry run ruff check ...` -> pass
- regression / docs / architecture gates：
  - `poetry run pytest --capture=sys tests/unit/llm/agent tests/unit/llm/tools tests/unit/scripts/test_run_local_tool_call_eval.py tests/unit/llm/test_parser.py tests/unit/llm/test_pipeline_state.py tests/unit/llm/tools/test_application_surface.py -q`
  - `487 passed`
  - `poetry run ruff check .` -> pass
  - `poetry run basedpyright` -> `0 errors, 0 warnings, 0 notes`
  - `poetry run mkdocs build --strict` -> pass
  - `git diff --check` -> pass
  - `poetry run python tests/architecture_compliance.py` -> `Architecture compliant!`

### 剩餘風險

- 這支撐 thesis-candidate tool-call benchmark evidence，但不等於整個 thesis package closure。
- true ChatPanel multi-turn / tool-command walkthrough、Windows launcher click-through、
  MCP Inspector / release config、完整 import wizard UI 驗收仍未完成。

## 2026-05-04 Local assistant tool-call normalization full rerun

### 背景

Guardrail smoke 清掉了 placeholder / blocked substitute 的小樣本問題，但正式 full eval 仍需
把真 local model raw output 對齊產品 verifier / ApplicationService 語意。

### 變更

- `CommandParser` 支援 command-only JSON 和 bare tool name 輸出。
- 新增 `XBrainLab.llm.agent.tool_call_normalizer`：
  - aliases：`create_epoch` -> `epoch_data`、`train` -> `start_training`、
    `get_dataset_info` -> typed `query_state`。
  - latest-turn substitute：scan / preview / validate / apply request 不再被前一輪 tool call
    重複覆蓋。
  - argument normalization：BIDS source hint、subject override、epoch event id stringification、
    dataset split defaults、recipe save default。
- 新增 `query_state` mock / real agent tool，並映射到 `ApplicationService`
  `QueryStateCommand`。
- placeholder validator 擋下 prose path / `path/to/your/...`。
- local eval 使用 backend result interpretation，避免把 successful load / confirmation boundary /
  recoverable failure 當成 raw tool 成功。

### 驗證

- full local eval：
  - `artifacts/agent_evals/local_primary/local_microsoft_phi_4_mini_instruct.md`
    -> `53 / 54` pass (`98.15%`)。
  - `artifacts/agent_evals/local_fallback/local_microsoft_phi_3.5_mini_instruct.md`
    -> `53 / 54` pass (`98.15%`)。
  - primary / fallback 都是 `gpu-ready`，cache `15.34 GB`，no download。
- `poetry run pytest --capture=sys tests/unit/llm/test_parser.py tests/unit/llm/agent/test_tool_call_normalizer.py tests/unit/llm/agent/test_verification_layer.py tests/unit/scripts/test_run_local_tool_call_eval.py tests/unit/llm/tools/test_application_surface.py tests/unit/llm/agent/test_controller.py tests/unit/llm/agent/test_intent.py -q`
  - `156 passed`
- targeted `poetry run ruff check ...`
  - pass
- targeted `poetry run basedpyright ...`
  - `0 errors, 0 warnings, 0 notes`
- `poetry run pytest --capture=sys tests/unit/llm/agent tests/unit/llm/tools tests/unit/scripts/test_run_local_tool_call_eval.py tests/unit/llm/test_parser.py tests/unit/llm/test_pipeline_state.py tests/unit/llm/tools/test_application_surface.py -q`
  - `464 passed`
- `poetry run ruff check .`
  - pass
- `poetry run basedpyright`
  - `0 errors, 0 warnings, 0 notes`
- `poetry run mkdocs build --strict`
  - pass
- `git diff --check`
  - pass

### 剩餘風險

- 仍不是 thesis-ready：只有 `54` cases，不是 `100` thesis candidate cases。
- 剩餘 failing case 是 bandpass-vs-standard preprocess 語意。
- 這仍不是 ChatPanel 長時間 walkthrough、Windows launcher click-through 或完整 UI product
  validation。

## 2026-05-04 Local assistant tool-call guardrails

### 背景

真 local LLM tool-call runner 已證明 primary / fallback 可以穩定產生 raw output，但 full run
只有 `18 / 54` 和 `20 / 54` pass。失敗主要集中在 placeholder path、blocked command
substitution、工具格式變體、standard preprocess / dataset split argument drift，以及 eval
artifact 把 raw tool JSON 當成 visible response。

### 變更

- `CommandParser` 支援 top-level tool-call array 和 OpenAI-style function tool call。
- `VerificationLayer` 新增 `PlaceholderArgumentValidator`，拒絕模型自造的 placeholder
  source / file / recipe path。
- 新增 `XBrainLab.llm.agent.intent`，集中 infer user intent、intent -> `CommandName` 和
  path label 對應。
- `LLMController` 新增 requested-intent boundary：最新使用者要求的 workflow command 若被
  `ApplicationService` capability policy 擋下，agent 不能改叫其他 tool 來 substitute。
- `LLMController` 會把 inferred latest intent 加進 prompt context，讓 local model 在多輪
  workflow 中知道最新要求的 direct command。
- local eval runner 套用同一 guardrail：
  - blocked requested intent 轉成 blocked prediction。
  - placeholder path 轉成 missing input。
  - `generate_dataset.val_ratio` 依 backend default 補 `0.2`。
  - successful tool-call 的 `visible_response` 不保存 raw JSON tool syntax。
- prompt / schema 補強：
  - standard preprocess 應使用 `apply_standard_preprocess`。
  - `generate_dataset.split_strategy` 只能是 `trial` / `session` / `subject`。
  - `individual` / `group` 是 `training_mode`。
  - current state 比 chat history 中較早的 scan / load request 更權威。

### 影響範圍

- Agent parser / verifier / controller。
- Local tool-call eval runner / deterministic eval intent helper。
- Tool definitions 的 prompt-facing descriptions。
- Local guardrail smoke artifacts。

### 驗證

- runtime preflight：
  - primary / fallback `gpu-ready`。
  - cache usage `15.34 GB`，低於 `20 GB` 上限。
  - no download。
- exploratory local smoke：
  - `artifacts/agent_evals/local_primary_guardrail_smoke/local_microsoft_phi_4_mini_instruct.md`
    -> `6 / 6` pass。
  - `artifacts/agent_evals/local_fallback_guardrail_smoke/local_microsoft_phi_3.5_mini_instruct.md`
    -> `6 / 6` pass。
- `poetry run pytest --capture=sys tests/unit/llm/agent/test_intent.py tests/unit/llm/agent/test_controller.py tests/unit/scripts/test_run_local_tool_call_eval.py tests/unit/llm/agent/test_verification_layer.py tests/unit/llm/test_parser.py tests/unit/llm/agent/test_assembler_stage.py -q`
  - `125 passed`
- `poetry run pytest --capture=sys tests/unit/llm/agent/test_assembler_stage.py tests/unit/scripts/test_run_local_tool_call_eval.py tests/unit/llm/tools/test_definitions.py -q`
  - `150 passed`
- `poetry run pytest --capture=sys tests/unit/llm/agent tests/unit/llm/tools tests/unit/scripts/test_run_local_tool_call_eval.py tests/unit/llm/test_parser.py tests/unit/llm/test_pipeline_state.py -q`
  - `426 passed`
- `poetry run python scripts/agent/evals/run_tool_call_eval.py --output-dir /tmp/xbrainlab_eval_guardrails`
  - temp deterministic report written。
- `poetry run ruff check .`
  - pass
- `poetry run basedpyright`
  - `0 errors, 0 warnings, 0 notes`
- `poetry run mkdocs build --strict`
  - pass
- `poetry run python tests/architecture_compliance.py`
  - `Architecture compliant`
- `git diff --check`
  - pass

### 剩餘風險

- 此段為 guardrail smoke 當時風險；正式 `54` cases x `3` primary / fallback full rerun 已由
  normalization slice 更新，但仍不能宣稱 thesis-ready。
- Smoke subset 已清掉 `multi-turn-scan-preview` 重複 scan；後續 full rerun 剩餘
  bandpass-vs-standard preprocess 語意 failure。
- 這不是 ChatPanel 長時間 walkthrough，也不是 Windows launcher click-through evidence。

## 2026-05-04 label import recipe trace integration

### 背景

Data Interpretation import flow 已可保存 recipe，但 Dataset panel 的 `Add Labels to Loaded Data`
仍只像舊 compatibility action：labels 可以套到 raw data，卻不會進入 Data Interpretation recipe
trace。這會讓後續 recipe reload、agent state snapshot、MCP / scorer evidence 看不到外部 label
語意是如何加入的。

### 變更

- `AppliedInterpretation` / `ImportRecipe` 新增 `label_imports`。
- `ApplicationService._handle_import_labels()` 成功後會在目前 applied interpretation 上記錄：
  - mode。
  - label carriers。
  - target files。
  - file mapping。
  - selected event names。
  - class map。
  - success count。
- `ApplicationStateSnapshot.interpretation` 新增 `label_carriers`、`label_import_count`、
  `label_imports`，讓 UI / agent / MCP / scorer 能讀到同一份 recipe trace。
- 若已有 session recipe，service 也同步更新 session recipe trace；若使用者後續保存 recipe，
  JSON 會包含 label import trace。
- Dataset panel 在 label import 成功且 `recipe_updated` 時，用人話提示使用者可保存更新後 recipe，
  並重用既有 `SaveInterpretationRecipeCommand`。

### 影響範圍

- Backend Data Interpretation lifecycle objects。
- ApplicationService label import command handler。
- Application state snapshot contract。
- Dataset panel label import success UX。
- Backend / UI / agent application-surface tests。

### 驗證

- `poetry run pytest --capture=sys tests/unit/backend/application/test_application_service.py::test_import_labels_updates_applied_interpretation_recipe_trace tests/unit/ui/test_ui_misc.py::TestDatasetActionHandler::test_import_label_offers_to_save_updated_recipe -q` -> `2 passed`
- `poetry run pytest --capture=sys tests/unit/backend/application/test_application_service.py tests/unit/ui/test_ui_misc.py::TestDatasetActionHandler -q` -> `74 passed`
- `poetry run pytest --capture=sys tests/unit/backend/application -q` -> `36 passed`
- `poetry run pytest --capture=sys tests/integration/backend/test_application_service_workflow.py -q` -> `3 passed`
- `poetry run pytest --capture=sys tests/unit/llm/tools/test_application_surface.py tests/unit/llm/agent/test_controller.py -q` -> `66 passed`
- targeted `ruff` / `basedpyright` clean。

### 剩餘風險

- 這仍是 `Add Labels to Loaded Data` compatibility UI 的 recipe trace integration，不是成熟的
  import wizard label/recipe editor。
- 尚未新增 UI screenshot replay 覆蓋 label import save prompt。
- 尚未驗證真使用者 click-through 或 agent 透過 local LLM 正確操作這段 label/recipe flow。

## 2026-05-04 stdio MCP server baseline

### 背景

Goal 1 已有 `mcp_tool_specs()` 和 headless JSON adapter，但那只是 MCP-shaped schema，
不是可由 external agent client 啟動並呼叫的 server。產品完成路線要求 MCP 作為 external
agent adapter，且 MCP calls 不能變成第三套 workflow truth 或繞過 ApplicationService。

### 變更

- 新增 `XBrainLab.mcp.server`：
  - 實作 stdio JSON-RPC loop。
  - 支援 MCP `initialize` lifecycle，宣告 `tools` capability。
  - 支援 `tools/list`，直接暴露 `backend.application.automation.mcp_tool_specs()`。
  - 支援 `tools/call`，將 tool name / arguments 轉成 `execute_automation_payload()`，並在同一個
    `ApplicationService` session 中執行。
  - unknown tool 回 protocol error；tool schema / business failure 回 MCP tool result
    `isError: true`，並保留 structured execution payload。
- 新增 `scripts/dev/run_mcp_server.py` 作為 prepared XBrainLab runtime 中的 stdio server
  entrypoint。
- `mcp_tool_specs()` 補 `title` 和 `outputSchema`，讓 external agent 能看到 input 與 execution
  envelope schema。
- 新增 `tests/unit/mcp/test_server.py` 和 `tests/integration/mcp/test_stdio_server.py`，覆蓋
  lifecycle、tool listing、同 session scan -> preview、schema repair result 和 stdio subprocess
  smoke。

### 影響範圍

- MCP adapter layer。
- Application automation schema metadata。
- Dev server entrypoint。
- Validation / current truth / planning docs。

### 驗證

- `poetry run pytest --capture=sys tests/unit/mcp tests/integration/mcp -q` -> `6 passed`
- `poetry run pytest --capture=sys tests/unit/mcp tests/integration/mcp tests/unit/backend/application/test_automation.py -q` -> `13 passed`
- `poetry run ruff check XBrainLab/mcp XBrainLab/backend/application/automation.py scripts/dev/run_mcp_server.py tests/unit/mcp tests/integration/mcp` -> `PASS`
- `poetry run basedpyright XBrainLab/mcp XBrainLab/backend/application/automation.py scripts/dev/run_mcp_server.py tests/unit/mcp tests/integration/mcp` -> `0 errors, 0 warnings, 0 notes`

### 剩餘風險

- 這是 stdio MCP server baseline，不是 external MCP client / Inspector walkthrough。
- 尚未補 Windows launcher / packaged config 讓使用者一鍵註冊 MCP server。
- 尚未驗證 long-running training tool through MCP、external agent recovery UX 或 HTTP transport。
- 這段風險已由後續 stdio external-client artifact、100-case local eval 和 one-turn ChatPanel
  local-model walkthrough 部分收斂；剩餘仍是 Inspector / release config、Windows launcher、
  multi-turn tool-command ChatPanel workflow 和成熟 import wizard UI。

## 2026-05-04 Local LLM tool-call runner and schema verifier

### 背景

Goal 1 不能只用 deterministic scorer 宣稱 agent tool-call evidence。既有
`run_tool_call_eval.py` 已有 `54` 個 cases，但仍是 scripted baseline；同時 local model output
可能是可解析 JSON，卻使用未註冊 tool name、缺 required parameter 或不合法 enum，不能等到 backend
execution 才發現。

### 變更

- 新增 `scripts/agent/evals/run_local_tool_call_eval.py`：
  - 共用 deterministic eval 的 cases、state fixtures 和 scoring dimensions。
  - 接真 local model raw output，保存 per-repeat raw output、parsed tool calls、schema verification
    和 score breakdown。
  - 支援 `--model-role primary|fallback`、`--repeat-count`、`--case-id`、`--case-limit` 和
    `--max-new-tokens`。
- `CommandParser` 可解析 `parameters` / `arguments`、top-level `name`，以及 `tool_calls` list。
- `VerificationLayer` 增加 `ToolSchemaValidator`，可檢查 unknown tool、required input、JSON-like
  type 和 enum。
- `LLMController` 用目前 real `ToolRegistry` schema 建立 `VerificationLayer`，因此可在 tool
  execution 前攔下 schema-invalid JSON。
- verifier rejection 會轉成 user-facing repair prompt 並寫入 structured `Tool Output`
  diagnostics，不再裸露 schema wording 或進入無限 retry。

### 影響範圍

- Agent parser / verifier / controller。
- Local tool-call eval artifacts。
- Validation docs。

### 驗證

- `poetry run pytest --capture=sys tests/unit/llm/test_parser.py tests/unit/llm/agent/test_verification_layer.py tests/unit/scripts/test_run_local_tool_call_eval.py -q` -> `44 passed`
- `poetry run pytest --capture=sys tests/unit/llm/agent/test_verification_layer.py tests/unit/llm/agent/test_controller.py tests/unit/llm/agent/test_controller_integration.py tests/integration/agent/test_product_flow.py tests/integration/agent/test_tool_call_eval.py -q` -> `98 passed`
- `poetry run pytest --capture=sys tests/unit/llm/agent tests/unit/llm/tools tests/unit/scripts/test_run_local_tool_call_eval.py tests/unit/llm/test_parser.py -q` -> `383 passed`
- `poetry run pytest --capture=sys tests/unit/backend/application -q` -> `35 passed`
- `poetry run pytest --capture=sys tests/integration/backend tests/integration/io/test_io_integration.py -q` -> `34 passed, 8 warnings`
- pipeline smoke -> `2 passed`
- `poetry run python scripts/dev/update_quality_dashboard.py` -> overall `PASS`
- final `ruff` / `basedpyright` / `mkdocs build --strict` / `architecture_compliance` / `git diff --check`
  clean。
- primary full local eval：
  - `54` cases x `3` repeats。
  - `18 / 54` pass，pass rate `33.33%`。
  - schema-invalid outputs `9`。
- fallback full local eval：
  - `54` cases x `3` repeats。
  - `20 / 54` pass，pass rate `37.04%`。
  - schema-invalid outputs `6`。

### 剩餘風險

- 這是 local LLM raw-output evidence，不是真 ChatPanel 長時間 walkthrough。
- 目前 pass rate 只支撐 failure taxonomy 和 engineering baseline，不能宣稱 thesis-ready
  tool-call accuracy。
- VerificationLayer 現在有 schema gate，但 self-correction / prompt feedback 還需要後續改善，
  否則 schema-invalid output 只會被攔下，不代表模型會自動修好。

## 2026-05-04 Label import compatibility wording

### 背景

主資料入口已改成 Data Interpretation，但 Dataset sidebar 仍有舊 `Import Label` 按鈕，容易讓
使用者把舊 label-first 心智模型當成同級主入口。實作上 label import 已先走
`ImportLabelsCommand(LabelImportPlan)`，controller 只是 fallback。

### 變更

- Dataset sidebar 按鈕從 `Import Label` 改成 `Add Labels to Loaded Data`。
- tooltip 改為 `Apply external labels to loaded files`。
- 更新 / 重跑相關 UI regression 和 Data Interpretation replay artifact。

### 影響範圍

- Dataset sidebar visible wording。
- Data Interpretation applied screenshot / replay JSON。

### 驗證

- `poetry run pytest --capture=sys tests/unit/ui/dataset/test_dataset_sidebar.py tests/unit/ui/test_ui_misc.py::TestDatasetActionHandler -q` -> `48 passed`
- `poetry run ruff check XBrainLab/ui/panels/dataset/sidebar.py` -> `PASS`
- `poetry run basedpyright XBrainLab/ui/panels/dataset/sidebar.py` -> `0 errors, 0 warnings, 0 notes`
- `xvfb-run -a poetry run python scripts/dev/capture_data_interpretation_replay.py` -> exit `0`

### 剩餘風險

- label import 仍是對已載入資料的 compatibility action；尚未整合進 Data Interpretation recipe
  語意。

## 2026-05-04 Data Interpretation recipe save UI path

### 背景

Dataset panel main import entry 已經走 scan / preview / validate / apply，但 UI 還沒有讓使用者在
apply 後保存 Data Interpretation recipe。這讓產品流程仍缺 `apply -> recipe` 的 UI-visible step。

### 變更

- `DataInterpretationPreviewDialog` 新增 `Save recipe after applying` checkbox。
- `DatasetActionHandler._run_data_interpretation_import()` 讀取 dialog result：
  - `confirmed` 繼續控制 `ApplyInterpretationCommand.confirmed`。
  - `save_recipe` 會在 apply 成功後觸發 `_save_interpretation_recipe()`。
- `_save_interpretation_recipe()` 使用 `QFileDialog.getSaveFileName()` 取得 JSON path，並只透過
  `SaveInterpretationRecipeCommand` 保存 recipe。
- 若使用者取消路徑選擇，仍會用無 path 的 `SaveInterpretationRecipeCommand` 將 recipe 保留在
  backend session。
- 更新 Dataset action tests、preview dialog test 和 UI replay artifact。

### 影響範圍

- Dataset import action。
- Data Interpretation preview dialog。
- UI replay artifact。

### 驗證

- `poetry run pytest --capture=sys tests/unit/ui/test_ui_misc.py::TestDatasetActionHandler tests/unit/ui/dialogs/dataset/test_data_interpretation_preview_dialog.py tests/integration/ui/test_product_walkthrough.py::test_pipeline_product_walkthrough_uses_user_facing_actions -q` -> `46 passed`
- `poetry run ruff check XBrainLab/ui/dialogs/dataset/data_interpretation_preview_dialog.py XBrainLab/ui/panels/dataset/actions.py tests/unit/ui/test_ui_misc.py tests/unit/ui/dialogs/dataset/test_data_interpretation_preview_dialog.py tests/integration/ui/test_product_walkthrough.py` -> `PASS`
- `poetry run basedpyright XBrainLab/ui/dialogs/dataset/data_interpretation_preview_dialog.py XBrainLab/ui/panels/dataset/actions.py tests/unit/ui/dialogs/dataset/test_data_interpretation_preview_dialog.py` -> `0 errors, 0 warnings, 0 notes`
- `xvfb-run -a poetry run python scripts/dev/capture_data_interpretation_replay.py` -> exit `0`

### 剩餘風險

- label import 目前是 compatibility action for already-loaded data；尚未納入 Data Interpretation
  recipe。
- save dialog click-through 有 unit coverage，UI replay artifact 顯示 checkbox state，但不等於真人
  file save dialog 操作。

## 2026-05-04 Data Interpretation UI replay artifact

### 背景

Goal 1 明確要求不能只用 backend JSON replay 宣稱 UI 正確；Data Interpretation import flow
需要 visible state、screenshot 或等價 UI artifact。

### 變更

- 新增 `scripts/dev/capture_data_interpretation_replay.py`。
- 腳本：
  - 產生 deterministic synthetic `.fif` source。
  - 啟動 real `MainWindow` / Dataset panel。
  - 使用 `ApplicationService` 跑 scan / preview / validate。
  - 開啟真 `DataInterpretationPreviewDialog` 並保存 screenshot。
  - 驗證 unconfirmed apply 會被 confirmation boundary 擋下。
  - 用 confirmed apply 載入資料，刷新 Dataset panel，保存 applied screenshot。
  - 寫出 replay JSON，包含 transcript、command result、visible dialog state、metadata rows、
    dataset panel visible state 和 screenshot filenames。
- 新增 artifacts：
  - `artifacts/ui/data-interpretation-preview.png`
  - `artifacts/ui/data-interpretation-applied.png`
  - `artifacts/ui/data-interpretation-replay.json`

### 影響範圍

- Dev validation script。
- UI artifacts。
- Validation / planning / current docs。

### 驗證

- `xvfb-run -a poetry run python scripts/dev/capture_data_interpretation_replay.py` -> exit `0`
- replay JSON observed:
  - dialog decision `needs_confirmation`
  - unconfirmed apply `failed / confirmation_required`
  - confirmed apply `ok`
  - Dataset panel row count `1`

### 剩餘風險

- 這不是完整真人 click-through；file picker 與 dialog acceptance 仍由 script programmatic flow
  驗證。
- ChatPanel visible transcript replay 尚未補。
- recipe save UI 和 label import migration 仍未完成。

## 2026-05-04 Data Interpretation non-mocked workflow evidence

### 背景

Goal 1 不允許只用 backend command unit tests 或 deterministic eval 宣稱資料入口可交付；至少要有
一條 source -> recipe -> preprocess -> epoch -> dataset 的 non-mocked workflow evidence。

### 變更

- 在 `tests/integration/backend/test_application_service_workflow.py` 新增
  `test_data_interpretation_to_dataset_workflow_is_non_mocked`。
- test 使用 real synthetic MNE `.fif` file，不 mock loader / preprocessor / dataset generator。
- workflow：
  - `scan_source`
  - `preview_interpretation`
  - `validate_interpretation`
  - unconfirmed `apply_interpretation` blocked by `confirmation_required`
  - confirmed `apply_interpretation`
  - `save_interpretation_recipe`
  - new service `reload_interpretation_recipe`
  - normalize preprocess
  - epoch
  - trial-wise dataset generation
- assertions 包含 interpretation state、recipe file existence、reload 不直接 apply、epoch count、
  split audit 和 train / val / test counts。

### 影響範圍

- Backend integration coverage only。
- 不新增產品 UI；不改 ApplicationService behavior。

### 驗證

- `poetry run pytest --capture=sys tests/integration/backend/test_application_service_workflow.py::test_data_interpretation_to_dataset_workflow_is_non_mocked -q` -> `1 passed`
- `poetry run pytest --capture=sys tests/integration/backend/test_application_service_workflow.py tests/unit/backend/application/test_application_service.py tests/unit/backend/application/test_automation.py -q` -> `38 passed`
- `poetry run pytest --capture=sys tests/integration/backend/test_application_service_workflow.py -q` -> `3 passed`
- `poetry run ruff check tests/integration/backend/test_application_service_workflow.py` -> `PASS`
- `poetry run basedpyright tests/integration/backend/test_application_service_workflow.py` -> `0 errors, 0 warnings, 0 notes`

### 剩餘風險

- 這是 backend-visible workflow evidence，不是 UI-observable replay。
- UI recipe save entry、label import migration 和完整 MCP server 仍未完成。

## 2026-05-04 Goal 1 automation adapter and eval baseline

### 背景

Goal 1 要求 UI、agent、headless runner 和 MCP external agent 共用同一套
`ApplicationService / Command API` truth。前面 slices 已完成 Data Interpretation backend、
agent surface 和 Dataset panel 主要 import entry，但 headless / MCP-ready schema 仍缺一個薄
adapter，deterministic eval 也仍停在舊 `21` cases，無法代表新的 Data Interpretation workflow。

### 變更

- 新增 `XBrainLab/backend/application/automation.py`。
  - `command_specs(service)` 從 typed command dataclass 產生 JSON schema、taxonomy 和 live
    capability / autonomy policy。
  - `mcp_tool_specs(service)` 使用同一份 schema 產生 MCP-shaped tool specs。
  - `execute_automation_payload(service, payload)` 驗證 JSON payload，轉 typed command，並只經
    `ApplicationService.execute()` 執行。
- 新增 `scripts/dev/run_application_command.py`，提供 headless schema listing、MCP-shaped tool
  listing 和 JSON payload execution。
- 擴充 `scripts/agent/evals/run_tool_call_eval.py`：
  - `54` cases。
  - `15` multi-turn cases。
  - `34 / 54` negative / blocked / confirmation / missing-input / recovery cases。
  - Data Interpretation / recipe / metadata choice cases 成為 engineering baseline。
  - artifact schema 保存 user command、initial state、available commands、expected / actual
    verification result、state delta、parsed tool call、simulated backend result、visible response
    和 score breakdown。
- 更新 `tests/integration/agent/test_tool_call_eval.py` 和新增
  `tests/unit/backend/application/test_automation.py`。

### 影響範圍

- Backend ApplicationService adapter layer。
- Headless dev script。
- Agent deterministic eval runner / artifact shape。
- Validation、current truth、planning 和 target architecture docs。

### 驗證

- `poetry run pytest --capture=sys tests/unit/backend/application/test_automation.py -q` -> `7 passed`
- `poetry run pytest --capture=sys tests/integration/agent/test_tool_call_eval.py -q` -> `1 passed`
- `poetry run ruff check XBrainLab/backend/application/automation.py scripts/dev/run_application_command.py scripts/agent/evals/run_tool_call_eval.py tests/unit/backend/application/test_automation.py tests/integration/agent/test_tool_call_eval.py` -> `PASS`
- `poetry run basedpyright XBrainLab/backend/application/automation.py scripts/dev/run_application_command.py scripts/agent/evals/run_tool_call_eval.py tests/unit/backend/application/test_automation.py tests/integration/agent/test_tool_call_eval.py` -> `0 errors, 0 warnings, 0 notes`
- `poetry run python scripts/agent/evals/run_tool_call_eval.py --output-dir artifacts/agent_evals`

### 剩餘風險

- `mcp_tool_specs()` 是 MCP-ready schema，不是已啟動的 MCP server。
- deterministic eval 仍是 scripted engineering baseline，不是 local LLM 真實 tool-call accuracy。
- backend/headless evidence 仍不能替代 UI-observable replay；wizard screenshot / visible state /
  transcript artifact 尚未完成。
- source -> recipe -> preprocess -> epoch -> dataset 的 non-mocked product walkthrough 尚未補齊。

## 2026-05-04 Goal 1 runbook prepared

### 背景

target、roadmap、now、validation 已經定義出第一個大 goal：Backend Command Spine +
Data Interpretation System + Agent Tool Surface Migration。使用者希望後續 runner 不要再
小修一段就回報，而是依工程級成品目標長跑，並以 reviewer 驗收。

### 變更

- 新增 `artifacts/goal/goal-1-product-autopilot.md`。
- 新增 `artifacts/goal/README.md`，記錄 `/goal <objective>` 的開啟方式與 troubleshooting。
- runbook 明確要求 runner 讀 target / architecture / validation / research docs。
- runbook 把 Data Interpretation command surface、agent tool taxonomy、autonomy policy、
  UI import alignment、tool-call eval、UI-observable replay、MCP-ready surface 和 commit
  discipline 寫成同一個產品目標。
- runbook 補強資料入口 UI 授權：新的 Data Interpretation / load data 機制可以且應該修改 UI，
  不能只做 backend 或沿用舊 `Import Data` / `Import Label` 心智模型。
- 補 target docs 中 UI / agent / headless / MCP external agent 共用 workflow truth 的用語。
- 更新 `docs/planning/now.md`，把 runbook 標記為已建立，下一步改成 docs checkpoint 與啟動 goal。

### 影響範圍

- Goal 啟動文件、target wording、short-term planning truth。
- 不改 source code、不改 tests。

### 驗證

- repo-local skill frontmatter quick check。
- `codex-cli 0.128.0`；`codex features list` 顯示 `goals under development true`。

### 剩餘風險

- Goal runner 尚未啟動；Data Interpretation、MCP-ready command surface、UI-observable replay
  仍是下一輪實作工作，不是已完成能力。

## 2026-05-04 MCP and UI-observable replay

### 背景

使用者指出 scripted replay 不能只看 backend 報告，因為 tool call 正確不代表 UI 行為正確；
同時也指出 headless script 的產品價值有限，MCP 作為 external agent adapter 更有意義，且
外部 agent client 不需要自行安裝 XBrainLab 的大型科學計算 / UI 依賴。

### 變更

- `docs/planning/roadmap.md` 新增 Automation Adapters / MCP track。
- `docs/target/architecture.md` 補 MCP server 作為 external agent adapter，並要求 MCP calls
  仍經 ApplicationService、capability policy 和 autonomy policy。
- `docs/validation/thesis_protocol.md` 將 scripted replay 拆成 backend replay 與 UI-observable
  replay；UI replay 需要 transcript、screenshots、visible state、button enablement 或 wizard
  artifact。
- `docs/planning/now.md` 補 MCP-ready automation surface 與 UI-observable scripted replay
  進 Goal 1 範圍 / done definition / validation gates。

### 影響範圍

- roadmap、target architecture、thesis validation protocol、short-term planning truth。
- 不改 source code、不改 tests。

### 驗證

- `git diff --check`
- `poetry run mkdocs build --strict`

### 剩餘風險

- MCP 目前只進 roadmap / target，尚未實作；Goal 1 最低要求是 MCP-ready command surface。
- UI-observable replay 仍需 runner 實作 artifact capture。

## 2026-05-04 Now aligned for Goal 1

### 背景

`docs/planning/roadmap.md` 已重寫為成品主線，target docs 也補完 Data Interpretation、
Autonomy Policy / Decision Boundary 和 tool taxonomy。舊 `now.md` 仍是過去 product-delivery
長 checklist，已不適合作為設定下一個 Codex goal 前的施工入口。

### 變更

- 重寫 `docs/planning/now.md`。
- 將 `now.md` 定位為 Goal 1 啟動前的短期施工焦點。
- 明確定義 Goal 1 範圍：Backend Command Spine + Data Interpretation System +
  Agent Tool Surface Migration。
- 補 Goal 1 Scope、Done Definition、Goal 前必做、Validation Gates、不能宣稱與下一步。
- 明確要求 goal 前建立 docs checkpoint，且不要混入 `.vscode/settings.json` 或 root
  `settings.json` 的本機變更。

### 影響範圍

- planning truth。
- 不改 source code、不改 tests。

### 驗證

- `git diff --check`
- `poetry run mkdocs build --strict`

### 剩餘風險

- 這次只更新短期施工入口；下一步仍需建立 docs checkpoint 與 Goal 1 runbook。

## 2026-05-04 Agent autonomy and tool taxonomy

### 背景

使用者指出 agent 不能只靠「聰明」自行判斷何時停下，也不能沿用舊 tool 種類。成熟方案需要在
workflow state 與 capability policy 之上，定義 command-specific autonomy policy / decision
boundary，讓 backend / Verification Layer 強制控制 agent 是否可自動執行、是否必須停下來問使用者。

### 變更

- `docs/target/agent.md` 新增 Autonomy Policy / Decision Boundary。
- 定義 `Workflow State`、`Capability Policy`、`Autonomy Policy` 三層分工。
- 補 command-specific autonomy 欄位：`can_auto_execute`、`requires_confirmation`、
  `decision_boundary`、`continue_allowed_after_success`、`retry_limit`、`stop_after_success`、
  `blocks_downstream_until_confirmed`。
- 將 tool surface 重寫成成熟 taxonomy：Discovery / Query、Data Interpretation、
  Metadata Resolution、Data Transform、Experiment Setup、Execution、Lifecycle / Destructive、
  UI Routing。
- `docs/target/data_interpretation_system.md` 補 subject / session / task / run metadata 作為
  Data Interpretation 核心語意。
- `docs/target/architecture.md` 補 Command API 需回傳 autonomy decision / decision boundary。
- `docs/validation/thesis_protocol.md` 補 autonomy-boundary metrics 和 benchmark cases。

### 影響範圍

- agent target、data interpretation target、target architecture、thesis validation protocol。
- 不改 source code、不改 tests。

### 驗證

- `git diff --check`
- `poetry run mkdocs build --strict`

### 剩餘風險

- 目前是 target design；實作仍需把現有 agent tool surface、ApplicationService command result、
  verifier 和 scorer 對齊 autonomy policy。

## 2026-05-04 Roadmap product tracks

### 背景

target design、Data Interpretation System、agent validation 和 thesis protocol 已經收斂到可作為
後續施工依據。原 roadmap 仍混合歷史階段、短期 TODO 和產品主線，容易讓 autopilot 誤把
局部完成當成成品完成。

### 變更

- 重寫 `docs/planning/roadmap.md`。
- 將 roadmap 定位為工程級成品主線，不取代 `docs/current.md` 或 `docs/planning/now.md`。
- 新增 Product North Star、路線原則、Product Completion Tracks、Roadmap Order、Non-goals
  與成品判定。
- 明確把 Data Interpretation System、Backend Command Spine、Agent Tool Surface、
  Tool-call Evaluation 和 Packaging / Release 分成可驗收主線。

### 影響範圍

- planning truth。
- 不改 source code、不改 tests。

### 驗證

- `git diff --check`
- `poetry run mkdocs build --strict`

### 剩餘風險

- roadmap 已定義成品主線，但 `docs/planning/now.md` 仍需在下一步更新成對應的短期施工焦點。

## 2026-05-03 Validation model alignment

### 背景

Data Interpretation 設計完成後，仍需要把驗證邏輯明確分層。否則後續 agent 實作可能把
LLM confidence、資料解讀 validation 和 backend state gate 混在一起。

### 變更

- `docs/target/data_interpretation_system.md` 新增三層驗證模型：
  Data Interpretation validation、Workflow State validation、Agent Tool-call validation。
- 明確定義 recipe reload 必須重新 scan / rebuild / preview / validate，不能直接套用。
- `docs/target/agent.md` 將資料入口 tool surface 對齊 Data Interpretation flow，不再把
  `load_data` / `attach_labels` 當成目標心智模型。
- `docs/validation/thesis_protocol.md` 補 Data Interpretation tool-call benchmark cases 與
  Verification Layer guard 條件。

### 影響範圍

- target truth、agent target、thesis validation protocol。
- 不改 source code、不改 tests。

### 驗證

- `git diff --check`
- `poetry run mkdocs build --strict`

### 剩餘風險

- 目前只是文件目標對齊；實際 agent tool surface 仍保留舊 `load_data` / `attach_labels` path，
  下一輪實作必須移到 Data Interpretation command。

## 2026-05-03 Data Interpretation design alignment

### 背景

全盤盤點 target design 後，確認 Data Interpretation 主軸成立，但 target architecture 仍保留
舊 `load_data` / `attach_labels` 作為理想 command；agent confidence gate 也需要和資料解讀
validation 區分。

### 變更

- `docs/target/architecture.md` 改成以 Data Interpretation flow 作為資料入口理想 command surface。
- `docs/target/agent.md` 保留 confidence gate，但明確定義它是 agent retry / self-correction
  gate，不能覆蓋 backend / Data Interpretation validation。
- `docs/target/data_interpretation_system.md` 補資料解讀生命週期：
  `ScanResult`、`InterpretationCandidate`、`InterpretationPreview`、
  `ValidationDecision`、`AppliedInterpretation`、`ImportRecipe`。
- 補 BIDS metadata 缺失的 `warning` / `limited` / `blocked` 分層。

### 影響範圍

- target truth 與 agent 目標文件。
- 不改 source code、不改 tests。

### 驗證

- `git diff --check`
- `poetry run mkdocs build --strict`

### 剩餘風險

- 文件已對齊，但實作尚未開始；下一步才適合產生 goal prompt 或 implementation plan。

## 2026-05-03 Data Interpretation target design

### 背景

使用者確認資料來源調查已足夠進入方案設計，並要求不要用 V1 / V2 或 legacy compatibility
作為對外原則。設計目標應是終局態：使用者提供資料位置，XBrainLab 建立可靠、可預覽、
可驗證、可重跑的資料解讀，而不是只 load file 或 attach label。

### 變更

- 新增 `docs/target/data_interpretation_system.md` 作為 canonical target design。
- 明確定義輸入模型：`source_path` 為核心，`source_hint`、user choices、recipe path 為可選。
- 明確定義輸出模型：`DataInterpretation`、label carriers、event roles、class map、time model、
  granularity、metadata、warnings、confirmations、recipe。
- 定義統一流程：scan -> interpret -> preview -> validate -> confirm -> apply -> save recipe。
- 定義判斷策略：`safe`、`needs_confirmation`、`blocked`。
- 將 BIDS 定位為 folder-level 一等入口；training / saliency 是下游 acceptance，而不是 import
  主模組。
- 更新 `docs/target/README.md`、`mkdocs.yml` 和 `docs/decisions/README.md`。

### 影響範圍

- target truth、文件導覽與決策入口。
- 不改 source code、不改 tests。

### 驗證

- `git diff --check`
- `poetry run mkdocs build --strict`

### 剩餘風險

- 這次只定義終局目標設計；實作、UI flow、agent tool-call benchmark 和 migration cleanup
  尚未開始。

## 2026-05-03 BCI/EEG import label design source

### 背景

使用者確認這份文件的定位不是 deficiency report，也不是 roadmap，而是後續設計
import / label / BIDS / fallback 機制時使用的整理過資料來源。文件需要整理真實
EEG / BCI 使用場景、資料格式、label / event carrier、metadata 結構與常見歧義。

### 變更

- 新增 `docs/research/bci_eeg_import_label_design_source.md`。
- 將使用者族群拆成 BCI 研究者、cognitive neuroscience / BIDS 使用者、BIDS curator /
  consumer、初學者、benchmark / replication 使用者、自建資料使用者、臨床長時間 EEG
  使用者。
- 整理 label carrier、coverage classes、BIDS 獨立章節、統一分析維度、import wizard /
  label preview / confirmation / recipe / agent eval 的設計問題。
- `mkdocs.yml` 新增 Research 導航入口。

### 影響範圍

- 文件與後續設計討論的資料來源。
- 不改 source code、不改 tests。

### 驗證

- `git diff --check`
- `poetry run mkdocs build --strict`

### 剩餘風險

- 這份文件只整理案例與設計依據；正式 import / label / BIDS / fallback 方案仍需另行設計
  並落到 target / architecture。

## 2026-05-03 Tool-call eval minimum gates

### 背景

使用者確認 tool-call thesis 主線後，進一步要求把 tool 重構、verification architecture 和足量
資料 / case 數寫成明確條件，而不是只寫方向。

### 變更

- 在 thesis protocol、agent target、backend goal runbook 和 `AGENTS.md` 補明確 gate。
- tool surface 需要重構為 service-backed command，mutating agent tools 不直接包 controller。
- Verification Layer contract 需要檢查 schema、required parameters、state precondition、
  resource existence、confirmation boundary、unsafe / destructive action、confidence threshold。
- tool-call eval cases 數量明確化：engineering baseline 至少 `50` cases，thesis candidate
  至少 `100` cases，negative / blocked / recovery cases 至少 `30%`，multi-turn 至少 `15` cases，
  local LLM primary / fallback runner 至少重跑 `3` 次。
- 資料級支撐需要 checked-in compact fixtures、event-rich public fixture slice；external EEG dataset
  只作 pipeline support。

### 影響範圍

- 文件與長任務 runner 驗收條件。
- 不改 source code、不改 tests。

### 驗證

- `git diff --check`
- `poetry run mkdocs build --strict`

### 剩餘風險

- 這次只把 gate 寫入文件；scorer、case schema、runner 和 fixture coverage 仍待實作。

## 2026-05-03 Thesis evidence positioning correction

### 背景

使用者指出論文要仔細驗證的是 agent tool-call 準確率，而不是 EEG 訓練準確率。既有文件雖然有
寫 agent tool-call eval 要獨立於 EEG classification metrics，但 `thesis_protocol` 和部分
validation wording 仍容易把 external dataset / training metrics 誤讀成 thesis 主線。

### 變更

- 將 `docs/validation/thesis_protocol.md` 改成 Thesis Tool-Call Evaluation Protocol。
- 明確寫下 thesis 主指標：intent、tool selection、parameter、state-transition、
  blocked-command handling、error recovery、invalid call rate、parser / verifier failure。
- 將 EEG split、training / evaluation metrics、external dataset runner 降格為 product
  pipeline support / domain task sanity。
- 更新 `docs/validation/README.md`、`docs/architecture/validation.md`、`docs/current.md`、
  `.agents/context/thesis.md` 和 backend goal runbook，避免後續 runner 被帶去優先做
  training accuracy thesis。

### 影響範圍

- 文件定位與 agent 發包指令。
- 不改 source code、不改測試、不改既有 split audit helper。

### 驗證

- `git diff --check`
- `poetry run mkdocs build --strict`

### 剩餘風險

- records 裡的歷史紀錄仍保留當時 wording；current truth 已改到 validation / architecture /
  thesis context。若後續要寫正式論文章節，還需要把 benchmark case schema 和 report format
  落成程式碼。

## 2026-05-03 Supervisor delivery gate, window fallback, backend rollback boundary

### 背景

人工退件指出先前把局部修復與 dashboard PASS 誤當成完成。使用者要求主 agent
扮演審查者 / 發包者，worker 完成回報不能直接轉交；仍有已知 blocker 時必須打回。
同時 Windows/WSLg offset dual-monitor layout 讓新增的置中 / recovery 邏輯把視窗開到
螢幕上方，backend 也仍需補強 service-first contract 的可靠邊界。

### 變更

- `AGENTS.md`、`.agents/README.md`、`.agents/runbooks/autopilot.md` 補上 supervisor
  model：主 agent 必須自己讀 diff、看 artifact、跑 tests、確認 docs/current truth。
- `MainWindow` 對 first launch、不健康 saved geometry、post-show recovery 改用
  maximized fallback；fullscreen geometry 視為不健康，不保存。
- Window placement tests 加入使用者回報的 offset monitor layout 與 virtual-gap cursor
  regression。
- `ApplicationService.generate_dataset` 把 split apply 與 audit 包進同一 rollback boundary；
  apply exception 或 audit blocking issue 都會還原 datasets / generator / trainer。
- `evaluate` / `clear_training_history` capability 改以 actual training plan history 為準。
- 修正 architecture/current/now 文件，不再把 synthetic UI walkthrough 或 deterministic eval
  說成完整產品交付證據。

### 影響範圍

- Agent 操作規則：`AGENTS.md`、`.agents/README.md`、`.agents/runbooks/autopilot.md`。
- UI shell：`XBrainLab/ui/main_window.py`、window geometry tests。
- Backend contract：`XBrainLab/backend/application/capabilities.py`、
  `XBrainLab/backend/application/service.py`、`XBrainLab/backend/facade.py`。
- Documentation：`docs/current.md`、`docs/planning/now.md`、architecture docs、records。

### 驗證

- `git diff --check`
- Python ruff gate on touched Python files：PASS
- Window geometry gate：`22 passed`
- Backend application / facade / agent surface gate：`80 passed`
- Assistant chat product slice：`48 passed`
- `poetry run basedpyright`：`0 errors, 0 warnings, 0 notes`
- `poetry run mkdocs build --strict`：PASS

### 剩餘風險

- 真 Windows/WSLg 雙螢幕 Desktop launcher click-through 尚未人工驗收。
- 現有 UI product walkthrough 仍使用 patched training / synthetic records，不是真 UI 點按到
  real training/evaluation/visualization completion。
- true local model 在 ChatPanel 中的長時間 UI walkthrough 尚未完成。

## 2026-05-02 Launcher visible startup logs and geometry diagnostics

### 背景

人工退件指出 Windows launcher 啟動後 terminal 一片黑，無法判斷目前跑到哪裡；同時主視窗仍可能
出現在正上方。需要先排除 Desktop launcher 是否指向舊 repo / stale generated app，再補可以
定位 WSLg / Windows 雙螢幕行為的啟動診斷。

### 變更

- 確認 `/mnt/c/Users/Administrator/Desktop/XBrainLab.cmd` 指向 active repo
  `/mnt/d/workspace_v2/projects/lab/XBrainLab`；Desktop 上沒有其他 XBrainLab app / shortcut。
- Desktop `.cmd` 和 repo `.cmd` 改成 bootstrap active repo 的 PowerShell launcher，啟動時直接顯示
  active repo、PowerShell launcher path 和啟動狀態。
- PowerShell launcher 會顯示 log path、開 log / tail log 指令，並用 live tee 把 WSL / Python
  stdout、stderr 同時寫入 terminal 和 `%LOCALAPPDATA%\XBrainLab\logs\launcher-*.log`。
- 新增 `XBRAINLAB_STARTUP_DIAGNOSTICS=1` gated startup geometry diagnostics；啟用時 log screens、
  cursor、splash geometry、MainWindow restore/default placement、show event 和 post-show geometry。
- MainWindow post-show recovery 從單次 `0ms` 改成 `0ms + 250ms`，避免 Windows / WSLg 在 show 後才
  finalize native frame 或移動 window 時漏掉 top-edge recovery。
- Launcher 增加 `XBRAINLAB_LAUNCHER_SMOKE=1` basic smoke mode，讓 `.cmd` / `.ps1` 可驗證 preamble、
  active repo delegation 和 log 寫入，不會真的啟動 GUI。

### 影響範圍

- Launchers：`scripts/launchers/xbrainlab_wsl_launcher.cmd`、
  `scripts/launchers/xbrainlab_wsl_launcher.ps1`、
  `/mnt/c/Users/Administrator/Desktop/XBrainLab.cmd`。
- Startup shell：`run.py`。
- UI shell：`XBrainLab/ui/main_window.py`、`XBrainLab/ui/window_placement.py`。
- Tests：`tests/integration/ui/test_window_geometry.py`、
  `tests/unit/ui/test_window_placement.py`。

### 驗證

- `poetry run pytest --capture=sys tests/integration/ui/test_window_geometry.py tests/unit/ui/test_window_placement.py tests/unit/test_run_splash_geometry.py -q`
  - `19 passed`
- `poetry run ruff check run.py XBrainLab/ui/main_window.py XBrainLab/ui/window_placement.py tests/integration/ui/test_window_geometry.py tests/unit/ui/test_window_placement.py tests/unit/test_run_splash_geometry.py`
  - `All checks passed!`
- `poetry run basedpyright`
  - `0 errors, 0 warnings, 0 notes`
- Launcher smoke：
  - PowerShell parser：`PowerShell syntax OK`
  - repo `.cmd` smoke：active repo bootstrap passed
  - Desktop `.cmd` smoke：active repo bootstrap passed
  - repo `.ps1` smoke：WSL stdout / stderr were mirrored to terminal and launcher log

### 剩餘風險

- 本輪仍未執行真人雙螢幕 Windows click-through；automated / smoke tests 可證明 launcher 指向 active
  repo、terminal 不再黑、diagnostic logging 可用、post-show recovery 有 regression coverage，但不能
  完全替代真 Windows window manager 驗收。

## 2026-05-02 Dual-monitor startup geometry follow-up

### 背景

第一版 MainWindow geometry recovery 通過 automated tests，但人工回報真 Windows desktop
launcher 仍會把視窗打到最上方，且啟動 loading splash 不在螢幕中央。這代表原修復只覆蓋
top-left / offscreen，沒有完整處理 top-edge、native frame titlebar、dual-monitor startup
screen selection。

### 變更

- 新增 `XBrainLab/ui/window_placement.py`，集中處理：
  - saved geometry screen ranking
  - cursor / primary fallback
  - startup screen hint
  - splash centering
  - frame-aware geometry health check
- `run.py` 在 splash `show()` 前先置中，並記住同一個 startup screen，讓 splash 和
  MainWindow 不再各自選螢幕。
- MainWindow 改用 shared placement helper；restored / persisted geometry 會檢查
  client geometry、native frame geometry、available geometry 和 full screen geometry。
- top-edge、top-center、top-right、frame top 超出螢幕、跨螢幕 frame 都會視為不健康並
  reset / recenter。
- 預設 window size 改成保留更多上下視覺空間，避免小螢幕上看起來貼在最上方。

### 影響範圍

- Startup shell：`run.py`。
- UI shell：`XBrainLab/ui/main_window.py`、`XBrainLab/ui/window_placement.py`。
- Tests：`tests/integration/ui/test_window_geometry.py`、
  `tests/unit/ui/test_window_placement.py`、`tests/unit/test_run_splash_geometry.py`。

### 驗證

- `poetry run pytest --capture=sys tests/integration/ui/test_window_geometry.py tests/unit/ui/test_window_placement.py tests/unit/test_run_splash_geometry.py -q`
  - `15 passed`
- `poetry run ruff check run.py XBrainLab/ui/main_window.py XBrainLab/ui/window_placement.py tests/integration/ui/test_window_geometry.py tests/unit/ui/test_window_placement.py tests/unit/test_run_splash_geometry.py`
  - `All checks passed!`
- `poetry run basedpyright`
  - `0 errors, 0 warnings, 0 notes`

### 剩餘風險

- 本輪仍需要真雙螢幕 Windows launcher 人工 click-through。Automated tests 可覆蓋 screen
  ranking、top-edge rejection、splash centering helper，但不能完全替代 Windows / WSLg
  window manager 行為。

## 2026-05-02 MainWindow saved geometry recovery

### 背景

人工退件指出 Windows desktop launcher 開啟後主視窗會卡到螢幕左上角且移動不了。
既有實作只要 `restoreGeometry()` 成功就只做 available-screen clamp，沒有判斷該 geometry
是否產品上可拖曳、titlebar 是否可達，也會在 `closeEvent()` 反覆保存壞狀態。

### 變更

- `MainWindow` 新增 restore/persist 前的 geometry 健康檢查：貼左上、offscreen、尺寸不合理、
  titlebar 不可達會被視為不健康。
- 啟動時若 saved `main_window/geometry` 不健康，會 `remove("main_window/geometry")` 並用
  留出 titlebar 拖曳空間的預設位置重置。
- 首次啟動的預設大小 / 位置會避開左上角，仍限制在 available screen 內。
- `closeEvent()` 只保存健康的 normal geometry；壞 geometry 會移除，避免永久卡住。
- 補 Assistant dock titlebar event regression，確認自訂 titlebar 空白區不吃掉
  `QDockWidget` 原生拖曳事件。

### 影響範圍

- UI shell：`XBrainLab/ui/main_window.py`。
- Regression tests：`tests/integration/ui/test_window_geometry.py`、
  `tests/unit/ui/components/test_agent_manager.py`。
- Docs：`docs/planning/now.md`、`docs/records/worklog.md`、
  `docs/records/implementation_log.md`。

### 驗證

- `poetry run pytest --capture=sys tests/integration/ui/test_window_geometry.py -q`
  - `6 passed`
- `poetry run pytest --capture=sys tests/unit/ui/components/test_agent_manager.py tests/integration/ui/test_product_walkthrough.py -q`
  - `32 passed`
- `poetry run ruff check XBrainLab/ui/main_window.py XBrainLab/ui/components/agent_manager.py tests/integration/ui/test_window_geometry.py`
  - `All checks passed!`
- `poetry run basedpyright`
  - `0 errors, 0 warnings, 0 notes`

### 剩餘風險

- 本輪沒有執行真人 Windows Desktop launcher click-through；persisted bad geometry recovery
  已由 automated regression tests 覆蓋。

## 2026-05-02 Product validation closure

### 背景

最後一輪 review 指出 fast dashboard 曾經 FAIL，且 canonical docs 仍有 stale evidence。
需要把退件修復、最新 dashboard 和剩餘 manual evidence 收斂成 current truth。

### 變更

- 修正 assistant local-disabled startup，讓使用者在 transcript 看到明確 unavailable reason。
- 修正 confirmation / tool transcript，不再把 raw tool names、schema 或 backend wording 當產品文字顯示。
- 修正 montage apply path，避免繞過 `ApplicationService` command surface。
- 修正 `run.py` / assistant startup path，維持 local-only runtime；remote backend modules 已從
  product package 移除，remote SDK 只在 optional legacy group。
- 穩定 UI baseline capture geometry。
- 更新 UI unit legacy runtime expectations：remote model switch fail-closed 到 local-only，
  active local model deletion 會被 block。
- 刷新 deterministic agent eval artifact：`artifacts/agent_evals/latest.json`。
- 更新 canonical docs：`current.md`、`validation/README.md`、records。

### 影響範圍

- Product validation truth：fast dashboard、UI product gate、agent/backend command gate、
  backend / IO / pipeline integration、LLM local settings / scripts。
- Documentation：current state、validation strategy、worklog、implementation log。
- Related commits：`8b04380`、`1883d4b`、`8a6099a`、`41ec91c`、`3edee21`、
  `5ed1c87`、`4cd4d4c`、`406719c`、`e5454c7`。

### 驗證

- Latest fast dashboard:
  - `artifacts/quality/latest.md`
  - generated at `2026-05-02 20:35:07 UTC+08:00`
  - overall `PASS`
  - Ruff PASS
  - Basedpyright PASS：`0 errors, 0 warnings, 0 notes`
  - Architecture PASS
  - Startup Smoke PASS
  - UI Baseline PASS
  - UI Dialog PASS
  - UI Unit Suite：`814 passed`
  - Real-Data IO Integration：`31 passed, 8 warnings`
- Additional supervisor gates:
  - `git diff --check` PASS
  - `poetry run ruff check .` PASS
  - `poetry run basedpyright` PASS
  - `poetry run mkdocs build --strict` PASS
  - `poetry run python tests/architecture_compliance.py` PASS
  - UI product / geometry gate：`121 passed`
  - agent / backend command gate：`225 passed`
  - backend + IO integration：`33 passed, 8 warnings`
  - full pipeline integration：`70 passed, 4 warnings`
  - LLM / local settings / script unit gate：`674 passed`
  - deterministic tool-call eval artifact refresh：commit
    `e5454c7 test: refresh agent eval artifact`
- Local model preflight:
  - primary `microsoft/Phi-4-mini-instruct` already cached
  - current / projected cache `15.34 GB`
  - available disk `158.54 GB`
  - estimated download `0.00 GB`
  - VRAM estimate `9.0 GB`
  - license MIT

### 剩餘風險

- Windows Desktop launcher click-through 尚未人工驗收。
- true local LLM ChatPanel long walkthrough 尚未跑。
- external thesis dataset experiment / statistical reporting 尚未完成。

## 2026-05-02 Local-only assistant runtime enforcement

### 背景

人工驗收指出先前只是把 Gemini/API 從一般 UI gate 隱藏，product code 仍可經由
`INFERENCE_MODE=api`、舊 settings 或 worker model switch 進入 remote backend。這不符合
local-only runtime 目標。

### 變更

- `LLMConfig` 變成 local-only runtime truth：舊 remote mode 只作 migration input，讀入後統一回
  `local`。
- `LLMEngine` 只 instantiate `LocalBackend`；product package 刪除 remote backend modules。
- `AgentWorker.reinitialize_agent(...)` 只接受 local model catalog 裡的 Phi primary / fallback 或
  generic `Local`，其他 model name fail closed。
- `ModelSettingsDialog` 移除 remote key verification / remote model UI，只保留 local model
  install/delete/activate 和 generation parameters。
- `pyproject.toml` default dependencies 移除 remote SDK；remote SDK 只保留 optional legacy group。
- 刪除 Gemini verify/list scripts，移除 legacy benchmark scripts 的 Gemini model option。
- `tests/architecture_compliance.py` 新增 local-only runtime static guard，禁止 product path 重新出現
  remote backend class / remote key env path。

### 影響範圍

- Runtime：`XBrainLab/llm/core/config.py`、`engine.py`、`agent/worker.py`、local backend package。
- UI settings：`XBrainLab/ui/dialogs/model_settings_dialog.py`。
- Tests / scripts / deps：LLM unit tests、model settings tests、benchmark model configs、Poetry deps。
- Docs：current、agent architecture、validation、records。

### 驗證

- Targeted subset：
  - `poetry run pytest --capture=sys tests/unit/llm/core/test_config.py tests/unit/llm/core/test_engine.py tests/unit/llm/agent/test_worker.py tests/unit/ui/dialogs/test_model_settings.py -q`
  - `73 passed`
- LLM unit suite:
  - `poetry run pytest --capture=sys tests/unit/llm -q`
  - `644 passed`
- Required validation:
  - `git diff --check`
  - `poetry run ruff check XBrainLab/llm XBrainLab/ui/dialogs/model_settings_dialog.py tests/unit/llm tests/unit/ui/dialogs tests/architecture_compliance.py`
  - `poetry run pytest --capture=sys tests/unit/llm tests/unit/ui/dialogs/test_model_settings.py tests/unit/scripts/test_plan_local_model_download.py tests/unit/scripts/test_inspect_local_assistant_runtime.py -q`
  - `674 passed`
  - `poetry run python tests/architecture_compliance.py`
  - `Architecture compliant`
- Manual fail-closed probes:
  - `INFERENCE_MODE=api` -> `local local`
  - settings JSON with Gemini mode -> `local local local False`
  - `reinitialize_agent("Gemini")` -> no backend switch, one error signal

### 剩餘風險

- 本輪不下載模型、不跑真 GPU 長 smoke。
- 真 local model 長時間 ChatPanel walkthrough 和 Windows launcher click-through 仍未完成。

## 2026-05-02 Assistant product shell and geometry rebuild

### 背景

人工退件指出 Assistant 仍像 debug / developer panel：第一層出現 runtime / backend 狀態、
mode wording、local model readiness，footer 沒有承擔使用者有用的 workflow hint；同時 app
啟動 geometry / dock titlebar 行為可能導致視窗 off-screen 或 dock 不易拖動。

### 變更

- `ChatPanel` 第一層重整為產品 shell：header 只保留產品標題與 icon-only `...` options；
  empty state 使用 EEG workflow 語言；composer footer 只顯示 workflow next action。
- runtime / backend diagnostics 從 visible first layer 移到 tooltip / settings / logs；visible
  transcript 不顯示 raw tool syntax、JSON、backend facade / service naming。
- `AgentManager` dock titlebar 改成會 ignore 空白區 mouse events 的 custom titlebar，保留
  QDockWidget 原生 drag / float；floating dock 會 clamp 到可用螢幕。
- `MainWindow` 新增 first-run centering、saved geometry restore、off-screen clamp，以及
  resize / maximize / restore regression test。
- `VRAMConflictChecker` 補上缺少 visualization panel 時的安全路徑，並移除 Gemini wording。
- 更新 chat / product walkthrough / AgentManager / window geometry tests 和 Assistant screenshot
  artifact / baseline。

### 影響範圍

- UI shell：`XBrainLab/ui/chat/panel.py`、`XBrainLab/ui/chat/styles.py`。
- Dock / window：`XBrainLab/ui/components/agent_manager.py`、
  `XBrainLab/ui/components/vram_checker.py`、`XBrainLab/ui/main_window.py`、
  `XBrainLab/ui/styles/stylesheets.py`。
- Tests / artifacts：chat unit、product walkthrough、AgentManager coverage、window geometry、
  `artifacts/ui/ai-assistant-open.png`、`tests/baselines/ui/ai-assistant-open.png`。

### 驗證

- `git diff --check`
- `poetry run ruff check XBrainLab/ui/chat XBrainLab/ui/components/agent_manager.py XBrainLab/ui/main_window.py tests/unit/ui/chat tests/integration/ui`
  - `All checks passed!`
- `scripts/dev/run_ui_pytest.sh tests/unit/ui/chat/test_chat_panel.py tests/integration/ui/test_product_walkthrough.py -q`
  - `42 passed in 9.22s`
- `scripts/dev/run_ui_pytest.sh tests/unit/ui/chat/test_chat_panel.py tests/integration/ui/test_product_walkthrough.py tests/integration/ui/test_window_geometry.py tests/unit/ui/components/test_agent_manager.py tests/unit/ui/test_agent_manager_coverage.py -q`
  - `92 passed in 10.86s`
- `xvfb-run -a poetry run python scripts/dev/capture_ui_baseline.py`
  - refreshed Assistant screenshot artifact and baseline.

### 剩餘風險

- 尚未做真 Windows launcher click-through。
- 尚未做真 local model 長時間 ChatPanel walkthrough；本輪沒有下載模型，也沒有改 LLM runtime core。

## 2026-05-02 Assistant product status polish

### 背景

Goal session 完成 Assistant product audit follow-up 後，人工審核仍發現 footer / runtime
status 有重複資訊風險：頂部已顯示 workflow guidance，底部再出現完整
`Workflow: ... | Assistant: ...` 會讓 Assistant dock 看起來像 debug console。此問題雖不會讓
測試失敗，但會影響使用者第一眼感受。

### 變更

- `ChatPanel` 不再把 legacy `runtime_status_label` 加到 visible composer footer；它保留為
  compatibility anchor / tooltip carrier，避免舊測試或 caller 直接斷裂。
- header subtitle 從較長的操作說明改成 `From data import to training`。
- footer runtime summary 改成低干擾狀態與 tooltip，不再在畫面底部重複 workflow diagnostics。
- 控制列高度從 70px 壓到 64px，讓 composer 區更像輸入區，而不是第二層 debug status bar。
- 更新 `artifacts/ui/ai-assistant-open.png` 和 `tests/baselines/ui/ai-assistant-open.png`。
- 修正 controller coverage 測試：exception path 不再用 `hi`，避免被 greeting shortcut 提前處理。

### 影響範圍

- UI：`XBrainLab/ui/chat/panel.py`、`XBrainLab/ui/chat/styles.py`。
- Tests / artifacts：chat panel unit、LLM controller coverage、Assistant dock screenshot baseline。

### 驗證

- `git diff --check`
- `poetry run pytest --capture=sys tests/unit/llm/agent/test_controller_cov.py tests/unit/ui/chat/test_chat_panel.py -q`
  - `67 passed`
- `poetry run ruff check XBrainLab/ui/chat/panel.py tests/unit/ui/chat/test_chat_panel.py tests/unit/llm/agent/test_controller_cov.py`
  - `All checks passed!`
- `poetry run ruff format --check XBrainLab/ui/chat/panel.py tests/unit/ui/chat/test_chat_panel.py tests/unit/llm/agent/test_controller_cov.py`
  - `3 files already formatted`
- `poetry run basedpyright`
  - `0 errors, 0 warnings, 0 notes`
- `poetry run python scripts/dev/update_quality_dashboard.py`
  - overall `PASS` at `2026-05-02 18:11:29 UTC+08:00`
  - includes Ruff, Basedpyright, Architecture Compliance, Startup Smoke, UI Baseline Capture,
    UI Dialog Acceptance, UI Unit Suite `830 passed`, and Real-Data IO Integration `31 passed`。

### 剩餘風險

- 真 Windows launcher click-through 尚未做。
- 真 local model 長時間 ChatPanel walkthrough 尚未做；本輪沒有下載模型，也沒有長時間 local
  LLM smoke。
- Gemini/API code path 已從一般產品入口隔離，但 source code 尚未刪除。

## 2026-05-02 Assistant product audit follow-up

### 背景

人工產品審核明確指出上一輪仍不合格：Assistant dock 頂部擠滿 chips / controls、主視覺仍像
debug panel、user bubble 在窄 dock 會切字、Retry 沒有上一則 request 時污染 transcript、
agent 會把 raw tool output / schema error / empty list 直接回給使用者。這些問題不能靠
dashboard PASS 或 deterministic eval 解釋掉，必須從產品 UI 與 agent visible-output boundary 修。

### 變更

- 重新整理 `ChatPanel`：
  - header 只保留產品名、自然語言 subtitle、`Options`。
  - workflow state / next step 改成單句 guidance，不再是 top chip dump。
  - local runtime / backend readiness 移到底部低干擾 status / tooltip / settings。
  - `Retry` / `Clear` 移到 composer footer；沒有 previous request 時 `Retry` disabled。
  - empty state 改成 EEG 使用者起始導引；message bubble 增加 minimum text column，避免
    `hello` 在 380px dock 被切碎。
- 改 `AgentManager.retry_last_user_input()`：沒有上一則 request 時只顯示 footer/status notice，
  不新增 assistant bubble。
- 改 `LLMController` visible-output path：
  - greeting shortcut 直接回產品導引，不先 call tool。
  - visible tool summary 使用產品語言，不顯示 `Tool <name> completed (...)`。
  - missing argument / empty result / backend precondition / runtime error 分 bucket 處理。
  - structured `Tool Output` 繼續保留在 controller history / diagnostics / logs，不進第一層
    ChatPanel transcript。
- 改 `ToolCommandResult` / `application_surface.py`：legacy read-only `list_files` /
  `get_dataset_info` 也會正規化為 typed result，避免 `"Error: ..."` 或 `[]` 被當成成功回覆。
- 隔離 legacy remote runtime：`XBRAINLAB_SHOW_LEGACY_REMOTE_LLM=1` 未設定時，ChatPanel
  model menu、ModelSettingsDialog remote section、AgentManager startup 都不顯示或啟動 Gemini。
- 更新 UI screenshot evidence：
  - `artifacts/ui/ai-assistant-open.png`
  - `tests/baselines/ui/ai-assistant-open.png`

### 影響範圍

- UI：`XBrainLab/ui/chat/*`、`AgentManager`、model settings、main-window debug feedback。
- Agent：`LLMController`、tool result adapter、agent product-flow tests。
- Runtime config：legacy remote runtime product visibility gate。
- Docs / records / UI baseline artifacts。

### 驗證

- UI assistant / settings / AgentManager gate：
  - `timeout 300s scripts/dev/run_ui_pytest.sh tests/unit/ui/chat/test_chat_panel.py tests/unit/ui/chat/test_message_bubble.py tests/unit/ui/dialogs/test_model_settings.py tests/unit/ui/components/test_agent_manager.py tests/unit/ui/test_agent_manager_coverage.py -q`
  - `131 passed`
- agent product-flow / tool formatting / config gate：
  - `timeout 240s poetry run pytest --capture=sys tests/integration/agent/test_product_flow.py tests/unit/llm/agent/test_controller.py tests/unit/llm/tools/test_application_surface.py tests/unit/llm/tools/real/test_real_tools.py tests/unit/llm/core/test_config.py -q`
  - `110 passed`
- backend application / facade workflow gate：
  - `timeout 240s poetry run pytest --capture=sys tests/unit/backend/application tests/integration/backend/test_application_service_workflow.py tests/unit/backend/test_facade_coverage.py tests/unit/backend/test_facade_headless.py -q`
  - `57 passed`
- product walkthrough / agent integration:
  - `timeout 300s scripts/dev/run_ui_pytest.sh tests/integration/ui/test_product_walkthrough.py -q`
  - `2 passed`
  - `timeout 180s poetry run pytest --capture=sys tests/integration/agent/test_tool_call_eval.py tests/integration/agent/test_product_flow.py -q`
  - `7 passed`
- UI capture：
  - `timeout 240s xvfb-run -a poetry run python scripts/dev/capture_ui_baseline.py`
  - saved `artifacts/ui/ai-assistant-open.png`
- aggregate dashboard：
  - `timeout 420s poetry run python scripts/dev/update_quality_dashboard.py`
  - overall `PASS` at `2026-05-02 17:44:37 UTC+08:00`

### 剩餘風險

- 這輪有 screenshot artifact 和 deterministic layout assertions，但仍需要人工 UI 審核判斷
  380-460px dock 是否符合產品質感。
- 真 Windows launcher click-through 尚未做。
- 真 local model 長時間 ChatPanel walkthrough 未做；本輪沒有下載模型，也沒有長時間 local LLM smoke。
- Gemini/API code path 只是從一般產品入口隔離，尚未從 codebase 刪除。
- label import、smart parse、montage confirmation 仍是 controller / UI-request legacy path。

## 2026-05-02 Assistant runtime consent、service query commands 與 thesis split protocol

### 背景

本輪人工接手要求把 XBrainLab 往工程級桌面產品交付推進，而不是只修局部 patch。
前一輪已修 chat visible-response blocker，但仍留下三個產品缺口：Assistant UI 第一層仍有
過多 debug/control 資訊、本地 LLM 啟用缺少 first-run consent、UI / agent / backend 對 query
commands 與 dialog submit path 尚未完整收斂。另外，thesis-grade validation 不能只靠 tiny
pipeline smoke，需要固定 split protocol 和 artifact audit。

### 變更

- ChatPanel 將 persona/runtime/step mode 收進 Options / 低干擾 status；主視覺保留自然語言
  workflow stage 和 next step，不顯示 raw command names。
- 新增 `LocalRuntimeFirstRunDialog`，首次啟用 local runtime 前顯示 GPU/CPU resource notice、
  estimated download、cache status、provider/license/VRAM estimate，提供 Enable / Download /
  Use existing cache / Later / Disable。
- `LLMConfig` 增加 `local_runtime_notice_acknowledged`，settings dialog 和 assistant panel
  共用 local runtime truth；app startup 不自動載入大型 local model。
- `ApplicationService` 將 `evaluate`、`visualize`、`saliency`、`new_session` 從 placeholder
  推進成 typed query / lifecycle command；`BackendFacade.get_latest_results()` 保留 legacy
  shape，同時保存 service diagnostics。
- UI dialog/query paths 改走 command adapter：channel selection、split dataset、model
  selection、training settings、evaluation query、visualization query、saliency setup/query。
- agent deterministic eval 更新 query-command 語意；tool result payload 保留 diagnostics /
  state / capability。
- 新增 `XBrainLab/backend/dataset/split_audit.py`、`scripts/dev/validate_split_artifact.py`、
  `docs/validation/thesis_protocol.md`、`docs/validation/split_artifact_schema.json`，支援 split
  indices 保存、subject/session leakage audit 和 artifact validation。

### 影響範圍

- backend ApplicationService / BackendFacade
- UI ChatPanel / AgentManager / model settings / workflow sidebars
- agent deterministic eval artifacts
- split validation helper、script、tests
- current / planning / architecture / validation / records docs

### 驗證

- `poetry run ruff check XBrainLab/ tests/ scripts/dev/validate_split_artifact.py` 通過。
- `poetry run ruff format --check XBrainLab/ tests/ scripts/dev/validate_split_artifact.py` 通過。
- `git diff --check` 通過。
- `poetry run mkdocs build --strict` 通過。
- UI product gate：
  - `timeout 300s scripts/dev/run_ui_pytest.sh tests/unit/ui/chat/test_chat_panel.py tests/unit/ui/components/test_agent_manager.py tests/unit/ui/dialogs/test_local_runtime_first_run_dialog.py tests/integration/ui/test_product_walkthrough.py -q`
  - `62 passed`
- backend / validation / config gate：
  - `timeout 300s poetry run pytest --capture=sys tests/unit/backend/application/test_application_service.py tests/unit/backend/dataset/test_split_audit.py tests/unit/scripts/test_validate_split_artifact.py tests/unit/llm/core/test_config.py -q`
  - `41 passed`
- agent / facade / backend workflow gate：
  - `timeout 300s poetry run pytest --capture=sys tests/unit/llm/tools/test_application_surface.py tests/unit/llm/agent/test_controller.py tests/unit/llm/agent/test_worker.py tests/unit/backend/test_facade_coverage.py tests/unit/backend/test_facade_headless.py tests/integration/backend/test_application_service_workflow.py -q`
  - `130 passed`
- deterministic eval artifact refresh：
  - `timeout 120s poetry run python scripts/agent/evals/run_tool_call_eval.py --output-dir artifacts/agent_evals`
  - `21 / 21` deterministic cases passed after query-command semantic update.
- full test gate：
  - `timeout 2400s poetry run pytest tests/ --deselect tests/unit/ui/test_visualization.py::TestSaliency3DEngine --tb=short -q`
  - `4386 passed, 3 skipped, 3 deselected, 1 xfailed, 14 warnings`

### 剩餘風險

- 真 Windows Desktop launcher click-through 尚未人工驗收。
- 真 local model 長時間 ChatPanel walkthrough 沒有跑；本輪只跑 preflight/cache/status/UI logic，
  沒有重複載入大型模型。
- label import、smart parse、montage confirmation 仍是 legacy / UI-request path。
- thesis protocol 已有 schema / audit / validator，但 external thesis dataset runner、repeat
  runs、baseline comparison、statistical reporting 尚未完成。

## 2026-05-02 Chat product flow blocker 與 visible-response contract

### 背景

使用者人工打開 AI Assistant 後發現兩個產品阻塞：介面仍像 debug dock，且輸入 `hello`
後沒有 assistant 回覆。這代表先前 automated final gate、local prompt smoke、launcher
startup smoke、deterministic eval 都沒有覆蓋最基本的 user-visible chat path，不能再宣稱
product delivery 完成。

### 變更

- `LLMController` 新增 visible-response contract：
  - empty model response 會回 visible error，不再 silent finalize。
  - tool-only successful turn 會產生 short tool summary，避免 JSON 被隱藏後使用者看不到結果。
  - ApplicationService blocked command 會立即發出 shared blocked reason。
  - busy re-entry 會顯示 assistant still processing，而不是默默忽略。
- `AgentManager` 在 controller busy 時不再先加入新的 user message 再被 controller 吃掉。
- `ChatPanel` 重新設計成產品級結構：
  - header：`XBrainLab Assistant`、backend stage chip、local model status chip、available command chip。
  - empty state：說明 assistant 可做 state inspection、blocked reason explanation、workflow guidance。
  - conversation area：專業 bubble、padding、max width、可讀 contrast。
  - composer：清楚 `Send` / `Stop` 狀態，processing 時禁用會造成 race 的 controls。
- 新增 product-flow tests：
  - normal `hello` path 產生 user bubble + assistant bubble + non-empty content。
  - empty response fallback visible。
  - worker error visible。
  - local unavailable first-open visible。
  - ChatPanel structure / status chips / composer controls。
- 文件校正 automated evidence 邊界：dashboard / deterministic eval / local smoke 不能替代真 chat product flow。

### 影響範圍

- UI chat panel
- AgentManager wiring
- LLMController response finalization
- UI / agent validation tests
- current / planning / architecture / validation docs

### 驗證

- `timeout 240s scripts/dev/run_ui_pytest.sh tests/unit/ui/chat/test_chat_panel.py tests/unit/ui/components/test_agent_manager.py -q`
  - `55 passed`
- `timeout 180s poetry run pytest --capture=sys tests/unit/llm/agent/test_controller.py tests/unit/llm/agent/test_worker.py -q`
  - `75 passed`
- `timeout 300s scripts/dev/run_ui_pytest.sh tests/unit/ui -q`
  - `817 passed`
- `timeout 300s poetry run pytest --capture=sys tests/unit/llm -q`
  - `652 passed`
- `timeout 180s poetry run basedpyright`
  - `0 errors, 0 warnings, 0 notes`
- `timeout 180s poetry run pytest --capture=sys tests/unit/llm/agent/test_controller.py tests/unit/llm/agent/test_worker.py tests/unit/llm/core/test_local_backend.py tests/unit/llm/core/test_engine.py -q`
  - `102 passed`
- `timeout 120s poetry run mkdocs build --strict`
  - passed
- `timeout 60s git diff --check`
  - passed
- `timeout 360s poetry run python scripts/dev/update_quality_dashboard.py`
  - overall `PASS`
  - UI baseline capture `PASS`
  - Basedpyright `0 errors`

### 剩餘風險

- 這一輪的 normal chat product-flow tests 使用 fake controller / fake engine，不載入大模型；
  真 local Phi model 的 full chat walkthrough 仍需 resource-safe smoke。
- Windows Desktop shortcut 的人工 click-through 仍未完成。
- UI action execution 仍有 controller direct-call legacy path；本輪修的是 chat product blocker，
  不是完成所有 UI command adapter migration。

## 2026-05-02 Deterministic tool-call eval baseline

### 背景

product-delivery final gate 通過後，可以開始 tool-call eval / thesis evidence 的第一層。
為避免把 local model loading 和 eval framework 綁死，先建立 deterministic scripted baseline；
這能驗證 case schema、scoring 維度、artifact 產出和 ApplicationService state/capability
邏輯，不宣稱 local LLM 真實成功率。

### 變更

- 新增 `scripts/agent/evals/run_tool_call_eval.py`。
- 建立 `21` 個 XBrainLab 專用 cases，覆蓋 empty/load/preprocess/epoch/dataset/train/reset/
  visualize/saliency/invalid parameter/multi-turn recovery/tool-result interpretation。
- scoring 維度包含 intent、tool selection、argument correctness、state-aware decision、
  blocked-command handling、multi-turn recovery、tool result interpretation、trajectory quality、
  runtime safety、local LLM reliability。
- 產出 machine-readable `artifacts/agent_evals/latest.json` 與 human-readable
  `artifacts/agent_evals/latest.md`。
- 新增 `tests/integration/agent/test_tool_call_eval.py`，驗證至少 20 cases、summary metrics 和
  artifact writing。

### 影響範圍

- agent validation scripts
- validation artifacts
- thesis evidence foundation
- validation docs

### 驗證

- `timeout 180s poetry run pytest --capture=sys tests/integration/agent -q`
  - `1 passed`
- `timeout 120s poetry run python scripts/agent/evals/run_tool_call_eval.py --output-dir artifacts/agent_evals`
  - `21 / 21` deterministic cases passed
  - artifacts written to `artifacts/agent_evals/latest.json` and `artifacts/agent_evals/latest.md`

### 剩餘風險

- 這是 deterministic baseline，不是 local LLM primary / fallback 真實 tool-call result。
- 下一步要接 local model runner，測同一批 cases 的穩定性、structured-output failure、
  retry / recovery 和 model-to-model 差異。

## 2026-05-02 Final product gate 與 local model preflight idempotence

### 背景

final gate 前的 local model preflight 暴露出一個產品交付問題：primary model 已在
`XBrainLab/llm/core/models` cache 中，但 preflight 仍把它當成新下載，導致 projected cache
從 `15.34 GB` 誤算成 `23.03 GB` 並回報超過 20GB 上限。這會讓已安裝模型的使用者看到錯誤
下載狀態。

### 變更

- `plan_model_download()` 現在會辨識 Hugging Face cache layout 和 safe local cache layout。
- 若模型已存在，preflight 回傳 `ok=True`、estimated download `0.00 GB`，projected cache
維持 current cache。
- 補 `test_download_preflight_allows_already_cached_model_without_increment()`。
- final gate 依 resource-safe execution 單項執行 backend、UI、LLM、pipeline、local runtime、
launcher、MkDocs 與 whitespace 檢查。

### 影響範圍

- local model download preflight
- operations / validation docs
- final product gate evidence

### 驗證

- `timeout 120s poetry run pytest --capture=sys tests/unit/llm/core/test_model_catalog.py tests/unit/scripts/test_plan_local_model_download.py -q`
  - `7 passed`
- `timeout 120s poetry run python scripts/dev/plan_local_model_download.py --format markdown`
  - `ok=True`; primary already cached; projected cache `15.34 GB`
- `timeout 300s poetry run pytest --capture=sys tests/unit/backend -q`
  - `2661 passed, 1 skipped, 1 xfailed, 3 warnings`
- `timeout 300s poetry run pytest --capture=sys tests/integration/backend tests/integration/io/test_io_integration.py -q`
  - `33 passed, 8 warnings`
- `timeout 600s poetry run pytest --capture=sys tests/integration/pipeline -q`
  - `70 passed, 4 warnings`
- `timeout 300s scripts/dev/run_ui_pytest.sh tests/unit/ui -q`
  - `811 passed`
- `timeout 300s poetry run pytest --capture=sys tests/unit/llm -q`
  - `649 passed`
- `timeout 300s poetry run python scripts/dev/inspect_local_assistant_runtime.py --format markdown --prompt-smoke --structured-smoke`
  - classification `gpu-ready`; prompt smoke `passed`; structured-output smoke `passed`
- `timeout 45s xvfb-run -a poetry run python run.py --model local`
  - `MainWindow initialized` before expected timeout.

### 剩餘風險

- launcher smoke is still automated startup under `xvfb`, not a human click-through of the Windows Desktop shortcut.
- local runtime health confirms prompt / structured smoke, but not full multi-turn scientific workflow quality.
- tool-call eval / thesis evidence still must wait until product walkthrough is stable.

## 2026-05-02 Agent tool typed result adapter

### 背景

UI / agent command surface 已開始共用 ApplicationService capability policy，但 agent real tools
仍有一個產品級可靠性缺口：部分 legacy tools 用字串回傳錯誤，例如 `"Error: ..."` 或
`"Failed ..."`，而 controller 會把「工具正常返回字串」當成 successful execution。這會讓
assistant 把 failed backend operation 記成成功，後續對話和 UI feedback 都會失真。

### 變更

- 在 `XBrainLab/llm/tools/application_surface.py` 新增 `ToolCommandResult` typed adapter。
- 將 ApplicationService blocked command 轉成 structured failed result，包含 command name、
  blocked reason、capability 和 state snapshot。
- 將 legacy string result 正規化：`Error:`、`Failed ...`、`Dataset generation failed ...`
  等會被視為 failed result，不再當成成功。
- `LLMController._execute_tool_no_loop()` 對 ApplicationService-backed tools 回傳
  `ToolCommandResult`，並把 failure 記入 metrics / history。
- `Tool Output` JSON payload 現在保留 `command_name`、`error_type`、`recoverable`、
  `blocked_reason`、`state`、`capability`、`raw_result`。
- 修正 `tests/unit/llm/agent/test_worker.py`，避免 LLM unit tests 將 repo `settings.json`
  污染回 Gemini / API mode。

### 影響範圍

- agent tool execution
- ApplicationService capability gate
- structured tool result history
- LLM unit tests and local runtime default config hygiene

### 驗證

- `timeout 120s poetry run pytest --capture=sys tests/unit/llm/tools/test_application_surface.py tests/unit/llm/agent/test_controller.py -q`
  - `55 passed`
- `timeout 180s poetry run pytest --capture=sys tests/unit/llm/agent tests/unit/llm/tools -q`
  - `321 passed`
- `timeout 60s git diff --check`
  - 通過

### 剩餘風險

- 部分 real tools 仍先走 `BackendFacade` legacy method，再由 adapter 包成 structured result；
  之後應逐步讓 load / preprocess / epoch / dataset / train execution 直接回傳 backend
  `CommandResult`。
- UI side effects 仍使用 `Request:` 字串協定；下一步應改成 typed UI request/event。

## 2026-05-02 Local LLM runtime 與 desktop launcher baseline

### 背景

product-delivery 主線要求 XBrainLab 能逐步成為可直接使用的桌面軟體。使用者也明確要求
不可使用 Qwen，並進一步限制不可使用中國公司或中國來源模型。因此 local assistant runtime
不能保留 Qwen / DeepSeek / Yi / GLM / Baichuan / InternLM / MiniCPM 等模型作為候選，也不能
依賴 Gemini/API 作為產品路線。

### 變更

- 新增 `XBrainLab/llm/core/model_catalog.py`：
  - 定義 primary `microsoft/Phi-4-mini-instruct`。
  - 定義 fallback `microsoft/Phi-3.5-mini-instruct`。
  - 封裝非中國模型 allow-list、blocked provider policy、單模型 10GB / 總 cache 20GB preflight。
- 更新 local runtime：
  - `LLMConfig` 預設 local model 改為 Phi-4 mini，4-bit 不是預設硬需求。
  - `AgentWorker` 在 primary 不可用且 fallback cache ready 時依 policy 切到 fallback。
  - `LocalBackend` 阻擋 unsupported / policy-blocked local model。
  - 補 Phi remote-code compatibility patch，並讓 generation thread exception 回傳錯誤。
- 更新 UI：
  - Model settings 只列 product catalog 內的 local model。
  - AgentManager 第一次打開 chat panel 不再強迫 settings modal；local runtime unavailable 時面板保持可見並顯示原因。
- 更新 scripts：
  - `scripts/dev/plan_local_model_download.py`
  - `scripts/dev/inspect_local_assistant_runtime.py`
  - `scripts/launchers/xbrainlab_wsl_launcher.cmd`
  - `scripts/launchers/xbrainlab_wsl_launcher.ps1`
- 清理舊 Qwen cache，下載 primary / fallback Phi cache，並把可執行 benchmark script 的 Qwen model entry 移除。
- 複製可點擊 launcher 到 `/mnt/c/Users/Administrator/Desktop/XBrainLab.cmd`。

### 影響範圍

- local LLM model selection / download / health check
- agent runtime startup and fallback
- model settings dialog
- chat panel first-open failure boundary
- Windows launcher / operations docs
- local runtime and launcher validation docs

### 驗證

- fallback preflight：
  - `poetry run python scripts/dev/plan_local_model_download.py --model microsoft/Phi-3.5-mini-instruct --format markdown`
  - `ok: True`
  - projected cache `15.33 GB`
- primary health:
  - `poetry run python scripts/dev/inspect_local_assistant_runtime.py --format markdown --prompt-smoke --structured-smoke`
  - prompt smoke `passed`
  - structured-output smoke `passed`
- fallback health:
  - `poetry run python scripts/dev/inspect_local_assistant_runtime.py --model microsoft/Phi-3.5-mini-instruct --format markdown --prompt-smoke --structured-smoke`
  - prompt smoke `passed`
  - structured-output smoke `passed`
- startup smoke:
  - `timeout 35s xvfb-run -a poetry run python run.py --model local`
  - `MainWindow initialized` 後 timeout，屬 GUI smoke 預期結果。
- targeted tests:
  - `poetry run pytest --capture=sys tests/unit/llm/core/test_config.py tests/unit/llm/agent/test_worker.py tests/unit/ui/components/test_agent_manager.py -q`
  - `66 passed`
  - `poetry run pytest --capture=sys tests/unit/llm/core/test_local_backend.py -q`
  - `18 passed`

### 剩餘風險

- API / Gemini runtime code 仍存在，需要在產品收斂中隔離或移除；目前不再作產品目標。
- fallback 已驗證可載入與輸出，但尚未跑完整 agent multi-turn tool workflow。
- desktop launcher 已產出並通過 startup path smoke，但尚未完成真 click-through
  launcher -> chat panel -> tool call product walkthrough。
- local LLM smoke 尚未納入 fast quality dashboard 預設 profile。

## 2026-05-02 Product delivery 文件指令校準

### 背景

使用者指出 agent 仍把自己限制在「第一版後端 command layer 收尾」，但目前目標已經是
product-delivery engineering：backend、UI、agent、local LLM、desktop launcher 與後續
tool-call eval 要一路推進到工程級可用。檢查後發現 `docs/planning/now.md`、
`docs/index.md`、`.agents/runbooks/*`、`docs/planning/roadmap.md` 等 current-facing 文件
仍殘留文件整理期或全盤架構複盤期的保守指令。

### 變更

- 將 `docs/current.md` 和 `docs/index.md` 校準為 product-delivery 現況。
- 將 `docs/planning/now.md` 的「現在不做 / 第一版後端 Done Definition」改成
  Product Delivery Done Definition。
- 將 `docs/planning/roadmap.md` 改成 backend core、UI / agent command surface、
  UI chat、local LLM、desktop launcher、product stabilization、tool-call eval 的路線。
- 更新 `.agents/README.md`、`.agents/stack.md`、setup、autopilot、active queue、
  session prompts 和 architecture-review workflow，避免 agent 被舊 review gate 擋住。
- 更新 `docs/decisions/README.md`，記錄 milestone 是最低門檻、eval 要等產品穩定、
  local LLM 下載要受容量邊界控制。
- 更新 `docs/validation/README.md`，把目前優先驗證改成 product delivery 主線。

### 影響範圍

- agent 進場定位
- product delivery milestone
- planning / roadmap / decisions
- validation priority
- long-running autopilot behavior

### 驗證

- `poetry run mkdocs build --strict` 通過。
- `git diff --check -- docs .agents AGENTS.md README.md mkdocs.yml` 通過。
- stale instruction scan 通過：current-facing 文件中已沒有會要求「先全盤架構複盤、不開工、
  不一次做 UI / agent」的過期停止條件。
- legacy / active path check 通過：`docs/legacy/`、`docs/active/`、`.agents/legacy/`、
  `docs/records/documentation_audit.md` 皆不存在。

### 剩餘風險

- `docs/records/` 內仍保留歷史語句，作為流水帳與交接紀錄，不應被 agent 當 current truth。
- `architecture-review` workflow 仍可用於純 review 任務，但已標明不阻擋 product delivery。

## 2026-05-02 UI / Agent command surface unification

### 背景

後端 ApplicationService 第一版通過 contract tests，但 product-delivery gate 要求更高：
UI、Agent、Script 不應各自複製 readiness 判斷、state transition 規則或 blocked reason。
回頭驗收 Milestone 1 時也發現 `preprocess` capability 的前置條件判斷不夠準：raw-only
state 應允許 preprocessing，真正需要 preprocessed data 的是 `create_epoch`。

### 變更

- 修正 `CapabilityPolicy`：
  - `preprocess` 以 raw data 作為前置條件。
  - `create_epoch` 仍以 preprocessed data 作為前置條件。
- 新增 UI capability helper：
  - `XBrainLab/ui/application_capabilities.py`
  - UI component 可從 nearest real `Study` 取得 `BackendFacade.get_capabilities()`。
- UI 第一批 readiness 改讀 ApplicationService policy：
  - Dataset import -> `load_data`
  - Preprocess operations -> `preprocess`
  - Epoching -> `create_epoch`
  - Start Training -> `train`
- 新增 agent command surface：
  - `XBrainLab/llm/tools/application_surface.py`
  - 將 agent tool names 對映到 `CommandName`。
  - `ContextAssembler` 用 ApplicationService policy 列 available tools 和 blocked command reason。
  - `LLMController` 在 tool execution 前重新檢查同一 policy。
- Agent tool output 寫回 structured JSON payload：`ok`、`tool_name`、`message`、`raw_result`。
- Chat / AgentManager 補產品化控制：
  - retry
  - clear
  - backend/model compact diagnostics
  - debug tool flow 接到 `LLMController.execute_debug_tool()`
- 修正 `AgentWorker` runtime config reload：沒有 persisted config 時保留現有 engine config，
  避免生成前把已載入 runtime 誤覆蓋成 default unavailable local config。

### 影響範圍

- backend capability policy
- UI dataset / preprocess / training readiness
- chat panel and agent manager
- agent context assembly and execution guard
- local agent worker config sync
- backend / UI / LLM unit tests
- architecture docs

### 驗證

- `poetry run pytest --capture=sys tests/unit/backend/application -q` 通過，`9 passed`。
- `poetry run pytest --capture=sys tests/unit/backend/test_facade_coverage.py tests/unit/backend/test_facade_headless.py -q` 通過，`44 passed`。
- `poetry run pytest --capture=sys tests/unit/llm/agent tests/unit/llm/tools -q` 通過，`318 passed`。
- `scripts/dev/run_ui_pytest.sh tests/unit/ui -q` 通過，`807 passed`。
- `poetry run pytest --capture=sys tests/integration/backend/test_application_service_workflow.py -q` 通過，`2 passed`。
- `poetry run mkdocs build --strict` 通過。
- `git diff --check` 通過。

### 剩餘風險

- UI execution path 仍大量直接呼叫 controllers；目前完成的是 readiness / blocked reason 統一，
  不是完整 service-first UI migration。
- Real tools 還是透過 `BackendFacade` 舊字串回傳；conversation history 已保留 structured
  output，但 tool 本身尚未全面回傳 `CommandResult`。
- UI side effects 仍靠 `Request:` 字串協定，尚未 typed request/event 化。
- `evaluate`、`visualize`、`saliency`、`new_session` 仍是 disabled future command。

## 2026-05-02 Backend Application Service contract 收斂

### 背景

前一輪已新增 `XBrainLab/backend/application/`，但第二輪驗收發現 command
contract 還有不一致：部分 `CommandName` 有 policy entry，但沒有 command object 或
execute handler；`set_montage` 在 service 內回成功訊息但實際仍需 UI confirmation；
`reset_session` 只清資料與 trainer，尚未明確清掉 training config。

### 變更

- 補齊 future command objects：
  - `EvaluateCommand`
  - `VisualizeCommand`
  - `SaliencyCommand`
  - `NewSessionCommand`
- `CapabilityPolicy` 將 `evaluate`、`visualize`、`saliency`、`new_session` 標成
  unavailable future contract，不再宣稱可執行。
- `ApplicationService.execute()` 對未實作但保留的 command 回穩定 failure，不再可能因
  handler table 缺漏變成 `KeyError`。
- `set_montage` preprocess operation 改回 confirmation-required failure；實際 montage
  auto-match 仍留在 `BackendFacade` legacy path。
- `reset_session` 補 active session invalidation：除了 raw / preprocess / epoch /
  dataset / trainer，也清掉 model holder、training option 和 saliency params。
- `BackendFacade.load_data()` 在 total failure 時保留舊 `(count, errors)` raw error list
  shape；`stop_training()` inactive no-op 不再依賴錯誤訊息字串。
- 補強 tests：
  - command/policy coverage
  - future command stable failure
  - last_error lifecycle
  - reset confirmation and invalidation
  - training readiness capability transition
  - facade failure-shape / legacy montage / run-training precondition parity

### 影響範圍

- backend application command contract
- capability policy
- backend state snapshot / reset semantics
- `BackendFacade` compatibility surface
- backend application and facade tests
- backend architecture / planning docs

### 驗證

- `poetry run ruff check XBrainLab/backend/application XBrainLab/backend/facade.py tests/unit/backend/application tests/integration/backend/test_application_service_workflow.py tests/unit/backend/test_facade_coverage.py tests/unit/backend/test_facade_headless.py` 通過。
- `poetry run basedpyright XBrainLab/backend/application XBrainLab/backend/facade.py` 通過。
- `poetry run pytest --capture=sys tests/unit/backend/application tests/integration/backend/test_application_service_workflow.py tests/unit/backend/test_facade_coverage.py tests/unit/backend/test_facade_headless.py -q` 通過，`54 passed`。
- `poetry run pytest --capture=sys tests/unit/backend -q` 通過，`2660 passed, 1 skipped, 1 xfailed`。
- `poetry run pytest --capture=sys tests/integration/backend tests/integration/io/test_io_integration.py -q` 通過，`33 passed`。
- `poetry run pytest --capture=sys tests/integration/pipeline -q` 通過，`70 passed`。
- `poetry run mkdocs build --strict` 通過。
- `git diff --check` 通過。
- `poetry run python scripts/dev/update_quality_dashboard.py` 通過，`artifacts/quality/latest.md` 更新為 `PASS`。

### 剩餘風險

- UI 仍直接使用 controllers，尚未 service-first。
- `evaluate`、`visualize`、`saliency`、`new_session` 是明確 disabled 的 future contract，
  尚未實作 query/command behavior。
- `set_montage()` 仍是 `BackendFacade` legacy path。
- facade/controller parity 還需要更多 real workflow tests，尤其是 UI controller path。
- agent real tools 仍格式化 facade 舊回傳值，尚未直接消費 `CommandResult`。

## 2026-05-01 Backend Application Service / Command API 第一版

### 背景

後端在接手時已拆出 `DataManager` 和 `TrainingManager`，但 UI、assistant tools、
headless scripts 仍分別繞 controllers / `BackendFacade`。使用者確認本輪要實質推進
後端重構，方向是 UI / Agent / Script 共用 Application Service / Command API，
且 `BackendFacade` 只能作 wrapper，不能變成新的大泥球。

### 變更

- 新增 `XBrainLab/backend/application/`：
  - `commands.py`
  - `state.py`
  - `capabilities.py`
  - `results.py`
  - `errors.py`
  - `service.py`
- `ApplicationService` 提供：
  - state snapshot
  - backend-owned capability policy
  - command result envelope
  - application error boundary
  - command execution for load / attach labels / preprocess / epoch / dataset /
    training config / train / stop / reset
- `BackendFacade` 改成包 `ApplicationService`：
  - 保留舊方法名稱與舊回傳形狀，供 assistant real tools / scripts 相容。
  - 核心 workflow 不再在 facade 內重新拼裝。
- 修正 `RealListFilesTool` 在 WSL/Linux 下把不存在的 Windows fallback path
  resolve 成 repo root，導致 `tests/data` 被誤判成敏感路徑的問題。
- 補測試：
  - `tests/unit/backend/application/test_application_service.py`
  - `tests/integration/backend/test_application_service_workflow.py`
  - 更新 facade unit tests，對齊 service wrapper 行為。

### 影響範圍

- backend application layer
- agent/headless facade path
- command/capability/state contract
- backend unit and integration tests
- backend architecture / planning docs

### 驗證

- `poetry run ruff check XBrainLab/backend/application XBrainLab/backend/facade.py tests/unit/backend/application tests/integration/backend/test_application_service_workflow.py tests/unit/backend/test_facade_coverage.py tests/unit/backend/test_facade_headless.py` 通過。
- `poetry run basedpyright XBrainLab/backend/application XBrainLab/backend/facade.py` 通過。
- `poetry run pytest --capture=sys tests/unit/backend/application tests/integration/backend/test_application_service_workflow.py -q` 通過，`4 passed`。
- `poetry run pytest --capture=sys tests/unit/backend/test_facade_coverage.py tests/unit/backend/test_facade_headless.py -q` 通過，`40 passed`。
- `poetry run pytest --capture=sys tests/unit/backend -q` 通過，`2651 passed, 1 skipped, 1 xfailed`。
- `poetry run pytest --capture=sys tests/integration/backend/test_application_service_workflow.py tests/integration/io/test_io_integration.py -q` 通過，`32 passed`。
- `poetry run pytest --capture=sys tests/integration/pipeline -q` 通過，`70 passed`。
- `poetry run mkdocs build --strict` 通過。
- `git diff --check` 通過。
- `poetry run python scripts/dev/update_quality_dashboard.py` 通過，`artifacts/quality/latest.md` 更新為 `PASS`。

### 剩餘風險

- UI 仍直接使用 controllers，尚未改成 service-first。
- `set_montage()` 仍是 `BackendFacade` legacy path，因為它牽涉 UI confirmation。
- agent real tools 仍格式化 facade 舊回傳值，尚未直接消費 `CommandResult`。
- state invalidation、training readiness、facade/controller parity 還需要更多 real workflow tests。

## 2026-05-01 Documentation audit 收束

### 背景

`docs/records/documentation_audit.md` 是文件整理初期用來判斷可信度的過渡表。文件已重排成 current、target、architecture、planning、decisions、validation、records 後，這份 audit 會變成額外維護成本。

### 變更

- 刪除 `docs/records/documentation_audit.md`。
- 從 `README.md`、`docs/current.md`、`mkdocs.yml` 移除 active 入口。
- 從 `.agents/runbooks/setup.md` 和 `.agents/runbooks/autopilot.md` 移除對 audit 檔的依賴。
- 將文件可信度責任併回各 canonical 文件：現況寫 `current.md`，架構證據寫 `architecture/`，驗證邊界寫 `validation/README.md`，決策寫 `decisions/README.md`。

### 影響範圍

- 文件站 navigation
- repo root 入口
- agent reading order
- records 資料夾定位

### 驗證

- `poetry run mkdocs build --strict` 通過。
- `git diff --check -- README.md CHANGELOG.md AGENTS.md .agents docs mkdocs.yml` 通過。
- active stale reference scan 通過：排除 `docs/records/**` 後，沒有文件再引用 `documentation_audit` 或 `records/documentation_audit`。

## 2026-05-01 API / Gemini 移除決策校準

### 背景

文件原本把 API / Gemini code path 描述成待簡化或舊相容路徑。使用者確認這不是要保留的相容路徑，而是後續要拔掉的範圍。

### 變更

- 更新 `current.md`、`index.md`、`operations.md`、`decisions/README.md`。
- 更新 `planning/roadmap.md`、`planning/now.md` 和 `.agents/runbooks/active-queue.md`。
- 更新 `architecture/README.md`、`architecture/agent.md`、`architecture/validation.md`、`validation/README.md`。
- 更新 `.agents/context/project.md` 和 `.agents/runbooks/architecture-review.md`。

### 影響範圍

- assistant runtime 目標
- agent 架構複盤 checklist
- 後續 agent runtime 簡化範圍
- validation 目標邊界

### 驗證

- `poetry run mkdocs build --strict` 通過。
- `git diff --check -- docs .agents README.md CHANGELOG.md mkdocs.yml AGENTS.md` 通過。
- active wording scan 通過：active 文件已沒有 `移除或降級`、`legacy compatibility`、`compatibility path`、`待簡化殘留` 等會誤導成保留相容路線的說法。

## 2026-05-01 Target requirements 補 XBrainLab 本體

### 背景

`docs/target/requirements.md` 原本太快進入 assistant、command API 和 thesis validation，對 XBrainLab 本體作為本地 EEG 桌面分析工具的描述不足。

### 變更

- 補強產品定位：XBrainLab 的核心是本地 EEG workflow，不是聊天或模型 demo。
- 新增主要使用者描述。
- 新增 EEG workflow 本體需求。
- 新增桌面應用體驗、資料與狀態可追蹤、訓練與評估、視覺化與解釋需求。
- 將 assistant 放回 workflow 操作層，明確說明沒有 agent 時核心 EEG workflow 仍應可用。
- 修正 `target/README.md` 中 API / Gemini 殘留說法，對齊後續移除決策。

### 影響範圍

- target requirements
- target overview
- 後續全盤架構複盤的產品需求基準

### 驗證

- `poetry run mkdocs build --strict` 通過。
- `git diff --check -- docs/target docs/records/implementation_log.md docs/records/worklog.md` 通過。
- target wording scan 確認 `requirements.md` 已包含 EEG workflow、資料匯入、訓練與評估、視覺化、本地桌面 app、assistant 非唯一入口等本體需求。

## 2026-05-01 Target agent 補 State Manager / Verification Layer

### 背景

`docs/target/agent.md` 原本有寫 tool-call validation，但沒有把使用者設計的 Context Assembler、Prompt components、State Manager、Verification Layer、Self-Correction loop 明確記錄下來。

### 變更

- 新增 target control loop Mermaid 圖。
- 補 Context Assembler 的輸入：system prompt、tool definitions、RAG context、memory、state snapshot。
- 補 State Manager 的目標責任：workflow stage、data state、training state、command availability、recent tool result。
- 補 Verification Layer 的執行前檢查與失敗回饋。
- 補 tool schema 應標示 input、required state、side effect、result、error、confirmation。

### 影響範圍

- target agent 設計
- tool-call validation 目標
- 後續 agent runtime / command API 設計

### 驗證

- `poetry run mkdocs build --strict` 通過。
- `git diff --check -- docs/target/agent.md docs/records/implementation_log.md docs/records/worklog.md` 通過。
- target agent wording scan 確認 `Context Assembler`、`State Manager`、`Verification Layer`、`Self-Correction` 和 tool contract 欄位已寫入。

## 2026-05-01 Thesis evidence 改成 tool-call scoring system

### 背景

`docs/target/requirements.md` 原本只說 thesis evidence 要對到 command、test、artifact 或 experiment。使用者指出 thesis evidence 應該具體建立一套評分 agent tool-call 準確率的工具，並用它測試。

### 變更

- 更新 `target/requirements.md`，將 thesis evidence 改成 agent tool-call 評分工具與 benchmark report。
- 更新 `target/agent.md`，補 tool-call scoring system 的分項指標、case 類型與 thesis 邊界。
- 更新 `validation/README.md`，新增 Agent Tool-Call Scoring 區塊。
- 明確標示舊 `scripts/agent/benchmarks/*` 只能作歷史參考，新的 thesis evidence 要對齊 local-only runtime、State Manager、Verification Layer 和未來 Command API。

### 影響範圍

- thesis evidence 定義
- agent validation 目標
- 後續 benchmark / scorer 工具設計

### 驗證

- `poetry run mkdocs build --strict` 通過。
- `git diff --check -- docs/target/requirements.md docs/target/agent.md docs/validation/README.md docs/records/implementation_log.md docs/records/worklog.md` 通過。
- scoring wording scan 確認 `tool-call scoring system`、`benchmark cases`、`accuracy`、`score report`、`failure taxonomy` 已寫入 target / validation 文件。

## 2026-05-01 Target agent 補四個 contract 外框

### 背景

使用者確認 agent 目標應再定仔細一點，但不要把每個 tool schema 寫爆。需要先定能支撐後續實作與 thesis scoring 的 contract 外框。

### 變更

- 在 `docs/target/agent.md` 新增 Target contracts。
- 補 State Snapshot Contract。
- 補 Tool Call Contract。
- 補 Verification Result Contract。
- 補 Scoring Contract。
- 更新 backend / agent 重構順序，加入四個 contract schema 的第一版定義。

### 影響範圍

- agent target design
- State Manager / Verification Layer
- thesis tool-call scoring
- 後續 Command API schema 設計

### 驗證

- `poetry run mkdocs build --strict` 通過。
- `git diff --check -- docs/target/agent.md docs/records/implementation_log.md docs/records/worklog.md` 通過。
- contract wording scan 確認 State Snapshot、Tool Call、Verification Result、Scoring 四個 contract 已寫入。

## 2026-05-01 Command gate 與多資源 workflow 校準

### 背景

使用者指出 `available_commands` 不應只是把所有 tool 和可選 tool 丟給 agent，讓 agent 自己決定。更合理的是 backend / Application Service 根據目前狀態產生 capability policy。使用者也指出 workflow 不能假設成單一路徑：第一筆資料 train 完後，可能同時看 visualization / saliency，或開始下一筆資料的 training。

### 變更

- 更新 `docs/target/agent.md`：
  - `available_commands` 改成 backend capability policy 的輸出。
  - State Snapshot 補 `capability_policy`、`active_jobs`、`completed_runs`。
  - 補 workflow state 不應是單一路徑，而應以 resources / jobs / results 為核心。
  - Tool Call / Verification / Scoring contract 補 target resource 與 policy source。
- 更新 `docs/target/architecture.md`：
  - Command API 需提供 backend-controlled capability policy。
  - 目標 workflow 需支援多資源 / 多任務狀態。
- 更新 `docs/architecture/agent.md`：
  - 標明目前 stage gate 是現況限制，不足以描述多 run / visualization / 下一筆 training 並行情境。

### 影響範圍

- target agent state model
- Application Service / Command API target
- tool availability / verification 設計
- 後續多資料、多 run、visualization / saliency workflow

### 驗證

- `poetry run mkdocs build --strict` 通過。
- `git diff --check -- docs/target/agent.md docs/target/architecture.md docs/architecture/agent.md docs/records/implementation_log.md docs/records/worklog.md` 通過。
- capability wording scan 確認 capability policy、active jobs、completed runs、target resource、policy source、多資源 / 多任務狀態已寫入。

## 2026-05-01 多資源不等於任意並行

### 背景

前一版文字容易讓人誤解成支援多資源 / 多任務後，每個 tool 都可以並行。使用者指出 load data 前不能 run train，command 仍必須受前置條件控制。

### 變更

- 更新 `docs/target/agent.md`，補 dependency gate：
  - 沒 loaded data 不能 preprocess。
  - 沒 label / event 對齊，不能產生可信 dataset。
  - 沒 dataset 不能 training。
  - 沒 trained result 不能 saliency / model-based visualization。
  - long-running job 寫入某 resource 時，不能同時對同一 resource 做破壞性操作。
- 更新 `docs/target/architecture.md` 和 `docs/architecture/agent.md`，明確區分多資源共存與任意並行。

### 影響範圍

- capability policy
- target state model
- command dependency gate
- agent verification rule

### 驗證

- `poetry run mkdocs build --strict` 通過。
- `git diff --check -- docs/target/agent.md docs/target/architecture.md docs/architecture/agent.md docs/records/implementation_log.md docs/records/worklog.md` 通過。
- dependency wording scan 確認沒有 loaded data / dataset / trained result 時的禁止條件已寫入。

## 2026-05-01 Active dataset pipeline 邊界校準

### 背景

前一版文字仍可能被理解成 XBrainLab 目標要同時開多個 dataset。使用者指出一次只能開一個 dataset，epoch 後不該讓 agent 開新的資料集。

### 變更

- 更新 `docs/target/agent.md`：
  - State Snapshot 改成一個 active dataset pipeline。
  - 多資源說法改成同一 dataset 上的多個 training run / evaluation / visualization result。
  - epoch / dataset 形成後，`load_data` / 開新 dataset 不應是一般 available command。
  - 若要載入新資料，必須走 reset / new session / fork 類高風險 command，且需要使用者確認。
- 更新 `docs/target/architecture.md` 和 `docs/architecture/agent.md`，同步 active dataset pipeline 邊界。

### 影響範圍

- state model
- capability policy
- load data / generate dataset command gate
- reset / new session / fork 邊界

### 驗證

- `poetry run mkdocs build --strict` 通過。
- `git diff --check -- docs/target/agent.md docs/target/architecture.md docs/architecture/agent.md docs/records/implementation_log.md docs/records/worklog.md` 通過。
- active dataset wording scan 確認一個 active dataset pipeline、epoch / dataset 後阻擋一般 load new data、reset / new session / fork 高風險邊界已寫入。

## 2026-05-01 blocked commands 定位

### 背景

使用者詢問 `blocked_commands` 是否需要。結論是保留，但不應完整餵給 LLM。它主要用於 verifier、scorer、debug 和 UI 診斷；Context Assembler 只在與當前 user intent 相關時摘要 blocked reason。

### 變更

- 更新 `docs/target/agent.md`：
  - `blocked_commands` 定位為 Verification Layer、scorer、debug、UI diagnostics 使用。
  - 明確寫出完整 blocked list 不應直接塞進 LLM prompt。
  - Context Assembler 只摘要和當前 user intent 相關的 blocked reason。

### 影響範圍

- State Snapshot Contract
- Context Assembler
- Verification Layer
- Scoring / debug report

### 驗證

- `poetry run mkdocs build --strict` 通過。
- `git diff --check -- docs/target/agent.md docs/records/implementation_log.md docs/records/worklog.md` 通過。
- blocked command wording scan 確認完整 blocked list 不直接塞給 LLM、只摘要相關 blocked reason 的邊界已寫入。

## 2026-05-01 .agents skills / workflows 第一版

### 背景

使用者指出目前 `.agents` 設計仍不滿意，缺少 skill / workflow。現有 `.agents` 主要是 runbooks 和 context，還不像可重用 agent operating layer。

### 變更

- 新增 `.agents/skills/README.md`。
- 新增五個 repo-local skills：
  - `docs-curator`
  - `architecture-reviewer`
  - `validation-runner`
  - `refactor-slicer`
  - `agent-toolcall-designer`
- 新增 `.agents/workflows/README.md`。
- 新增四個 workflows：
  - `documentation-review.md`
  - `architecture-review.md`
  - `refactor-slice.md`
  - `agent-toolcall-scoring.md`
- 更新 `.agents/README.md`、`.agents/stack.md`、setup / autopilot / active queue。

### 影響範圍

- agent 操作入口
- reusable skills
- multi-step workflows
- 後續架構複盤與重構開工流程

### 驗證

- `poetry run mkdocs build --strict` 通過。
- `git diff --check -- .agents docs/records/implementation_log.md docs/records/worklog.md` 通過。
- agent skill/workflow scan 確認 TDD、test-quality、code-review、software-design skills，以及 `tdd-change` / `test-audit` workflows 已寫入。
- context scan 確認 `.agents/context/*` 已標示為導讀，不保存 current / target / architecture 的第二份 truth。

## 2026-05-01 .agents 工程 workflow skill pack 校準

### 背景

使用者補充希望 skills 參考 TDD、軟體設計、測試品質等已被實際使用過的 workflow，而不是只由本專案即興發明。使用者也指出 context 可能和 architecture 產生多個 truth。

### 變更

- 新增工程 workflow skills：
  - `tdd-guard`
  - `test-quality-reviewer`
  - `code-reviewer`
  - `software-design-reviewer`
- 新增 workflows：
  - `tdd-change.md`
  - `test-audit.md`
- 更新 `refactor-slice.md` 和 `architecture-review.md`，串接新的工程 skills。
- 更新 `.agents/skills/README.md`，標出 skills 參考 OpenAI / Codex skill-creator、GitHub Copilot best practices、Claude Code workflows / best practices 與社群 TDD 經驗。
- 將 `.agents/context/*` 降級成導讀，不保存完整 architecture truth。

### 影響範圍

- repo-local skills
- repo-local workflows
- context source-of-truth 邊界
- 後續 TDD / refactor / test audit 工作流

### 驗證

- 待本輪 final validation 補記。

## 2026-05-01 Workspace 搬遷與文件可信度稽核

### 背景

XBrainLab 原本位於 `/mnt/d/repos/XBrainLab`。為了納入目前的 `workspace_v2/projects` 結構，將 active repo 搬到：

- `/mnt/d/workspace_v2/projects/lab/XBrainLab`

### 變更

- 使用 `rsync` 完整複製 repo 到新 workspace。
- 舊路徑因 Windows 拒絕 rename / move，所以保留為備援副本。
- 新增 repo 內文件可信度稽核：
  - `docs/records/documentation_audit.md`
- 開始建立新的 canonical docs 架構。

### 影響範圍

- workspace path
- documentation entry points
- quality dashboard path assumptions
- Poetry virtualenv selection

### 驗證

- `git rev-parse --show-toplevel` 顯示新 active path。
- branch 保持 `codex/stabilization-autopilot`。
- remote 保持 `https://github.com/hxin-an/XBrainLab.git`。
- `rsync --dry-run` 沒列出新舊差異。
- `poetry check` exit 0，但有 metadata deprecation warnings。
- `poetry install --with dev,test,docs` 已在新 workspace env 完成。
- import probe 已通過 `PIL`、`mne`、`PyQt6`、`torch`、`pytest`、`XBrainLab`。
- `poetry run mkdocs build --strict` 通過。

### 剩餘風險

- 舊文件裡仍有大量舊絕對路徑；後續已把 `docs/legacy/` 從 repo 閱讀面移除。
- optional `llm` dependency group 尚未納入這輪標準驗證，`torchinfo` 仍未安裝。
- 舊文件中仍有大量 `/mnt/d/repos/XBrainLab` 絕對路徑。

## 2026-05-01 Runtime 驗證與 UI test 修正

### 背景

搬到新 workspace 後，需要重新建立今天的 runtime evidence。第一次 dashboard refresh 顯示兩個 UI unit failure 和一個 UI baseline reference mismatch。

### 變更

- 修正 `tests/unit/ui/test_model_summary.py`：
  - 用 fake `torchinfo` module 測 lazy optional dependency 行為。
  - 避免標準 `dev,test` 環境被 optional `llm` dependency group 綁住。
- 修正 `tests/unit/ui/test_ui_misc.py`：
  - 將 `AgentManager.set_model("Gemini")` 的 expectation 改成 runtime mode key `gemini`。
  - 這和 `LLMConfig.normalize_backend_mode()`、`ChatPanel._set_model()` 目前行為一致。

### 影響範圍

- UI unit tests
- agent manager model mode normalization
- quality dashboard evidence
- active 文件狀態

### 驗證

- targeted UI tests：
  - `2 passed`
- fast quality dashboard：
  - generated at `2026-05-01 19:16:09 UTC+08:00`
  - workspace `/mnt/d/workspace_v2/projects/lab/XBrainLab`
  - Ruff Lint `PASS`
  - Basedpyright `PASS`
  - Architecture Compliance `PASS`
  - Startup Smoke `PASS`
  - UI Dialog Acceptance `PASS`
  - UI Unit Suite `PASS` (`799 passed`)
  - Real-Data IO Integration `PASS` (`31 passed`)
- docs build：
  - `poetry run mkdocs build --strict` 通過。

### 剩餘風險

- `llm` optional group 沒納入這輪，因此不要把 local LLM / transformer / `torchinfo` runtime 說成已驗證。

## 2026-05-01 UI baseline 決策與 clean dashboard

### 背景

fast dashboard 第二次刷新後只剩 `ai-assistant-open.png` baseline mismatch。live artifact 和 repo HEAD reference 都是 `(1428, 800)`，但 dirty worktree reference 是 `(1523, 800)`。

### 變更

- 接受 `(1428, 800)` 作為 `tests/baselines/ui/ai-assistant-open.png` 的 approved baseline。
- 重新刷新 fast quality dashboard。
- 將 clean dashboard 判定規則寫入 `validation/README.md`。

### 影響範圍

- UI baseline reference
- quality dashboard artifact
- active validation 文件

### 驗證

- fast quality dashboard：
  - generated at `2026-05-01 19:28:48 UTC+08:00`
  - overall `PASS`
  - 所有 checks 都是 `pass`
  - UI Baseline Capture `PASS`
  - UI Unit Suite `PASS` (`799 passed`)
  - Real-Data IO Integration `PASS` (`31 passed`)

### 剩餘風險

- clean dashboard 仍只是 fast engineering health gate。
- optional `llm` group、local LLM runtime、完整 thesis validation 尚未完成。

## 2026-05-01 Roadmap 與 pipeline validation 分層

### 背景

fast dashboard clean 後，下一個問題是完整 pipeline 是否可信，以及路線規劃要放在哪裡才不會讓文件膨脹。

### 變更

- 新增 `docs/planning/roadmap.md`。
- 在 `validation/README.md` 補上 pipeline validation 分層：
  - fast dashboard
  - tiny E2E pipeline smoke
  - public fixture pipeline smoke
  - scientific validation
- 對齊 `/mnt/d/workspace_v2/core/lab/meetings/progress/reports/2026-04-26.md` 的 To Do List：
  - GUI 重構
  - 建立新 Agent 架構
  - 後端重構
  - 穩定化
  - tool call 驗證
  - 優化迭代
- 在 `records/worklog.md` 補上 pipeline smoke 抽樣紀錄。

### 影響範圍

- active 文件入口
- MkDocs nav
- validation evidence taxonomy

### 驗證

- targeted pipeline smoke：
  - `tests/integration/pipeline/test_full_pipeline.py::TestFullPipeline::test_train_and_evaluate_metrics`
  - `tests/integration/pipeline/test_study_training_e2e.py::TestStudyTrainCycle::test_full_cycle_eegnet`
  - 結果：`2 passed in 7.54s`

### 剩餘風險

- tiny pipeline smoke 目前還沒有納入 fast dashboard。
- public cross-source training smoke 和 scientific reproducibility 還沒在本輪驗證。
- repo legacy status 仍可作輔助脈絡，但 active roadmap 以 2026-04-26 會議進度報告為主要來源。

## 2026-05-01 Agent 架構文件與 local-only runtime 決策

### 背景

agent 文件原本只描述高層方向，沒有清楚說明目前 UI、controller、worker、tool、backend 之間的實際接線。整理時也確認新的產品方向要簡化為 local-only assistant，不再把 API / Gemini 當成未來目標。

### 變更

- 重寫 `docs/architecture/agent.md`：
  - 記錄目前實際路徑是 UI -> AgentManager -> LLMController -> Worker / Parser / Verifier / Tools -> BackendFacade -> Study。
  - 標記目前是可工作的中間狀態，不是最終架構。
  - 將未來目標改成 local-only runtime + shared Application Service / Command API。
- 更新 `docs/decisions/README.md`：
  - 新增 `assistant runtime local-only`。
- 更新 `docs/validation/README.md`：
  - agent runtime 後續只驗證 local model、optional `llm` group、GPU/CPU fallback、local tool-call output。
- 對齊兩個 agent unit test：
  - `LLMController.set_model("Gemini")` 目前會 normalize 成 `gemini`。
  - `AgentWorker.generate_from_messages()` 的 thread 啟動測試明確 mock local backend ready，避免被本機 optional `llm` dependency 缺失影響。

### 影響範圍

- agent architecture 文件
- active decisions
- validation strategy
- agent unit tests

### 驗證

- docs build：
  - `poetry run mkdocs build --strict` 通過。
- targeted agent tests：
  - `poetry run pytest --capture=sys tests/unit/llm/test_pipeline_state.py tests/unit/llm/agent/test_controller.py tests/unit/llm/agent/test_worker.py tests/unit/llm/tools/real/test_real_tools.py tests/unit/ui/components/test_agent_manager.py tests/unit/ui/chat/test_chat_panel.py -q`
  - 結果：`157 passed in 7.61s`

### 剩餘風險

- 程式碼目前仍保留 API / Gemini runtime，尚未移除。
- optional `llm` group、本地模型 cache、GPU readiness 尚未完成 runtime 驗證。
- RAG 品質和真實多步 tool-call workflow 尚未驗證。

## 2026-05-01 Active / Architecture 文件校準

### 背景

使用者希望先把文件整理完，再 review，接著清 legacy 文件；後端與 agent 實作先不開工。

### 變更

- 重寫 / 校準 active 入口：
  - `docs/current.md`
  - `docs/operations.md`
- 校準 architecture 入口與剩餘架構文件：
  - `docs/architecture/README.md`
  - `docs/architecture/ui.md`
  - `docs/architecture/validation.md`
- 更新總入口與可信度稽核：
  - `docs/index.md`
  - `docs/planning/roadmap.md`
  - `docs/records/documentation_audit.md`

### 影響範圍

- 文件閱讀順序
- 操作指令入口
- UI 架構說明
- validation architecture
- legacy cleanup 前的 canonical 文件基準

### 驗證

- 各 sub-agent 分別跑過 `poetry run mkdocs build --strict`。
- 主流程最後再跑一次總 `poetry run mkdocs build --strict`，結果通過。
- `git diff --check` 針對本輪文件變更通過。

### 剩餘風險

- legacy 文件尚未清理。
- `ui.md` 已對照主要 UI wiring，但尚未逐一審所有 dialog。
- 後端重構還沒開始；目前文件只描述現況與目標。

## 2026-05-01 Docs / agent legacy 刪除與 test mock 邊界

### 背景

使用者確認 legacy cleanup 的目標不是永久保留短期快照，而是把有用內容整合到目前文件系統後刪除。多數 legacy 文件只是近兩天 AI / agent 工作產物，不應繼續污染閱讀面。

同時，使用者追問 test 是否 mock 太多、能不能真的測到問題。

### 變更

- 刪除 `docs/legacy/current/`、`decisions/`、`workflows/`、`guides/`、`api/`、`thesis/`、`history/`。
- 從 MkDocs nav 移除 deleted legacy sections。
- 更新 `docs/legacy/README.md`，改成「整合後刪除」策略。
- 更新 active audit，將非 archive legacy 標記為 `deleted-after-integration`。
- 刪除 `.agents/legacy/` 舊 role、skill、AQ queue、workflow、multi-session prompt。
- 更新 `AGENTS.md`、`.agents/stack.md`、`.agents/runbooks/*`，讓 agent 入口不再指向 `.agents/legacy/`。
- 在 `validation/README.md` 和 `validation.md` 補上 mock-heavy test 邊界。

### 影響範圍

- legacy 文件結構
- agent 操作層
- MkDocs nav
- validation 文件
- 文件可信度 audit

### 驗證

- `poetry run mkdocs build --strict` 通過。

### 剩餘風險

- mock-heavy tests 仍是現況；文件已標出邊界，但測試結構尚未改。

## 2026-05-01 Docs legacy archive 收掉

### 背景

使用者決定連 `docs/legacy/archive/` 也不要留在目前文件站，避免新文件和舊設計混在一起。

### 變更

- 刪除整個 `docs/legacy/`。
- 從 `mkdocs.yml` 移除 Legacy nav。
- 更新 `README.md`、`AGENTS.md`、`.agents/stack.md`、canonical docs、architecture 入口和 audit。

### 影響範圍

- 文件站 navigation
- repo 文件入口
- agent reading order
- 文件可信度 audit

### 驗證

- `poetry run mkdocs build --strict` 通過。
- `git diff --check -- AGENTS.md .agents README.md docs mkdocs.yml` 通過。
- stale link scan 沒有 active nav / markdown link 指回 `docs/legacy/`。

### 剩餘風險

- mock-heavy tests 仍是現況；文件已標出邊界，但測試結構尚未改。

## 2026-05-01 Active folder 收掉

### 背景

使用者決定 `docs/active/` 這一層也不需要保留。canonical 文件直接放在 `docs/` 根層，避免文件入口被資料夾層級切得太碎。

### 變更

- 將 `current.md`、`planning/roadmap.md`、`validation/README.md`、`operations.md`、`decisions/README.md`、`records/documentation_audit.md`、`records/implementation_log.md`、`records/worklog.md` 從 `docs/active/` 移到 `docs/`。
- 刪除 `docs/active/README.md`。
- 更新 `mkdocs.yml`，將 nav 從 Active 改成 Core。
- 更新 `README.md`、`AGENTS.md`、`.agents/*`、`docs/index.md`、architecture 文件中的路徑。

### 影響範圍

- 文件站 navigation
- repo 文件入口
- agent reading order
- thesis context links

### 驗證

- `poetry run mkdocs build --strict` 通過。
- `git diff --check -- AGENTS.md .agents README.md docs mkdocs.yml` 通過。
- `test ! -e docs/active`、`test ! -e docs/legacy`、`test ! -e .agents/legacy` 通過。
- stale path scan 沒有 active markdown link 指向已刪除資料夾。

## 2026-05-01 Root homepage 文件收斂

### 背景

root README 仍列出 root `ROADMAP.md` 和 `CHANGELOG.md`，但 root `ROADMAP.md` 是舊 Track A/B 大計畫，和現在的 `docs/planning/roadmap.md` 衝突。

### 變更

- 刪除 root `ROADMAP.md`。
- 更新 `README.md`，改指向 `docs/planning/roadmap.md`。
- 更新 `CHANGELOG.md` 開頭，標明它只保留歷史版本紀錄，現況、路線、接手後工程紀錄以 `docs/*` canonical 文件為準。
- 更新 `records/documentation_audit.md` 和 `current.md`。

### 影響範圍

- GitHub root homepage
- roadmap source-of-truth
- historical changelog framing

### 驗證

- `test ! -e ROADMAP.md` 通過。
- `poetry run mkdocs build --strict` 通過。
- `git diff --check -- README.md CHANGELOG.md planning/roadmap.md AGENTS.md .agents docs mkdocs.yml` 通過。

## 2026-05-01 文件資訊架構第一版

### 背景

使用者指出文件仍然擠在同一層，短期、長期、決策、紀錄、需求與理想架構混在一起。需要重新建立文件資訊架構，並補 `.agents` 的操作文件。

### 變更

- 將 docs 重排為：
  - `current.md`
  - `operations.md`
  - `target/`
  - `architecture/`
  - `planning/`
  - `decisions/`
  - `validation/`
  - `records/`
- 新增 `docs/target/README.md`、`requirements.md`、`architecture.md`、`agent.md`。
- 新增 `docs/planning/now.md`，並將 roadmap 移到 `docs/planning/roadmap.md`。
- 將 decisions、validation、implementation log、worklog、documentation audit 移入對應資料夾。
- 將 `architecture/validation_architecture.md` 改名為 `architecture/validation.md`。
- 新增 `.agents/README.md`、`.agents/context/project.md`、`.agents/context/architecture-target.md`。
- 新增 `.agents/runbooks/architecture-review.md`、`.agents/runbooks/refactor-gate.md`。
- 更新 `README.md`、`AGENTS.md`、`.agents/*`、`mkdocs.yml` 和文件連結。

### 影響範圍

- 文件站 navigation
- 文件 source-of-truth
- agent reading order
- 後續架構複盤流程

### 驗證

- `poetry run mkdocs build --strict` 通過。
- `git diff --check -- README.md CHANGELOG.md AGENTS.md .agents docs mkdocs.yml` 通過。
- stale path scan 沒有 active markdown link 指向舊大寫 canonical 檔名、`docs/active/`、`docs/legacy/` 或 `validation_architecture.md`。

## 2026-05-02 Product delivery stabilization slice

### 背景

使用者要求把 partial assistant fix 往可直接使用的桌面產品收斂。人工驗收指出 AI
Assistant 仍像 developer/debug dock，raw command names 污染主 UI，user bubble 會吃掉
最後一個字，且缺少真正從 UI button path 走 pipeline 的 product E2E evidence。

### 變更

- Assistant product UI：
  - 新增 `XBrainLab/ui/product_language.py`，集中 stage、command、runtime、mode 的使用者語言。
  - ChatPanel header 改成 `XBrainLab Assistant` + workflow guidance + compact readable badges。
  - Retry / Clear / Stop / Settings 從說明文字旁拆成 controls。
  - `Coder / Local / Multi` 重新表達為 `Workflow guide`、`Local model`、`Single step`、`Auto steps`。
  - 第一層 UI 移除 `load_data`、`configure_training`、`reset_session` 這類 raw command name；
    raw diagnostics 只放 tooltip / advanced details。
  - 修正 message bubble padding、max width、right margin、word wrap，避免 user bubble 截字。
- Backend / UI alignment：
  - `XBrainLab/ui/application_capabilities.py` 新增 `execute_application_command(...)`。
  - Dataset import 走 `LoadDataCommand`。
  - Dataset reset / clear 走 `ResetSessionCommand(confirmed=True)`。
  - Preprocess filter / resample / rereference / normalize 走 `PreprocessCommand`。
  - Epoching 走 `CreateEpochCommand`。
  - Training start / stop 走 `TrainCommand` / `StopTrainingCommand`。
  - mock / incomplete `Study` 保留 controller fallback，避免測試假物件誤觸 service contract。
- Agent alignment：
  - `XBrainLab/llm/tools/application_surface.py` 新增 direct command execution helper。
  - `LLMController._execute_tool_no_loop()` 先嘗試 mapped ApplicationService command，再 fallback real tool。
  - `attach_labels`、preprocess tools、`epoch_data`、`generate_dataset`、`set_model`、
    `configure_training`、`start_training`、`clear_dataset` 可直接回 structured
    `ToolCommandResult.from_command_result(...)`。
  - `load_data` 仍保留 directory expansion / safety legacy path；`set_montage`、`switch_panel`
    仍保留 UI request path。
- Product validation：
  - 新增 `tests/integration/ui/test_product_walkthrough.py`。
  - `test_assistant_product_click_through_layout` 覆蓋 assistant header/status/control row、
    command diagnostics、message bubble、composer、panel navigation。
  - `test_pipeline_product_walkthrough_uses_user_facing_actions` 用 synthetic FIF 走 Dataset import
    button、Preprocess filter、epoching、Training split/model/settings、dry-run Start Training、
    Evaluation result-ready 狀態。
- Docs：
  - 更新 current、planning、backend/ui/agent/validation architecture、validation README、
    worklog、implementation log，區分已完成 baseline、service-first migration 完成範圍和剩餘風險。

### 驗證

- Assistant UI product slice：
  - `timeout 240s scripts/dev/run_ui_pytest.sh tests/unit/ui/chat/test_chat_panel.py tests/unit/ui/chat/test_message_bubble.py tests/unit/ui/components/test_agent_manager.py tests/unit/ui/test_agent_manager_coverage.py -q`
  - `78 passed`
- UI command adapter / backend slice：
  - `timeout 240s scripts/dev/run_ui_pytest.sh tests/unit/ui/test_application_capabilities.py tests/unit/ui/dataset/test_panel.py tests/unit/ui/dataset/test_dataset_sidebar.py tests/unit/ui/preprocess/test_preprocess_panel.py tests/unit/ui/preprocess/test_preprocess_panel_normalize.py tests/unit/ui/training/test_training_sidebar.py tests/unit/ui/test_sidebars_and_components.py -q`
  - `74 passed`
  - `timeout 180s poetry run pytest --capture=sys tests/unit/backend/application tests/integration/backend/test_application_service_workflow.py -q`
  - `11 passed`
- Agent command result slice:
  - `timeout 180s poetry run pytest --capture=sys tests/unit/llm/tools/test_application_surface.py tests/unit/llm/agent/test_controller.py -q`
  - `60 passed`
- Product walkthrough:
  - `timeout 240s scripts/dev/run_ui_pytest.sh tests/integration/ui/test_product_walkthrough.py -q`
  - `2 passed`
- Combined gates after implementation:
  - UI product gate: `62 passed`
  - agent / backend gate: `95 passed`
  - IO integration: `31 passed, 8 warnings`
  - selected pipeline smoke: `2 passed`
  - launcher startup smoke: `MainWindow initialized` appeared before expected GUI timeout.

### 剩餘風險

- UI service-first migration 尚未覆蓋 label import、smart parse、channel selection、split /
  model / training setting dialog submit、evaluation / visualization query actions。
- Agent `load_data`、`set_montage`、`switch_panel` 仍有 legacy / UI request semantics。
- `evaluate` / `visualize` / `saliency` / `new_session` 仍是 disabled future command contract。
- 真 Windows launcher click-through 和 true local model UI walkthrough 尚未人工驗收。
- deterministic tool-call eval 不是 local LLM 真實 performance claim。

## 2026-05-03 Backend Workflow Contract v2 first slice

### 背景

Backend 已有 `ApplicationService` command spine，但 reset / cleanup / eval / visualization /
saliency / split audit 仍有 service bypass 或過寬 policy。這個切片目標是先消除高風險
mutating/lifecycle bypass，並讓 thesis evidence path 不會把 invalid split 當成功。

### 變更

- Command contract：
  - 新增 `ClearDatasetsCommand`、`ClearTrainingHistoryCommand`、`ResetPreprocessCommand`。
  - 更新 command export、handler routing、capability policy、confirmation gate 和
    `BackendFacade` wrapper compatibility。
- Dataset audit：
  - `GenerateDatasetCommand` 會執行 split audit，回傳 `split_audit`、`protocol`、
    `rolled_back` 等 structured diagnostics。
  - empty train/validation/test 或 leakage 會變成 `DATA_MISMATCH` command failure。
  - audit failure 會 rollback dataset / generator / trainer state，避免 failure 後仍可 train。
  - custom UI generator 會從 `test_splitter_list` 推斷 audit protocol，避免 trial split
    被 default subject-wise audit 誤擋。
- Query/readiness：
  - `evaluate`、`visualize`、`saliency` 不再於 empty state 無條件 available。
  - blocked query / lifecycle commands 仍回 `CommandResult` envelope。
  - `saliency` 回傳 `action=configure/query`；configure 可先保存參數，但 saliency view
    readiness 仍依 finished evaluation + configured params。

### 驗證

- `poetry run ruff check XBrainLab tests`
  - pass
- `poetry run basedpyright XBrainLab/backend/application XBrainLab/backend/facade.py`
  - `0 errors, 0 warnings, 0 notes`
- `poetry run pytest tests/unit/backend/application/test_application_service.py tests/integration/backend/test_application_service_workflow.py tests/integration/ui/test_product_walkthrough.py tests/integration/pipeline/test_public_cross_source_training_smoke.py`
  - `32 passed, 3 warnings`
- `poetry run pytest tests/unit/backend/application tests/integration/backend tests/integration/pipeline`
  - `95 passed, 4 warnings`
- `poetry run basedpyright`
  - `0 errors, 0 warnings, 0 notes`

### 剩餘風險

- 這是 Backend Workflow Contract v2 + Evidence-Ready Pipeline 的第一個可交付切片，不是終局。
- UI service-first migration 還有剩餘 bypass；本切片沒有完成整個 UI service-first migration。
- thesis evidence 還需要 external dataset runner、repeat/baseline/statistics 和 artifact emission policy。

## 2026-05-03 Assistant UI single-toolbar product correction

### 背景

人工驗收指出上一輪 Assistant UI 仍不夠像使用者產品：chat panel 內還有 `Conversation`
標題、composer 底下狀態列、兩組功能列、未設計完成的 `Assistant mode` / `Step behavior`
選項，以及過大的短訊息 bubble。

### 變更

- ChatPanel 內移除可見 header、第二條 status footer、developer mode controls 和第二個
  options menu；對話區第一視覺回到 empty state / transcript。
- Dock title bar 成為唯一第一層功能列：`XBrainLab`、retry icon、new conversation、
  settings menu、float/dock。`Clear conversation` 收進 settings menu。
- Retry 沒有上一則 request 時 disabled；有上一則 request 時只在 title bar 單一位置啟用。
- tool/debug output 由 `AgentManager` 攔截並轉成 notice，不再把 `Tool list_files completed...`
  或 schema/internal class name 放進 visible transcript。
- user / assistant short message bubble 降低 minimum width，避免 `hello` 形成過大的框，同時
  保留窄 dock 可讀文字欄。

### 驗證

- `poetry run ruff check XBrainLab/ui/chat XBrainLab/ui/components/agent_manager.py tests/unit/ui/chat tests/integration/ui/test_product_walkthrough.py`
  - pass
- `poetry run pytest --capture=sys tests/unit/ui/chat tests/integration/ui/test_product_walkthrough.py -q`
  - `50 passed`
- combined assistant UI + backend workflow contract gate：
  - `poetry run basedpyright` -> `0 errors, 0 warnings, 0 notes`
  - `poetry run pytest --capture=sys tests/unit/ui/chat tests/integration/ui/test_product_walkthrough.py tests/unit/backend/application/test_application_service.py tests/integration/backend/test_application_service_workflow.py tests/unit/backend/test_facade_headless.py tests/integration/pipeline/test_public_cross_source_training_smoke.py -q` -> `80 passed, 3 warnings`

## 2026-05-04 Data Interpretation backend command baseline

### 背景

Goal 1 的第一個核心缺口是資料入口仍受舊 `load_data / attach_labels` 心智模型影響。
本切片先不改 UI layout，而是建立 backend command contract，讓 UI / agent / headless /
MCP adapter 後續可以共用同一套 Data Interpretation lifecycle。

### 變更

- 新增 `XBrainLab/backend/application/data_interpretation.py`。
- 新增 lifecycle objects：
  - `ScanResult`
  - `InterpretationCandidate`
  - `InterpretationPreview`
  - `ValidationDecision`
  - `AppliedInterpretation`
  - `ImportRecipe`
- 新增 ApplicationService commands：
  - `ScanSourceCommand`
  - `PreviewInterpretationCommand`
  - `ValidateInterpretationCommand`
  - `ApplyInterpretationCommand`
  - `SaveInterpretationRecipeCommand`
  - `ReloadInterpretationRecipeCommand`
- `ApplicationStateSnapshot` 新增 `interpretation` snapshot。
- `CommandCapability` 新增 autonomy policy 欄位：
  - `can_auto_execute`
  - `requires_confirmation`
  - `decision_boundary`
  - `continue_allowed_after_success`
  - `retry_limit`
  - `stop_after_success`
  - `blocks_downstream_until_confirmed`
- `scan_source` 可掃描 file / folder / BIDS-like root / recipe source，並記錄 EEG files、
  label carriers、BIDS summary、subject / session / task / run metadata source / decision /
  reason / recipe trace。
- `validate_interpretation` 只產生 `safe`、`needs_confirmation`、`blocked`。
- `apply_interpretation` 對 `needs_confirmation` enforce confirmation boundary；`blocked`
  不會觸發 dataset import side effect。
- `reload_interpretation_recipe` 重新 scan / preview / validate，不直接 apply。
- deterministic eval state builder 補 `InterpretationStateSnapshot`，避免 scorer 使用過期 state
  shape。

### 驗證

- `poetry run pytest --capture=sys tests/unit/backend/application/test_application_service.py -q`
  - `28 passed`
- `poetry run ruff check XBrainLab/backend/application tests/unit/backend/application/test_application_service.py scripts/agent/evals/run_tool_call_eval.py`
  - pass
- `poetry run basedpyright XBrainLab/backend/application scripts/agent/evals/run_tool_call_eval.py tests/unit/backend/application/test_application_service.py`
  - `0 errors, 0 warnings, 0 notes`
- `poetry run pytest --capture=sys tests/unit/backend/application/test_application_service.py tests/unit/llm/tools/test_application_surface.py tests/unit/llm/agent/test_controller.py tests/integration/backend/test_application_service_workflow.py tests/integration/agent/test_tool_call_eval.py -q`
  - `92 passed`
- `git diff --check`
  - pass
- `poetry run mkdocs build --strict`
  - pass
- `poetry run ruff check .`
  - pass
- `poetry run basedpyright`
  - `0 errors, 0 warnings, 0 notes`
- `poetry run python tests/architecture_compliance.py`
  - `Architecture compliant`

### 不能宣稱完成

- UI import entry 尚未重做，使用者仍會看到舊 Dataset panel import / label flow。
- agent tool definitions / Context Assembler 尚未暴露 mature Data Interpretation taxonomy。
- headless / MCP adapter 尚未包裝新 command surface。
- 尚未有 UI-observable replay artifact 或 screenshot 證明新 import workflow。
- 尚未有 source -> scan -> preview -> validate -> apply -> recipe -> preprocess -> epoch ->
  dataset 的 non-mocked synthetic workflow evidence。

## 2026-05-04 Goal 1 Data Interpretation agent tool surface

### 背景

backend command baseline 完成後，agent 仍只註冊舊 `load_data / attach_labels` 型工具。
若不補 tool definitions / registry / application surface，LLM prompt 和 controller execution
都不會使用新的 Data Interpretation taxonomy。

### 變更

- `XBrainLab/llm/tools/definitions/dataset_def.py` 新增：
  - `BaseScanSourceTool`
  - `BasePreviewInterpretationTool`
  - `BaseValidateInterpretationTool`
  - `BaseApplyInterpretationTool`
  - `BaseSaveInterpretationRecipeTool`
  - `BaseReloadInterpretationRecipeTool`
- `mock/dataset_mock.py` 和 `real/dataset_real.py` 新增對應工具。
- `XBrainLab/llm/tools/__init__.py` 註冊 mock / real Data Interpretation tools。
- `application_surface.py` 新增 tool-to-command mapping 和 command builder。
- `ToolAvailability` serializes autonomy policy 欄位。
- `LLMController` 會讀 backend dynamic confirmation boundary；`apply_interpretation` 在
  user confirmation 後帶 `confirmed=True`。
- `BackendFacade(study)` 改為重用同一個 `ApplicationService`，且 `ApplicationService`
  會掛回 `Study._application_service`。這修掉 scan result 只存在 transient service、下一個
  tool call 讀不到的 lifecycle bug。
- `PathExistsValidator` 補 Data Interpretation source / recipe path。

### 驗證

- `poetry run pytest --capture=sys tests/unit/llm/tools/test_application_surface.py tests/unit/llm/tools/test_definitions.py tests/unit/llm/tools/test_mock_tools.py tests/unit/llm/agent/test_controller.py -q`
  - `219 passed`
- `poetry run pytest --capture=sys tests/unit/llm/tools/test_application_surface.py tests/unit/llm/tools/test_definitions.py tests/unit/llm/tools/test_mock_tools.py tests/unit/llm/tools/real/test_real_tools.py tests/unit/llm/agent/test_controller.py tests/unit/llm/agent/test_assembler_stage.py tests/unit/llm/agent/test_verification_layer.py tests/integration/agent/test_product_flow.py tests/integration/agent/test_tool_call_eval.py -q`
  - `286 passed`
- `poetry run ruff check <slice files>`
  - pass
- `poetry run basedpyright <slice source files>`
  - `0 errors, 0 warnings, 0 notes`
- `poetry run ruff check .`
  - pass
- `poetry run basedpyright`
  - `0 errors, 0 warnings, 0 notes`
- `poetry run mkdocs build --strict`
  - pass
- `poetry run python tests/architecture_compliance.py`
  - `Architecture compliant`
- `poetry run python scripts/agent/evals/run_tool_call_eval.py --output-dir artifacts/agent_evals_tmp_goal1_agent_surface`
  - pass；temporary artifact directory removed
- `git diff --check`
  - pass

### 不能宣稱完成

- UI import entry 仍未重做。
- headless / MCP adapter 仍未暴露新 command taxonomy。
- deterministic / local LLM eval case set 尚未以 Data Interpretation 作為主要資料入口。
- 尚未有完整 non-mocked synthetic workflow evidence。

## 2026-05-04 Goal 1 Dataset panel Data Interpretation entry

### 背景

backend 和 agent surface 都有 Data Interpretation taxonomy 後，Dataset panel 仍用
`Import Data` 直接載入 raw files。這會讓使用者可見的產品心智模型繼續停在舊
`load_data` 路徑。

### 變更

- Dataset sidebar 主按鈕改為 `Interpret Data Source`。
- `DatasetActionHandler.import_data()` 改為執行：
  - `ScanSourceCommand`
  - `PreviewInterpretationCommand`
  - `ValidateInterpretationCommand`
  - `ApplyInterpretationCommand`
- 新增 `DataInterpretationPreviewDialog`：
  - 顯示 source path。
  - 顯示 preview summary。
  - 顯示 validation decision。
  - 顯示 subject / session / task / run metadata preview。
  - 顯示 warnings / confirmation items / blocked reasons。
  - `blocked` decision disable apply。
- `needs_confirmation` decision 只有在使用者接受 preview dialog 後才帶 `confirmed=True`。
- mock / unsupported panel path 保留 fallback 到 `LoadDataCommand` / legacy controller import，
  以避免既有 mock-heavy tests 失去 compatibility。
- 多檔跨資料夾選取不再使用 common filesystem root 作為 scan source，避免掃描過大的上層路徑。

### 驗證

- `poetry run pytest --capture=sys tests/unit/ui/test_ui_misc.py::TestDatasetActionHandler tests/unit/ui/dialogs/dataset/test_data_interpretation_preview_dialog.py tests/unit/ui/dataset/test_panel.py tests/integration/ui/test_product_walkthrough.py::test_pipeline_product_walkthrough_uses_user_facing_actions -q`
  - `50 passed`
- `poetry run pytest --capture=sys tests/unit/ui/dataset tests/unit/ui/dialogs/dataset tests/unit/ui/test_ui_misc.py tests/unit/ui/test_application_capabilities.py tests/integration/ui/test_product_walkthrough.py -q`
  - `166 passed`
- `poetry run pytest --capture=sys tests/integration/agent/test_product_flow.py tests/unit/ui/chat/test_chat_panel.py tests/unit/ui/components/test_agent_manager.py -q`
  - `76 passed`
- `poetry run ruff check <ui data interpretation slice files>`
  - pass
- `poetry run basedpyright <ui data interpretation source files>`
  - `0 errors, 0 warnings, 0 notes`
- `poetry run ruff check .`
  - pass
- `poetry run basedpyright`
  - `0 errors, 0 warnings, 0 notes`
- `poetry run mkdocs build --strict`
  - pass
- `poetry run python tests/architecture_compliance.py`
  - `Architecture compliant`
- `git diff --check`
  - pass

### 不能宣稱完成

- recipe save UI 尚未接上。
- label import 仍是舊入口。
- headless / MCP adapter 尚未暴露新 taxonomy。
- 尚未有完整 non-mocked synthetic workflow evidence。

## 2026-05-04 ChatPanel Data Interpretation tool-chain handoff

### 背景

先前已有 true local ChatPanel one-turn 回覆、單步 `query_state` tool-command，以及 two-turn
workflow continuity artifact。但仍缺一條「真 local model 經可見 ChatPanel 連續執行多個
Data Interpretation command」的 evidence。

### 變更

- 新增 `scripts/dev/capture_chatpanel_local_tool_chain_walkthrough.py`：
  - 建立 deterministic synthetic FIF。
  - 打開真 `MainWindow` / `ChatPanel`。
  - 使用 offline HF / Transformers local runtime。
  - 透過 visible composer 送出三個 turns。
  - 要求 local model 依序執行 `scan_source`、`preview_interpretation`、
    `validate_interpretation`。
  - 保存 ready / per-turn screenshots、visible transcript、executed tools 和 final
    interpretation state。
- 新增 `tests/unit/scripts/test_capture_chatpanel_local_tool_chain_walkthrough.py`。
- 修 `XBrainLab/llm/agent/tool_call_normalizer.py`：
  - `preview_interpretation.scan_id` 只保留 backend 真 id 格式 `scan-<n>`。
  - `validate_interpretation.candidate_id` / `apply_interpretation.candidate_id` 只保留
    `candidate-<n>`。
  - local model 自造或 schema-derived 的 `latest_scan_id`、`current_candidate` 等 id 會被移除，
    讓 ApplicationService 使用目前 latest state。

### 驗證

- 首次真 local-model run 失敗並定位 root cause：
  - `scan_source` 成功。
  - `preview_interpretation` 失敗為 `Scan a data source before previewing interpretation.`
  - final state 已有 `latest_scan_id=scan-1`，證明 failure 是 generated placeholder id 覆蓋
    backend latest-state fallback。
- 修正後真 local-model run：
  - `timeout 620s env QT_QPA_PLATFORM=offscreen poetry run python scripts/dev/capture_chatpanel_local_tool_chain_walkthrough.py --output-dir artifacts/ui/chatpanel-local-tool-chain --timeout-seconds 580`
  - artifact status：`passed`
  - runtime：primary `microsoft/Phi-4-mini-instruct`，`gpu-ready`
  - executed tools：`scan_source`、`preview_interpretation`、`validate_interpretation` 全部 `ok`
  - final interpretation state：scan / candidate / preview / validation decision present；
    `validation_decision=needs_confirmation`
- Targeted gates：
  - `poetry run pytest --capture=sys tests/unit/llm/agent/test_tool_call_normalizer.py tests/unit/scripts/test_capture_chatpanel_local_tool_chain_walkthrough.py -q`
    - `30 passed`
  - targeted `ruff`
    - pass
  - targeted `basedpyright`
    - `0 errors, 0 warnings, 0 notes`

### 不能宣稱完成

- 這支撐短鏈 Data Interpretation tool-command workflow，不是完整 autonomous workflow。
- 還沒有 ChatPanel confirm/apply -> preprocess -> epoch -> dataset -> train/eval/saliency 長鏈
  walkthrough。
- Windows Desktop launcher 真人 click-through、MCP Inspector GUI、label import 內嵌 wizard /
  format-specific anchor editor 仍未完成。
- Goal 不能標 complete。

## 2026-05-04 ChatPanel import-to-dataset pipeline chain

### 背景

short Data Interpretation chain 只證明 local ChatPanel 可走到 validation。下一個產品缺口是：
同一可見 ChatPanel/local-model path 能否在 confirmation boundary 後繼續走 apply、preprocess、
epoch 和 dataset，而不是停在 backend JSON 或 deterministic eval。

### 變更

- 新增 `scripts/dev/capture_chatpanel_local_pipeline_chain_walkthrough.py`：
  - 產生 deterministic synthetic FIF。
  - 打開真 `MainWindow` / `ChatPanel`。
  - 以 offline local model 經 visible composer 送出 7 turns。
  - 每個 turn 預期一個 tool：`scan_source`、`preview_interpretation`、
    `validate_interpretation`、`apply_interpretation`、`apply_standard_preprocess`、
    `epoch_data`、`generate_dataset`。
  - 自動觀察並核准 `Confirm Action` QMessageBox，artifact 保存 confirmation record。
  - 最後檢查 typed backend state：applied interpretation、epoch available、dataset available。
- `XBrainLab/llm/tools/application_surface.py`：
  - `apply_standard_preprocess` 直接建 `PreprocessCommand(operation=STANDARD)`，讓 agent path
    回 typed `ToolCommandResult`。
- `XBrainLab/llm/agent/tool_call_normalizer.py`：
  - `_extract_epoch_args` 支援 `events left and right` 這類多 event prompt。
- 新增 `tests/unit/scripts/test_capture_chatpanel_local_pipeline_chain_walkthrough.py`。
- 補 `tests/unit/llm/tools/test_application_surface.py` regression，確認 standard preprocess
  route 到 `CommandName.PREPROCESS`。

### 驗證

- 首次真 local-model run：
  - apply confirmation、standard preprocess、epoch 都成功。
  - `generate_dataset` 被 split audit 擋下，原因是 single-event 3 epochs 造成 empty validation。
  - guardrail 保持；沒有放寬 split audit。
- 修正後真 local-model run：
  - `timeout 840s env QT_QPA_PLATFORM=offscreen poetry run python scripts/dev/capture_chatpanel_local_pipeline_chain_walkthrough.py --output-dir artifacts/ui/chatpanel-local-pipeline-chain --timeout-seconds 800`
  - artifact status：`passed`
  - runtime：primary `microsoft/Phi-4-mini-instruct`，`gpu-ready`
  - executed tools：七個 expected tools 全部 `ok`
  - confirmation dialogs observed：`1`
  - final state：epoch count `6`、dataset available `True`、dataset count `1`
- Targeted gates：
  - `poetry run pytest --capture=sys tests/unit/llm/agent/test_tool_call_normalizer.py tests/unit/llm/tools/test_application_surface.py::test_application_tool_command_routes_standard_preprocess tests/unit/scripts/test_capture_chatpanel_local_pipeline_chain_walkthrough.py -q`
    - `32 passed`
  - targeted `ruff`
    - pass
  - targeted `basedpyright`
    - `0 errors, 0 warnings, 0 notes`

### 不能宣稱完成

- 這支撐 true local ChatPanel import-to-dataset path，不支撐 training / evaluation / saliency 長鏈。
- 還沒有真人 Windows Desktop launcher click-through。
- MCP Inspector GUI / release config 還沒完成。
- Label import 仍不是成熟 import wizard 內嵌 label/anchor editor。
- Goal 不能標 complete。

## 2026-05-04 Usage-refresh handoff

### 背景

目前 runner 因用量即將刷新而停止，不能把 product-completion goal 包裝成完成。需要讓下一輪
可以直接接續已驗證 slice，不重跑已證明的 UI chain，也不誤碰受保護設定檔。

### 變更

- 新增 `artifacts/goal/handoff-2026-05-04-usage-refresh.md`：
  - 記錄 active repo、硬性邊界、latest commits、expected dirty files。
  - 摘要 `0cb480e assistant: capture import to dataset chain` 的可見 UI artifact、修正點和驗證。
  - 明確列出仍不能宣稱完成的 product blockers。
  - 指定下一輪優先切片：evaluation / visualization / saliency agent-tool exposure，再做
    ChatPanel dataset -> training / evaluation readiness walkthrough。
- 更新 `artifacts/goal/continuation-2026-05-04-product-completion.md`，加入 handoff 文件索引。

### 驗證邊界

這是交接文件切片，不新增產品 runtime 行為。下一輪仍需從 `git status --short` 開始，確認只剩
`.vscode/settings.json` 和 root `settings.json` 是 dirty protected files。

### 不能宣稱完成

- 仍沒有 ChatPanel dataset -> model / training settings -> train -> evaluation / saliency 長鏈。
- evaluation / visualization / saliency 仍需 agent tool exposure audit / implementation。
- Windows Desktop launcher 真人 click-through、MCP Inspector GUI、完整 import wizard label editor
  仍未完成。
- Goal 不能標 complete。

## 2026-05-04 Agent analysis-tool exposure

### 背景

交接後第一個產品缺口是：backend 已有 `EvaluateCommand`、`VisualizeCommand`、`SaliencyCommand`
typed command，但 agent tool registry / parser / ApplicationService tool mapping 尚未把它們當成
一等 workflow tools。這會讓 ChatPanel 的 evaluation / visualization / saliency request 落回
UI routing 或 substitute tool 心智模型。

### 變更

- 新增 `XBrainLab/llm/tools/definitions/analysis_def.py`：
  - `BaseEvaluateTool`
  - `BaseVisualizeTool`
  - `BaseSaliencyTool`
- 新增 `XBrainLab/llm/tools/mock/analysis_mock.py` 和
  `XBrainLab/llm/tools/real/analysis_real.py`。
- 更新 `XBrainLab/llm/tools/__init__.py`，讓 mock / real registry 會載入三個 tools。
- 更新 `XBrainLab/llm/tools/application_surface.py`：
  - `evaluate` -> `EvaluateCommand`
  - `visualize` -> `VisualizeCommand`
  - `saliency` -> `SaliencyCommand`
- 更新 `XBrainLab/llm/agent/parser.py`，支援三個 bare tool names。
- 更新 `XBrainLab/llm/agent/intent.py`，將 evaluation request 映射到
  `CommandName.EVALUATE`。
- 更新 `XBrainLab/llm/pipeline_state.py`，trained stage prompt 直接引導使用
  `evaluate` / `visualize` / `saliency` readiness tools，而不是只建議切 panel。

### 驗證

- TDD failure：
  - 新測試初跑因缺 `XBrainLab.llm.tools.definitions.analysis_def` 和
    `XBrainLab.llm.tools.mock.analysis_mock` collection error 而失敗。
- Targeted unit：
  - `poetry run pytest --capture=sys tests/unit/llm/tools/test_definitions.py tests/unit/llm/tools/test_mock_tools.py tests/unit/llm/tools/test_application_surface.py tests/unit/llm/tools/real/test_real_tools.py tests/unit/llm/test_parser.py tests/unit/llm/agent/test_intent.py tests/unit/llm/agent/test_assembler_stage.py tests/unit/llm/test_tools_and_debug.py tests/unit/llm/test_tools_and_debug_cov.py -q`
  - `293 passed`
- Broader agent/tools:
  - `poetry run pytest --capture=sys tests/unit/llm/agent tests/unit/llm/tools tests/unit/llm/test_parser.py tests/unit/llm/test_tools_and_debug.py tests/unit/llm/test_tools_and_debug_cov.py -q`
  - `516 passed`
- Deterministic eval:
  - `poetry run python scripts/agent/evals/run_tool_call_eval.py --output-dir artifacts/agent_evals --repeat-count 2`
  - `100 / 100` pass。
- Affected-case local LLM smoke:
  - primary `microsoft/Phi-4-mini-instruct`：`5 / 5` pass，`gpu-ready`，no download。
  - fallback `microsoft/Phi-3.5-mini-instruct`：`5 / 5` pass，`gpu-ready`，no download。
  - artifacts:
    - `artifacts/agent_evals/local_primary_analysis_tools/`
    - `artifacts/agent_evals/local_fallback_analysis_tools/`
- Static / docs gates:
  - targeted `ruff` -> pass
  - `poetry run ruff check .` -> pass
  - `poetry run basedpyright` -> `0 errors, 0 warnings, 0 notes`
  - `poetry run python tests/architecture_compliance.py` -> `Architecture compliant!`
  - `poetry run mkdocs build --strict` -> pass
  - `git diff --check` -> pass

### 不能宣稱完成

- 這支撐 analysis commands 已成為 ApplicationService-backed agent tools。
- 仍沒有真 ChatPanel dataset -> model / training settings -> train -> evaluate / visualize /
  saliency readiness 長鏈 artifact。
- Goal 不能標 complete。

## 2026-05-04 ChatPanel training-readiness boundary

### 背景

analysis tools 已經進入 agent registry 後，下一個產品問題是：真 local ChatPanel 是否能從
dataset-ready state 進到 model selection、training settings、training confirmation boundary 和
analysis readiness，而不是只靠 backend JSON 或 deterministic eval。

### 變更

- 新增 `scripts/dev/capture_chatpanel_local_training_readiness_walkthrough.py`：
  - 使用 `ApplicationService` 先準備 synthetic dataset-ready state。
  - 打開真 `MainWindow` / `ChatPanel`。
  - 使用 offline local model path。
  - visible turns：
    - `set_model`
    - `configure_training`
    - `start_training` confirmation observed / rejected
    - `visualize`
    - `saliency`
    - `evaluate` blocked reason
  - 保存 ready / turn screenshots、visible transcript、executed tools、confirmation dialog 和
    final state。
- 新增 `tests/unit/scripts/test_capture_chatpanel_local_training_readiness_walkthrough.py`。

### 驗證

- Unit:
  - `poetry run pytest --capture=sys tests/unit/scripts/test_capture_chatpanel_local_training_readiness_walkthrough.py -q`
  - `4 passed`
- Static:
  - targeted `ruff` -> pass
  - targeted `basedpyright` -> `0 errors, 0 warnings, 0 notes`
- True local ChatPanel run:
  - `timeout 900s env QT_QPA_PLATFORM=offscreen poetry run python scripts/dev/capture_chatpanel_local_training_readiness_walkthrough.py --output-dir artifacts/ui/chatpanel-local-training-readiness --timeout-seconds 840`
  - status：`passed`
  - runtime：primary `microsoft/Phi-4-mini-instruct`，`gpu-ready`
  - cache：`15.34 GB`，no download
  - confirmation dialogs observed：`1`，`approved=False`
  - final state：dataset available、model `EEGNet`、training option present、trainer not created、
    training not running、evaluation unavailable。
  - visible assistant text clean check：pass。

### 不能宣稱完成

- 這支撐 high-impact training confirmation boundary 和 analysis-readiness tools。
- 這不是 actual training completion，也沒有 evaluation metrics 或 saliency render。
- Goal 不能標 complete。

## 2026-05-04 Usage-refresh handoff refresh

### 背景

目前 runner 因使用量即將刷新而停止。先前 handoff 已存在，但頂部 latest commits / latest
verified slice 還停在 import-to-dataset chain；需要更新到 analysis-tool exposure 和
training-readiness boundary 後的實際狀態，避免下一輪重做已完成 slice 或誤判 goal complete。

### 變更

- 刷新 `artifacts/goal/handoff-2026-05-04-usage-refresh.md`：
  - latest commits 更新到 `a228a9d` / `84d9c66` / `9f26e4f` / `0cb480e` / `9513dfa`。
  - latest verified slice 改為
    `a228a9d assistant: capture training readiness boundary`。
  - 保留 protected dirty files 邊界：只應忽略 `.vscode/settings.json` 和 root `settings.json`。
  - 明確列出 analysis-tool exposure 已完成，不要重做。
  - 下一手 resume plan 指向 `configure_training` tool `output_dir` path 和 controlled tiny
    training completion evidence。

### 驗證邊界

這是交接文件切片，不新增 product runtime behavior。下一輪仍需先跑 `git status --short`，
並在任何產品切片後跑對應 targeted tests / static gates / UI artifact capture。

### 不能宣稱完成

- Actual ChatPanel training completion 未完成。
- Post-training evaluate metrics、visualization render、saliency render artifact 未完成。
- Windows Desktop human click-through、MCP Inspector / release config、mature import wizard label
  editor 和 external thesis experiment package 仍未完成。
- Goal 不能標 complete。

## 2026-05-04 Configure-training output directory surface

### 背景

下一個產品切片需要從 ChatPanel 執行 controlled tiny training completion。若 agent 不能指定
training `output_dir`，真 training walkthrough 會落回預設 `./output`，造成 artifact 不可控、
清理困難，也讓使用者看不出訓練輸出是否屬於本次驗證。

### 變更

- `XBrainLab/llm/tools/definitions/training_def.py`
  - `BaseConfigureTrainingTool.parameters` 新增 optional `output_dir: string`。
- `XBrainLab/llm/tools/application_surface.py`
  - `configure_training` tool -> `ConfigureTrainingCommand` mapping 現在保留 `output_dir`。
- `XBrainLab/llm/tools/real/training_real.py`
  - legacy real tool wrapper 也會把 `output_dir` 傳給 `BackendFacade.configure_training`。
- 測試：
  - `tests/unit/llm/tools/test_definitions.py`
  - `tests/unit/llm/tools/test_application_surface.py`
  - `tests/unit/llm/tools/real/test_real_tools.py`

### 驗證

- TDD failure：
  - focused tests 初跑為 `3 failed`，分別對應 schema 缺欄位、ApplicationService mapping 丟失
    `output_dir`、real wrapper 丟失 `output_dir`。
- Focused pass：
  - `poetry run pytest --capture=sys tests/unit/llm/tools/test_definitions.py::TestConfigureTrainingDefinitions::test_output_dir_is_optional_schema_parameter tests/unit/llm/tools/test_application_surface.py::test_application_tool_command_preserves_training_output_dir tests/unit/llm/tools/real/test_real_tools.py::TestRealTrainingTools::test_configure_and_start_training -q`
  - `3 passed`
- Regression:
  - `poetry run pytest --capture=sys tests/unit/llm/tools/test_definitions.py tests/unit/llm/tools/test_application_surface.py tests/unit/llm/tools/real/test_real_tools.py tests/unit/llm/tools/test_mock_tools.py tests/unit/llm/test_tools_and_debug.py tests/unit/llm/test_tools_and_debug_cov.py tests/unit/llm/agent/test_verification_layer.py -q`
  - `311 passed`
- Static:
  - targeted `ruff` -> pass
  - targeted `basedpyright` -> `0 errors, 0 warnings, 0 notes`
- Deterministic tool-call eval:
  - `poetry run python scripts/agent/evals/run_tool_call_eval.py --output-dir artifacts/agent_evals --repeat-count 2`
  - `100 / 100` pass

### 不能宣稱完成

- 這只讓下一個 training walkthrough 的 output path 可控。
- 還沒有 actual ChatPanel training completion、post-training evaluation metrics、visualization render
  或 saliency render artifact。
- Goal 不能標 complete。

## 2026-05-04 ChatPanel controlled tiny training completion

### 背景

Goal 1 baseline 仍缺真 ChatPanel / local model 從 dataset-ready state 走到訓練完成與訓練後分析
readiness 的可觀察 evidence。前一個 readiness slice 只證明 training confirmation boundary 可以被
觀察並拒絕，不能支撐 actual training completion、evaluation metrics 或 saliency availability。

### 變更

- 新增 `scripts/dev/capture_chatpanel_local_training_completion_walkthrough.py`：
  - 在 repo 外 `/tmp` 寫入 deterministic synthetic FIF。
  - 先經 `ApplicationService` 執行 `scan_source` -> `preview_interpretation` ->
    `validate_interpretation` -> `apply_interpretation` -> `preprocess` -> `create_epoch` ->
    `generate_dataset`。
  - 開啟真 `MainWindow` / `ChatPanel` / local primary model。
  - visible turns 為 `set_model`、`configure_training` with controlled `output_dir`、
    observed / approved `start_training` confirmation、training completion wait、`evaluate`、
    `saliency` configure、`visualize`、saliency readiness query。
  - 保存 ready / trained screenshots、turn screenshots、visible transcript、executed tools、
    confirmation dialogs 和 final backend state。
- 新增 `tests/unit/scripts/test_capture_chatpanel_local_training_completion_walkthrough.py`。
- 修正 walkthrough 暴露出的產品缺口：
  - synthetic fixture 改成 14s raw / 1.5s epochs，避免 EEGNet minimum epoch duration guardrail。
  - `SaliencyCommand` 將 agent-friendly flat `method` / `params` normalize 成 evaluator 需要的
    `SmoothGrad` / `SmoothGrad_Squared` / `VarGrad` params。
  - `infer_user_intent()` 認得 `visualization` / `visualisation`。
  - saliency readiness query 會清掉前一輪 stale saliency config params，避免把 query 誤當 configure。
  - metrics bar chart `tight_layout` singular-matrix failure 降級為 warning。
  - 缺 optional `torchinfo` 時回傳 model-summary unavailable message，不再打 traceback。

### 驗證

- Focused regression:
  - `poetry run pytest --capture=sys tests/unit/backend/application/test_application_service.py::test_saliency_command_can_configure_params tests/unit/backend/application/test_application_service.py::test_saliency_command_normalizes_flat_method_params tests/unit/llm/agent/test_intent.py tests/unit/llm/agent/test_tool_call_normalizer.py tests/unit/scripts/test_capture_chatpanel_local_training_completion_walkthrough.py tests/unit/backend/controller/test_evaluation_controller.py -q`
  - `48 passed`
- UI fallback regression:
  - `scripts/dev/run_ui_pytest.sh tests/unit/ui/test_ui_components.py::TestMetricsBarChart -q`
  - `3 passed`
- Broader agent regression:
  - `poetry run pytest --capture=sys tests/unit/llm/agent -q`
  - `235 passed`
- Static:
  - targeted `ruff` -> pass
  - targeted `basedpyright` -> `0 errors, 0 warnings, 0 notes`
- Deterministic eval:
  - `poetry run python scripts/agent/evals/run_tool_call_eval.py --output-dir artifacts/agent_evals --repeat-count 2`
  - `100 / 100` pass
- True local ChatPanel run:
  - `timeout 1200s env QT_QPA_PLATFORM=offscreen poetry run python scripts/dev/capture_chatpanel_local_training_completion_walkthrough.py --output-dir artifacts/ui/chatpanel-local-training-completion --timeout-seconds 1080`
  - status：`passed`
  - runtime：primary `microsoft/Phi-4-mini-instruct`，`gpu-ready`，cache `15.34 GB`，no download
  - final state：finished runs `1`、evaluation metrics available `True`、saliency configured /
    available `True`、ChatPanel idle。
  - artifact：
    `artifacts/ui/chatpanel-local-training-completion/chatpanel-local-training-completion-walkthrough.md`
    和同目錄 screenshots / JSON。

### 不能宣稱完成

- 這支撐 true local ChatPanel controlled tiny training completion、post-training metrics query 和
  saliency / visualization readiness summary。
- 仍不是完整 saliency / visualization canvas render UI walkthrough。
- 仍未完成真人 Windows Desktop launcher click-through、MCP Inspector GUI / release config、mature
  import wizard label editor、external thesis experiment package。
- Goal 不能標 complete。

## 2026-05-04 VisualizationPanel Matplotlib render evidence

### 背景

前一個 ChatPanel training-completion artifact 只證明 `visualize` / `saliency` tools 能回傳 readiness
summary。產品缺口是使用者在真 MainWindow 的 VisualizationPanel 是否能看到訓練後 saliency
canvas，而不是只看到 backend JSON 或 assistant summary。

### 變更

- 新增 `scripts/dev/capture_visualization_render_walkthrough.py`：
  - repo 外 `/tmp` 建立 deterministic synthetic FIF 和 controlled training output。
  - 用 `ApplicationService` 執行 source -> Data Interpretation apply -> preprocess -> epoch ->
    dataset -> `ConfigureTrainingCommand` -> `SaliencyCommand` -> `ApplyMontageCommand` ->
    `TrainCommand`。
  - 開啟真 `MainWindow`，切到 `VisualizationPanel`，依序 capture `Saliency Map`、
    `Spectrogram`、`Topographic Map`。
  - 每個 tab 都驗證 visible canvas、無 error label、figure axes 和 rendered image artist。
  - offscreen run 會 auto-dismiss `Done / All training jobs finished.` completion dialog，避免
    modal event loop 擋住 artifact capture。
- 新增 `tests/unit/scripts/test_capture_visualization_render_walkthrough.py`：
  - 驗證 render tab 覆蓋範圍。
  - 驗證 payload 不接受缺 tab、placeholder canvas 或 image count `0`。
  - 驗證 artifact markdown 記錄 3D claim boundary。

### 驗證

- TDD failure：
  - `poetry run pytest --capture=sys tests/unit/scripts/test_capture_visualization_render_walkthrough.py -q`
  - 初跑因 `scripts.dev.capture_visualization_render_walkthrough` module 不存在而 collection failed。
- Unit:
  - `poetry run pytest --capture=sys tests/unit/scripts/test_capture_visualization_render_walkthrough.py -q`
  - `6 passed`
- Existing visualization UI regression:
  - `scripts/dev/run_ui_pytest.sh tests/unit/ui/test_visualization_panel_redesign.py tests/unit/ui/test_visualization.py -q`
  - `20 passed`
- True UI render run:
  - `timeout 600s env QT_QPA_PLATFORM=offscreen poetry run python scripts/dev/capture_visualization_render_walkthrough.py --output-dir artifacts/ui/visualization-render --timeout-seconds 540`
  - status：`passed`
  - final state：finished runs `1`、metrics available `True`、saliency available `True`、montage
    available `True`。
  - render evidence：
    - `Saliency Map` axes `3` / image `3`
    - `Spectrogram` axes `3` / image `3`
    - `Topographic Map` axes `3` / image `4`
    - all error visible `False`、canvas visible `True`
  - artifact：
    `artifacts/ui/visualization-render/visualization-render-walkthrough.md`、
    `artifacts/ui/visualization-render/visualization-render-walkthrough.json` 和 screenshots。
- Static / docs:
  - targeted `ruff` -> pass
  - targeted `basedpyright` -> `0 errors, 0 warnings, 0 notes`
  - `poetry run mkdocs build --strict` -> pass
  - `git diff --check` -> pass

### 不能宣稱完成

- 這支撐 true MainWindow VisualizationPanel post-training Matplotlib saliency renders。
- 這不支撐 3D / PyVista render、ChatPanel UI-routing render、真人 Windows launcher
  click-through、MCP Inspector GUI / release config、mature import wizard label editor 或 external
  thesis experiment package。
- Goal 不能標 complete。

## 2026-05-04 3D headless blocked UX guard

### 背景

Matplotlib render artifact 完成後，下一個 visualization gap 是 `3D Plot`。臨時真 run 在
`QT_QPA_PLATFORM=offscreen` / `PYVISTA_OFF_SCREEN=true` 切到 `3D Plot` 時，PyVista / X11 直接
觸發 `BadWindow (invalid Window parameter)` 並結束 process。這不是可接受的產品狀態：在無法
render 3D 的 runtime，UI 應該顯示 blocked reason，而不是 crash。

### 變更

- `XBrainLab/ui/panels/visualization/saliency_views/plot_3d_view.py`
  - 新增 `_interactive_3d_runtime_available()`。
  - 在建立 `pyvistaqt.QtInteractor` 前檢查：
    - `QT_QPA_PLATFORM=offscreen|minimal`
    - `PYVISTA_OFF_SCREEN=1|true|yes`
    - Linux 沒有 `DISPLAY`
  - 不可用時以 `show_message()` 顯示：
    `3D rendering requires an interactive OpenGL desktop session...`
  - 不建立 PyVista plotter，避免 X11 crash。
- `scripts/dev/capture_visualization_render_walkthrough.py`
  - 新增 `BLOCKED_TAB_SPECS`。
  - capture `3D Plot` blocked screenshot、blocked reason 和 `plotter_created` 狀態。
  - payload validation 要求 headless 3D blocked evidence 存在。
- `tests/unit/ui/test_visualization.py`
  - 新增 offscreen guard test，確保 blocked runtime 不呼叫 `QtInteractor`。
- `tests/unit/scripts/test_capture_visualization_render_walkthrough.py`
  - 新增 blocked tab contract 和 validation。

### 驗證

- TDD failure：
  - `scripts/dev/run_ui_pytest.sh tests/unit/ui/test_visualization.py::TestSaliency3DPlotWidget::test_update_plot_blocks_offscreen_before_qtinteractor -q`
  - 初跑失敗，因 current code 仍呼叫 `pyvistaqt.QtInteractor`。
- Focused:
  - `scripts/dev/run_ui_pytest.sh tests/unit/ui/test_visualization.py::TestSaliency3DPlotWidget::test_update_plot_blocks_offscreen_before_qtinteractor -q`
  - `1 passed`
  - `poetry run pytest --capture=sys tests/unit/scripts/test_capture_visualization_render_walkthrough.py -q`
  - `8 passed`
- True UI run:
  - `timeout 600s env QT_QPA_PLATFORM=offscreen PYVISTA_OFF_SCREEN=true poetry run python scripts/dev/capture_visualization_render_walkthrough.py --output-dir artifacts/ui/visualization-render --timeout-seconds 540`
  - status：`passed`
  - 2D tabs：Saliency Map / Spectrogram / Topographic Map all rendered。
  - 3D tab：blocked reason visible、`plotter_created=False`、screenshot captured。

### 不能宣稱完成

- 這支撐 headless/offscreen 3D blocked UX。
- 這不支撐 interactive desktop 3D / PyVista render；Windows / WSLg 3D click-through 仍未驗證。
- Goal 不能標 complete。

## 2026-05-04 Usage refresh handoff refresh

### 背景

使用量即將刷新，本輪不再繼續開下一個產品 slice。為避免下一個 runner 從過期 handoff 接錯，
需要把 handoff 和 continuation prompt 更新到最新產品 commit，並明確列出哪些缺口仍不能宣稱完成。

### 變更

- 更新 `artifacts/goal/handoff-2026-05-04-usage-refresh.md`：
  - 最新 commit 改為 `15002a1 ui: show label import target context`。
  - 補入已完成的 shared import state propagation、安全多檔 timestamp / sequence label mapping、
    label carrier `Matched EEG` UI 和 post-load label target context。
  - 移除已完成項目作為 next step 的舊提示。
  - 下一步改為 MCP Inspector / release config hardening。
- 更新 `artifacts/goal/continuation-2026-05-04-product-completion.md`：
  - 明確要求刷新後先看 handoff，再從 MCP external-client config / launch manifest slice 接續。
  - 保留不能宣稱完成的 blocker 和 protected worktree files。
- 更新 `docs/records/worklog.md` 保存停工位置。

### 驗證

- Handoff 是文件 / artifact refresh；本段只跑文件必要驗證。
- `git diff --check` -> pass。
- `poetry run mkdocs build --strict` -> pass with existing MkDocs Material warning。

### 不能宣稱完成

- 這只是 usage refresh handoff，不是產品 closure。
- Goal 不能標 complete。
