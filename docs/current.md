# XBrainLab 目前狀態

最後更新：`2026-05-04`

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

2026-05-03 人工產品審核 follow-up 又補了一輪產品級修正：Assistant dock 頂部不再顯示
chip dump，chat panel 內也不再放 `Conversation` 標題、第二條狀態列或 developer mode
controls。第一層只保留 dock title bar 的單一功能列：`XBrainLab`、retry icon、new
conversation、settings menu、float/dock；`Clear conversation` 收進 settings menu。`Retry`
沒有上一則 request 時預設 disabled，直接呼叫也只顯示 notice/status，不再污染 transcript。
agent visible transcript 不再顯示 `Tool <name> completed (...)`、schema error、empty list 或
snake_case command；raw tool payload 保留在 controller history / diagnostics。Assistant
runtime 已改成 product local-only：API / Gemini backend modules 已從 product package 移除，
settings / worker / engine 不再接受 remote execution mode。

UI action execution 已把 import、preprocess、epoch、split / model / training setting
dialogs、evaluation / visualization / saliency query、training start / stop、reset /
new session、metadata update、smart parse、remove files、label import 和 montage confirmation
這批 path 接到 `ApplicationService.execute()`；agent mapped tools 也可直接取得
`CommandResult` payload。新增 `LabelImportPlan`、`apply_montage` 和 `query_state`
讓 UI / agent 不必繞 controller 拿 typed result。本輪新增 split audit / thesis protocol
artifact schema，讓 train/validation/test split 可保存、重跑、審計。2026-05-03
`Backend Workflow Contract v2` 第一個切片新增 reset/cleanup lifecycle commands，
並讓 dataset split apply / audit failure 以 structured `DATA_MISMATCH` failure 回傳且
rollback dataset / generator / trainer state，避免半成功後仍可 train。`evaluate` /
`clear_training_history` capability 也改以 actual training plan history 為準。
2026-05-04 Goal 1 第一個 backend slice 新增 Data Interpretation command baseline：
`scan_source`、`preview_interpretation`、`validate_interpretation`、
`apply_interpretation`、`save_interpretation_recipe`、`reload_interpretation_recipe`
已進入 `ApplicationService / Command API`，並有 `ScanResult`、
`InterpretationCandidate`、`InterpretationPreview`、`ValidationDecision`、
`AppliedInterpretation`、`ImportRecipe` lifecycle object、state snapshot、capability /
autonomy policy 欄位和 recipe reload review flow。這仍只是 backend contract baseline；
2026-05-04 下一個 slice 已把 Data Interpretation command 暴露到 agent tool definitions /
mock / real tools、`application_surface.py` 和 `ContextAssembler` 可見工具集合。agent
controller 現在會讀 backend autonomy policy 的 dynamic confirmation boundary，且
`BackendFacade(study)` 會重用同一個 `ApplicationService`，避免 scan / preview / validate
lifecycle 在連續 tool calls 間遺失。Dataset panel 主要資料入口也已改為
`Interpret Data Source`，會走 scan -> preview dialog -> validate -> confirm/apply。
同日下一個 slice 新增 `backend.application.automation` 和
`scripts/dev/run_application_command.py`，讓 headless / MCP-ready adapter 以 JSON payload
轉 typed command，並回傳 live capability / autonomy / result schema；deterministic
tool-call eval 也已從舊 `21` cases 擴到 `54` cases，包含 Data Interpretation、recipe、
metadata choice、confirmation、blocked、missing-input 和 `15` 個 multi-turn cases。這仍不是
local LLM 真實 tool-call accuracy。下一個 product-completion slice 已新增真 stdio MCP
server baseline：`XBrainLab.mcp.server` 支援 MCP `initialize`、`tools/list`、`tools/call`，
並由 `scripts/dev/run_mcp_server.py` 啟動；tool schema 仍來自
`backend.application.automation.mcp_tool_specs()`，tool call 仍轉成
`execute_automation_payload()` 並只透過 `ApplicationService.execute()` 執行。這代表不再只是
MCP-shaped schema，但尚未完成外部 MCP client / Inspector click-through、Windows launcher
整合或 release config。另已新增 non-mocked backend
workflow evidence：synthetic FIF source 會走 scan -> preview -> validate ->
confirmation-blocked apply -> confirmed apply -> save recipe -> reload recipe review ->
preprocess -> epoch -> dataset，並檢查 split audit / train-val-test counts。UI-observable
replay 也有第一份 artifact：`scripts/dev/capture_data_interpretation_replay.py` 會保存
`artifacts/ui/data-interpretation-preview.png`、`data-interpretation-applied.png` 和
`data-interpretation-replay.json`，對照 visible dialog state、dataset panel state 和 command
result。Data Interpretation preview dialog 也提供 apply 後保存 recipe 的使用者選項，並透過
`SaveInterpretationRecipeCommand` 寫入 recipe。舊 label import 已降成「Add Labels to Loaded
Data」的 service-backed compatibility path；下一個 slice 已讓 label import 成功後更新
applied interpretation 的 `label_imports` / `label_carriers` / recipe trace，UI 也會提示使用者
可保存更新後 recipe。它仍是「對已載入資料加 label」的 compatibility UI，不是完整 import
wizard label/recipe 編輯器。完整 MCP external-client 驗收尚未完成，舊 `load_data /
attach_labels` 仍不能宣稱已完全退出產品心智模型。
同日後續 slice 新增真 local LLM tool-call runner：
`scripts/agent/evals/run_local_tool_call_eval.py` 會用同一份 `54` cases / scorer 接 primary /
fallback 本地模型 raw output，且每個 case 重跑 `3` 次。最新 artifact 顯示 primary
`microsoft/Phi-4-mini-instruct` 為 `18 / 54` pass、fallback
`microsoft/Phi-3.5-mini-instruct` 為 `20 / 54` pass；這是可重跑的真模型 evidence，但也證明
目前 local LLM tool-call accuracy 不能宣稱 thesis-ready。`VerificationLayer` 也補上
registered tool schema / required / type / enum 檢查，controller 會在 tool execution 前攔下
可解析但不可執行的 tool JSON。
MainWindow 首次啟動或壞 saved geometry 現在 fallback 到 maximized，不再用過度聰明的
跨螢幕置中當最後保護。真 Windows launcher 人工 click-through、真 local model 長時間
UI walkthrough、external thesis experiment runner 仍未完成，不能宣稱完整 release closure。

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

