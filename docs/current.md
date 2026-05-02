# XBrainLab 目前狀態

最後更新：`2026-05-02`

## 摘要

XBrainLab 的 active repo 已在目前 workspace 專案區。標準 `dev,test,docs` 環境可用，fast quality dashboard 已在新路徑刷新，結果是 clean `PASS`。

目前階段已進入 product-delivery engineering。`2026-05-02` 人工驗收曾修正先前的
產品判斷：AI Assistant 當時仍像 debug dock，且一般輸入 `hello` 後沒有任何 assistant
回覆。這代表先前 automated final gate、local runtime smoke、launcher startup smoke、
deterministic eval 都不能被解讀成「可用桌面產品已完成」。

後端 `ApplicationService / Command API` 第一版已落地，並完成 command contract、
capability policy、reset state invalidation 和 facade compatibility 的驗收補強。UI / Agent
command surface 第一批統一也已完成：UI readiness 和 agent tool availability 都開始讀同一套
ApplicationService capability policy，agent tool result 已收斂成 typed adapter。local LLM
runtime 已完成非中國 primary / fallback 模型選型、cache preflight、下載、GPU prompt smoke
和 structured-output smoke；desktop launcher 已產出並完成 startup smoke。

目前 chat release blocker 已完成產品級修復：normal text input 有可見 assistant 回覆，
空回覆 / worker error / local unavailable 都有可見狀態，ChatPanel 已改成使用者導向
產品面板，第一層 UI 不再顯示 raw command names。local assistant runtime 現在有 first-run
consent，使用者明確選擇 Enable / Download / Use existing cache / Later / Disable 前不會
偷偷載入大型模型。

2026-05-02 人工產品審核 follow-up 又補了一輪產品級修正：Assistant dock 頂部不再顯示
chip dump，主 header 只保留產品名、自然語言 subtitle 和 Options；workflow / next step 改成
單句 guidance，runtime / backend readiness 降到 dock 底部低干擾 status。`Retry` 沒有上一則
request 時預設 disabled，直接呼叫也只顯示 footer/status notice，不再污染 transcript。
agent visible transcript 不再顯示 `Tool <name> completed (...)`、schema error、empty list 或
snake_case command；raw tool payload 保留在 controller history / diagnostics。Gemini / remote
runtime UI 已從一般產品入口隔離，只有明確設定 `XBRAINLAB_SHOW_LEGACY_REMOTE_LLM=1` 才顯示。

UI action execution 已把 import、preprocess、epoch、split / model / training setting
dialogs、evaluation / visualization / saliency query、training start / stop、reset /
new session、metadata update、smart parse、remove files、label import 和 montage confirmation
這批 path 接到 `ApplicationService.execute()`；agent mapped tools 也可直接取得
`CommandResult` payload。新增 `LabelImportPlan`、`apply_montage` 和 `query_state`
讓 UI / agent 不必繞 controller 拿 typed result。本輪新增 split audit / thesis protocol
artifact schema，讓 train/validation/test split 可保存、重跑、審計。真 Windows launcher
人工 click-through、真 local model 長時間 UI walkthrough、external thesis experiment runner
仍未完成，不能宣稱完整 release closure。

## 可信狀態

- active repo：`/mnt/d/workspace_v2/projects/lab/XBrainLab`
- 舊 repo 副本：`/mnt/d/repos/XBrainLab`，目前只作 archive / reference。
- branch：`codex/stabilization-autopilot`
- remote：`https://github.com/hxin-an/XBrainLab.git`
- docs 已收斂成 `target/`、`architecture/`、`planning/`、`decisions/`、`validation/`、`records/`，根層只保留入口與目前狀態 / 操作文件。
- root `ROADMAP.md` 已刪除；目前路線只看 `docs/planning/roadmap.md`。
- `CHANGELOG.md` 只保留歷史版本紀錄，不作 current truth。
- 標準 Poetry env 已安裝 `dev,test,docs` dependency group：
  - `/home/administrator/.cache/pypoetry/virtualenvs/xbrainlab-TKrzxeIe-py3.12`
- import probe 已通過：
  - `PIL 12.1.0`
  - `mne 1.11.0`
  - `PyQt6`
  - `torch 2.11.0+cu130`
  - `pytest 8.4.2`
  - `XBrainLab 0.5.6`
- 文件站點已可用：
  - `poetry run mkdocs build --strict`
- local assistant runtime 已可用且受 first-run consent 控制：
  - primary：`microsoft/Phi-4-mini-instruct`
  - fallback：`microsoft/Phi-3.5-mini-instruct`
  - cache：`XBrainLab/llm/core/models`
  - current cache usage：約 `15.34 GB`
  - Qwen cache 已刪除；中國公司或中國來源模型不列入選型。
- 桌面 launcher 已產出：
  - repo source：`scripts/launchers/xbrainlab_wsl_launcher.cmd`
  - repo source：`scripts/launchers/xbrainlab_wsl_launcher.ps1`
  - Windows Desktop：`/mnt/c/Users/Administrator/Desktop/XBrainLab.cmd`

## 品質門檻

最新 fast dashboard：

