# XBrainLab Validation

最後更新：`2026-05-05`

## 這份文件的用途

這份文件整理 XBrainLab 的驗證策略。

重點不是列出所有測試，而是回答：

- 哪些測試代表哪些可信度？
- 哪些 evidence 可以支撐 thesis claim？
- 哪些只是 engineering smoke？
- 現在有哪些驗證還不能信？

## 目前狀態

`artifacts/quality/latest.*` 已可引用作為今天的 fast engineering evidence，但 `2026-05-02`
人工產品驗收修正了它的可信邊界：fast engineering evidence 不能代表 AI Assistant
已達可用產品狀態。使用者實際打開 assistant 後曾發現 chat UI 仍像 debug dock，且輸入
`hello` 沒有 assistant 回覆。該 blocker 已完成第一輪 targeted 修復和 product tests；
後續 assistant product audit follow-up 又修掉 top chip dump、Retry transcript pollution、
raw tool output 外洩、窄 dock bubble wrapping 和 legacy remote runtime 產品入口暴露。
但仍不能用 dashboard PASS、local runtime smoke 或 deterministic eval 直接宣稱完整 release
closure。

## Evidence 分層與 Claim Boundary

本文件把 UI / backend / 人工驗收分成三層，避免把可重跑 script 擴張成真人產品驗收：

| Evidence 層級 | 可支撐的 claim | 不能支撐的 claim |
| --- | --- | --- |
| Backend replay | `ApplicationService / Command API` contract、state transition、typed result、capability / autonomy policy 可重跑。 | 不能證明使用者看得到、按得到或 UI 文案合理。 |
| UI-observable automated walkthrough | automated replay 透過真 Qt UI path 產生 screenshots、visible text、button state、workflow state、transcript 和 backend state snapshot，可證明主要 UI path 在 replay 條件下可操作。 | 不能等同真人 Windows desktop acceptance，也不能證明雙螢幕、DPI、launcher、長時間 local model session 都可用。 |
| Human desktop acceptance | 真人從 Windows desktop launcher 在實際螢幕 / DPI / GPU / local model session 操作並確認。 | 這層目前仍未完成；未完成前不能宣稱 product-complete。 |

最新使用者要求的「單一 automated human-like walkthrough」已新增：
`scripts/dev/capture_human_like_product_walkthrough.py` 產出
`artifacts/ui/human-like-walkthrough/human-like-walkthrough.json` / `.md` 和 `20` 張 screenshots。
artifact 覆蓋 startup、Data Interpretation wizard、recipe reload、preprocess、epoch、dataset、
training readiness、analysis readiness、ChatPanel empty / normal / clarification / blocked /
success / narrow、reset / new session boundary、error recovery 和 eval dashboard report。
最新 artifact summary 是 status `passed`、`26 / 26` required phases、`20` screenshots。UI polish
後已刷新 screenshots；reset / new-session boundary 截圖也已確認不再顯示 stale chat bubbles
或 stale `Ready to train` workflow status。最新 metadata apply slice 也讓 applied-state Dataset
table 顯示 reviewed `S01` / `session-01`，且 training readiness 回到 dataset-ready / Start Training
enabled。最新 artifact 另有 top-level `observable_evidence` / `ui_quality_review`：`26`
個 phase 都有 visible text、button state、workflow/backend snapshot index，`20` 張 screenshot
全數 nonblank，visible text raw tool / schema / traceback leakage findings 為 `0`。這支撐
automated PyQt replay 的主要 UI 操作路徑，但仍不能
替代 human desktop acceptance。

目前 fast engineering artifact 狀態是：

- generated at: `2026-05-04 04:07:48 UTC+08:00`
- workspace: `/mnt/d/workspace_v2/projects/lab/XBrainLab`
- overall: `PASS`

`ai-assistant-open.png` 已接受 `(1684, 800)` product redesign approved baseline。最新
UI baseline capture 結果：

- `7 UI artifacts match approved references`
- `max mean diff 0.114`
- `max changed 0.66%`
- fast dashboard after assistant product audit follow-up: `PASS`

最新 fast dashboard summary：

- Ruff Lint：`PASS`
- Basedpyright：`PASS`，`0 errors, 0 warnings, 0 notes`
- Architecture Compliance：`PASS`
- Startup Smoke：`PASS`
- UI Baseline Capture：`PASS`
- UI Dialog Acceptance：`PASS`
- UI Unit Suite：`831 passed`
- Real-Data IO Integration：`31 passed, 8 warnings`

同輪或 supervisor final closure 已通過：

- `git diff --check`
- `poetry run ruff check .`
- `poetry run basedpyright`
- `poetry run mkdocs build --strict`
- `poetry run python tests/architecture_compliance.py`
- UI product / geometry gate：`121 passed`
- agent / backend command gate：`225 passed`
- backend + IO integration：`33 passed, 8 warnings`
- full pipeline integration：`70 passed, 4 warnings`
- LLM / local settings / script unit gate：`674 passed`
- deterministic tool-call eval refresh：commit `e5454c7 test: refresh agent eval artifact`
  tracked `artifacts/agent_evals/latest.json`

這些 closure gates 修正並覆蓋了先前 fast dashboard fail：

- local-disabled assistant startup 現在有 visible reason。
- confirmation transcript 不再暴露 raw tool names。
- montage apply 不再 bypass command surface。
- `run.py` assistant startup path 維持 local-only。
- UI baseline geometry 已穩定。
- UI unit legacy runtime expectations 已改成 remote switch fail-closed / active local deletion block。
- deterministic agent eval artifact 已刷新。

2026-05-05 backend command boundary cleanup 另有可重跑 focused evidence：

- `TrainingCommandService` 承接 `configure_training`、`train`、`stop_training`、
  `clear_training_history` 和 reset-time training config clear。
- `DatasetGenerationCommandService` 承接 `generate_dataset`、`clear_datasets`、split config、
  split audit、rollback、split summary 和 dataset cleanup。
- `LifecycleCommandService` 承接 `reset_preprocess`、`reset_session`、`new_session`、
  downstream rollback 和 reset-time dependent-state clear。
- `DataCompatibilityCommandService` 承接舊 `load_data`、`attach_labels`、`import_labels` 和
  label helper，並維持 Data Interpretation recipe trace update。
- `DataTableCommandService` 承接 `update_metadata`、`apply_smart_parse` 和 `remove_files`，
  並維持 loaded-data table mutation diagnostics。
- `PreprocessCommandService` 承接 preprocessing operations 和 `create_epoch`，並維持
  `set_montage` UI confirmation boundary。
- `StateSnapshotService` / `QueryStateCommandService` 承接 state snapshot assembly 和
  `query_state` diagnostics，並維持 agent `query_state` tool surface。
- focused test-first 紅燈先確認缺少
  `XBrainLab.backend.application.training_service` /
  `XBrainLab.backend.application.dataset_generation_service` /
  `XBrainLab.backend.application.lifecycle_service` /
  `XBrainLab.backend.application.data_compatibility_service` /
  `XBrainLab.backend.application.data_table_service` /
  `XBrainLab.backend.application.preprocess_service` /
  `XBrainLab.backend.application.state_service`，再以 service unit tests 驗證 model
  holder、training option snapshot、start / stop、history cleanup diagnostics、config reset
  notification、dataset split config、audit blocking、rollback、cleanup diagnostics、reset
  notification、dependent-state clearing、legacy load failure mapping、attach labels、label import
  recipe update、metadata skipped row reporting、smart parse normalization、remove-count delta、
  standard preprocess batching、core preprocessing operations、epoch creation、montage boundary、
  state snapshot construction、query diagnostics 和 smart-filter suggestions。
- regression gate 已通過 `tests/unit/backend/application`、`tests/integration/backend`、
  `tests/unit/llm/agent tests/unit/llm/tools` 和 `tests/integration/agent`。
- 這支撐 backend handler boundary cleanup；不能擴張成 product-complete、Windows human
  acceptance、完整 Data Interpretation wizard 或 MCP long-running training claim。

仍未完成的 evidence：

- Windows Desktop launcher 真人 click-through；目前已有 automated command walkthrough，不等於
  人工桌面驗收。
- true local LLM ChatPanel 已有一輪真模型 UI 回覆 walkthrough、一輪單步 `query_state`
  tool-command walkthrough，以及兩 turn workflow walkthrough；長時間 tool-command chain 仍未完成。
- local LLM primary / fallback tool-call runner 已有 `117` thesis-candidate cases x `3`
  score report；primary / fallback 都是 `117 / 117` pass，dashboard 已列 model comparison、
  metric pass rate、case family pass rate 和 failure taxonomy。這支撐 tool-call benchmark
  evidence，但不代表 launcher / UI 產品 walkthrough 已完成。
- external EEG dataset experiment / statistical reporting 只是 pipeline support，不是 thesis 主評分。

data pipeline 文件驗證時也重跑：

- `poetry run pytest --capture=sys tests/integration/io/test_io_integration.py -q`
  - `31 passed, 8 warnings`
- tiny E2E pipeline smoke
  - `2 passed in 5.89s`

agent 架構文件整理時也跑：

- `poetry run pytest --capture=sys tests/unit/llm/test_pipeline_state.py tests/unit/llm/agent/test_controller.py tests/unit/llm/agent/test_worker.py tests/unit/llm/tools/real/test_real_tools.py tests/unit/ui/components/test_agent_manager.py tests/unit/ui/chat/test_chat_panel.py -q`
  - `157 passed in 7.61s`

2026-05-02 UI / Agent command surface unification 後新增一組 product engineering gate：

- backend command contract：
  - `poetry run pytest --capture=sys tests/unit/backend/application -q`
  - `9 passed`
- facade/headless compatibility：
  - `poetry run pytest --capture=sys tests/unit/backend/test_facade_coverage.py tests/unit/backend/test_facade_headless.py -q`
  - `44 passed`
- agent command surface / controller：
  - `poetry run pytest --capture=sys tests/unit/llm/agent tests/unit/llm/tools -q`
  - `318 passed`
- UI readiness / chat / panel unit suite：
  - `scripts/dev/run_ui_pytest.sh tests/unit/ui -q`
  - `807 passed`
- ApplicationService low-mock backend workflow:
  - `poetry run pytest --capture=sys tests/integration/backend/test_application_service_workflow.py -q`
  - `2 passed`

這組 gate 只代表 backend policy / UI readiness / agent command surface 的工程可信度；
它仍不是 thesis-grade tool-call evaluation。

2026-05-04 Backend ApplicationService boundary cleanup 新增一組 architecture gate：

- Data Interpretation command coordinator / apply service focused gate：
  - `timeout 300s poetry run ruff check XBrainLab/backend/application/service.py XBrainLab/backend/application/data_interpretation_service.py XBrainLab/backend/application/data_interpretation_apply.py tests/unit/backend/application/test_data_interpretation_service.py tests/unit/backend/application/test_application_service.py`
  - pass
  - `timeout 300s poetry run basedpyright XBrainLab/backend/application/service.py XBrainLab/backend/application/data_interpretation_service.py XBrainLab/backend/application/data_interpretation_apply.py tests/unit/backend/application/test_data_interpretation_service.py`
  - `0 errors, 0 warnings, 0 notes`
- backend command contract:
  - `timeout 300s poetry run pytest --capture=sys tests/unit/backend/application -q`
  - `54 passed`
- backend integration:
  - `timeout 300s poetry run pytest --capture=sys tests/integration/backend -q`
  - `3 passed`
- agent command surface / controller:
  - `timeout 300s poetry run pytest --capture=sys tests/unit/llm/agent tests/unit/llm/tools -q`
  - `466 passed`
  - `timeout 300s poetry run pytest --capture=sys tests/integration/agent -q`
  - `7 passed`
- static / docs / architecture:
  - `timeout 300s poetry run ruff check .`
  - pass
  - `timeout 300s poetry run basedpyright`
  - `0 errors, 0 warnings, 0 notes`
  - `timeout 300s poetry run python tests/architecture_compliance.py`
  - `Architecture compliant!`
  - `timeout 300s poetry run mkdocs build --strict`
  - pass with existing MkDocs Material warning
  - `timeout 120s git diff --check`
  - pass

這組 gate 支撐「Data Interpretation lifecycle 已從 `ApplicationService` 拆到 focused service，
reviewed apply side effects 已拆到 apply service，且 UI / agent / MCP-facing command contract
沒有回歸」。它不能支撐整個 backend architecture closure；後續 cleanup 已另外拆出
analysis、training、dataset generation、lifecycle、data compatibility、data-table、preprocess /
epoch 和 state/query handlers。這仍不能支撐 product completion，因為 UI / agent / MCP
runtime 旁路、import wizard maturity、Windows human acceptance 和 long-running local assistant
verification 仍要另外驗證。

2026-05-05 Analysis command boundary cleanup 新增一組 architecture gate：

- test-first focused gate：
  - `timeout 300s poetry run pytest --capture=sys tests/unit/backend/application/test_analysis_service.py -q`
  - 初始紅燈 `ModuleNotFoundError: XBrainLab.backend.application.analysis_service`
- analysis service focused/static gate：
  - `timeout 300s poetry run ruff check XBrainLab/backend/application/service.py XBrainLab/backend/application/analysis_service.py tests/unit/backend/application/test_analysis_service.py tests/unit/backend/application/test_application_service.py`
  - pass
  - `timeout 300s poetry run basedpyright XBrainLab/backend/application/service.py XBrainLab/backend/application/analysis_service.py tests/unit/backend/application/test_analysis_service.py`
  - `0 errors, 0 warnings, 0 notes`
  - `timeout 300s poetry run pytest --capture=sys tests/unit/backend/application/test_analysis_service.py tests/unit/backend/application/test_application_service.py -q`
  - `46 passed`
- backend command contract:
  - `timeout 300s poetry run pytest --capture=sys tests/unit/backend/application -q`
  - `56 passed`
- backend / agent regression:
  - `timeout 300s poetry run pytest --capture=sys tests/integration/backend -q`
  - `3 passed`
  - `timeout 300s poetry run pytest --capture=sys tests/unit/llm/agent tests/unit/llm/tools -q`
  - `466 passed`
  - `timeout 300s poetry run pytest --capture=sys tests/integration/agent -q`
  - `7 passed`
- static / docs / architecture:
  - `timeout 300s poetry run ruff check .`
  - pass
  - `timeout 300s poetry run basedpyright`
  - `0 errors, 0 warnings, 0 notes`
  - `timeout 300s poetry run python tests/architecture_compliance.py`
  - `Architecture compliant!`
  - `timeout 300s poetry run mkdocs build --strict`
  - pass with existing MkDocs Material warning
  - `timeout 120s git diff --check`
  - pass

這組 gate 支撐「`evaluate`、`visualize`、`saliency` 和 confirmed `apply_montage` 已從
`ApplicationService` 拆到 focused analysis service，且 UI / agent-facing command contract 沒有
回歸」。它不能支撐 full visualization UI render、interactive 3D / PyVista desktop acceptance、
training lifecycle closure 或 complete backend architecture closure。

### 2026-05-02 Chat product-flow blocker

先前 gate 漏掉的 product blocker：

- normal user text path 沒有被產品級測試覆蓋。`hello` 這種不需要 tool 的普通輸入，
  必須驗證 user bubble、assistant bubble、非空內容、processing 回 idle。
- empty model response 先前可被視為「生成完成」，但 UI 沒有 visible fallback。
- tool-only successful response 可能隱藏 JSON 並直接 finalize，導致成功執行但沒有使用者可見回饋。
- worker error / local unavailable 需要在 chat transcript 中形成可理解 message，而不是只改 status。
- UI baseline 只能檢查 pixels 是否接近 approved reference，不能判斷介面是否已產品級、也不能抓
  no-response。

新的 relevant chat gate 必須至少包含：

```bash
timeout 240s scripts/dev/run_ui_pytest.sh \
  tests/unit/ui/chat/test_chat_panel.py \
  tests/unit/ui/components/test_agent_manager.py -q

timeout 180s poetry run pytest --capture=sys \
  tests/unit/llm/agent/test_controller.py \
  tests/unit/llm/agent/test_worker.py -q
```

這些測試要證明：

- normal chat response product flow 有可見 assistant bubble。
- empty response 會變 visible fallback error。
- worker error 會變 visible error。
- local unavailable first-open 會顯示原因。
- ChatPanel 結構包含簡潔 header、單句 workflow guidance、empty state、composer controls、
  disabled Retry、窄 dock bubble wrapping。

broader UI / LLM suite 仍需要跑，但不能取代上述 product-flow gate。

本輪修復後的驗證結果：

- `timeout 240s scripts/dev/run_ui_pytest.sh tests/unit/ui/chat/test_chat_panel.py tests/unit/ui/components/test_agent_manager.py -q`
  - `55 passed`
- `timeout 180s poetry run pytest --capture=sys tests/unit/llm/agent/test_controller.py tests/unit/llm/agent/test_worker.py -q`
  - `75 passed`
- `timeout 300s scripts/dev/run_ui_pytest.sh tests/unit/ui -q`
  - `817 passed`
- `timeout 300s poetry run pytest --capture=sys tests/unit/llm -q`
  - `652 passed`
- `timeout 120s poetry run mkdocs build --strict`
  - passed
- `timeout 60s git diff --check`
  - passed
- `timeout 360s poetry run python scripts/dev/update_quality_dashboard.py`
  - overall `PASS`
  - Basedpyright `0 errors`
  - UI baseline capture `PASS`

2026-05-02 product delivery UI / backend / agent slice 新增驗證：

- assistant product click-through / layout + synthetic pipeline walkthrough：
  - `timeout 240s scripts/dev/run_ui_pytest.sh tests/integration/ui/test_product_walkthrough.py -q`
  - `2 passed`
- combined UI product gate：
  - `timeout 300s scripts/dev/run_ui_pytest.sh tests/unit/ui/chat/test_chat_panel.py tests/unit/ui/chat/test_message_bubble.py tests/unit/ui/components/test_agent_manager.py tests/integration/ui/test_product_walkthrough.py -q`
  - `62 passed`
- combined agent / backend command gate：
  - `timeout 300s poetry run pytest --capture=sys tests/unit/llm/agent/test_controller.py tests/unit/llm/agent/test_worker.py tests/unit/llm/tools/test_application_surface.py tests/unit/backend/application tests/integration/backend/test_application_service_workflow.py -q`
  - `95 passed`
- real-data IO integration:
  - `timeout 300s poetry run pytest --capture=sys tests/integration/io/test_io_integration.py -q`
  - `31 passed, 8 warnings`
- selected tiny pipeline smoke:
  - `timeout 600s poetry run pytest --capture=sys tests/integration/pipeline/test_full_pipeline.py::TestFullPipeline::test_train_and_evaluate_metrics tests/integration/pipeline/test_study_training_e2e.py::TestStudyTrainCycle::test_full_cycle_eegnet -q`
  - `2 passed`
- launcher startup smoke:
  - `timeout 45s xvfb-run -a poetry run python run.py --model local`
  - `MainWindow initialized` appeared before the expected GUI timeout.

