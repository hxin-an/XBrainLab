# XBrainLab Validation

最後更新：`2026-05-04`

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

目前 fast engineering artifact 狀態是：

- generated at: `2026-05-02 20:35:07 UTC+08:00`
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
- UI Unit Suite：`814 passed`
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

仍未完成的 evidence：

- Windows Desktop launcher 人工 click-through。
- true local LLM ChatPanel 長時間 walkthrough。
- local LLM primary / fallback tool-call accuracy run、score report、failure taxonomy。
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
  - latest fast dashboard UI Unit Suite：`814 passed`
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

這是 deterministic scripted baseline，不是 local LLM performance claim。local model primary /
fallback 真實 tool-call success rate 仍需在下一輪用相同 case schema 接 model runner 後再量測。

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

這批 evidence 支撐 Dataset panel main import entry 的新心智模型。它仍不支撐 recipe save UI、
label import migration、headless / MCP adapter 或 local LLM 真實 tool-call accuracy。

## Automated Evidence vs Product Evidence

| Evidence | 目前能證明 | 不能證明 |
| --- | --- | --- |
| startup smoke | `MainWindow` 能初始化 | assistant dock 打開後可用、可回覆、可讀 |
| local prompt smoke | local backend 能對最小 prompt 回文字 | UI chat flow 已接上、streaming 不被吃掉、錯誤可見 |
| structured-output smoke | 模型可按 prompt 產出 tool JSON | agent 在真 UI 中能穩定選 tool、解釋 blocked reason |
| deterministic eval | case schema / scoring / scripted policy 正確 | local LLM 真實 tool-call 成功率 |
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
- 比對 intent、tool selection、parameters、state transition、blocked-command handling、
  error recovery 和 user-visible response。
- 產生 machine-readable report 和 human-readable summary。

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

這只代表 EEG split protocol 與 artifact audit 能重跑；正式 thesis evidence 還需要 local
LLM tool-call runner、repeat runs、score report 和 failure taxonomy。external dataset runner、
baseline comparison 和 statistical reporting 是 pipeline support，不是 tool-call thesis 主指標。

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

建議分數：

- intent accuracy。
- tool selection accuracy。
- parameter accuracy。
- state-transition accuracy。
- error-recovery accuracy。
- invalid / unsafe call rate。
- self-correction success rate。

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