- generated at：`2026-05-04 04:07:48 UTC+08:00`
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
- UI Unit Suite：`PASS`，`831 passed`
- Real-Data IO Integration：`PASS`，`31 passed, 8 warnings`

補充已知通過項目：

- supervisor final gates：
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
  - deterministic tool-call eval refreshed tracked `artifacts/agent_evals/latest.json`：
    commit `e5454c7 test: refresh agent eval artifact`
- backend Application Service / facade contract suite：
  - `poetry run pytest --capture=sys tests/unit/backend/application -q`
  - `9 passed`
  - `poetry run pytest --capture=sys tests/integration/backend/test_application_service_workflow.py -q`
  - `2 passed`
  - `poetry run pytest --capture=sys tests/unit/backend/test_facade_coverage.py tests/unit/backend/test_facade_headless.py -q`
  - `44 passed`
- 2026-05-03 assistant UI + backend workflow contract gate：
  - `poetry run basedpyright`
  - `0 errors, 0 warnings, 0 notes`
  - `poetry run ruff check XBrainLab/ui/chat XBrainLab/ui/components/agent_manager.py XBrainLab/backend/application XBrainLab/backend/facade.py tests/unit/ui/chat tests/integration/ui/test_product_walkthrough.py tests/unit/backend/application/test_application_service.py tests/integration/backend/test_application_service_workflow.py tests/integration/pipeline/test_public_cross_source_training_smoke.py tests/unit/backend/test_facade_headless.py`
  - `PASS`
  - `poetry run pytest --capture=sys tests/unit/ui/chat tests/integration/ui/test_product_walkthrough.py tests/unit/backend/application/test_application_service.py tests/integration/backend/test_application_service_workflow.py tests/unit/backend/test_facade_headless.py tests/integration/pipeline/test_public_cross_source_training_smoke.py -q`
  - `80 passed, 3 warnings`
- 2026-05-04 Data Interpretation backend command baseline gate：
  - `poetry run pytest --capture=sys tests/unit/backend/application/test_application_service.py -q`
  - `28 passed`
  - `poetry run pytest --capture=sys tests/unit/backend/application/test_application_service.py tests/unit/llm/tools/test_application_surface.py tests/unit/llm/agent/test_controller.py tests/integration/backend/test_application_service_workflow.py tests/integration/agent/test_tool_call_eval.py -q`
  - `92 passed`
  - `poetry run ruff check XBrainLab/backend/application tests/unit/backend/application/test_application_service.py scripts/agent/evals/run_tool_call_eval.py`
  - `PASS`
  - `poetry run basedpyright XBrainLab/backend/application scripts/agent/evals/run_tool_call_eval.py tests/unit/backend/application/test_application_service.py`
  - `0 errors, 0 warnings, 0 notes`
  - broader static/docs gates:
    `poetry run ruff check .` -> `PASS`;
    `poetry run basedpyright` -> `0 errors, 0 warnings, 0 notes`;
    `poetry run python tests/architecture_compliance.py` -> `Architecture compliant`;
    `poetry run mkdocs build --strict` -> `PASS`