這批測試支撐「assistant product layout、visible chat failure handling、主要 UI button path、
backend command adapter、agent mapped command result」的工程狀態。它仍不是人工 Windows
launcher click-through，也不是真 local model 長時間 UI walkthrough。

2026-05-02 local runtime first-run / query command / thesis protocol slice 新增驗證：

- local runtime first-run dialog / disabled state / cache-ready state：
  - `tests/unit/ui/dialogs/test_local_runtime_first_run_dialog.py`
  - `tests/unit/ui/components/test_agent_manager.py`
- service-backed query commands：
  - `EvaluateCommand`
  - `VisualizeCommand`
  - `SaliencyCommand`
  - `NewSessionCommand`
- split audit / thesis artifact protocol：
  - `XBrainLab/backend/dataset/split_audit.py`
  - `scripts/dev/validate_split_artifact.py`
  - `docs/validation/thesis_protocol.md`
  - `docs/validation/split_artifact_schema.json`
  - `tests/unit/backend/dataset/test_split_audit.py`
  - `tests/unit/scripts/test_validate_split_artifact.py`

這批 evidence 支撐 first-run consent、disabled / cache status UI 邏輯、service-backed
evaluation / visualization / saliency summary query、split artifact schema 與 leakage audit。
它仍不是真 local model 長時間 UI walkthrough，也不是 local LLM tool-call accuracy run。external
EEG dataset experiment 屬於 pipeline support，不是 thesis 主評分。

本輪 validation closure：

- `poetry run ruff check XBrainLab/ tests/ scripts/dev/validate_split_artifact.py` -> pass
- `poetry run ruff format --check XBrainLab/ tests/ scripts/dev/validate_split_artifact.py` -> pass
- `git diff --check` -> pass
- `poetry run mkdocs build --strict` -> pass
- UI product gate -> `62 passed`
- backend / split audit / config gate -> `41 passed`
- agent / facade / backend workflow gate -> `130 passed`
- deterministic eval refresh -> `21 / 21` cases passed
- full test gate:
  - `timeout 2400s poetry run pytest tests/ --deselect tests/unit/ui/test_visualization.py::TestSaliency3DEngine --tb=short -q`
  - `4386 passed, 3 skipped, 3 deselected, 1 xfailed, 14 warnings`

2026-05-02 local LLM runtime gate 已另行通過，不屬於 fast dashboard 預設 profile：

- primary model：
  - `microsoft/Phi-4-mini-instruct`
  - estimated download `7.69 GB`
  - prompt smoke `passed`
  - structured-output smoke `passed`
- fallback model：
  - `microsoft/Phi-3.5-mini-instruct`
  - estimated download `7.64 GB`
  - prompt smoke `passed`
  - structured-output smoke `passed`
- cache directory：`XBrainLab/llm/core/models`
- cache usage：約 `15.34 GB`
- cache policy：單模型 10GB 內、總 cache 20GB 內。
- 已刪除 Qwen cache；中國公司或中國來源模型不列入候選。

2026-05-02 launcher / startup smoke：

- `timeout 45s xvfb-run -a poetry run python run.py --model local`
- `MainWindow initialized` 出現後 timeout 結束，屬於 GUI smoke 預期結果。

2026-05-04 Windows launcher automated command walkthrough：

- 新增 `scripts/dev/capture_windows_launcher_walkthrough.py`：
  - 從 Windows `cmd.exe` 執行 Desktop `C:\Users\Administrator\Desktop\XBrainLab.cmd` smoke。
  - 從 PowerShell 執行 repo `xbrainlab_wsl_launcher.ps1` 的 `wsl` smoke，確認 stdout /
    stderr 會 mirror 到 launcher output 和 log。
  - 從同一 PowerShell launcher path 執行 `startup` smoke，經 `wsl.exe` 進 active repo 並跑
    bounded `run.py --model local` startup。
- artifact：
  - `artifacts/launcher/windows-launcher-walkthrough.json`
  - `artifacts/launcher/windows-launcher-walkthrough.md`
- artifact summary：
  - status：`passed`
  - Desktop command points to `/mnt/d/workspace_v2/projects/lab/XBrainLab`
  - `WSL_launcher_smoke_stdout` / `WSL_launcher_smoke_stderr` both observed
  - launcher logs exist under `/mnt/c/Users/Administrator/AppData/Local/XBrainLab/logs/`
  - startup smoke saw `MainWindow initialized`
  - startup smoke was bounded by timeout and returned `0`
  - startup geometry diagnostics logged screen count, screen detail, splash geometry, and
    main-window geometry.
- commands:
  - `timeout 180s poetry run python scripts/dev/capture_windows_launcher_walkthrough.py --output-dir artifacts/launcher --startup-timeout 150`
  - `poetry run pytest --capture=sys tests/unit/scripts/test_capture_windows_launcher_walkthrough.py -q`
  - `3 passed`
  - targeted `ruff check` / `ruff format --check` -> pass.
  - `poetry run basedpyright scripts/dev/capture_windows_launcher_walkthrough.py`
  - `0 errors, 0 warnings, 0 notes`
  - `poetry run mkdocs build --strict` -> pass with existing MkDocs Material warning.
  - `poetry run python tests/architecture_compliance.py` -> Architecture compliant.
  - `git diff --check` -> pass.

這批 evidence 支撐 Windows Desktop command、PowerShell launcher、WSL bridge、launcher log 和
bounded startup path，也支撐 automated startup geometry diagnostics 會被寫入 launcher
stdout/log。它仍不是真人雙螢幕 Desktop click-through、packaged installer approval 或完整
release validation。

2026-05-02 product-delivery final gate：

- backend unit：
  - `timeout 300s poetry run pytest --capture=sys tests/unit/backend -q`
  - `2661 passed, 1 skipped, 1 xfailed, 3 warnings`
- backend + IO integration：
  - `timeout 300s poetry run pytest --capture=sys tests/integration/backend tests/integration/io/test_io_integration.py -q`
  - `33 passed, 8 warnings`
- pipeline integration：
  - `timeout 600s poetry run pytest --capture=sys tests/integration/pipeline -q`
  - `70 passed, 4 warnings`
- UI unit:
  - `timeout 300s scripts/dev/run_ui_pytest.sh tests/unit/ui -q`
  - latest fast dashboard UI Unit Suite：`831 passed`
- LLM unit:
  - LLM / local settings / script unit gate：`674 passed`
- local model preflight:
  - `timeout 120s poetry run python scripts/dev/plan_local_model_download.py --format markdown`
  - `ok=True`; primary `microsoft/Phi-4-mini-instruct` already cached; estimated download `0.00 GB`;
    current / projected cache `15.34 GB`; available disk `158.54 GB`; VRAM estimate `9.0 GB`;
    license MIT
- local runtime health:
  - `timeout 300s poetry run python scripts/dev/inspect_local_assistant_runtime.py --format markdown --prompt-smoke --structured-smoke`
  - classification `gpu-ready`; prompt smoke `passed`; structured-output smoke `passed`

2026-05-02 deterministic tool-call eval baseline：