- generated at：`2026-05-02 17:44:37 UTC+08:00`
- workspace：`/mnt/d/workspace_v2/projects/lab/XBrainLab`
- overall：`PASS`
- 來源：`artifacts/quality/latest.json`、`artifacts/quality/latest.md`

當時全部 gate 都是 `PASS`：

- Ruff Lint
- Basedpyright
- Architecture Compliance
- Startup Smoke
- UI Baseline Capture
- UI Dialog Acceptance
- UI Unit Suite
- Real-Data IO Integration

最新 fast dashboard 摘要：

- Ruff Lint：`PASS`
- Basedpyright：`PASS`，`0 errors, 0 warnings, 0 notes`
- Architecture Compliance：`PASS`
- Startup Smoke：`PASS`
- UI Baseline Capture：`PASS`，`7 UI artifacts match approved references`
- UI Dialog Acceptance：`PASS`
- UI Unit Suite：`PASS`，`830 passed`
- Real-Data IO Integration：`PASS`，`31 passed, 8 warnings`

補充已知通過項目：

- backend Application Service / facade contract suite：
  - `poetry run pytest --capture=sys tests/unit/backend/application -q`
  - `9 passed`
  - `poetry run pytest --capture=sys tests/integration/backend/test_application_service_workflow.py -q`
  - `2 passed`
  - `poetry run pytest --capture=sys tests/unit/backend/test_facade_coverage.py tests/unit/backend/test_facade_headless.py -q`
  - `44 passed`
- UI unit suite：
  - `scripts/dev/run_ui_pytest.sh tests/unit/ui -q`
  - `817 passed`
- LLM unit suite：
  - `poetry run pytest --capture=sys tests/unit/llm -q`
  - `652 passed`
- agent tool/control suite：
  - `poetry run pytest --capture=sys tests/unit/llm/agent tests/unit/llm/tools -q`
  - `321 passed`
- 2026-05-02 product delivery targeted gate：
  - `timeout 300s scripts/dev/run_ui_pytest.sh tests/unit/ui/chat/test_chat_panel.py tests/unit/ui/chat/test_message_bubble.py tests/unit/ui/components/test_agent_manager.py tests/integration/ui/test_product_walkthrough.py -q`
  - `62 passed`
  - `timeout 300s poetry run pytest --capture=sys tests/unit/llm/agent/test_controller.py tests/unit/llm/agent/test_worker.py tests/unit/llm/tools/test_application_surface.py tests/unit/backend/application tests/integration/backend/test_application_service_workflow.py -q`
  - `95 passed`
  - `timeout 300s poetry run pytest --capture=sys tests/integration/io/test_io_integration.py -q`
  - `31 passed, 8 warnings`
  - `timeout 600s poetry run pytest --capture=sys tests/integration/pipeline/test_full_pipeline.py::TestFullPipeline::test_train_and_evaluate_metrics tests/integration/pipeline/test_study_training_e2e.py::TestStudyTrainCycle::test_full_cycle_eegnet -q`
  - `2 passed`
- backend unit suite：
  - `poetry run pytest --capture=sys tests/unit/backend -q`
  - `2661 passed, 1 skipped, 1 xfailed`
- backend + IO integration：
  - `poetry run pytest --capture=sys tests/integration/backend tests/integration/io/test_io_integration.py -q`
  - `33 passed`
- full pipeline integration：
  - `poetry run pytest --capture=sys tests/integration/pipeline -q`
  - `70 passed`
- local assistant runtime smoke：
  - preflight：
  - `poetry run python scripts/dev/plan_local_model_download.py --format markdown`
  - primary already cached；estimated download `0.00 GB`；projected cache `15.34 GB`
  - `poetry run python scripts/dev/inspect_local_assistant_runtime.py --format markdown --prompt-smoke --structured-smoke`
  - primary prompt smoke：`passed`
  - primary structured-output smoke：`passed`
  - `poetry run python scripts/dev/inspect_local_assistant_runtime.py --model microsoft/Phi-3.5-mini-instruct --format markdown --prompt-smoke --structured-smoke`
  - fallback prompt smoke：`passed`
  - fallback structured-output smoke：`passed`
- startup smoke：
  - `timeout 45s xvfb-run -a poetry run python run.py --model local`
  - `MainWindow initialized` 後 timeout 結束，屬於 GUI smoke 預期結果。
- tool-call eval deterministic baseline：
  - `poetry run python scripts/agent/evals/run_tool_call_eval.py --output-dir artifacts/agent_evals`
  - artifacts：`artifacts/agent_evals/latest.json`、`artifacts/agent_evals/latest.md`
  - `21 / 21` cases passed；deterministic baseline，不是 local LLM performance claim。
- 2026-05-02 assistant runtime consent / query command / thesis protocol closure：
  - UI product gate：`62 passed`
  - backend / split audit / config gate：`41 passed`
  - agent / facade / backend workflow gate：`130 passed`
  - full test gate：`4386 passed, 3 skipped, 3 deselected, 1 xfailed, 14 warnings`
- `ai-assistant-open.png` 的 `(1684, 800)` product redesign baseline 已接受，尺寸和
  live artifact、repo HEAD reference 一致。