- UI unit suite：
  - latest fast dashboard UI Unit Suite：`831 passed`
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
  - primary `microsoft/Phi-4-mini-instruct` already cached；estimated download `0.00 GB`；
    current / projected cache `15.34 GB`；available disk `158.54 GB`；VRAM estimate `9.0 GB`；
    license MIT
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
- 2026-05-02 final repair / closure commits：
  - `8b04380 ui: rebuild assistant sidebar product shell`
  - `1883d4b backend: complete command surface migration`
  - `8a6099a llm: enforce local-only assistant runtime`
  - `41ec91c docs: align local-only runtime status`
  - `3edee21 ui: clarify assistant unavailable and confirmations`
  - `5ed1c87 backend: route montage through command surface`
  - `4cd4d4c test: align agent manager local-only expectations`
  - `406719c ui: stabilize baseline capture geometry`
  - `e5454c7 test: refresh agent eval artifact`
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
- agent runtime 目前是 local-only product path。`INFERENCE_MODE=api`、舊 settings 中的
  Gemini active mode、或 worker 直接要求 remote model，都會被 local migration / fail-closed
  guard 擋住，不會 instantiate remote backend。
- remote SDK 只留在 optional legacy dependency group；default dependency 不包含 OpenAI /
  Google Gemini SDK。
- thesis protocol 已建立 split artifact schema、split audit helper 和 validator script；正式
  external dataset runner、統計報告還沒完成。local LLM 真實 tool-call runner 已有
  primary / fallback `54` case x `3` repeat engineering evidence，但 pass rate 尚未支撐
  thesis claim。

## 目前 blocker / release risks

目前舊 final gate 判定已失效，不能用它宣稱 product delivery 完成。新的狀態是：

- AI Assistant 一般輸入 `hello` 曾出現 silent no-response；本輪已補 visible-response contract、
  deterministic product-flow test 和 product click-through smoke。
- ChatPanel 視覺曾偏 debug dock；本輪 follow-up 已把 top chip row、`Conversation` header、
  chat composer 底下狀態列和不存在的 mode/step controls 移除。第一層控制收斂到 dock
  title bar 的單一功能列，並用 regression tests 保護 disabled Retry、empty state、bubble
  minimum width、composer fit 和 raw tool output 不外洩。
- automated gate 漏掉了最基本的 user-visible chat product flow。deterministic eval `21 / 21`、
  local prompt smoke、launcher startup smoke 都不能替代真 chat flow 驗收；local tool-call
  eval runner 也不能替代 true ChatPanel 長時間 walkthrough。
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
- Windows/WSLg 雙螢幕開窗問題已用使用者回報的 offset screen geometry 補 regression；
  fallback policy 是 maximized，不是 fullscreen。但這仍不能取代真人桌面 click-through。
- `tests/integration/ui/test_product_walkthrough.py` 仍是 synthetic / patched training
  walkthrough，不是真正從 UI click 到 real TrainCommand completion 的產品 E2E。

仍存在的非阻塞架構風險：

- `evaluate` / `visualize` / `saliency` / `new_session` 已是 service-backed query / lifecycle
  command；它們目前回傳 summary / setup diagnostics，不等於完整互動式 analysis workflow
  已完成。
- tool-call eval 已有 deterministic baseline 和 primary / fallback 真 local model runner；但
  primary `18 / 54`、fallback `20 / 54` 的結果只能作 failure taxonomy，不能宣稱 thesis-ready。
- Data Interpretation backend command baseline、agent tool exposure、Dataset panel main
  import entry、recipe save option、headless/MCP-ready command schema、stdio MCP server
  baseline、deterministic eval cases 和第一版 UI-observable replay artifact 已進入新心智模型；
  label import 目前仍是 service-backed compatibility UI，但成功結果已會寫入 Data
  Interpretation recipe trace；MCP external-client / Inspector walkthrough 尚未完成。

## 目前執行中

1. 等待真 Windows Desktop launcher click-through。
2. 等待 true local LLM ChatPanel 長時間 walkthrough。
3. 補真正 UI button-click 到 training / evaluation / visualization completion 的 E2E。
4. 用目前 primary / fallback local tool-call report 改善 prompt / verifier feedback / case
   taxonomy，之後才收集 thesis-grade accuracy。
5. external EEG dataset experiment / statistical reporting 只作 pipeline support，不作 thesis
   主評分。

## 相關文件

- [target/README.md](target/README.md)
- [planning/now.md](planning/now.md)
- [operations.md](operations.md)
- [validation/README.md](validation/README.md)