- methodology references:
  - [Berkeley Function Calling Leaderboard](https://huggingface.co/datasets/gorilla-llm/Berkeley-Function-Calling-Leaderboard)
  - [LangSmith trajectory evaluations](https://docs.langchain.com/langsmith/trajectory-evals)
  - [OpenAI structured outputs](https://platform.openai.com/docs/guides/structured-outputs)
- script:
  - `timeout 120s poetry run python scripts/agent/evals/run_tool_call_eval.py --output-dir artifacts/agent_evals`
- test:
  - `timeout 180s poetry run pytest --capture=sys tests/integration/agent -q`
  - `1 passed`
- artifacts:
  - `artifacts/agent_evals/latest.json`
  - `artifacts/agent_evals/latest.md`
- deterministic baseline result:
  - total cases `21`
  - passed `21`
  - failed `0`
  - intent / tool selection / argument / state-aware / blocked / recovery /
    trajectory / runtime safety accuracy：`100%`

這是 deterministic scripted baseline，不是 local LLM performance claim。Goal 1 後續已新增
local model runner，見下方 `2026-05-04 Local LLM tool-call runner and schema gate`。

2026-05-04 Data Interpretation backend command baseline：

- 新增 backend command contract：
  - `scan_source`
  - `preview_interpretation`
  - `validate_interpretation`
  - `apply_interpretation`
  - `save_interpretation_recipe`
  - `reload_interpretation_recipe`
- validation coverage：
  - GDF + external label carrier scan / preview / `needs_confirmation` validation /
    confirmed apply。
  - labels-only source -> `blocked` validation，apply 不會呼叫 dataset import。
  - recipe save / reload -> reload 只重新 scan / preview / validate，不會自動 apply。
  - capability policy 覆蓋新 commands，並暴露 autonomy policy 欄位。
- commands:
  - `poetry run pytest --capture=sys tests/unit/backend/application/test_application_service.py -q`
  - `28 passed`
  - `poetry run pytest --capture=sys tests/unit/backend/application/test_application_service.py tests/unit/llm/tools/test_application_surface.py tests/unit/llm/agent/test_controller.py tests/integration/backend/test_application_service_workflow.py tests/integration/agent/test_tool_call_eval.py -q`
  - `92 passed`
  - `poetry run ruff check XBrainLab/backend/application tests/unit/backend/application/test_application_service.py scripts/agent/evals/run_tool_call_eval.py`
  - `PASS`
  - `poetry run basedpyright XBrainLab/backend/application scripts/agent/evals/run_tool_call_eval.py tests/unit/backend/application/test_application_service.py`
  - `0 errors, 0 warnings, 0 notes`
  - broader gates：
    - `poetry run ruff check .` -> `PASS`
    - `poetry run basedpyright` -> `0 errors, 0 warnings, 0 notes`
    - `poetry run python tests/architecture_compliance.py` -> `Architecture compliant`
    - `poetry run mkdocs build --strict` -> `PASS`

這批 evidence 只支撐 backend Data Interpretation command baseline 和 deterministic scorer
compatibility。它不支撐「UI import flow 已重做」、「agent tool taxonomy 已遷移」或
「local LLM 真實 tool-call accuracy 已驗證」。

2026-05-04 Data Interpretation agent tool surface slice：

- 新增 agent tool definitions / mock / real tools：
  - `scan_source`
  - `preview_interpretation`
  - `validate_interpretation`
  - `apply_interpretation`
  - `save_interpretation_recipe`
  - `reload_interpretation_recipe`
- `application_surface.py` 會把上述 tools 映射到同名 ApplicationService commands，並把
  autonomy policy 欄位帶進 `ToolAvailability.to_dict()`。
- `LLMController` 會依 backend policy 的 `requires_confirmation` / `confirmation_required`
  暫停 dynamic boundary，確認後對 `apply_interpretation` 注入 `confirmed=True`。
- `BackendFacade(study)` 重用同一個 ApplicationService，已用 agent surface test 覆蓋
  scan -> preview -> validate 連續 tool call 不遺失 lifecycle state。
- commands:
  - `poetry run pytest --capture=sys tests/unit/llm/tools/test_application_surface.py tests/unit/llm/tools/test_definitions.py tests/unit/llm/tools/test_mock_tools.py tests/unit/llm/agent/test_controller.py -q`
  - `219 passed`
  - `poetry run pytest --capture=sys tests/unit/llm/tools/test_application_surface.py tests/unit/llm/tools/test_definitions.py tests/unit/llm/tools/test_mock_tools.py tests/unit/llm/tools/real/test_real_tools.py tests/unit/llm/agent/test_controller.py tests/unit/llm/agent/test_assembler_stage.py tests/unit/llm/agent/test_verification_layer.py tests/integration/agent/test_product_flow.py tests/integration/agent/test_tool_call_eval.py -q`
  - `286 passed`
  - `poetry run ruff check <slice files>`
  - `PASS`
  - `poetry run basedpyright <slice source files>`
  - `0 errors, 0 warnings, 0 notes`
  - broader gates:
    - `poetry run ruff check .` -> `PASS`
    - `poetry run basedpyright` -> `0 errors, 0 warnings, 0 notes`
    - `poetry run mkdocs build --strict` -> `PASS`
    - `poetry run python tests/architecture_compliance.py` -> `Architecture compliant`
    - `poetry run python scripts/agent/evals/run_tool_call_eval.py --output-dir artifacts/agent_evals_tmp_goal1_agent_surface`
      -> pass; temporary artifact directory removed.

這批 evidence 支撐 agent taxonomy / command mapping / dynamic confirmation boundary。它仍不支撐
「UI import flow 已重做」、「headless / MCP adapter 已完成」或「local LLM 真實 tool-call
accuracy 已驗證」。

2026-05-04 Dataset panel Data Interpretation entry slice：

- Dataset sidebar 主按鈕改為 `Interpret Data Source`。
- UI import action 走 `scan_source` -> `preview_interpretation` ->
  `validate_interpretation` -> `apply_interpretation`。
- 新增 preview dialog，顯示 source、metadata preview、warnings、confirmation items、
  validation decision 和 blocked reasons。
- product walkthrough synthetic `.fif` import 已通過新 dialog / apply path。
- commands:
  - `poetry run pytest --capture=sys tests/unit/ui/test_ui_misc.py::TestDatasetActionHandler tests/unit/ui/dialogs/dataset/test_data_interpretation_preview_dialog.py tests/unit/ui/dataset/test_panel.py tests/integration/ui/test_product_walkthrough.py::test_pipeline_product_walkthrough_uses_user_facing_actions -q`
  - `50 passed`
  - `poetry run pytest --capture=sys tests/unit/ui/dataset tests/unit/ui/dialogs/dataset tests/unit/ui/test_ui_misc.py tests/unit/ui/test_application_capabilities.py tests/integration/ui/test_product_walkthrough.py -q`
  - `166 passed`
  - `poetry run pytest --capture=sys tests/integration/agent/test_product_flow.py tests/unit/ui/chat/test_chat_panel.py tests/unit/ui/components/test_agent_manager.py -q`
  - `76 passed`
  - `poetry run ruff check <ui data interpretation slice files>` -> `PASS`
  - `poetry run basedpyright <ui data interpretation source files>` ->
    `0 errors, 0 warnings, 0 notes`
  - broader gates:
    - `poetry run ruff check .` -> `PASS`
    - `poetry run basedpyright` -> `0 errors, 0 warnings, 0 notes`
    - `poetry run mkdocs build --strict` -> `PASS`
    - `poetry run python tests/architecture_compliance.py` -> `Architecture compliant`
    - `git diff --check` -> `PASS`

這批 evidence 支撐 Dataset panel main import entry 的新心智模型。後續 recipe save option
和 headless / MCP-ready adapter 已補；label import 已降為 service-backed compatibility path，
且後續已整合進 Data Interpretation recipe trace。stdio MCP server baseline、stdio external-client
walkthrough artifact、Inspector release config、Inspector GUI walkthrough 和 local LLM 真實
ChatPanel walkthrough 都已另有 evidence；這個早期 gate 本身不能替代那些後續 evidence。

2026-05-04 MCP-ready automation adapter + deterministic eval expansion：

- 新增 `XBrainLab.backend.application.automation`：
  - `command_specs(service)` 產生所有 `ApplicationService` command 的 JSON schema、
    workflow taxonomy 和 live capability / autonomy policy。
  - `mcp_tool_specs(service)` 使用同一份 command schema 產生 MCP-shaped tool specs。
  - `execute_automation_payload(service, payload)` 將 JSON payload 轉 typed command，並只透過
    `ApplicationService.execute()` 執行；adapter 本身不新增 controller business logic。
- 新增 `scripts/dev/run_application_command.py`：
  - `--list-schemas` 輸出 headless command schema。
  - `--mcp-tools` 輸出 MCP-ready tool schema。
  - `--payload` / `--payload-file` 在同一個 headless `ApplicationService` session 中跑一個或多個
    command payload。
- deterministic tool-call eval：
  - cases：`54 / 54` pass。
  - multi-turn cases：`15`。
  - negative / blocked / confirmation / missing-input / recovery cases：`34 / 54`。
  - case artifact 現在保存 user command、initial state、available command summary、expected /
    actual verification result、expected state delta、parsed tool call、simulated backend result、
    visible response 和 score breakdown。
- commands:
  - `poetry run pytest --capture=sys tests/unit/backend/application/test_automation.py -q`
  - `7 passed`
  - `poetry run pytest --capture=sys tests/integration/agent/test_tool_call_eval.py -q`
  - `1 passed`
  - `poetry run ruff check XBrainLab/backend/application/automation.py scripts/dev/run_application_command.py scripts/agent/evals/run_tool_call_eval.py tests/unit/backend/application/test_automation.py tests/integration/agent/test_tool_call_eval.py`
  - `PASS`
  - `poetry run basedpyright XBrainLab/backend/application/automation.py scripts/dev/run_application_command.py scripts/agent/evals/run_tool_call_eval.py tests/unit/backend/application/test_automation.py tests/integration/agent/test_tool_call_eval.py`
  - `0 errors, 0 warnings, 0 notes`
  - `poetry run python scripts/agent/evals/run_tool_call_eval.py --output-dir artifacts/agent_evals`
  - refreshed `artifacts/agent_evals/latest.json` and `artifacts/agent_evals/latest.md`

這批 evidence 支撐 headless / MCP-ready command schema 和 deterministic engineering
tool-call baseline。它仍不支撐「MCP server 已完成」、「local LLM 真實 tool-call accuracy 已驗證」、
或「UI-observable replay 已完成」。

2026-05-04 stdio MCP server baseline：

- 新增 `XBrainLab.mcp.server`：
  - 支援 MCP `initialize` lifecycle，回傳 `tools` capability。
  - 支援 `tools/list`，直接使用 `mcp_tool_specs(service)` 暴露同一組 command schema、
    output schema、taxonomy 和 live capability / autonomy metadata。
  - 支援 `tools/call`，在同一個 server session 中將 MCP arguments 轉成
    `execute_automation_payload()`，並只透過 `ApplicationService.execute()` 執行。
  - tool result 同時回傳 MCP `content` 和 `structuredContent`；schema / business failure 以
    `isError: true` 表達，方便 external agent self-correction。
- 新增 `scripts/dev/run_mcp_server.py` 作為 stdio server entrypoint。
- commands:
  - `poetry run pytest --capture=sys tests/unit/mcp tests/integration/mcp -q`
  - `6 passed`
  - `poetry run pytest --capture=sys tests/unit/mcp tests/integration/mcp tests/unit/backend/application/test_automation.py -q`
  - `13 passed`
  - `poetry run ruff check XBrainLab/mcp XBrainLab/backend/application/automation.py scripts/dev/run_mcp_server.py tests/unit/mcp tests/integration/mcp`
  - `PASS`
  - `poetry run basedpyright XBrainLab/mcp XBrainLab/backend/application/automation.py scripts/dev/run_mcp_server.py tests/unit/mcp tests/integration/mcp`
  - `0 errors, 0 warnings, 0 notes`

這批 evidence 支撐「已有可啟動的 stdio MCP server baseline，且 MCP calls 不繞過
ApplicationService」。它仍不支撐外部 MCP client / Inspector walkthrough、Windows release
config、HTTP transport、或 product completion。

2026-05-04 MCP stdio external-client walkthrough：

- 新增 `scripts/dev/capture_mcp_stdio_walkthrough.py`：
  - client process 只 import Python standard-library modules。
  - prepared XBrainLab runtime 仍在 server process：`scripts/dev/run_mcp_server.py`。
  - client 透過 MCP stdio JSON-RPC 跑 `initialize`、`tools/list`、`scan_source`、
    `preview_interpretation`、`validate_interpretation`。
  - artifact 保存到 `artifacts/mcp/stdio-walkthrough.json` 和
    `artifacts/mcp/stdio-walkthrough.md`。
- artifact summary：
  - initialized：`True`
  - tool count：`28`
  - `scan_source` listed：`True`
  - `scan_source` taxonomy：`data_interpretation`
  - `scan_source` status：`ok`
  - `preview_interpretation` status：`ok`
  - `validate_interpretation` status：`ok`，visible text 為
    `Interpretation validation: needs_confirmation.`
- commands:
  - `poetry run python scripts/dev/capture_mcp_stdio_walkthrough.py --output-dir artifacts/mcp`
  - wrote `artifacts/mcp/stdio-walkthrough.json` and `.md`
  - `poetry run pytest --capture=sys tests/unit/mcp tests/integration/mcp -q`
  - `7 passed`
  - `poetry run ruff check scripts/dev/capture_mcp_stdio_walkthrough.py tests/integration/mcp/test_stdio_walkthrough_artifact.py`
  - `PASS`
  - `poetry run basedpyright scripts/dev/capture_mcp_stdio_walkthrough.py tests/integration/mcp/test_stdio_walkthrough_artifact.py`
  - `0 errors, 0 warnings, 0 notes`

這批 evidence 支撐 external stdio client 可以不安裝 XBrainLab EEG / PyQt / PyTorch client-side
dependencies，並透過 prepared XBrainLab MCP server 走同一套 ApplicationService command surface。
它本身仍不支撐 MCP Inspector GUI click-through、Windows release registration / config、HTTP
transport、long-running training tool through MCP、或 product completion；Inspector release config
和 GUI walkthrough 已由後續 artifacts 補上。

2026-05-04 MCP Inspector-style release config baseline：

- 新增 `scripts/dev/run_mcp_server_for_client.sh`：
  - 外部 MCP client / Inspector 只需要啟動這個 prepared runtime wrapper。
  - wrapper 會切回 active repo，再用 `poetry run python scripts/dev/run_mcp_server.py`
    啟動真正 server。
- 新增 `scripts/dev/write_mcp_client_config.py`：
  - 產生 `artifacts/mcp/xbrainlab-mcp.json` 和 `artifacts/mcp/xbrainlab-mcp.md`。
  - config 使用 Inspector 支援的 `mcpServers` / `type: "stdio"` / `command` / `args` 格式。
  - `default-server` 用 `bash <wrapper>`，`xbrainlab-windows-wsl` 用
    `wsl.exe bash <wrapper>`。
  - validator 明確拒絕直接把 client config 指到 client-side Python，避免把 EEG / PyQt /
    PyTorch dependencies 推給 external client。
- 新增 `tests/unit/scripts/test_write_mcp_client_config.py` 和
  `tests/integration/mcp/test_client_config.py`：
  - unit tests 驗證 config shape、server command extraction、committed artifact contract 和
    CLI regeneration。
  - integration test 讀 committed config，透過 config command 啟動 prepared runtime wrapper，
    再重跑 stdio `initialize`、`tools/list`、`scan_source`、`preview_interpretation`
    walkthrough。
- commands:
  - `poetry run pytest --capture=sys tests/unit/scripts/test_write_mcp_client_config.py tests/integration/mcp/test_client_config.py -q`
  - `6 passed`
  - manual config walkthrough:
    `poetry run python scripts/dev/capture_mcp_stdio_walkthrough.py --output-dir /tmp/xbrainlab-mcp-config-walkthrough --server-command bash /mnt/d/workspace_v2/projects/lab/XBrainLab/scripts/dev/run_mcp_server_for_client.sh`
  - wrote `/tmp/xbrainlab-mcp-config-walkthrough/stdio-walkthrough.json` and `.md`
  - first official Inspector CLI attempt failed with `Connection closed` because Windows-side
    `wsl.exe` launched a non-login shell where `poetry` was not on PATH.
  - wrapper now resolves `POETRY_BIN`, `command -v poetry`, or `$HOME/.local/bin/poetry`.
  - Windows-side WSL stdio smoke:
    `timeout 10s /mnt/c/Windows/System32/wsl.exe bash /mnt/d/workspace_v2/projects/lab/XBrainLab/scripts/dev/run_mcp_server_for_client.sh`
    with MCP `initialize` request -> valid JSON-RPC initialize response.
  - official Inspector CLI:
    `timeout 180s '/mnt/c/Program Files/nodejs/npx' -y @modelcontextprotocol/inspector --cli --config artifacts/mcp/xbrainlab-mcp.json --server xbrainlab-windows-wsl --method tools/list`
    -> exit `0`, `28` tools listed.
  - artifact:
    `artifacts/mcp/inspector-cli-tools-list.json` / `.md`

這批 evidence 支撐 Inspector-style release config baseline、prepared-runtime launch path 和 official
Inspector CLI `tools/list`。它本身仍不支撐 Inspector GUI click-through、Windows Desktop 真人啟動、HTTP
transport、long-running training through MCP 或 product completion；Inspector GUI baseline 已由下一段
artifact 補上。

2026-05-04 MCP Inspector GUI click-through baseline：

- script：`scripts/dev/capture_mcp_inspector_gui_walkthrough.py`
- artifact：
  - `artifacts/mcp/inspector-gui-walkthrough.json`
  - `artifacts/mcp/inspector-gui-walkthrough.md`
  - `artifacts/mcp/inspector-gui-connected.png`
- command：
  - `timeout 210s poetry run python scripts/dev/capture_mcp_inspector_gui_walkthrough.py --output-dir artifacts/mcp --timeout-seconds 150`
- result：
  - status：`passed`
  - visible Inspector state：`Connect` clicked、`Connected` visible、`Disconnect` visible、
    server `xbrainlab` visible、Tools panel visible。
  - client boundary：Inspector / Chrome run as Windows external client processes; server entry uses
    `wsl.exe bash /mnt/d/workspace_v2/projects/lab/XBrainLab/scripts/dev/run_mcp_server_for_client.sh`
    to launch the prepared XBrainLab runtime.
  - visible Data Interpretation tools:
    - `scan_source` / `Scan Source`
    - `preview_interpretation` / `Preview Interpretation`
    - `validate_interpretation` / `Validate Interpretation`
    - `apply_interpretation` / `Apply Interpretation`
  - cleanup: post-run Windows `node.exe` Inspector processes and Chrome processes tied to
    XBrainLab MCP artifacts were absent.
- unit/static:
  - `poetry run pytest --capture=sys tests/unit/scripts/test_capture_mcp_inspector_gui_walkthrough.py -q`
  - `5 passed`
  - targeted `ruff check` / `ruff format --check` clean
  - `poetry run basedpyright scripts/dev/capture_mcp_inspector_gui_walkthrough.py`
  - `0 errors, 0 warnings, 0 notes`

這批 evidence 支撐 automated MCP Inspector GUI click-through with connected tools list and prepared
Windows WSL runtime wrapper。它仍不是 human GUI session、full MCP client certification、HTTP
transport、long-running training through MCP、Windows Desktop真人啟動或 product completion。

2026-05-04 Local LLM tool-call runner and schema gate：

- 新增 `scripts/agent/evals/run_local_tool_call_eval.py`：
  - 使用同一份 `scripts/agent/evals/run_tool_call_eval.py` case schema / scorer。
  - 接真 local model raw output，不執行 workflow command。
  - 每個 case 保存 prompt-derived state、raw output、parsed tool calls、schema verification、
    score breakdown 和 failure taxonomy。
  - `repeat_count < 3` 或 cases `< 50` 時標成 exploratory；本次 primary / fallback full run
    都是 `54` cases x `3` repeats，非 exploratory。
- `CommandParser` 現在可解析：
  - `parameters`
  - `arguments`
  - top-level `name`
  - `tool_calls` list
- `VerificationLayer` 現在可用 registered tool schema 檢查：
  - unknown / unregistered tool。
  - required parameter。
  - JSON-like type。
  - enum value。
  `LLMController` 會用 real `ToolRegistry` schema 建立 verifier，因此可在 execution 前攔下
  可解析但不可執行的 tool JSON。
- local runtime preflight：
  - primary / fallback cache 都已存在，不需下載。
  - cache usage：`15.34 GB`，低於 `20 GB` 上限。
  - classification：`gpu-ready`。
- primary run：
  - command：`timeout 3600s poetry run python scripts/agent/evals/run_local_tool_call_eval.py --model-role primary --repeat-count 3 --max-new-tokens 128 --output-dir artifacts/agent_evals/local_primary`
  - artifact：
    - `artifacts/agent_evals/local_primary/local_microsoft_phi_4_mini_instruct.json`
    - `artifacts/agent_evals/local_primary/local_microsoft_phi_4_mini_instruct.md`
  - result：`18 / 54` pass，pass rate `33.33%`。
  - schema-invalid tool outputs：`9`。
- fallback run：
  - command：`timeout 3600s poetry run python scripts/agent/evals/run_local_tool_call_eval.py --model-role fallback --repeat-count 3 --max-new-tokens 128 --output-dir artifacts/agent_evals/local_fallback`
  - artifact：
    - `artifacts/agent_evals/local_fallback/local_microsoft_phi_3.5_mini_instruct.json`
    - `artifacts/agent_evals/local_fallback/local_microsoft_phi_3.5_mini_instruct.md`
  - result：`20 / 54` pass，pass rate `37.04%`。
  - schema-invalid tool outputs：`6`。
- targeted validation:
  - `poetry run pytest --capture=sys tests/unit/llm/test_parser.py tests/unit/llm/agent/test_verification_layer.py tests/unit/scripts/test_run_local_tool_call_eval.py -q`
  - `44 passed`
  - `poetry run pytest --capture=sys tests/unit/llm/agent/test_verification_layer.py tests/unit/llm/agent/test_controller.py tests/unit/llm/agent/test_controller_integration.py tests/integration/agent/test_product_flow.py tests/integration/agent/test_tool_call_eval.py -q`
  - `98 passed`
  - `poetry run pytest --capture=sys tests/unit/llm/agent tests/unit/llm/tools tests/unit/scripts/test_run_local_tool_call_eval.py tests/unit/llm/test_parser.py -q`
  - `383 passed`
  - `poetry run ruff check XBrainLab/llm/agent/parser.py XBrainLab/llm/agent/verifier.py XBrainLab/llm/agent/controller.py scripts/agent/evals/run_local_tool_call_eval.py tests/unit/llm/test_parser.py tests/unit/llm/agent/test_verification_layer.py tests/unit/scripts/test_run_local_tool_call_eval.py`
  - `PASS`
  - `poetry run basedpyright XBrainLab/llm/agent/parser.py XBrainLab/llm/agent/verifier.py XBrainLab/llm/agent/controller.py scripts/agent/evals/run_local_tool_call_eval.py tests/unit/llm/test_parser.py tests/unit/llm/agent/test_verification_layer.py tests/unit/scripts/test_run_local_tool_call_eval.py`
  - `0 errors, 0 warnings, 0 notes`

這批 evidence 支撐「真 local LLM runner / parser / schema gate 已建立」。它明確不支撐
「local LLM tool-call accuracy thesis-ready」、「真 ChatPanel 長時間 workflow 已通過」或
「agent 可無監督完成多步 workflow」。

2026-05-04 Local assistant tool-call guardrail smoke：

- 變更範圍：
  - `CommandParser` 支援 top-level tool-call array 和 OpenAI-style function tool call。
  - `VerificationLayer` 新增 `PlaceholderArgumentValidator`，拒絕模型自造的 placeholder
    source / file / recipe path。
  - `LLMController` 新增 requested-intent boundary：最新使用者要求的 workflow command 若被
    `ApplicationService` capability policy 擋下，agent 不能改叫其他 tool 來替代。
  - `LLMController` 也把 inferred latest intent 放入 prompt context，讓 local model 不必從多輪
    history 猜下一個 workflow step。
  - local eval runner 使用同一 guardrail 語意，且成功 tool-call 的 `visible_response` 不再保存
    raw JSON tool syntax。
  - prompt / schema 補 standard preprocess、dataset split 和 state-authoritative latest-turn
    規則。
- preflight：
  - primary / fallback classification：`gpu-ready`。
  - cache usage：`15.34 GB`，低於 `20 GB` 上限。
  - no download；沒有 disallowed cache candidates。
- exploratory smoke artifacts：
  - primary：
    `artifacts/agent_evals/local_primary_guardrail_smoke/local_microsoft_phi_4_mini_instruct.md`
    -> `6 / 6` pass。
  - fallback：
    `artifacts/agent_evals/local_fallback_guardrail_smoke/local_microsoft_phi_3.5_mini_instruct.md`
    -> `6 / 6` pass。
- targeted validation:
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

這批 evidence 支撐「local assistant tool-call guardrails 方向有效，且不再把 raw tool syntax
當作 visible response」。此段為 guardrail smoke 當時的結論；正式 full rerun 已由下方
normalization slice 更新。

2026-05-04 Local assistant tool-call normalization full rerun：

- 變更範圍：
  - `CommandParser` 進一步支援 command-only JSON 和 bare tool name 輸出。
  - 新增 `tool_call_normalizer`，在 verifier 前處理 local model 常見但可安全歸一的 tool
    variants：`create_epoch` -> `epoch_data`、`train` -> `start_training`、
    `get_dataset_info` -> typed `query_state`、latest-turn scan / preview / validate / apply
    substitute、BIDS source hint、subject override、dataset split defaults 和 recipe save default。
  - `query_state` agent tool 走 `ApplicationService` / `QueryStateCommand`，不再只依賴
    legacy `get_dataset_info` 心智模型。
  - placeholder validator 擋下 prose path，例如 `Please provide the absolute path...`。
  - local eval 將 backend result interpretation 納入 scoring，讓 successful load、
    confirmation-boundary validation、recoverable backend failure 不被誤判成 raw tool 成功。
- full local eval artifacts：
  - primary：
    `artifacts/agent_evals/local_primary/local_microsoft_phi_4_mini_instruct.md`
    -> `53 / 54` pass (`98.15%`)。
  - fallback：
    `artifacts/agent_evals/local_fallback/local_microsoft_phi_3.5_mini_instruct.md`
    -> `53 / 54` pass (`98.15%`)。
  - runtime classification：primary / fallback 都是 `gpu-ready`。
  - cache usage：`15.34 GB`，低於 `20 GB` 上限。
  - no download。
- targeted validation：
- `poetry run pytest --capture=sys tests/unit/llm/test_parser.py tests/unit/llm/agent/test_tool_call_normalizer.py tests/unit/llm/agent/test_verification_layer.py tests/unit/scripts/test_run_local_tool_call_eval.py tests/unit/llm/tools/test_application_surface.py tests/unit/llm/agent/test_controller.py tests/unit/llm/agent/test_intent.py -q`
  - `156 passed`
  - targeted `poetry run ruff check ...`
  - pass
  - targeted `poetry run basedpyright ...`
  - `0 errors, 0 warnings, 0 notes`
- regression / docs gates：
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

這批 evidence 支撐 local assistant tool-call guardrail 已從不可用的 `33%` / `37%` 區間提升到
工程 baseline 可用區間；它仍不支撐 thesis-ready claim，因為 benchmark 仍只有 `54` cases、
不是要求的 `100` thesis candidate cases，且仍有 bandpass-vs-standard preprocess 語意
failure。

2026-05-04 Local LLM tool-call thesis-candidate 100-case rerun：

- 變更範圍：
  - deterministic / local eval cases 從 `54` 擴到 `100`，覆蓋 Data Interpretation file /
    folder / BIDS / recipe、metadata choice、relative / missing path、confirmation、blocked /
    recovery、多輪 workflow、bandpass-only vs standard preprocess、dataset split、visualization /
    saliency readiness 和 query-state。
  - local parser / normalizer / verifier 補上 partial tool-name JSON、command-only JSON with
    confirmation metadata、blank / relative source path rejection、metadata choice cleanup、
    bandpass-only demotion、dataset split vs training mode normalization、epoch default window、
    visualization / saliency substitute guardrail。
  - controller requested-intent boundary 會擋下 saliency / visualization request 被模型改成
    setup / UI-route tool 的 substitute call。
- resource boundary：
  - primary / fallback model cache 已存在；本輪沒有下載模型。
  - runtime classification：primary / fallback 都是 `gpu-ready`。
  - cache usage：`15.34 GB`，低於 `20 GB` 上限。
- deterministic baseline：
  - command：`poetry run python scripts/agent/evals/run_tool_call_eval.py --repeat-count 2 --output-dir artifacts/agent_evals/deterministic`
  - artifacts：
    - `artifacts/agent_evals/deterministic/latest.md`
    - full deterministic JSON is generated by the command but not tracked because it exceeds
      the repository large-file hook limit.
  - result：`100 / 100` pass (`100.00%`)。
- primary local model：
  - command：`timeout 3600s poetry run python scripts/agent/evals/run_local_tool_call_eval.py --model-role primary --repeat-count 3 --max-new-tokens 128 --output-dir artifacts/agent_evals/local_primary`
  - artifacts：
    - `artifacts/agent_evals/local_primary/local_microsoft_phi_4_mini_instruct.json`
    - `artifacts/agent_evals/local_primary/local_microsoft_phi_4_mini_instruct.md`
  - result：`100 / 100` pass (`100.00%`)。
- fallback local model：
  - command：`timeout 3600s poetry run python scripts/agent/evals/run_local_tool_call_eval.py --model-role fallback --repeat-count 3 --max-new-tokens 128 --output-dir artifacts/agent_evals/local_fallback`
  - artifacts：
    - `artifacts/agent_evals/local_fallback/local_microsoft_phi_3.5_mini_instruct.json`
    - `artifacts/agent_evals/local_fallback/local_microsoft_phi_3.5_mini_instruct.md`
  - result：`100 / 100` pass (`100.00%`)。
- targeted validation:
  - `poetry run pytest --capture=sys tests/unit/llm/test_parser.py tests/unit/llm/agent/test_tool_call_normalizer.py tests/unit/llm/agent/test_verification_layer.py tests/unit/llm/agent/test_intent.py tests/unit/scripts/test_run_local_tool_call_eval.py tests/unit/llm/agent/test_controller.py -q`
  - `166 passed`
  - targeted `poetry run ruff check ...`
  - pass
- regression / docs / architecture gates：
  - `poetry run pytest --capture=sys tests/unit/llm/agent tests/unit/llm/tools tests/unit/scripts/test_run_local_tool_call_eval.py tests/unit/llm/test_parser.py tests/unit/llm/test_pipeline_state.py tests/unit/llm/tools/test_application_surface.py -q`
  - `487 passed`
  - `poetry run ruff check .`
  - pass
  - `poetry run basedpyright`
  - `0 errors, 0 warnings, 0 notes`
  - `poetry run mkdocs build --strict`
  - pass
  - `git diff --check`
  - pass
  - `poetry run python tests/architecture_compliance.py`
  - `Architecture compliant!`

這批 evidence 支撐 thesis-candidate local tool-call benchmark：同一 `100` cases 被 deterministic
baseline、primary local model 和 fallback local model 各自以可重跑 artifact 驗證。它仍不能替代
true ChatPanel multi-turn walkthrough、Windows launcher click-through、
MCP HTTP / long-running client workflows、完整 import wizard UI 驗收或論文最終統計報告。

2026-05-04 Tool-call best-practices 117-case dashboard refresh：

- design input：
  - OpenAI Structured Outputs / function calling：schema-constrained arguments、validation、
    bounded repair。
  - Berkeley Function Calling Leaderboard：multi-turn、multi-language、multiple tool candidates、
    relevance / no-call、blocked / recovery coverage。
  - LangSmith agent trajectory evaluation：評估 tool path、arguments、state transition 和
    visible response，而不只看 final answer。
- 變更範圍：
  - prompt-facing `schema_contract.py` 以 tool taxonomy 輸出 stricter contracts，並把
    Data Interpretation 標成資料入口主線、`load_data / attach_labels` 標成 legacy compatibility。
  - `preview_interpretation.choices` 變成 structured object：selected EEG files、label carrier、
    event role、class map、anchor、subject / session / task / run。
  - controller 在 no-tool / ask-clarification intent 上可直接用使用者語言回覆，不執行 mutating
    tool。
  - parser / normalizer 支援 local model 常見 function-call variants，並修補 safe structured
    output drift；verifier 新增 nested object required / enum / type / unknown-field checks。
  - eval cases 擴到 `117`，新增 Chinese、mixed Chinese / English、ambiguous request、missing
    input、no-call、should-not-call、wrong-tool temptation、blocked command、multi-intent、
    multi-turn recovery、Data Interpretation confirmation boundary、BIDS / label ambiguity /
    subject metadata、destructive / long-running confirmation 和 EEG/BCI domain phrasing。
  - scorer 新增 tool/no-tool decision、clarification behavior、confirmation boundary、visible
    response quality、case family pass rates、failure taxonomy、worst cases 和 repeated-run
    stability。
- deterministic baseline：
  - command：`poetry run python scripts/agent/evals/run_tool_call_eval.py --output-dir artifacts/agent_evals --repeat-count 2`
  - artifact：`artifacts/agent_evals/latest.json` / `latest.md`
  - result：`117 / 117` pass (`100.00%`)。
- primary local model：
  - command：`poetry run python scripts/agent/evals/run_local_tool_call_eval.py --model-role primary --repeat-count 3 --output-dir artifacts/agent_evals/local_primary --max-new-tokens 160`
  - artifact：`artifacts/agent_evals/local_primary/local_microsoft_phi_4_mini_instruct.json` /
    `.md`
  - result：`117 / 117` pass (`100.00%`)。
- fallback local model：
  - command：`poetry run python scripts/agent/evals/run_local_tool_call_eval.py --model-role fallback --repeat-count 3 --output-dir artifacts/agent_evals/local_fallback --max-new-tokens 160`
  - artifact：`artifacts/agent_evals/local_fallback/local_microsoft_phi_3.5_mini_instruct.json` /
    `.md`
  - result：`117 / 117` pass (`100.00%`)。
- dashboard：
  - command：`poetry run python scripts/agent/evals/write_tool_call_eval_dashboard.py --eval-dir artifacts/agent_evals`
  - artifact：`artifacts/agent_evals/dashboard.md`
  - visible sections：overall model comparison、metric pass rates、family pass rates、failure
    taxonomy、worst cases、source / artifact paths、thesis claim boundary。

這批 evidence 支撐本 benchmark slice 的 thesis-candidate tool-call claim。它仍不能替代
UI-observable automated walkthrough、human Windows desktop acceptance、雙螢幕 / DPI、長時間
local model session、EEG training quality 或 product completion。

2026-05-04 UI-observable automated human-like walkthrough：

- script：`scripts/dev/capture_human_like_product_walkthrough.py`
- artifacts：
  - `artifacts/ui/human-like-walkthrough/human-like-walkthrough.json`
  - `artifacts/ui/human-like-walkthrough/human-like-walkthrough.md`
  - `artifacts/ui/human-like-walkthrough/*.png` (`20` screenshots)
  - `artifacts/ui/human-like-walkthrough/walkthrough-import.recipe.json`
- coverage：
  - app startup / main window initial state / Dataset page。
  - data source selection and Data Interpretation wizard scan / preview / confirm / apply /
    save recipe / reload recipe。
  - safe / needs_confirmation / blocked decision probes。
  - preprocessing、epoch creation、dataset generation。
  - training readiness by configuring EEGNet CPU training settings without starting a long run。
  - evaluation / visualization / saliency readiness queries。
  - ChatPanel empty state、normal message、missing-input clarification、blocked command、
    successful tool result summary、narrow panel、repeated open / close。
  - reset / new session confirmation boundary and error recovery after a missing scan.
  - visible text snapshots、button enabled / disabled state、workflow state snapshots、
    command / tool transcript、user-facing transcript、CommandResult payloads、process/thread notes.
  - top-level `observable_evidence` indexes visible text、button states、workflow snapshots and
    backend state snapshots by phase；`ui_quality_review` records nonblank screenshot checks,
    forbidden visible text findings and the human-review boundary.
- observed result：
  - status：`passed`
  - phases：`26 / 26`
  - screenshots：`20`
  - human desktop acceptance：`not performed`
  - observable evidence：`26` visible text snapshots、`26` button-state snapshots、`26`
    workflow/backend snapshots.
  - UI quality review：automated checks `passed`、forbidden visible text findings `0`.
  - resource notes：Python thread count returned to `1`; Qt active thread count `0`.

這批 evidence 支撐 automated UI-observable replay 條件下主要 path 可操作。它仍不能宣稱真人
Windows desktop launcher、雙螢幕 / DPI、長時間 true local model desktop session 或 full
product completion 已完成。

2026-05-04 agent analysis-tool exposure validation：

- 變更範圍：
  - `evaluate` / `visualize` / `saliency` 新增 tool definitions、mock tools、real tools 和
    `get_all_tools()` registration。
  - `application_surface.py` 直接轉成 `EvaluateCommand`、`VisualizeCommand`、
    `SaliencyCommand`，因此 execution / blocked reason 走 `ApplicationService` capability
    policy。
  - `CommandParser` 支援三個 bare tool names；intent mapping 補上 `evaluate`。
- deterministic eval refresh：
  - command：`poetry run python scripts/agent/evals/run_tool_call_eval.py --output-dir artifacts/agent_evals --repeat-count 2`
  - artifact：`artifacts/agent_evals/latest.json` / `latest.md`
  - result：`100 / 100` pass (`100.00%`)。
- affected-case local LLM smoke：
  - primary command：`timeout 1200s poetry run python scripts/agent/evals/run_local_tool_call_eval.py --model-role primary --repeat-count 3 --max-new-tokens 128 --case-id saliency-before-trained-block --case-id visualize-before-trained-block --case-id trained-visualize-ready-summary --case-id trained-saliency-ready-summary --case-id dataset-saliency-readiness-summary --output-dir artifacts/agent_evals/local_primary_analysis_tools`
  - primary result：`5 / 5` pass (`100.00%`)，runtime `gpu-ready`，cache `15.34 GB`，no download。
  - fallback command：`timeout 1200s poetry run python scripts/agent/evals/run_local_tool_call_eval.py --model-role fallback --repeat-count 3 --max-new-tokens 128 --case-id saliency-before-trained-block --case-id visualize-before-trained-block --case-id trained-visualize-ready-summary --case-id trained-saliency-ready-summary --case-id dataset-saliency-readiness-summary --output-dir artifacts/agent_evals/local_fallback_analysis_tools`
  - fallback result：`5 / 5` pass (`100.00%`)，runtime `gpu-ready`，cache `15.34 GB`，no download。
- regression gates:
  - `poetry run pytest --capture=sys tests/unit/llm/tools/test_definitions.py tests/unit/llm/tools/test_mock_tools.py tests/unit/llm/tools/test_application_surface.py tests/unit/llm/tools/real/test_real_tools.py tests/unit/llm/test_parser.py tests/unit/llm/agent/test_intent.py tests/unit/llm/agent/test_assembler_stage.py tests/unit/llm/test_tools_and_debug.py tests/unit/llm/test_tools_and_debug_cov.py -q`
  - `293 passed`
  - `poetry run pytest --capture=sys tests/unit/llm/agent tests/unit/llm/tools tests/unit/llm/test_parser.py tests/unit/llm/test_tools_and_debug.py tests/unit/llm/test_tools_and_debug_cov.py -q`
  - `516 passed`
  - targeted `ruff` -> pass
  - `poetry run basedpyright` -> `0 errors, 0 warnings, 0 notes`
  - `poetry run ruff check .` -> pass
  - `poetry run python tests/architecture_compliance.py` -> `Architecture compliant!`
  - `poetry run mkdocs build --strict` -> pass
  - `git diff --check` -> pass

這批 evidence 支撐 analysis commands 已成為 ApplicationService-backed agent tools。它仍不支撐
ChatPanel dataset -> training -> evaluation / visualization / saliency 長鏈完成。

2026-05-04 ChatPanel local training-readiness boundary walkthrough：

- script：`scripts/dev/capture_chatpanel_local_training_readiness_walkthrough.py`
- artifact：
  - `artifacts/ui/chatpanel-local-training-readiness/chatpanel-training-readiness-ready.png`
  - `artifacts/ui/chatpanel-local-training-readiness/chatpanel-training-readiness-turn-1.png`
  - `artifacts/ui/chatpanel-local-training-readiness/chatpanel-training-readiness-turn-2.png`
  - `artifacts/ui/chatpanel-local-training-readiness/chatpanel-training-readiness-turn-3.png`
  - `artifacts/ui/chatpanel-local-training-readiness/chatpanel-training-readiness-turn-4.png`
  - `artifacts/ui/chatpanel-local-training-readiness/chatpanel-training-readiness-turn-5.png`
  - `artifacts/ui/chatpanel-local-training-readiness/chatpanel-training-readiness-turn-6.png`
  - `artifacts/ui/chatpanel-local-training-readiness/chatpanel-local-training-readiness-walkthrough.json`
  - `artifacts/ui/chatpanel-local-training-readiness/chatpanel-local-training-readiness-walkthrough.md`
- command：
  - `timeout 900s env QT_QPA_PLATFORM=offscreen poetry run python scripts/dev/capture_chatpanel_local_training_readiness_walkthrough.py --output-dir artifacts/ui/chatpanel-local-training-readiness --timeout-seconds 840`
- result：
  - status：`passed`
  - runtime：primary `microsoft/Phi-4-mini-instruct`，`gpu-ready`
  - cache usage：`15.34 GB`，no download
  - dataset preparation：`scan_source` -> `preview_interpretation` -> `validate_interpretation`
    -> `apply_interpretation` -> `preprocess` -> `create_epoch` -> `generate_dataset` all `ok`
  - ChatPanel turns：`set_model` ok、`configure_training` ok、`start_training` confirmation
    observed and rejected、`visualize` ok、`saliency` ok、`evaluate` blocked with user-facing reason。
  - final state：dataset available `True`、model `EEGNet`、training option present, trainer
    `False`, training running `False`, evaluation available `False`。
  - visible assistant text clean check：no `Tool Output`, fenced JSON, traceback,
    `ApplicationService`, or `BackendFacade` markers.
- unit/static:
  - `poetry run pytest --capture=sys tests/unit/scripts/test_capture_chatpanel_local_training_readiness_walkthrough.py -q`
  - `4 passed`
  - targeted `ruff` -> pass
  - targeted `basedpyright` -> `0 errors, 0 warnings, 0 notes`

這批 evidence 支撐 high-impact training confirmation boundary 與 analysis-readiness tools 的 true
ChatPanel path。它仍不支撐 actual training completion、evaluation metrics 或 saliency render。

2026-05-04 ChatPanel local controlled tiny training-completion walkthrough：

- script：`scripts/dev/capture_chatpanel_local_training_completion_walkthrough.py`
- artifact：
  - `artifacts/ui/chatpanel-local-training-completion/chatpanel-training-completion-ready.png`
  - `artifacts/ui/chatpanel-local-training-completion/chatpanel-training-completion-trained.png`
  - `artifacts/ui/chatpanel-local-training-completion/chatpanel-training-completion-turn-1.png`
  - `artifacts/ui/chatpanel-local-training-completion/chatpanel-training-completion-turn-2.png`
  - `artifacts/ui/chatpanel-local-training-completion/chatpanel-training-completion-turn-3.png`
  - `artifacts/ui/chatpanel-local-training-completion/chatpanel-training-completion-turn-4.png`
  - `artifacts/ui/chatpanel-local-training-completion/chatpanel-training-completion-turn-5.png`
  - `artifacts/ui/chatpanel-local-training-completion/chatpanel-training-completion-turn-6.png`
  - `artifacts/ui/chatpanel-local-training-completion/chatpanel-training-completion-turn-7.png`
  - `artifacts/ui/chatpanel-local-training-completion/chatpanel-local-training-completion-walkthrough.json`
  - `artifacts/ui/chatpanel-local-training-completion/chatpanel-local-training-completion-walkthrough.md`
- command：
  - `timeout 1200s env QT_QPA_PLATFORM=offscreen poetry run python scripts/dev/capture_chatpanel_local_training_completion_walkthrough.py --output-dir artifacts/ui/chatpanel-local-training-completion --timeout-seconds 1080`
- result：
  - status：`passed`
  - runtime：primary `microsoft/Phi-4-mini-instruct`，`gpu-ready`
  - cache usage：`15.34 GB`，no download
  - dataset preparation：`scan_source` -> `preview_interpretation` -> `validate_interpretation`
    -> `apply_interpretation` -> `preprocess` -> `create_epoch` -> `generate_dataset` all `ok`
  - ChatPanel turns：`set_model` ok、`configure_training` ok with controlled temp `output_dir`、
    `start_training` confirmation observed and approved、training completion observed、
    `evaluate` ok、`saliency` configure ok、`visualize` ok、saliency readiness query ok。
  - final state：dataset available `True`、model `EEGNet`、training option present、trainer
    `True`、training running `False`、finished runs `1`、evaluation metrics available `True`、
    saliency configured / available `True`。
  - UI state：ChatPanel returned idle; visible assistant text stayed product-facing.
- supporting fixes validated in the same slice：
  - `configure_training` tool schema / ApplicationService mapping preserves `output_dir`。
  - saliency command normalizes flat `method` / `params` into backend-required
    `SmoothGrad` / `SmoothGrad_Squared` / `VarGrad` parameter keys。
  - `visualization` text maps to visualize intent, and saliency readiness queries drop stale
    configuration params from previous turns。
  - evaluation bar chart `tight_layout` failure degrades to warning, and missing `torchinfo`
    returns a model-summary unavailable message without logging traceback。
- unit/static/regression:
  - `poetry run pytest --capture=sys tests/unit/backend/application/test_application_service.py::test_saliency_command_can_configure_params tests/unit/backend/application/test_application_service.py::test_saliency_command_normalizes_flat_method_params tests/unit/llm/agent/test_intent.py tests/unit/llm/agent/test_tool_call_normalizer.py tests/unit/scripts/test_capture_chatpanel_local_training_completion_walkthrough.py tests/unit/backend/controller/test_evaluation_controller.py -q`
  - `48 passed`
  - `scripts/dev/run_ui_pytest.sh tests/unit/ui/test_ui_components.py::TestMetricsBarChart -q`
  - `3 passed`
  - `poetry run pytest --capture=sys tests/unit/llm/agent -q`
  - `235 passed`
  - targeted `ruff` -> pass
  - targeted `basedpyright` -> `0 errors, 0 warnings, 0 notes`
  - deterministic tool-call eval refresh -> `100 / 100` pass

這批 evidence 支撐 true local ChatPanel controlled tiny training completion、post-training metrics
query 和 saliency / visualization readiness summary。它仍不等於完整 saliency / visualization
canvas render、真人 Windows launcher click-through、mature import wizard label editor 或
MCP HTTP / long-running client workflow 完成。

2026-05-04 MainWindow VisualizationPanel Matplotlib render walkthrough：

- script：`scripts/dev/capture_visualization_render_walkthrough.py`
- artifact：
  - `artifacts/ui/visualization-render/visualization-render-ready.png`
  - `artifacts/ui/visualization-render/visualization-render-saliency-map.png`
  - `artifacts/ui/visualization-render/visualization-render-spectrogram.png`
  - `artifacts/ui/visualization-render/visualization-render-topographic-map.png`
  - `artifacts/ui/visualization-render/visualization-render-3d-blocked.png`
  - `artifacts/ui/visualization-render/visualization-render-walkthrough.json`
  - `artifacts/ui/visualization-render/visualization-render-walkthrough.md`
- command：
  - `timeout 600s env QT_QPA_PLATFORM=offscreen PYVISTA_OFF_SCREEN=true poetry run python scripts/dev/capture_visualization_render_walkthrough.py --output-dir artifacts/ui/visualization-render --timeout-seconds 540`
- result：
  - status：`passed`
  - dataset preparation：`scan_source` -> `preview_interpretation` -> `validate_interpretation`
    -> `apply_interpretation` -> `preprocess` -> `create_epoch` -> `generate_dataset` all `ok`
  - training/setup commands：`configure_training` model `EEGNet` ok、1 epoch CPU settings ok、
    `saliency` configure ok、`apply_montage` ok、`train` ok。
  - final state：finished runs `1`、metrics available `True`、saliency available `True`、montage
    available `True`。
  - ApplicationService `visualize` result reported `saliency map`、`spectrogram`、
    `topographic map` 和 `3D plot` available views。
  - UI render evidence：
    - `Saliency Map`：axes count `3`、image count `3`、error visible `False`、canvas visible `True`
    - `Spectrogram`：axes count `3`、image count `3`、error visible `False`、canvas visible `True`
    - `Topographic Map`：axes count `3`、image count `4`、error visible `False`、canvas visible `True`
    - `3D Plot`：blocked reason visible、`plotter_created=False`、screenshot captured。
  - offscreen capture auto-dismissed the training completion dialog `Done / All training jobs
    finished.` so the modal did not mask render state.
- unit/static:
  - `poetry run pytest --capture=sys tests/unit/scripts/test_capture_visualization_render_walkthrough.py -q`
  - `8 passed`
  - `scripts/dev/run_ui_pytest.sh tests/unit/ui/test_visualization.py::TestSaliency3DPlotWidget::test_update_plot_blocks_offscreen_before_qtinteractor -q`
  - `1 passed`
  - `scripts/dev/run_ui_pytest.sh tests/unit/ui/test_visualization_panel_redesign.py tests/unit/ui/test_visualization.py -q`
  - `20 passed`
  - targeted `ruff` -> pass
  - targeted `basedpyright` -> `0 errors, 0 warnings, 0 notes`
  - `poetry run mkdocs build --strict` -> pass
  - `git diff --check` -> pass

這批 evidence 支撐 true MainWindow VisualizationPanel post-training Matplotlib saliency renders，
並支撐 headless/offscreen 3D tab 會顯示人話 blocked reason 而不是 crash。它仍不支撐
interactive desktop 3D / PyVista render、ChatPanel UI-routing render、真人 Windows launcher
click-through、mature import wizard label editor 或 MCP HTTP / long-running client workflow 完成。

2026-05-04 PyVistaQt runtime probe：

- script:
  - `scripts/dev/probe_pyvistaqt_runtime.py`
- artifacts:
  - `artifacts/ui/visualization-render/pyvistaqt-runtime-probe.json`
  - `artifacts/ui/visualization-render/pyvistaqt-runtime-probe.md`
- result:
  - status `blocked`
  - environment captured `DISPLAY=:0`, `WAYLAND_DISPLAY=wayland-0`
  - child probe attempted a minimal `pyvistaqt.QtInteractor` + sphere render
  - stderr: X `BadWindow (invalid Window parameter)`
  - screenshot was not created
- commands:
  - direct exploratory probe first failed with the same X `BadWindow`
  - `timeout 90s poetry run python scripts/dev/probe_pyvistaqt_runtime.py --output-dir artifacts/ui/visualization-render --timeout-seconds 60`
  - `poetry run pytest --capture=sys tests/unit/scripts/test_probe_pyvistaqt_runtime.py -q`
  - `2 passed`
  - targeted `ruff check` / `ruff format --check` -> pass.
  - `poetry run basedpyright scripts/dev/probe_pyvistaqt_runtime.py`
  - `0 errors, 0 warnings, 0 notes`
  - `poetry run mkdocs build --strict` -> pass with existing MkDocs Material warning.
  - `poetry run python tests/architecture_compliance.py` -> Architecture compliant.
  - `git diff --check` -> pass.

這批 evidence 支撐目前 runner session 無法驗證 interactive PyVistaQt render，因此不能把
headless 3D blocked UX 包裝成產品 3D 完成。它仍不支撐 XBrainLab 3D saliency render、真人
OpenGL desktop walkthrough 或 Windows release click-through。

2026-05-04 ChatPanel true local-model one-turn walkthrough：

- 新增 `scripts/dev/capture_chatpanel_local_walkthrough.py`：
  - 在 `HF_HUB_OFFLINE=1` / `TRANSFORMERS_OFFLINE=1` 下執行，避免模型下載或 remote path。
  - 打開真 `MainWindow` / `ChatPanel`，並用 UI composer / Send button 送出 prompt。
  - runtime path 是 `AgentManager -> LLMController -> AgentWorker -> LLMEngine -> LocalBackend`。
  - 保存 `artifacts/ui/chatpanel-local-ready.png`、
    `artifacts/ui/chatpanel-local-response.png`、
    `artifacts/ui/chatpanel-local-walkthrough.json` 和 `.md`。
- artifact summary：
  - status：`passed`
  - runtime classification：`gpu-ready`
  - model：`microsoft/Phi-4-mini-instruct`
  - cache usage：`15.34 GB`
  - visible user prompt：
    `In one short user-facing sentence, explain what EEG preprocessing does. Do not use tools.`
  - visible assistant response：
    `EEG preprocessing involves cleaning and organizing the raw EEG data to prepare it for further analysis.`
  - send button：`Send`
  - input enabled：`True`
  - chat / controller processing：`False`
- commands:
  - `poetry run python scripts/dev/inspect_local_assistant_runtime.py --format markdown`
  - `classification: gpu-ready`，cache `15.34 GB`
  - `timeout 420s xvfb-run -a poetry run python scripts/dev/capture_chatpanel_local_walkthrough.py --output-dir artifacts/ui --timeout-seconds 360`
  - wrote walkthrough JSON / Markdown and two screenshots。
  - `poetry run pytest --capture=sys tests/unit/scripts/test_capture_chatpanel_local_walkthrough.py -q`
  - `2 passed`
  - `poetry run ruff check scripts/dev/capture_chatpanel_local_walkthrough.py tests/unit/scripts/test_capture_chatpanel_local_walkthrough.py`
  - `PASS`
  - `poetry run basedpyright scripts/dev/capture_chatpanel_local_walkthrough.py tests/unit/scripts/test_capture_chatpanel_local_walkthrough.py`
  - `0 errors, 0 warnings, 0 notes`

這批 evidence 支撐 true local model 可以在 ChatPanel 中產生使用者可見回覆，且 visible transcript
沒有 raw tool syntax、schema、traceback 或 debug payload。它仍不支撐 multi-turn tool-command
workflow、Windows Desktop launcher click-through、長時間 assistant 操作、完整 import wizard UI
驗收或 release closure。

2026-05-04 ChatPanel local tool-command walkthrough：

- 目的：
  - 驗證真 local model 從 ChatPanel UI composer 觸發 tool call 時，UI 會顯示產品語言回覆，
    不會把 raw tool JSON、schema、traceback 或 `Tool Output` 暴露給使用者。
- artifact：
  - `artifacts/ui/chatpanel-local-tool/chatpanel-local-ready.png`
  - `artifacts/ui/chatpanel-local-tool/chatpanel-local-response.png`
  - `artifacts/ui/chatpanel-local-tool/chatpanel-local-walkthrough.json`
  - `artifacts/ui/chatpanel-local-tool/chatpanel-local-walkthrough.md`
- artifact summary：
  - status：`passed`
  - runtime classification：`gpu-ready`
  - model：`microsoft/Phi-4-mini-instruct`
  - cache usage：`15.34 GB`
  - executed tool：`query_state` `ok`
  - visible assistant response：`Application state snapshot ready.`
  - send button：`Send`
  - input enabled：`True`
  - chat / controller processing：`False`
- commands:
  - `timeout 420s env QT_QPA_PLATFORM=offscreen poetry run python scripts/dev/capture_chatpanel_local_walkthrough.py --output-dir artifacts/ui/chatpanel-local-tool --timeout-seconds 360 --prompt "Check what is ready in the current XBrainLab workflow. Use the state query tool if needed, then answer in one short sentence."`
  - wrote walkthrough JSON / Markdown and two screenshots。
  - `scripts/dev/run_ui_pytest.sh tests/integration/ui/test_product_walkthrough.py -q`
  - `3 passed`
  - `poetry run pytest --capture=sys tests/unit/scripts/test_capture_chatpanel_local_walkthrough.py -q`
  - `3 passed`
  - targeted `ruff` / `basedpyright`
  - clean。

這批 evidence 支撐單步 ApplicationService-backed tool execution 可以經 ChatPanel 走真 local
model path 並回到 idle。它仍不支撐多輪 tool-command chain、長時間 assistant 操作、Windows
Desktop launcher click-through 或完整 release closure。

2026-05-04 ChatPanel local two-turn workflow walkthrough：

- root cause fixed:
  - 初次 multi-turn capture 顯示 turn 1 `query_state` 成功後，完整 state JSON 被寫回
    conversation history。
  - turn 2 prompt 約 `10.7k` input tokens，local model generation timeout。
  - `LLMController._format_tool_output()` 已改為 compact feedback：保留 tool message、
    capability、`state_summary` 和 small diagnostics，移除 full `state` / `raw_result`。
- artifact：
  - `artifacts/ui/chatpanel-local-workflow/chatpanel-workflow-ready.png`
  - `artifacts/ui/chatpanel-local-workflow/chatpanel-workflow-turn-1.png`
  - `artifacts/ui/chatpanel-local-workflow/chatpanel-workflow-turn-2.png`
  - `artifacts/ui/chatpanel-local-workflow/chatpanel-local-workflow-walkthrough.json`
  - `artifacts/ui/chatpanel-local-workflow/chatpanel-local-workflow-walkthrough.md`
- artifact summary：
  - status：`passed`
  - runtime classification：`gpu-ready`
  - model：`microsoft/Phi-4-mini-instruct`
  - turn 1 executed tool：`query_state` `ok`
  - turn 2 local-model follow-up completed with no tool call
  - turn 2 input tokens dropped to about `2.46k` in run log
  - visible transcript has no raw `Tool Output`、schema、traceback or debug payload
  - UI returned idle
- commands:
  - `timeout 520s env QT_QPA_PLATFORM=offscreen poetry run python scripts/dev/capture_chatpanel_local_workflow_walkthrough.py --output-dir artifacts/ui/chatpanel-local-workflow --timeout-seconds 480`
  - `poetry run pytest --capture=sys tests/unit/llm/agent/test_controller.py::TestPipelineGate::test_tool_output_history_uses_compact_state_summary tests/unit/llm/agent/test_controller.py::TestPipelineGate::test_allowed_tool_executes -q`
  - `2 passed`
  - `poetry run pytest --capture=sys tests/unit/scripts/test_capture_chatpanel_local_workflow_walkthrough.py -q`
  - `1 passed`

這批 evidence 支撐真 local ChatPanel 可以在 tool turn 後維持第二輪正常對話，並修掉 prompt
bloat timeout。它仍不支撐長時間 autonomous tool-command chain、完整資料到訓練操作或真人
Windows walkthrough。

2026-05-04 ChatPanel local Data Interpretation tool-chain walkthrough：

- root cause fixed:
  - 首次真 local-model run 中，turn 1 `scan_source` 成功，但 turn 2
    `preview_interpretation` failed with `Scan a data source before previewing interpretation.`
  - artifact final state 顯示 backend 已有 `latest_scan_id=scan-1`，所以 failure 不是
    ApplicationService lifecycle 遺失，而是 local model 傳入 schema-derived placeholder
    `scan_id`，覆蓋了 backend latest-state fallback。
  - `tool_call_normalizer` 現在只保留 backend 會真生成的 `scan-<n>` / `candidate-<n>` id；
    `latest_scan_id`、`current_candidate` 等 generated placeholder 會移除，讓
    ApplicationService 使用目前 state。
- artifact：
  - `artifacts/ui/chatpanel-local-tool-chain/chatpanel-tool-chain-ready.png`
  - `artifacts/ui/chatpanel-local-tool-chain/chatpanel-tool-chain-turn-1.png`
  - `artifacts/ui/chatpanel-local-tool-chain/chatpanel-tool-chain-turn-2.png`
  - `artifacts/ui/chatpanel-local-tool-chain/chatpanel-tool-chain-turn-3.png`
  - `artifacts/ui/chatpanel-local-tool-chain/chatpanel-local-tool-chain-walkthrough.json`
  - `artifacts/ui/chatpanel-local-tool-chain/chatpanel-local-tool-chain-walkthrough.md`
- artifact summary：
  - status：`passed`
  - runtime classification：`gpu-ready`
  - model：`microsoft/Phi-4-mini-instruct`
  - expected tools：`scan_source` -> `preview_interpretation` -> `validate_interpretation`
  - executed tools：all `ok`
  - final interpretation state：scan / candidate / preview / validation decision present
  - validation decision：`needs_confirmation`
  - visible transcript has no raw `Tool Output`、schema、traceback or debug payload
  - UI returned idle
- commands:
  - `timeout 620s env QT_QPA_PLATFORM=offscreen poetry run python scripts/dev/capture_chatpanel_local_tool_chain_walkthrough.py --output-dir artifacts/ui/chatpanel-local-tool-chain --timeout-seconds 580`
  - `poetry run pytest --capture=sys tests/unit/llm/agent/test_tool_call_normalizer.py tests/unit/scripts/test_capture_chatpanel_local_tool_chain_walkthrough.py -q`
  - `30 passed`
  - `poetry run ruff check XBrainLab/llm/agent/tool_call_normalizer.py scripts/dev/capture_chatpanel_local_tool_chain_walkthrough.py tests/unit/llm/agent/test_tool_call_normalizer.py tests/unit/scripts/test_capture_chatpanel_local_tool_chain_walkthrough.py`
  - pass
  - `poetry run basedpyright XBrainLab/llm/agent/tool_call_normalizer.py scripts/dev/capture_chatpanel_local_tool_chain_walkthrough.py tests/unit/llm/agent/test_tool_call_normalizer.py tests/unit/scripts/test_capture_chatpanel_local_tool_chain_walkthrough.py`
  - `0 errors, 0 warnings, 0 notes`

這批 evidence 支撐真 local ChatPanel 可以做一段 Data Interpretation tool chain，且每 turn
只執行一個 verified ApplicationService-backed command。它仍不支撐 confirm/apply、
preprocess、epoch、dataset、training 的長鏈 autonomous workflow，也不支撐 Windows
Desktop launcher 真人 click-through。

2026-05-04 ChatPanel local import-to-dataset pipeline-chain walkthrough：

- root cause fixed:
  - `apply_standard_preprocess` 已在 agent application surface 直接 route 到
    `PreprocessCommand(operation=STANDARD)`，讓 agent path 回 `ToolCommandResult` / typed
    ApplicationService state，而不是 real-tool legacy string fallback。
  - 首次真 pipeline-chain run 在 `generate_dataset` 被 split audit 擋下：
    `Generated dataset failed split audit; fix empty splits or leakage before training.`
  - failure root cause 是 prompt 只讓 normalizer 抽出 `left` 單一 event，形成 3 epochs；trial
    split 會出現 empty validation。這個 guardrail 沒有放寬。
  - `tool_call_normalizer` 現在可從 `events left and right` 抽多個 event ids，讓 same source
    建出 6 epochs 並通過 split audit。
- artifact：
  - `artifacts/ui/chatpanel-local-pipeline-chain/chatpanel-pipeline-chain-ready.png`
  - `artifacts/ui/chatpanel-local-pipeline-chain/chatpanel-pipeline-chain-turn-1.png`
  - `artifacts/ui/chatpanel-local-pipeline-chain/chatpanel-pipeline-chain-turn-2.png`
  - `artifacts/ui/chatpanel-local-pipeline-chain/chatpanel-pipeline-chain-turn-3.png`
  - `artifacts/ui/chatpanel-local-pipeline-chain/chatpanel-pipeline-chain-turn-4.png`
  - `artifacts/ui/chatpanel-local-pipeline-chain/chatpanel-pipeline-chain-turn-5.png`
  - `artifacts/ui/chatpanel-local-pipeline-chain/chatpanel-pipeline-chain-turn-6.png`
  - `artifacts/ui/chatpanel-local-pipeline-chain/chatpanel-pipeline-chain-turn-7.png`
  - `artifacts/ui/chatpanel-local-pipeline-chain/chatpanel-local-pipeline-chain-walkthrough.json`
  - `artifacts/ui/chatpanel-local-pipeline-chain/chatpanel-local-pipeline-chain-walkthrough.md`
- artifact summary：
  - status：`passed`
  - runtime classification：`gpu-ready`
  - model：`microsoft/Phi-4-mini-instruct`
  - expected tools：`scan_source` -> `preview_interpretation` -> `validate_interpretation` ->
    `apply_interpretation` -> `apply_standard_preprocess` -> `epoch_data` -> `generate_dataset`
  - executed tools：all `ok`
  - confirmation dialogs observed：`1`
  - final state：applied interpretation `True`、epoch available `True`、epoch count `6`、
    dataset available `True`、dataset count `1`
  - visible transcript has no raw `Tool Output`、schema、traceback or debug payload
  - UI returned idle
- commands:
  - `timeout 840s env QT_QPA_PLATFORM=offscreen poetry run python scripts/dev/capture_chatpanel_local_pipeline_chain_walkthrough.py --output-dir artifacts/ui/chatpanel-local-pipeline-chain --timeout-seconds 800`
  - `poetry run pytest --capture=sys tests/unit/llm/agent/test_tool_call_normalizer.py tests/unit/llm/tools/test_application_surface.py::test_application_tool_command_routes_standard_preprocess tests/unit/scripts/test_capture_chatpanel_local_pipeline_chain_walkthrough.py -q`
  - `32 passed`
  - `poetry run ruff check XBrainLab/llm/agent/tool_call_normalizer.py XBrainLab/llm/tools/application_surface.py scripts/dev/capture_chatpanel_local_pipeline_chain_walkthrough.py tests/unit/llm/agent/test_tool_call_normalizer.py tests/unit/llm/tools/test_application_surface.py tests/unit/scripts/test_capture_chatpanel_local_pipeline_chain_walkthrough.py`
  - pass
  - `poetry run basedpyright XBrainLab/llm/agent/tool_call_normalizer.py XBrainLab/llm/tools/application_surface.py scripts/dev/capture_chatpanel_local_pipeline_chain_walkthrough.py tests/unit/llm/agent/test_tool_call_normalizer.py tests/unit/llm/tools/test_application_surface.py tests/unit/scripts/test_capture_chatpanel_local_pipeline_chain_walkthrough.py`
  - `0 errors, 0 warnings, 0 notes`

這批 evidence 支撐真 local ChatPanel 可從 Data Interpretation apply confirmation 走到 dataset
ready，且每 turn 只執行一個 verified tool。它仍不支撐 model selection、training settings、
training、evaluation、saliency 的長鏈，也不支撐 Windows Desktop launcher 真人 click-through。

2026-05-04 Data Interpretation non-mocked backend workflow：

- 新增 `tests/integration/backend/test_application_service_workflow.py::test_data_interpretation_to_dataset_workflow_is_non_mocked`。
- 這條 test 會：
  - 產生 real synthetic MNE `.fif` source。
  - 跑 `scan_source` -> `preview_interpretation` -> `validate_interpretation`。
  - 驗證缺 subject / session / task / run metadata 時 decision 是 `needs_confirmation`。
  - 驗證未確認的 `apply_interpretation` 會被 `confirmation_required` 擋下。
  - 用 `confirmed=True` apply，並確認 raw state / interpretation state 更新。
  - `save_interpretation_recipe` 寫出 recipe。
  - 在新的 `ApplicationService` session 用 `reload_interpretation_recipe` 重新 scan / preview /
    validate，但不直接 apply。
  - 接續跑 normalize preprocess、epoch 和 trial-wise dataset generation，並檢查 split audit 與
    train / val / test counts。
- commands:
  - `poetry run pytest --capture=sys tests/integration/backend/test_application_service_workflow.py::test_data_interpretation_to_dataset_workflow_is_non_mocked -q`
  - `1 passed`
  - `poetry run pytest --capture=sys tests/integration/backend/test_application_service_workflow.py tests/unit/backend/application/test_application_service.py tests/unit/backend/application/test_automation.py -q`
  - `38 passed`
  - `poetry run pytest --capture=sys tests/integration/backend/test_application_service_workflow.py -q`
  - `3 passed`
  - `poetry run ruff check tests/integration/backend/test_application_service_workflow.py`
  - `PASS`
  - `poetry run basedpyright tests/integration/backend/test_application_service_workflow.py`
  - `0 errors, 0 warnings, 0 notes`

這批 evidence 支撐 backend non-mocked source -> recipe -> preprocess -> epoch -> dataset
workflow。它仍不等於 UI wizard / ChatPanel 可見行為；UI-observable replay 仍需 screenshot /
visible state / transcript artifact。

2026-05-04 Data Interpretation UI-observable replay artifact：

- 新增 `scripts/dev/capture_data_interpretation_replay.py`。
- replay 會啟動 real `MainWindow` / Dataset panel，在固定 temp source path 產生 synthetic MNE
  `.fif`，並用真 `ApplicationService` 跑 scan / preview / validate / apply。
- artifacts：
  - `artifacts/ui/data-interpretation-preview.png`
  - `artifacts/ui/data-interpretation-applied.png`
  - `artifacts/ui/data-interpretation-replay.json`
- replay JSON 保存：
  - transcript。
  - command result 對照。
  - visible Data Interpretation dialog state。
  - metadata preview rows。
  - dataset panel import button text / enabled state。
  - dataset table row count。
  - screenshot filenames。
- observed result：
  - dialog decision：`needs_confirmation`。
  - save recipe checkbox：`checked`。
  - unconfirmed apply：`failed / confirmation_required`。
  - confirmed apply：`ok`。
  - dataset table rows：`1`。
- command:
  - `xvfb-run -a poetry run python scripts/dev/capture_data_interpretation_replay.py`
  - exit code `0`

這批 evidence 支撐 Data Interpretation preview dialog 和 applied Dataset panel 的 UI-observable
replay。它仍不是完整真人 click-through，也尚未覆蓋 ChatPanel agent transcript。

2026-05-04 Data Interpretation wizard review hardening：

- `DataInterpretationPreviewDialog` 已從單層 preview modal 硬化為第一版 wizard review surface：
  - title：`Interpret Data Source`
  - visible steps：`Scan -> Preview -> Validate -> Confirm -> Apply -> Save recipe`
  - source/readiness group：source path、source kind、file count、label carrier count、BIDS status
  - metadata preview：file / subject / session / task / run
  - labels/events/recipe trace：label carriers、event roles、class map，或 no-carrier boundary
  - review notes：warnings、confirmations、blocked reasons、downstream impact、recipe trace
  - action button：`Confirm and Apply` for `needs_confirmation`；blocked decision disables apply and
    recipe save。
- replay artifact refreshed:
  - `env QT_QPA_PLATFORM=offscreen poetry run python scripts/dev/capture_data_interpretation_replay.py`
  - `artifacts/ui/data-interpretation-preview.png`
  - `artifacts/ui/data-interpretation-applied.png`
  - `artifacts/ui/data-interpretation-replay.json`
- targeted gates:
  - `scripts/dev/run_ui_pytest.sh tests/unit/ui/dialogs/dataset/test_data_interpretation_preview_dialog.py tests/unit/ui/test_ui_misc.py::TestDatasetActionHandler -q`
  - `47 passed`
  - `poetry run ruff check XBrainLab/ui/dialogs/dataset/data_interpretation_preview_dialog.py scripts/dev/capture_data_interpretation_replay.py tests/unit/ui/dialogs/dataset/test_data_interpretation_preview_dialog.py tests/unit/ui/test_ui_misc.py`
  - `PASS`
  - `poetry run basedpyright XBrainLab/ui/dialogs/dataset/data_interpretation_preview_dialog.py scripts/dev/capture_data_interpretation_replay.py tests/unit/ui/dialogs/dataset/test_data_interpretation_preview_dialog.py`
  - `0 errors, 0 warnings, 0 notes`

這批 evidence 支撐 Data Interpretation UI 已比 baseline preview 更接近 import wizard review
surface。下一個 slice 已補 first-pass metadata / class-map review editor；它仍不支撐
format-specific label editor、all-format manual compatibility matrix 或真人 click-through。

2026-05-04 Data Interpretation metadata / class-map editor slice：

- backend:
  - `PreviewInterpretationCommand(choices=...)` 現在可接
    `metadata_overrides`、`class_map`、`event_roles`。
  - metadata override 會把欄位標成 `source=user_override`、`decision=safe`，並寫入
    `metadata_override:<field>` recipe trace。
  - `AppliedInterpretation` / `ImportRecipe` 會保存 `event_roles` 和 `class_map`。
- UI:
  - `DataInterpretationPreviewDialog` 的 metadata review cells 可編輯 subject / session /
    task / run。
  - class map rows 可編輯 meaning。
  - `get_result()` 回傳 review `choices`；Dataset action 會在 apply 前 re-preview /
    re-validate，再套用新的 candidate。
- replay artifact refreshed:
  - `env QT_QPA_PLATFORM=offscreen poetry run python scripts/dev/capture_data_interpretation_replay.py`
  - `artifacts/ui/data-interpretation-preview.png`
  - `artifacts/ui/data-interpretation-applied.png`
  - `artifacts/ui/data-interpretation-replay.json`
  - replay JSON 顯示 `review_choices.metadata_overrides`：`S01`、`session-01`、
    `motor-imagery`，且 reviewed preview / apply path 保留 `metadata_override` recipe trace。
- targeted gates:
  - `scripts/dev/run_ui_pytest.sh tests/unit/ui/dialogs/dataset/test_data_interpretation_preview_dialog.py tests/unit/ui/test_ui_misc.py::TestDatasetActionHandler -q`
  - `49 passed`
  - `poetry run pytest --capture=sys tests/unit/backend/application -q`
  - `37 passed`
  - `poetry run pytest --capture=sys tests/integration/backend/test_application_service_workflow.py::test_data_interpretation_to_dataset_workflow_is_non_mocked -q`
  - `1 passed`

這批 evidence 支撐 first-pass metadata override / class-map review editor 已進入 Data
Interpretation recipe flow。它仍不支撐 format-specific label column / MAT variable / anchor
editor、label import 內嵌 wizard、完整真人 click-through 或全格式 compatibility matrix。

2026-05-04 Data Interpretation label carrier review slice：

- backend:
  - `InterpretationCandidate` / `InterpretationPreview` now expose `label_carrier_plan` /
    `label_carrier_preview` for MAT, CSV / TSV, BIDS `events.tsv`, and TXT carriers.
  - `PreviewInterpretationCommand(choices=...)` accepts `label_carrier_choices` with
    `label_field`, `anchor`, `time_model`, and `granularity`.
  - `AppliedInterpretation` / `ImportRecipe` save the reviewed `label_carrier_plan`, and
    recipe trace records `choices:label_carriers`.
- UI:
  - `DataInterpretationPreviewDialog` now shows editable label carrier review rows for
    carrier, format, label field / MAT variable, anchor, time model, and granularity.
  - `get_result()` returns edited label carrier choices, and Dataset action already
    re-previews / re-validates those choices before applying.
- replay artifact refreshed:
  - `timeout 180s env QT_QPA_PLATFORM=offscreen poetry run python scripts/dev/capture_data_interpretation_replay.py`
  - `artifacts/ui/data-interpretation-preview.png`
  - `artifacts/ui/data-interpretation-applied.png`
  - `artifacts/ui/data-interpretation-replay.json`
  - replay JSON shows visible `label_carrier_rows` with `trial_type` / `onset` /
    `seconds` / `trial`, and applied interpretation saves the same reviewed plan.
- targeted gates:
  - `poetry run pytest --capture=sys tests/unit/backend/application/test_application_service.py tests/integration/backend/test_application_service_workflow.py::test_data_interpretation_to_dataset_workflow_is_non_mocked -q`
  - `33 passed`
  - `scripts/dev/run_ui_pytest.sh tests/unit/ui/dialogs/dataset/test_data_interpretation_preview_dialog.py tests/unit/ui/test_ui_misc.py::TestDatasetActionHandler -q`
  - `50 passed`
  - `poetry run ruff check XBrainLab/backend/application/data_interpretation.py XBrainLab/backend/application/service.py XBrainLab/ui/dialogs/dataset/data_interpretation_preview_dialog.py scripts/dev/capture_data_interpretation_replay.py tests/unit/backend/application/test_application_service.py tests/unit/ui/dialogs/dataset/test_data_interpretation_preview_dialog.py`
  - `PASS`
  - `poetry run basedpyright XBrainLab/backend/application/data_interpretation.py XBrainLab/backend/application/service.py XBrainLab/ui/dialogs/dataset/data_interpretation_preview_dialog.py scripts/dev/capture_data_interpretation_replay.py tests/unit/backend/application/test_application_service.py tests/unit/ui/dialogs/dataset/test_data_interpretation_preview_dialog.py`
  - `0 errors, 0 warnings, 0 notes`

這批 evidence 支撐 first-pass format-specific label carrier review 已進入 Data Interpretation
wizard，包含 MAT variable / anchor recipe evidence 和 UI-observable BIDS-events / TSV label
column / anchor evidence。它仍不支撐完整 post-load label import 內嵌 wizard、全格式人工
compatibility matrix 或真人 click-through。

2026-05-04 Data Interpretation role review slice：

- UI:
  - `DataInterpretationPreviewDialog` now tracks editable event-role rows and returns
    `choices.event_roles` when the user changes an event role.
  - label carrier review rows gained a visible `Role` column; `get_result()` now returns
    carrier `role` along with target, label field, anchor, time model, and granularity.
- backend evidence:
  - `ApplicationService` recipe test now asserts reviewed label carrier role and event role flow
    into `AppliedInterpretation` / `ImportRecipe`, and recipe trace records
    `choices:event_roles`.
- replay artifact refreshed:
  - `xvfb-run -a poetry run python scripts/dev/capture_data_interpretation_replay.py`
  - `artifacts/ui/data-interpretation-preview.png`
  - `artifacts/ui/data-interpretation-applied.png`
  - `artifacts/ui/data-interpretation-replay.json`
  - replay JSON visible row:
    `events.tsv -> sub-01_task-mi_run-2_raw.fif -> BIDS events -> trial_type -> onset -> seconds -> trial -> class cue labels`
  - replay JSON `review_choices.event_roles.trial_type` is `class cue`.
- TDD evidence:
  - focused UI test first failed because `event_roles` was missing from dialog choices.
  - focused UI test first failed because carrier `role` was missing from `label_carrier_choices`.
- targeted gates:
  - `poetry run pytest --capture=sys tests/unit/ui/dialogs/dataset/test_data_interpretation_preview_dialog.py -q`
  - `8 passed`
  - `poetry run pytest --capture=sys tests/unit/backend/application/test_application_service.py::test_data_interpretation_label_carrier_choices_flow_into_recipe -q`
  - `1 passed`
  - `poetry run pytest --capture=sys tests/unit/ui/test_ui_misc.py::TestDatasetActionHandler -q`
  - `47 passed`
  - `poetry run pytest --capture=sys tests/unit/backend/application/test_application_service.py -q`
  - `43 passed`
  - targeted `ruff check` / `ruff format --check` -> pass.
  - `poetry run basedpyright scripts/dev/capture_data_interpretation_replay.py XBrainLab/ui/dialogs/dataset/data_interpretation_preview_dialog.py`
  - `0 errors, 0 warnings, 0 notes`

這批 evidence 支撐 Data Interpretation wizard 可讓使用者確認 event role 與 label carrier role，
並把這些語意保存到 recipe choices / backend recipe。它仍不是完整 post-load label import
內嵌 editor、raw trigger selector、全格式 real-data certification 或真人 click-through。

2026-05-04 Data Interpretation label carrier selector UI：

- UI:
  - label carrier review columns for label field, anchor, time model, granularity, and role now use
    `QComboBox` selectors instead of requiring free-form cell typing.
  - selector display text is user-facing for controlled values, e.g. `Seconds`, `Trial`, and
    `Class cue labels`.
  - `get_result()` reads combo `itemData` so recipe choices still carry backend values such as
    `seconds`, `trial`, and `class cue labels`.
- TDD evidence:
  - focused selector test first failed because label/anchor/time/granularity/role cells had no
    combo widgets.
- replay artifact refreshed:
  - `xvfb-run -a poetry run python scripts/dev/capture_data_interpretation_replay.py`
  - `artifacts/ui/data-interpretation-preview.png`
  - `artifacts/ui/data-interpretation-applied.png`
  - `artifacts/ui/data-interpretation-replay.json`
  - replay JSON visible row:
    `events.tsv -> sub-01_task-mi_run-2_raw.fif -> BIDS events -> trial_type -> onset -> Seconds -> Trial -> Class cue labels`
  - replay JSON recipe choices still use `time_model=seconds` and `granularity=trial`.
- targeted gates:
  - `poetry run pytest --capture=sys tests/unit/ui/dialogs/dataset/test_data_interpretation_preview_dialog.py -q`
  - `9 passed`
  - `poetry run pytest --capture=sys tests/unit/ui/test_ui_misc.py::TestDatasetActionHandler -q`
  - `47 passed`
  - `poetry run pytest --capture=sys tests/unit/backend/application/test_application_service.py::test_data_interpretation_label_carrier_choices_flow_into_recipe -q`
  - `1 passed`
  - targeted `ruff check` / `ruff format --check` -> pass.
  - `poetry run basedpyright scripts/dev/capture_data_interpretation_replay.py XBrainLab/ui/dialogs/dataset/data_interpretation_preview_dialog.py`
  - `0 errors, 0 warnings, 0 notes`

這批 evidence 支撐 import wizard label carrier review 的使用性改善：使用者不再需要手打主要
review 欄位。它仍不是完整 embedded post-load label import editor、raw trigger selector、
全格式 real-data certification 或真人 click-through。

2026-05-04 Dataset Add Labels compatibility guard：

- UI/action:
  - `DatasetSidebar.update_sidebar()` disables `Add Labels to Loaded Data` when no data is loaded
    and uses tooltip text `Interpret a data source before adding labels.`
  - the same button is disabled while the dataset is locked by downstream edits.
  - `DatasetActionHandler.import_label()` checks backend `ImportLabelsCommand` capability before
    opening the compatibility dialog.
  - `_get_target_files_for_import()` now warns immediately when the dataset table has no rows,
    instead of asking whether to apply labels to all files.
- replay artifact refreshed:
  - `xvfb-run -a poetry run python scripts/dev/capture_data_interpretation_replay.py`
  - `artifacts/ui/data-interpretation-replay.json`
  - empty dataset sidebar evidence:
    `Add Labels to Loaded Data`, enabled `False`, tooltip `Interpret a data source before adding labels.`
  - applied dataset sidebar evidence:
    enabled `True`, tooltip `Add labels to loaded data and update the current recipe trace.`
- TDD evidence:
  - focused sidebar tests first failed because the button remained enabled for locked / empty states.
  - focused action tests first failed because no-data and capability-block guards were missing.
- targeted gates:
  - `poetry run pytest --capture=sys tests/unit/ui/test_ui_misc.py::TestDatasetActionHandler tests/unit/ui/dataset/test_dataset_sidebar.py -q`
  - `54 passed`
  - targeted `ruff check` / `ruff format --check` -> pass.
  - `poetry run basedpyright scripts/dev/capture_data_interpretation_replay.py XBrainLab/ui/panels/dataset/actions.py XBrainLab/ui/panels/dataset/sidebar.py`
  - `0 errors, 0 warnings, 0 notes`

這批 evidence 支撐 post-load label compatibility path 不再在 empty / blocked state 裡鼓勵舊
attach-label 心智模型。它仍不是完整 embedded Data Interpretation label editor。

2026-05-04 Data Interpretation format capability boundary slice：

- backend:
  - `ScanResult` / `InterpretationCandidate` / `InterpretationPreview` / `AppliedInterpretation` /
    `ImportRecipe` now carry `format_capabilities`.
  - Scan reports review boundaries for GDF, EDF / BDF, EEGLAB `.set`, BrainVision `.vhdr` /
    `.vmrk`, MNE FIF, MAT labels, CSV / TSV labels, BIDS `events.tsv`, TXT labels, and XDF / LSL.
  - XDF / LSL is explicit `blocked` with a user-facing stream-selection unavailable reason; mixed
    folders with supported EEG keep importing the supported source while warning that blocked
    sources are not applied.
- UI:
  - `DataInterpretationPreviewDialog` review notes include a `Format capabilities` section and
    converts internal statuses such as `needs_review` into visible text like `needs review`.
- replay artifact refreshed:
  - `timeout 180s env QT_QPA_PLATFORM=offscreen poetry run python scripts/dev/capture_data_interpretation_replay.py`
  - `artifacts/ui/data-interpretation-preview.png`
  - `artifacts/ui/data-interpretation-replay.json`
  - replay JSON `review_notes` shows BIDS events as `needs review` and MNE FIF as `supported`.
- targeted gates:
  - `poetry run pytest --capture=sys tests/unit/backend/application/test_application_service.py tests/integration/backend/test_application_service_workflow.py::test_data_interpretation_to_dataset_workflow_is_non_mocked -q`
  - `34 passed`
  - `scripts/dev/run_ui_pytest.sh tests/unit/ui/dialogs/dataset/test_data_interpretation_preview_dialog.py tests/unit/ui/test_ui_misc.py::TestDatasetActionHandler -q`
  - `51 passed`
  - targeted `ruff` / `basedpyright` clean.

這批 evidence 支撐 import wizard 不再把特殊格式當成泛泛 label/event warning；使用者可以看到
哪些格式已可載入但需要語意確認，哪些格式目前 blocked。它仍不是 full manual compatibility
matrix 或 XDF stream parser implementation。

2026-05-04 Data Interpretation generated format capability matrix：

- artifacts:
  - `artifacts/data_interpretation/format-capability-matrix.json`
  - `artifacts/data_interpretation/format-capability-matrix.md`
- generator:
  - `scripts/dev/report_data_interpretation_format_matrix.py`
  - 透過 live `ApplicationService.execute(ScanSourceCommand)`、
    `PreviewInterpretationCommand`、`ValidateInterpretationCommand` 產生 matrix，而不是從 docs
    hard-code 產品 claim。
- coverage:
  - `13` rows across `9` synthetic scan fixtures。
  - 覆蓋 GDF、EDF、BDF、EEGLAB SET、BrainVision VHDR、BrainVision VMRK、MNE FIF、MAT labels、
    CSV labels、TSV labels、BIDS `events.tsv`、TXT labels、XDF / LSL stream export。
  - statuses 覆蓋 `supported`、`needs_review`、`context`、`blocked`。
  - validation decisions 覆蓋 `safe`、`needs_confirmation`、`blocked`。
- tests / commands:
  - TDD failure: initial focused test failed with
    `ModuleNotFoundError: No module named 'scripts.dev.report_data_interpretation_format_matrix'`。
  - CLI JSON purity failure: initial CLI test failed because `Study initialized` logs polluted
    stdout before JSON。
  - `poetry run pytest --capture=sys tests/unit/scripts/test_report_data_interpretation_format_matrix.py -q`
  - `3 passed`
  - `poetry run pytest --capture=sys tests/unit/scripts/test_report_data_interpretation_format_matrix.py tests/unit/backend/application/test_application_service.py::test_data_interpretation_scan_reports_format_capability_boundaries -q`
  - `4 passed`
  - targeted `ruff check` / `ruff format --check` for the reporter and tests -> pass.
  - `poetry run basedpyright scripts/dev/report_data_interpretation_format_matrix.py`
  - `0 errors, 0 warnings, 0 notes`
  - `poetry run python scripts/dev/report_data_interpretation_format_matrix.py --write-artifacts`
  - wrote both matrix artifacts.
  - `poetry run mkdocs build --strict` -> pass with existing MkDocs Material warning.
  - `poetry run python tests/architecture_compliance.py` -> Architecture compliant.
  - `git diff --check` -> pass.

這批 evidence 支撐 Data Interpretation format capability boundary 已有可重跑 artifact，並證明
XDF / LSL 目前是 blocked user-facing boundary。它仍不支撐 XDF / LSL stream parser、
raw-event-anchor-specific MAT/GDF alignment、或全格式 real-data manual certification。

2026-05-04 Data Interpretation reviewed MAT sample-anchor apply slice：

- backend:
  - `load_label_file()` now accepts reviewed MAT `label_field` + `anchor`.
  - When a MAT anchor is provided, the loader returns an MNE-style event array:
    `[sample_index, 0, class_label]`.
  - `apply_interpretation` now treats reviewed MAT plans with `time_model=sample_index`,
    `granularity=trial`, selected label/anchor, and confirmed class map as `anchored` label apply.
  - The apply path uses `apply_labels_batch`, records `label_import:anchored:<n>`, and keeps the
    applied interpretation / recipe trace updated.
- tests:
  - TDD failures:
    - focused label loader test first returned the plain class labels instead of MNE event rows.
    - focused ApplicationService test first returned `label_apply.status=skipped`.
  - `poetry run pytest --capture=sys tests/unit/backend/load_data/test_label_loader_coverage.py::TestLoadMat::test_mat_uses_selected_label_and_sample_anchor_as_events tests/unit/backend/application/test_application_service.py::test_apply_interpretation_applies_reviewed_mat_sample_anchor_label_carrier -q`
  - `2 passed`
  - `poetry run pytest --capture=sys tests/unit/backend/load_data/test_label_loader.py tests/unit/backend/load_data/test_label_loader_coverage.py tests/unit/backend/application/test_application_service.py::test_apply_interpretation_applies_reviewed_timestamp_label_carrier tests/unit/backend/application/test_application_service.py::test_apply_interpretation_applies_reviewed_timestamp_label_carriers_by_stem tests/unit/backend/application/test_application_service.py::test_apply_interpretation_skips_ambiguous_multi_file_timestamp_labels tests/unit/backend/application/test_application_service.py::test_apply_interpretation_applies_manually_mapped_generic_timestamp_label tests/unit/backend/application/test_application_service.py::test_apply_interpretation_applies_reviewed_mat_sequence_label_carrier tests/unit/backend/application/test_application_service.py::test_apply_interpretation_applies_reviewed_mat_sample_anchor_label_carrier tests/unit/backend/application/test_application_service.py::test_apply_interpretation_applies_reviewed_sequence_label_carriers_by_stem tests/unit/backend/application/test_application_service.py::test_apply_interpretation_skips_ambiguous_multi_file_sequence_labels tests/unit/backend/application/test_application_service.py::test_apply_interpretation_applies_manually_mapped_generic_sequence_label -q`
  - `35 passed`
  - `poetry run pytest --capture=sys tests/unit/backend/application/test_application_service.py -q`
  - `43 passed`
  - targeted `ruff check` / `ruff format --check` clean.
  - `poetry run basedpyright XBrainLab/backend/load_data/label_loader.py XBrainLab/backend/application/service.py`
  - `0 errors, 0 warnings, 0 notes`
  - `poetry run mkdocs build --strict` -> pass with existing MkDocs Material warning.
  - `poetry run python tests/architecture_compliance.py` -> Architecture compliant.
  - `git diff --check` -> pass.

這批 evidence 支撐 reviewed MAT + sample-index anchor 的窄版 GDF/MAT external-label apply path。
它仍不支撐任意 raw trigger selection、non-sample timestamp conversion、複雜 anchor
reconciliation、XDF stream parser 或 full real-data manual certification。

2026-05-04 Data Interpretation timestamp label apply slice：

- backend:
  - `load_label_file()` now accepts reviewed `label_field` and `anchor` selections.
  - MAT loading can use a selected MAT variable instead of heuristic selection.
  - CSV / TSV / BIDS events loading can use selected label and anchor columns to produce
    timestamp-style labels.
  - `apply_interpretation` now auto-applies labels only for the narrow safe path:
    one loaded EEG file, one reviewed timestamp CSV / TSV / BIDS events carrier, confirmed
    interpretation, and time model `seconds` / `relative_time`.
  - Successful apply records `label_apply` diagnostics, updates applied interpretation
    `label_imports`, and appends `label_import:timestamp:<n>` to recipe trace.
- replay artifact refreshed:
  - `timeout 180s env QT_QPA_PLATFORM=offscreen poetry run python scripts/dev/capture_data_interpretation_replay.py`
  - `artifacts/ui/data-interpretation-replay.json`
  - replay JSON shows `label_apply.status=applied`, one timestamp label import record, and
    `label_import:timestamp:1` in recipe trace.
- targeted gates:
  - `poetry run pytest --capture=sys tests/unit/backend/load_data/test_label_loader.py tests/unit/backend/load_data/test_label_loader_coverage.py tests/unit/backend/application/test_application_service.py tests/integration/backend/test_application_service_workflow.py::test_data_interpretation_to_dataset_workflow_is_non_mocked -q`
  - `60 passed`
  - `scripts/dev/run_ui_pytest.sh tests/unit/ui/dialogs/dataset/test_data_interpretation_preview_dialog.py tests/unit/ui/test_ui_misc.py::TestDatasetActionHandler -q`
  - `51 passed`
  - targeted `ruff` clean.
  - targeted `basedpyright` clean; `.basedpyright/baseline.json` refreshed with one fewer baseline error.

這批 evidence 支撐 reviewed timestamp label carrier 已從 recipe-only 進入 Data Interpretation
apply path。下一個 slice 已補 reviewed MAT / TXT trial-order sequence auto-apply；仍不支撐
raw-event-anchor-specific GDF/MAT alignment、多檔 label mapping、XDF stream parser 或完整
post-load label import 內嵌 wizard。

2026-05-04 Data Interpretation MAT/TXT sequence label apply slice：

- backend:
  - `apply_interpretation` now also auto-applies the narrow sequence path:
    one loaded EEG file, one reviewed MAT / TXT trial-order carrier, confirmed class map, and
    trial granularity.
  - This path uses `load_label_file(label_field=...)`, then existing `apply_labels_legacy()`, and
    records `label_import:legacy:<n>` in the recipe trace.
- targeted gate:
  - `poetry run pytest --capture=sys tests/unit/backend/application/test_application_service.py::test_apply_interpretation_applies_reviewed_mat_sequence_label_carrier tests/unit/backend/application/test_application_service.py::test_apply_interpretation_applies_reviewed_timestamp_label_carrier -q`
  - `2 passed`

這批 evidence 支撐 reviewed MAT trial-order labels 不再只是 recipe plan。它仍不支撐需要選 raw
event anchor 的 GDF/MAT alignment、多檔 label mapping 或 full manual compatibility matrix。

2026-05-04 Data Interpretation shared state snapshot propagation：

- backend:
  - `InterpretationStateSnapshot` now exposes `label_carrier_plan`,
    `format_capabilities`, `event_roles`, and `class_map`.
  - `ApplicationService._interpretation_snapshot()` sources those fields from applied
    interpretation first, then candidate / preview / scan state.
- automation / agent:
  - `query_state` returns the same interpretation review truth in diagnostics.
  - `execute_automation_payload()` includes the fields in its serialized state envelope,
    which is the MCP / headless path.
  - `execute_application_tool_command(..., "query_state", ...)` surfaces the same fields
    through the agent ApplicationService-backed tool surface.
- TDD evidence:
  - initial focused regression failed because `InterpretationStateSnapshot` had no
    `label_carrier_plan` attribute.
- targeted gates:
  - `poetry run pytest --capture=sys tests/unit/backend/application/test_application_service.py::test_data_interpretation_state_snapshot_preserves_import_review_truth tests/unit/backend/application/test_automation.py::test_execute_automation_payload_state_contains_interpretation_review_truth tests/unit/llm/tools/test_application_surface.py::test_query_state_tool_surfaces_interpretation_review_truth -q`
  - `3 passed`
  - `poetry run pytest --capture=sys tests/unit/backend/application/test_application_service.py tests/unit/backend/application/test_automation.py tests/unit/llm/tools/test_application_surface.py -q`
  - `61 passed`
  - targeted `ruff` clean.
  - targeted `ruff format --check` clean.
  - targeted `basedpyright` clean.
  - `poetry run mkdocs build --strict` -> pass with existing MkDocs Material warning.
  - `poetry run python tests/architecture_compliance.py` -> `Architecture compliant!`
  - `git diff --check` -> pass.
  - `poetry run mkdocs build --strict` -> pass with existing MkDocs Material warning.
  - `poetry run python tests/architecture_compliance.py` -> `Architecture compliant!`
  - `git diff --check` -> pass.
  - `poetry run mkdocs build --strict` -> pass with existing MkDocs Material warning.
  - `poetry run python tests/architecture_compliance.py` -> `Architecture compliant!`
  - `git diff --check` -> pass.
  - `poetry run mkdocs build --strict` -> pass with existing MkDocs Material warning.
  - `poetry run python tests/architecture_compliance.py` -> `Architecture compliant!`
  - `git diff --check` -> pass.

這批 evidence 支撐 UI / recipe 已確認的 import truth 不再停留在 backend JSON 或 wizard
內部；agent、headless automation 和 MCP-shaped envelope 可讀到同一份狀態。它仍不支撐 mature
embedded label import wizard、多檔 label mapping、raw-event-anchor-specific GDF/MAT alignment、
真人 Windows click-through、interactive desktop 3D 或 MCP HTTP / long-running client workflow。

2026-05-04 Data Interpretation multi-file timestamp label mapping：

- backend:
  - Reviewed timestamp carriers can now auto-apply to multiple loaded EEG files when each raw
    file has exactly one matching CSV / TSV / BIDS events carrier by normalized stem.
  - Existing single-file behavior remains unchanged: one target and one reviewed carrier can
    apply directly even when stems do not match.
  - Ambiguous multi-file cases such as one generic `events.tsv` for two loaded files are skipped
    with a reason instead of applying the same labels to multiple files.
- TDD evidence:
  - initial positive regression failed with `label_apply.status=skipped`.
- targeted gates:
  - `poetry run pytest --capture=sys tests/unit/backend/application/test_application_service.py::test_apply_interpretation_applies_reviewed_timestamp_label_carriers_by_stem tests/unit/backend/application/test_application_service.py::test_apply_interpretation_skips_ambiguous_multi_file_timestamp_labels tests/unit/backend/application/test_application_service.py::test_apply_interpretation_applies_reviewed_timestamp_label_carrier tests/unit/backend/application/test_application_service.py::test_apply_interpretation_applies_reviewed_mat_sequence_label_carrier -q`
  - `4 passed`
  - `poetry run pytest --capture=sys tests/unit/backend/application/test_application_service.py tests/unit/backend/application/test_automation.py tests/unit/llm/tools/test_application_surface.py -q`
  - `63 passed`
  - targeted `ruff` clean.
  - targeted `ruff format --check` clean.
  - targeted `basedpyright` clean.

這批 evidence 支撐 BIDS-style per-run timestamp labels 的 safe multi-file backend path。它仍不支撐
generic folder-level `events.tsv` disambiguation、multi-file MAT / TXT sequence mapping、
raw-event-anchor-specific GDF / MAT alignment、embedded label wizard UI 或真人 click-through。

2026-05-04 Data Interpretation multi-file sequence label mapping：

- backend:
  - Reviewed MAT / TXT trial-order sequence carriers can now auto-apply to multiple loaded EEG
    files when every raw file has exactly one matching carrier by normalized stem.
  - Sequence mapping calls existing `apply_labels_legacy()` once per matched target file, so
    per-file label sequences are not concatenated or shared across files.
  - Ambiguous multi-file cases such as one generic `labels.mat` for two loaded files are skipped
    with a reason instead of distributing labels by guesswork.
- TDD evidence:
  - initial positive regression failed with `label_apply.status=skipped`.
- targeted gates:
  - `poetry run pytest --capture=sys tests/unit/backend/application/test_application_service.py::test_apply_interpretation_applies_reviewed_sequence_label_carriers_by_stem tests/unit/backend/application/test_application_service.py::test_apply_interpretation_skips_ambiguous_multi_file_sequence_labels -q`
  - `2 passed`
  - `poetry run pytest --capture=sys tests/unit/backend/application/test_application_service.py tests/unit/backend/application/test_automation.py tests/unit/llm/tools/test_application_surface.py -q`
  - `65 passed`
  - targeted `ruff` clean.
  - targeted `ruff format --check` clean.
  - targeted `basedpyright` clean.

這批 evidence 支撐 per-file MAT/TXT trial-order label sequences 的 safe multi-file backend path。
它仍不支撐 generic label disambiguation、raw-event-anchor-specific GDF / MAT alignment、embedded
label wizard UI 或真人 click-through。

2026-05-04 Data Interpretation label carrier matched-EEG UI slice：

- UI:
  - `DataInterpretationPreviewDialog` label carrier table now includes a `Matched EEG` column.
  - Single-file direct match and multi-file unique stem match show the target EEG file name.
  - Ambiguous multi-file carrier rows show `Needs review`.
  - Label carrier choices still return `label_field`, `anchor`, `time_model`, and `granularity`
    from the shifted editable columns.
- UI-observable replay:
  - command: `timeout 180s env QT_QPA_PLATFORM=offscreen poetry run python scripts/dev/capture_data_interpretation_replay.py`
  - artifacts:
    - `artifacts/ui/data-interpretation-preview.png`
    - `artifacts/ui/data-interpretation-replay.json`
  - replay JSON `label_carrier_rows` shows:
    `product_replay_events.tsv -> product_replay_raw.fif`.
  - replay JSON still shows reviewed `trial_type` / `onset` / `seconds` / `trial` choices and
    `label_apply.status=applied`.
- targeted gates:
  - `scripts/dev/run_ui_pytest.sh tests/unit/ui/dialogs/dataset/test_data_interpretation_preview_dialog.py tests/unit/ui/test_ui_misc.py::TestDatasetActionHandler -q`
  - `52 passed`
  - targeted `ruff` clean.
  - targeted `ruff format --check` clean.
  - targeted `basedpyright` clean.

這批 evidence 支撐 import wizard 對 label carrier mapping 的使用者可見性。它仍不是完整 embedded
post-load label import wizard，也不支撐 raw-event-anchor-specific MAT/GDF alignment 或真人
click-through。

2026-05-04 Data Interpretation manual generic label target mapping:

- backend:
  - Label carrier choices now accept `target_file` and preserve it as
    `selected_target_file` in `label_carrier_plan`.
  - Reviewed generic timestamp carriers such as folder-level `events.tsv` can be applied to a
    user-selected loaded EEG file instead of being skipped as ambiguous.
  - Reviewed generic MAT / TXT trial-order carriers such as `labels.mat` can likewise be
    applied to a user-selected loaded EEG file through the legacy sequence label path.
  - If no target is selected, the previous ambiguous skip behavior remains.
- UI:
  - The editable `Matched EEG` column now contributes `target_file` to
    `label_carrier_choices` when the user changes it from `Needs review`.
  - The replay artifact was refreshed to show generic `events.tsv` mapped to
    `sub-01_task-mi_run-2_raw.fif`.
- UI-observable replay:
  - command: `timeout 180s env QT_QPA_PLATFORM=offscreen poetry run python scripts/dev/capture_data_interpretation_replay.py`
  - artifact:
    - `artifacts/ui/data-interpretation-preview.png`
    - `artifacts/ui/data-interpretation-replay.json`
  - replay JSON `label_carrier_rows` shows:
    `events.tsv -> sub-01_task-mi_run-2_raw.fif`.
  - replay JSON `review_choices.label_carrier_choices` includes `target_file`.
  - replay JSON `label_apply` shows `status=applied`, `success_count=1`, and target file
    `sub-01_task-mi_run-2_raw.fif`.
- targeted gates:
  - `scripts/dev/run_ui_pytest.sh tests/unit/ui/dialogs/dataset/test_data_interpretation_preview_dialog.py -q`
  - `7 passed`
  - `poetry run pytest --capture=sys tests/unit/backend/application/test_application_service.py::test_apply_interpretation_applies_manually_mapped_generic_timestamp_label tests/unit/backend/application/test_application_service.py::test_apply_interpretation_applies_manually_mapped_generic_sequence_label tests/unit/backend/application/test_application_service.py::test_apply_interpretation_skips_ambiguous_multi_file_timestamp_labels tests/unit/backend/application/test_application_service.py::test_apply_interpretation_skips_ambiguous_multi_file_sequence_labels -q`
  - `4 passed`
  - `poetry run pytest --capture=sys tests/unit/backend/application/test_application_service.py tests/unit/backend/application/test_automation.py tests/unit/llm/tools/test_application_surface.py -q`
  - `67 passed`
  - `scripts/dev/run_ui_pytest.sh tests/unit/ui/dialogs/dataset/test_data_interpretation_preview_dialog.py tests/unit/ui/test_ui_misc.py::TestDatasetActionHandler -q`
  - `54 passed`
  - targeted `ruff`, `ruff format --check`, and production `basedpyright` clean.
  - `poetry run python tests/architecture_compliance.py` -> Architecture compliant.
  - `poetry run mkdocs build --strict` -> pass with existing MkDocs Material warning.
  - `git diff --check` -> pass.

這批 evidence 支撐 generic label carrier disambiguation 的第一個 embedded wizard path。它仍不支撐
raw-event-anchor-specific GDF / MAT alignment、all-format manual compatibility matrix、post-load
label import full editor、或真人 click-through。

2026-05-04 Data Interpretation label target selector UX:

- UI:
  - Ambiguous label carrier rows now render a `QComboBox` in the `Matched EEG` column.
  - The selector options are `Needs review` plus scanned EEG file names.
  - `get_result()` reads the selector value, so the same `target_file` choice flows into
    preview / apply.
- UI-observable replay:
  - `tree_rows()` now reads cell-widget text, so replay JSON records the visible selector value.
  - refreshed replay still shows `events.tsv -> sub-01_task-mi_run-2_raw.fif`.
- targeted gates:
  - `scripts/dev/run_ui_pytest.sh tests/unit/ui/dialogs/dataset/test_data_interpretation_preview_dialog.py::test_data_interpretation_preview_dialog_returns_manual_label_target_mapping -q`
  - `1 passed`
  - `scripts/dev/run_ui_pytest.sh tests/unit/ui/dialogs/dataset/test_data_interpretation_preview_dialog.py -q`
  - `7 passed`
  - `timeout 180s env QT_QPA_PLATFORM=offscreen poetry run python scripts/dev/capture_data_interpretation_replay.py`
  - exit `0`
  - `scripts/dev/run_ui_pytest.sh tests/unit/ui/dialogs/dataset/test_data_interpretation_preview_dialog.py tests/unit/ui/test_ui_misc.py::TestDatasetActionHandler -q`
  - `54 passed`
  - `poetry run pytest --capture=sys tests/unit/backend/application/test_application_service.py::test_apply_interpretation_applies_manually_mapped_generic_timestamp_label tests/unit/backend/application/test_application_service.py::test_apply_interpretation_applies_manually_mapped_generic_sequence_label -q`
  - `2 passed`
  - targeted `ruff`, `ruff format --check`, and production `basedpyright` clean.

這批 evidence 支撐 generic carrier target mapping 的使用者操作不再依賴手打欄位。它仍不是完整
post-load label import full editor、all-format manual compatibility matrix 或真人 click-through。

2026-05-04 post-load label import target context slice：

- UI:
  - `ImportLabelDialog` title is now `Add Labels to Loaded Data`.
  - The dialog accepts selected target files and shows which loaded EEG file(s) will receive
    labels.
  - The dialog tells the user that a successful import updates the current import recipe trace
    when a data interpretation is active.
  - `DatasetActionHandler.import_label()` passes selected target files into the dialog.
- TDD evidence:
  - initial focused tests failed because `ImportLabelDialog` had no `target_files` argument and
    `DatasetActionHandler` did not pass target context.
- targeted gates:
  - `scripts/dev/run_ui_pytest.sh tests/unit/ui/dataset/test_import_label.py::test_import_label_dialog_shows_target_context tests/unit/ui/test_ui_misc.py::TestDatasetActionHandler::test_import_label_passes_target_context_to_dialog -q`
  - `2 passed`
  - `scripts/dev/run_ui_pytest.sh tests/unit/ui/dataset/test_import_label.py tests/unit/ui/test_ui_misc.py::TestDatasetActionHandler tests/unit/ui/test_ui_misc.py::TestImportLabelDialog -q`
  - `83 passed`
  - targeted `ruff` clean.
  - targeted `ruff format --check` clean.
  - production `basedpyright` for touched UI files clean.
  - `poetry run mkdocs build --strict` -> pass with existing MkDocs Material warning.
  - `poetry run python tests/architecture_compliance.py` -> `Architecture compliant!`
  - `git diff --check` -> pass.

這批 evidence 支撐 compatibility label import flow 的 target visibility and recipe-impact wording。
它仍不是完整 embedded label wizard，也沒有取代 Data Interpretation source-level import flow。

2026-05-04 Data Interpretation recipe save UI path：

- Preview dialog 新增 `Save recipe after applying` checkbox，blocked decision 會 disabled。
- Dataset panel apply 成功後，若使用者勾選保存 recipe，UI 會呼叫
  `SaveInterpretationRecipeCommand`；若使用者選擇路徑，recipe 寫入該 JSON 檔，否則保留在
  backend session。
- commands:
  - `poetry run pytest --capture=sys tests/unit/ui/test_ui_misc.py::TestDatasetActionHandler tests/unit/ui/dialogs/dataset/test_data_interpretation_preview_dialog.py tests/integration/ui/test_product_walkthrough.py::test_pipeline_product_walkthrough_uses_user_facing_actions -q`
  - `46 passed`
  - `poetry run ruff check XBrainLab/ui/dialogs/dataset/data_interpretation_preview_dialog.py XBrainLab/ui/panels/dataset/actions.py tests/unit/ui/test_ui_misc.py tests/unit/ui/dialogs/dataset/test_data_interpretation_preview_dialog.py tests/integration/ui/test_product_walkthrough.py`
  - `PASS`
  - `poetry run basedpyright XBrainLab/ui/dialogs/dataset/data_interpretation_preview_dialog.py XBrainLab/ui/panels/dataset/actions.py tests/unit/ui/dialogs/dataset/test_data_interpretation_preview_dialog.py`
  - `0 errors, 0 warnings, 0 notes`

這批 evidence 支撐 UI import flow 的 recipe save option。後續 label import trace integration
已補；舊 label import 仍是 `Add Labels to Loaded Data` compatibility UI，尚未成為完整 import
wizard label/recipe editor。

2026-05-04 label import recipe trace integration：

- `ImportRecipe` / `AppliedInterpretation` 新增 `label_imports`，並在成功
  `ImportLabelsCommand` 後保存：
  - label carriers。
  - target files / file mapping。
  - selected event names。
  - class map。
  - success count。
- `ApplicationStateSnapshot.interpretation` 現在暴露 `label_carriers`、`label_import_count` 和
  `label_imports`，供 UI / agent / MCP / scorer 讀同一份 recipe trace。
- Dataset panel 的 `Add Labels to Loaded Data` 成功後，若 backend 回報 recipe trace 更新，UI 會
  用使用者語言提示並可保存更新後 recipe。
- commands:
  - `poetry run pytest --capture=sys tests/unit/backend/application/test_application_service.py::test_import_labels_updates_applied_interpretation_recipe_trace tests/unit/ui/test_ui_misc.py::TestDatasetActionHandler::test_import_label_offers_to_save_updated_recipe -q`
  - `2 passed`
  - `poetry run pytest --capture=sys tests/unit/backend/application/test_application_service.py tests/unit/ui/test_ui_misc.py::TestDatasetActionHandler -q`
  - `74 passed`
  - `poetry run pytest --capture=sys tests/unit/backend/application -q`
  - `36 passed`
  - `poetry run pytest --capture=sys tests/integration/backend/test_application_service_workflow.py -q`
  - `3 passed`
  - `poetry run pytest --capture=sys tests/unit/llm/tools/test_application_surface.py tests/unit/llm/agent/test_controller.py -q`
  - `66 passed`
  - targeted `ruff` / `basedpyright` clean。

這批 evidence 支撐 label import 不再只停在 raw controller label mutation，而會進入 Data
Interpretation recipe trace。它仍不支撐成熟 import wizard label editor、UI screenshot replay
或真人 click-through。

## Automated Evidence vs Product Evidence

| Evidence | 目前能證明 | 不能證明 |
| --- | --- | --- |
| startup smoke | `MainWindow` 能初始化 | assistant dock 打開後可用、可回覆、可讀 |
| local prompt smoke | local backend 能對最小 prompt 回文字 | UI chat flow 已接上、streaming 不被吃掉、錯誤可見 |
| structured-output smoke | 模型可按 prompt 產出 tool JSON | agent 在真 UI 中能穩定選 tool、解釋 blocked reason |
| deterministic eval | case schema / scoring / scripted policy 正確 | local LLM 真實 tool-call 成功率 |
| local tool-call eval | 真 primary / fallback local model raw output 能被 parser / verifier / scorer 審計 | 真 UI ChatPanel multi-turn / tool-command workflow |
| UI baseline | approved screenshots 沒有大幅 pixel drift | UI 是否產品級、是否能互動、是否 no-response |
| product walkthrough smoke | assistant layout / panel navigation / synthetic EEG button path 可重跑 | 真 launcher 人工體驗、完整訓練品質、所有 dialog / query action |
| split artifact audit | train/validation/test indices 和 subject/session leakage 可審計 | classification quality 或 thesis conclusion |
| UI unit tests | signal / slot 和 widget state 有 regression protection | 真人 click-through 完整體驗 |

未來不能再只用 deterministic eval 或 dashboard PASS 宣稱 assistant product gate 完成。
assistant product gate 至少要包含 user-visible normal chat flow、blocked command feedback、
local unavailable feedback 和 launcher click-through evidence。

## Clean Dashboard 判定

fast quality dashboard 的 clean 判定不是只看 script 有沒有跑完。

目前專案採用的 clean 定義是：

1. `artifacts/quality/latest.json` 的 `overall_status` 必須是 `pass`。
2. `checks[*].status` 必須全部是 `pass`。
3. `artifacts/quality/latest.md` 的 summary table 不應有 `FAIL` 或 `WARN`。
4. `workspace` 必須是目前 active repo：
   - `/mnt/d/workspace_v2/projects/lab/XBrainLab`
5. `generated_at` 必須是本次驗證時間，不是舊 artifact。

腳本內部的 overall 規則是：

- 任何 check 是 `fail` -> overall 是 `fail`
- 沒有 `fail`，但有 `warn` -> overall 是 `warn`
- 全部都是 `pass` -> overall 才是 `pass`

因此「clean」比「command exit 0」更嚴格：我們要的是 overall `PASS`，不是只有 script 沒崩潰。

## 驗證層級

| 層級 | 用途 |
| --- | --- |
| unit tests | 保護局部行為和 regression。 |
| integration tests | 驗證 UI/backend/data pipeline 的跨模組行為。 |
| real-data tests | 驗證實際 EEG format / fixture path。 |
| UI baselines | 驗證核心 UI 畫面沒有明顯漂移。 |
| quality dashboard | 快速整合健康檢查。 |
| thesis validation | 將工程 evidence 映射到研究 claim。 |

## Mock-heavy Test 判讀

目前測試確實偏 mock-heavy。

快速掃描結果：

- test files：`254`
- 含 `MagicMock` / `Mock` / `patch` / `monkeypatch` / `mocker` 的 test files：`144`
- unit test files：`214`
- mock-heavy unit test files：`124`
- integration test files：`33`
- 含 mock 的 integration test files：`17`

這代表目前測試比較擅長抓：

- API contract 變了。
- UI signal / slot wiring 斷了。
- controller method 沒被呼叫。
- 錯誤處理、狀態切換、參數 normalization 出現 regression。
- dashboard 這類 fast gate 裡已納入的啟動、UI baseline、IO slice 壞掉。

目前比較不擅長抓：

- 真實使用者 workflow 的長鏈路錯誤。
- 真實 Qt event timing / thread race。
- 真實 LLM local runtime、GPU、model cache、tool-call output。
- controller -> manager -> data pipeline 的完整 side effect。
- 長時間訓練、真實資料集 reproducibility。
- thesis-grade tool-call validation。

所以 test health 的判讀是：

- daily regression floor：尚可。
- end-to-end confidence：中等偏弱。
- agent runtime confidence：低。
- thesis validation confidence：低。

要提升可信度，不是刪掉 mocks，而是補少量高價值 non-mocked path：

- real `Study` + real controllers 的 backend workflow tests。
- UI button-driven acceptance tests。
- local-only assistant runtime smoke。
- public fixture pipeline smoke。
- thesis validation matrix。

## Pipeline Validation 分層

完整 pipeline 要測，但不要只靠一個超大的測試。

目前採用四層判斷：

| 層級 | 要回答的問題 | 代表 evidence |
| --- | --- | --- |
| fast dashboard | repo 今天是否健康？ | lint、type、startup、UI、real-data IO |
| tiny E2E pipeline smoke | `dataset -> train -> evaluate` 是否能閉環？ | 小資料、CPU、1-2 epoch、metrics 不壞 |
| public fixture pipeline smoke | 真實 EEG 來源是否能走到 training smoke？ | public event-rich fixtures |
| scientific validation | 結果是否可重現且支撐 thesis claim？ | 固定 protocol、baseline、統計與 threat analysis |

### Tiny E2E Pipeline Clean 定義

tiny E2E pipeline clean 不是追求高 accuracy，而是確認流程正確：

1. dataset 能提供 training / validation / test split。
2. model args 和資料 shape 對得上。
3. CPU one-epoch 或 two-epoch training 能跑完。
4. loss / accuracy 等 metrics 存在且範圍合理。
5. evaluation record 存在。
6. 檔案輸出要被 patch 或寫到受控目錄，不能污染 workspace。

### 目前已跑過的 Pipeline Evidence

`2026-05-01` targeted pipeline smoke：

```bash
poetry run pytest --capture=sys \
  tests/integration/pipeline/test_full_pipeline.py::TestFullPipeline::test_train_and_evaluate_metrics \
  tests/integration/pipeline/test_study_training_e2e.py::TestStudyTrainCycle::test_full_cycle_eegnet \
  -q
```

首次結果：

- `2 passed in 7.54s`

data pipeline 文件驗證重跑結果：

- `2 passed in 5.89s`

這代表 tiny train/evaluate 和 Study facade train cycle 有基本閉環證據。

但它仍不代表：

- 所有 real EEG source 都能完整 training。
- training result 可重現。
- thesis claim 已成立。
- local LLM / agent runtime 的完整互動式產品流程已驗證。

## Thesis Protocol

thesis-grade validation protocol 目前放在：

```text
docs/validation/thesis_protocol.md
docs/validation/split_artifact_schema.json
```

核心定位：

- 論文要仔細驗證的是 agent tool-call accuracy，不是 EEG 訓練準確率。
- EEG data / split / training / evaluation 驗證只支撐產品 workflow 和 domain task sanity。
- 不可把 train/evaluate accuracy、split audit 或 external dataset runner 當作 agent thesis
  主結果。

tool-call thesis evidence 核心要求：

- 固定 benchmark cases。
- 同一 cases 接 deterministic baseline 與 local LLM primary / fallback runner。
- 比對 intent、tool / no-tool decision、tool selection、parameters、state transition、
  clarification behavior、blocked-command handling、confirmation boundary、error recovery、
  runtime safety、trajectory 和 user-visible response。
- 產生 machine-readable report、human-readable summary 和 dashboard。

目前最新 evidence：

- cases：`117`
- deterministic baseline：`117 / 117`
- primary local model：`117 / 117` x `3`
- fallback local model：`117 / 117` x `3`
- dashboard：`artifacts/agent_evals/dashboard.md`

EEG pipeline support 要求：

- dataset source 分層：checked-in fixtures、public fixtures、external thesis datasets。
- split protocol 明確標記 `trial-wise`、`session-wise` 或 `subject-wise`。
- train / validation / test indices 必須保存，且 validation 必須從 test 之外的 remaining data 產生。
- 若報告 EEG model sanity，metrics 至少包含 accuracy、balanced accuracy、macro F1、AUC、confusion matrix。
- baseline、config、logs、model summary、environment info 必須和 split artifact 一起保存。

目前 code support：

```bash
poetry run pytest --capture=sys \
  tests/unit/backend/dataset/test_split_audit.py \
  tests/unit/scripts/test_validate_split_artifact.py -q

poetry run python scripts/dev/validate_split_artifact.py artifacts/thesis/splits.json
```

這只代表 EEG split protocol 與 artifact audit 能重跑；正式 thesis evidence 目前已有 local
LLM tool-call runner、repeat runs、score report、dashboard 和 failure taxonomy。external dataset
runner、baseline comparison 和 statistical reporting 是 pipeline support，不是 tool-call thesis 主指標。

## Agent Runtime Validation

assistant product runtime 目前是 local-only。

這代表目前 validation 重點是：

- local model cache 是否存在。
- local transformer runtime 是否能在目標 GPU 上載入。
- GPU / CPU fallback 是否可預期。
- local generation timeout / stop / model reload 是否穩定。
- local model tool-call output 是否能穩定被 parser / verifier 接住。
- legacy remote settings 是否會 migrate / fail closed，而不是 instantiate remote backend。

目前已驗證：

- local model catalog、preflight、cache policy、health check 已落地。
- primary / fallback model cache 已存在且通過 CUDA prompt / structured-output smoke。
- `LLMConfig`、`LLMEngine`、`AgentWorker` 對 `api` / `gemini` legacy selection 會轉回 local
  或 fail closed；`reinitialize_agent("Gemini")` 不會建立 remote backend。
- product package 已移除 remote backend modules；architecture compliance 會掃 product code 中的
  remote backend class / key env path。
- model settings dialog 已收斂為 local-only UI；default dependencies 不包含 remote SDK。
- local runtime smoke 尚未納入 fast dashboard 預設 profile。
- local tool-call eval dashboard 已納入 validation artifact，但不能替代 UI-observable automated
  walkthrough 或 human desktop acceptance。

Gemini/API 不再列為未來產品驗證目標，也不是 product execution mode。若未來需要歷史比較，
必須放在 optional legacy fixture，不可由 product code import。

## Agent Tool-Call Scoring

thesis evidence 需要一套可重跑的 agent tool-call 評分工具。

這套工具應：

- 使用固定 benchmark cases。
- 驗證 LLM proposed tool call，而不是只看自然語言回答。
- 比對 expected intent、tool name、parameters、required state 和 expected result。
- 記錄 backend execution 是否成功，以及 state 是否如預期改變。
- 對 validation failure / self-correction 做分項評分。
- 產生 machine-readable report 和 human-readable summary。

目前 score 維度：

- intent accuracy。
- tool or no-tool decision accuracy。
- tool selection accuracy。
- parameter accuracy。
- state-transition accuracy。
- clarification behavior。
- blocked-command handling。
- confirmation-boundary handling。
- trajectory quality。
- visible response quality。
- runtime safety。
- error-recovery accuracy。
- repeated local-model stability。

舊 `scripts/agent/benchmarks/*` 可以作為歷史參考，但不能直接視為新的 thesis evidence。新的 scoring system 需要對齊 local-only runtime、State Manager、Verification Layer 和未來 Application Service / Command API。

## 目前優先驗證

1. Product delivery 主線優先：backend -> UI -> agent -> local LLM -> desktop launcher。
2. UI / agent command surface 統一後，補對應 backend、UI、agent regression tests。
3. Local LLM runtime 需要 health check、prompt smoke、structured-output / tool-call smoke 和 fallback evidence。
4. Desktop launcher 需要 startup smoke 與 missing local LLM 不閃退證據。
5. Tool-call eval / thesis evidence 只在產品主線穩定後開始。
6. Split artifact protocol 已建立，但它是 EEG pipeline support，不是 thesis 主評分。
7. scoring system 可重跑後，再收集 tool-call thesis validation evidence matrix。
8. Local LLM validation 只驗證符合選型限制的非中國模型；Qwen、DeepSeek、Yi、GLM、Baichuan、InternLM、MiniCPM 等不作為候選。

## 注意事項

- dashboard PASS 不是論文結論。
- training smoke 不是完整 reproducibility。
- local-only public fixtures 要和 checked-in baseline 分開標示。
- 每個 thesis claim 最後都應該能對到 command、test、artifact、experiment、score report 或文獻。
- `dev,test,docs` 是目前已驗證的標準 group；local LLM smoke 已另行驗證，但尚未納入 fast dashboard 預設 profile。
- assistant 是 local-only product runtime；Gemini/API key flow 不是必驗路線，相關 product code path
  已移除或由 architecture guard 阻擋回歸。