- 2026-05-02 assistant product audit follow-up targeted evidence：
  - UI assistant / settings / AgentManager gate：
    `timeout 300s scripts/dev/run_ui_pytest.sh tests/unit/ui/chat/test_chat_panel.py tests/unit/ui/chat/test_message_bubble.py tests/unit/ui/dialogs/test_model_settings.py tests/unit/ui/components/test_agent_manager.py tests/unit/ui/test_agent_manager_coverage.py -q`
    - `131 passed`
  - agent product-flow / backend command gate：
    `timeout 240s poetry run pytest --capture=sys tests/integration/agent/test_product_flow.py tests/unit/llm/agent/test_controller.py tests/unit/llm/tools/test_application_surface.py tests/unit/llm/tools/real/test_real_tools.py tests/unit/llm/core/test_config.py -q`
    - `110 passed`
  - backend application / facade workflow gate：
    `timeout 240s poetry run pytest --capture=sys tests/unit/backend/application tests/integration/backend/test_application_service_workflow.py tests/unit/backend/test_facade_coverage.py tests/unit/backend/test_facade_headless.py -q`
    - `57 passed`
  - product walkthrough / agent integration：
    `tests/integration/ui/test_product_walkthrough.py` -> `2 passed`
    `tests/integration/agent/test_tool_call_eval.py tests/integration/agent/test_product_flow.py` -> `7 passed`
  - UI capture artifact：
    `artifacts/ui/ai-assistant-open.png`，已同步更新 approved baseline
    `tests/baselines/ui/ai-assistant-open.png`。

## 邊界與未驗證事項

- `docs/legacy/` 已整合後刪除。
- `docs/active/` 已收掉；canonical 文件直接放在 `docs/` 根層。
- `.agents/legacy/` 已整合後刪除；現行 agent 操作層只剩 `.agents/stack.md`、runbooks、context。
- 舊文件裡的 `/mnt/d/repos/XBrainLab` 絕對路徑不代表現在 active path。
- thesis / agent performance claim 不能只靠 engineering dashboard 支撐。
- local transformer runtime 已以 primary / fallback model smoke 驗證；4-bit / bitsandbytes
  仍是 optional path，不是預設產品依賴。
- agent runtime 的目標方向是 local-only；目前 code 仍殘留 API / Gemini 相關路徑。一般產品 UI
  已用 `XBRAINLAB_SHOW_LEGACY_REMOTE_LLM=1` 隔離 legacy remote runtime，但 code path 尚未刪除，
  不能宣稱已完成 local-only runtime cleanup。
- thesis protocol 已建立 split artifact schema、split audit helper 和 validator script；正式
  external dataset runner、統計報告與 local LLM 真實 tool-call eval 還沒完成。

## 目前 blocker / release risks

目前舊 final gate 判定已失效，不能用它宣稱 product delivery 完成。新的狀態是：

- AI Assistant 一般輸入 `hello` 曾出現 silent no-response；本輪已補 visible-response contract、
  deterministic product-flow test 和 product click-through smoke。
- ChatPanel 視覺曾偏 debug dock；本輪 follow-up 已把 top chip row 移除，改成簡潔 header、
  單句 workflow guidance、底部低干擾 runtime/status、disabled Retry、empty state、bubble
  minimum width 和 composer fit。
- automated gate 漏掉了最基本的 user-visible chat product flow。deterministic eval `21 / 21`、
  local prompt smoke、launcher startup smoke 都不能替代真 chat flow 驗收。
- UI import / preprocess / epoch / channel selection、split / model / training setting dialogs、
  evaluation / visualization / saliency query、training start-stop / reset、metadata update、
  smart parse、remove files、label import、montage confirmation 已有 service-backed command
  adapter。mock / unit-test compatibility fallback 仍保留，但 real `Study` path 走
  `ApplicationService.execute()`。
- Agent mapped tools 的一批 path 已直接回 `CommandResult`；`load_data` 也已先做 directory
  expansion 再進 command surface。read-only `list_files` / `get_dataset_info` 會被正規化成
  typed result。visible transcript 只顯示使用者語言；raw tool payload 保留在 diagnostics。
  `set_montage` 和 `switch_panel` 仍是 UI request path；真正 montage apply 在 confirmation
  後走 `ApplyMontageCommand`。
- 真 Windows launcher / true local model UI walkthrough 尚未人工驗收。

仍存在的非阻塞架構風險：

- `evaluate` / `visualize` / `saliency` / `new_session` 已是 service-backed query / lifecycle
  command；它們目前回傳 summary / setup diagnostics，不等於完整互動式 analysis workflow
  已完成。
- tool-call eval 目前只有 deterministic baseline，尚未跑 local LLM primary / fallback 真實 agent runner。

## 目前執行中

1. 跑本輪 lint、format、docs、assistant UI、backend、agent、validation gates。
2. 分段 local commit；不 push，不納入 unrelated `settings.json`。

## 相關文件

- [target/README.md](target/README.md)
- [planning/now.md](planning/now.md)
- [operations.md](operations.md)
- [validation/README.md](validation/README.md)
