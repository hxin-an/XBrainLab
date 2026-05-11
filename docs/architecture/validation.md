# Validation Architecture

最後更新：`2026-05-03`

## 範圍

這份文件描述 XBrainLab 的驗證架構：哪些測試、dashboard、artifact 可以支撐哪些工程或論文主張。

核心原則：

- fast quality dashboard 是工程健康訊號，不是論文結論。
- real-data IO、tiny pipeline smoke、public fixture smoke、scientific validation 要分層看。
- UI baseline 是 artifact 對 approved reference 的比對，不是完整人工 UX 審查。
- AI Assistant product flow 不能只靠 local runtime smoke、deterministic eval 或 UI baseline 判斷；
  normal chat response、visible error、local unavailable、blocked-command feedback 必須有專門 gate。
- local agent runtime 已有 2026-05-02 standalone smoke evidence，但尚未納入 fast dashboard
  預設 profile；product runtime 現在已是 local-only。
- thesis-grade validation 的主指標是 agent tool-call accuracy。EEG split、training metrics、
  model summary 和 environment artifact 只支撐 product pipeline / domain task sanity，不能取代
  tool-call scoring。

## 驗證分層

```text
unit tests
  |
  v
integration tests
  |
  v
real-data IO / fixture validation
  |
  v
tiny pipeline smoke
  |
  v
quality dashboard
  |
  v
pipeline support / thesis evidence mapping
```

這個順序不是執行頻率，而是可信度邊界。日常開發先看 dashboard；論文主張必須另外對應固定
tool-call benchmark cases、scorer、repeat runs、artifact 和 threat analysis。EEG pipeline
protocol 是支撐工作流可信度，不是主要 thesis accuracy。

## 主要位置

| 位置 | 用途 |
| --- | --- |
| `docs/validation/README.md` | 現行驗證狀態與 evidence 邊界。 |
| `docs/validation/thesis_protocol.md` | thesis-grade tool-call scoring protocol；包含 EEG split artifact 作為 pipeline support。 |
| `XBrainLab/backend/dataset/split_audit.py` | split indices artifact helper 與 leakage audit。 |
| `scripts/dev/validate_split_artifact.py` | split artifact schema / leakage audit CLI。 |
| `scripts/dev/update_quality_dashboard.py` | fast dashboard 產生器。 |
| `scripts/dev/capture_ui_baseline.py` | UI screenshot capture。 |
| `tests/architecture_compliance.py` | 架構規則檢查。 |
| `tests/unit/` | 單元測試。 |
| `tests/integration/` | 跨模組與 IO / UI integration tests。 |
| `tests/regression/` | regression tests。 |
| `tests/fixtures/data/` | 測試資料與 fixture。 |
| `tests/baselines/ui/` | approved UI baseline images。 |
| `artifacts/quality/latest.json` | 最新 dashboard machine-readable artifact。 |
| `artifacts/quality/latest.md` | 最新 dashboard human-readable artifact。 |
| `artifacts/quality/history.jsonl` | dashboard 歷史紀錄。 |
| `artifacts/ui/` | 最新 UI capture artifacts。 |

## Fast Quality Dashboard

`scripts/dev/update_quality_dashboard.py` 的預設 profile 是 `fast`。

截至 `2026-05-01`，fast dashboard 包含：

| Check key | 名稱 | 類別 | 支撐內容 |
| --- | --- | --- | --- |
| `ruff_lint` | Ruff Lint | quality | Python lint / style gate。 |
| `basedpyright_type_check` | Basedpyright Type Check | quality | static type health。 |
| `architecture_compliance` | Architecture Compliance | quality | repo-local architecture rule gate。 |
| `startup_smoke` | Startup Smoke | runtime | Qt app 能在 timeout 前初始化 `MainWindow`。 |
| `ui_baseline_capture` | UI Baseline Capture | ui | capture 核心 UI screenshots，並比對 approved baselines。 |
| `ui_dialog_acceptance` | UI Dialog Acceptance | ui | dialog-level acceptance tests。 |
| `ui_unit_suite` | UI Unit Suite | ui | UI unit suite。 |
| `io_integration` | Real-Data IO Integration | io | real-data import / facade IO integration。 |

`--include-slow-checks` 會額外加入 `Mypy Type Check`，但它不是預設 fast dashboard 契約的一部分。

### Overall Status

dashboard clean 比 command exit 0 更嚴格。

`compute_overall_status()` 的規則是：

1. 任何 check 是 `fail` -> overall 是 `fail`
2. 沒有 `fail`，但有 `warn` -> overall 是 `warn`
3. 全部都是 `pass` -> overall 才是 `pass`

dashboard command 只有在 overall `fail` 時才會回傳 non-zero；overall `warn` 仍可能 exit 0。所以判斷 clean 時要讀 `artifacts/quality/latest.json`，不能只看 shell return code。

### Clean 定義

fast dashboard clean 必須同時滿足：

1. `artifacts/quality/latest.json` 的 `overall_status` 是 `pass`。
2. `checks[*].status` 全部是 `pass`。
3. `artifacts/quality/latest.md` summary table 沒有 `FAIL` 或 `WARN`。
4. `workspace` 是 active repo：`/mnt/d/workspace_v2/projects/lab/XBrainLab`。
5. `generated_at` 是本次驗證時間，不是舊 artifact。

這可以支撐日常工程健康判斷，但不能證明 model quality、scientific reproducibility 或 thesis claim。

## UI Baseline

UI baseline validation 分成兩步：

1. `scripts/dev/capture_ui_baseline.py` 將目前畫面寫入 `artifacts/ui/`。
2. `scripts/dev/update_quality_dashboard.py` 將 `artifacts/ui/` 和 `tests/baselines/ui/` 的 approved references 比對。

dashboard 會用 `CAPTURE_STEPS` 宣告的檔名作為 expected artifacts。

以下情況會 fail：

- `artifacts/ui/` 缺 expected artifact。
- capture 出來的圖片接近全黑。
- `tests/baselines/ui/` 缺 approved reference。
- candidate 和 reference 尺寸不同。
- pixel drift 超過門檻。

目前 script 中的門檻：

- `MAX_UI_MEAN_DIFF = 1.5`
- `MAX_UI_CHANGED_RATIO = 0.02`
- `PIXEL_DIFF_THRESHOLD = 12`

這份 evidence 能說明「核心 UI 畫面沒有明顯偏離 approved reference」。它不能取代完整 UX review、accessibility review、或完整 visual regression coverage。

## Pipeline Evidence

pipeline evidence 要分層，不要用單一大測試包全部。

| 層級 | 要回答的問題 | 代表 evidence |
| --- | --- | --- |
| fast dashboard | repo 今天是否健康？ | lint、type、architecture、startup、UI、real-data IO |
| real-data IO integration | real EEG formats / fixture paths 是否能進入 IO facade？ | `tests/integration/io/test_io_integration.py` |
| tiny E2E pipeline smoke | `dataset -> train -> evaluate` 是否能閉環？ | tiny CPU training smoke，1-2 epoch，metrics 存在 |
| public fixture pipeline smoke | public event-rich fixtures 是否能走到 training smoke？ | public fixture commands / artifacts |
| scientific validation | 結果是否可重現且支撐 thesis claim？ | fixed protocol、baselines、statistics、threat analysis |

目前的判讀：

- Real-data IO integration 只證明特定資料或 fixture 能走過預期 IO path。
- Tiny E2E smoke 只證明小型 train/evaluate loop 沒有 shape、metric、輸出路徑等基本錯誤。
- 兩者都不能直接當作 scientific validation。

## Evidence 邊界

| Evidence | 能支撐什麼 | 不能支撐什麼 |
| --- | --- | --- |
| unit tests | 局部行為與 regression protection | 完整 workflow 成功 |
| integration tests | 跨模組行為 | 所有 edge cases 或長時間穩定性 |
| architecture compliance | repo-local 結構規則 | product correctness 或 scientific validity |
| startup smoke | app 能在測試環境初始化 | 完整互動式 runtime 健康 |
| UI baseline screenshots | approved core UI screens 未明顯漂移 | 完整 visual regression 或 UX 品質 |
| chat product-flow tests | normal input / empty response / worker error / local unavailable 有可見 feedback | 真 local model 長時間穩定性或人工 click-through 完整體驗 |
| product UI walkthrough tests | assistant layout / panel navigation / synthetic pipeline button path 有 regression protection | 真 Windows launcher 人工驗收或長時間 local model UX |
| real-data IO tests | 特定 real-data / fixture import paths | 完整 data pipeline reproducibility |
| tiny pipeline smoke | 小型 train/evaluate path 能閉環 | model quality 或 thesis reproducibility |
| split audit artifact tests | split indices schema、index overlap、subject/session group leakage | model quality 或完整 external dataset experiment |
| quality dashboard | fast engineering health | thesis conclusion |
| thesis experiments | research claim support | 日常 development regression coverage |

## Mock 邊界

目前 test suite 有不少 mock。這不等於測試沒用，但要清楚知道它保護的是哪一層。

mock-heavy tests 比較適合保護：

- method contract。
- signal / slot wiring。
- UI 狀態切換。
- error handling。
- config normalization。
- 不想真的寫檔、開 GPU、跑長訓練時的 regression。

mock-heavy tests 不適合直接證明：

- 真實 app workflow 一定跑得通。
- backend side effect 一定正確落到資料結構。
- Qt thread / event timing 一定穩定。
- local LLM runtime 一定可用。
- thesis claim 成立。

因此目前 validation strategy 不能只看 unit pass count。要用少量 non-mocked smoke 補足關鍵邊界，例如 real-data IO、UI baseline capture、startup smoke、real controllers、tiny pipeline smoke、local-only assistant runtime smoke。

## Agent Runtime 邊界

assistant / agent runtime validation 不屬於目前 fast dashboard 預設 profile。

目前狀態：

- 2026-05-02 已建立 local model catalog / preflight / health check。
- primary `microsoft/Phi-4-mini-instruct` 已下載並通過 CUDA prompt smoke / structured-output smoke。
- fallback `microsoft/Phi-3.5-mini-instruct` 已下載並通過 CUDA prompt smoke / structured-output smoke。
- 目前模型 cache 約 `15.34 GB`，低於 20GB 上限。
- Qwen cache 已刪除；中國公司或中國來源模型不列入 local validation 候選。
- local agent runtime 還沒有被接受為 dashboard evidence。
- assistant product runtime 已完成 local-only cleanup：remote backend modules 已從 product
  package 移除，legacy API/Gemini selection 會 migrate local 或 fail closed。
- `openai` / `google-genai` 不在 default dependencies，只保留於 optional
  `legacy-remote-llm` dependency group。
- 真 local LLM 長時間 ChatPanel walkthrough 尚未跑；目前 smoke 不能取代完整 product acceptance。

後續 local-only validation 應該覆蓋：

- local model cache 是否存在。
- optional dependencies 是否可安裝。
- CPU / GPU fallback 是否可預期。
- generation timeout / stop / reload 是否穩定。
- local model tool-call output 是否能被 parser / verifier 穩定接住。

已可重跑的 local runtime checks：

```bash
poetry run python scripts/dev/plan_local_model_download.py --format markdown
poetry run python scripts/dev/inspect_local_assistant_runtime.py \
  --format markdown --prompt-smoke --structured-smoke
poetry run python scripts/dev/inspect_local_assistant_runtime.py \
  --model microsoft/Phi-3.5-mini-instruct \
  --format markdown --prompt-smoke --structured-smoke
```

這些 checks 只能支撐 local runtime smoke，不等於 thesis-grade tool-call eval。

## 2026-05-02 現況

目前 `docs/validation/README.md` 記錄的 refresh 狀態：

- latest fast dashboard artifact：`artifacts/quality/latest.*`
- generated at：`2026-05-02 12:29:06 UTC+08:00`
- workspace：`/mnt/d/workspace_v2/projects/lab/XBrainLab`
- overall：`PASS`
- UI baseline capture：`7 UI artifacts match approved references`
- max UI mean diff：`0.114`
- max UI changed ratio：`0.66%`

同一輪 chat product blocker 修復已記錄：

- `poetry run mkdocs build --strict` 通過。
- Real-data IO integration：`31 passed, 8 warnings`。
- UI unit validation：`817 passed`。
- LLM unit validation：`652 passed`。
- targeted chat product-flow validation：`55 passed`。
- targeted controller / worker validation：`75 passed`。

2026-05-02 product delivery slice 新增的 product-oriented gates：

- assistant click-through / layout smoke：
  - `tests/integration/ui/test_product_walkthrough.py::test_assistant_product_click_through_layout`
  - 覆蓋 header/status/control row 不重疊、raw command diagnostics 不污染主 UI、user bubble 不截字、
    composer / Send button fit、五個主要 panel navigation。
- synthetic EEG button-driven pipeline walkthrough：
  - `tests/integration/ui/test_product_walkthrough.py::test_pipeline_product_walkthrough_uses_user_facing_actions`
  - 從 Dataset import button 開始，經 Preprocess filter、epoching、Training split/model/settings、
    dry-run Start Training 到 Evaluation result-ready 狀態。
- targeted validation：
  - `timeout 300s scripts/dev/run_ui_pytest.sh tests/unit/ui/chat/test_chat_panel.py tests/unit/ui/chat/test_message_bubble.py tests/unit/ui/components/test_agent_manager.py tests/integration/ui/test_product_walkthrough.py -q`
  - `62 passed`
  - `timeout 300s poetry run pytest --capture=sys tests/unit/llm/agent/test_controller.py tests/unit/llm/agent/test_worker.py tests/unit/llm/tools/test_application_surface.py tests/unit/backend/application tests/integration/backend/test_application_service_workflow.py -q`
  - `95 passed`
  - `timeout 300s poetry run pytest --capture=sys tests/integration/io/test_io_integration.py -q`
  - `31 passed, 8 warnings`
  - selected pipeline smoke：`2 passed`

2026-05-02 pipeline support protocol slice：

- `docs/validation/thesis_protocol.md`
- `docs/validation/split_artifact_schema.json`
- `XBrainLab/backend/dataset/split_audit.py`
- `scripts/dev/validate_split_artifact.py`
- targeted tests：
  - `tests/unit/backend/dataset/test_split_audit.py`
  - `tests/unit/scripts/test_validate_split_artifact.py`

這批 evidence 只證明 split artifact schema、index mutual exclusion、subject/session leakage
audit 和 validator CLI 可用。它不能取代 local LLM tool-call accuracy run。

這些是 `2026-05-02` 的工程 evidence。引用到論文時，還需要 thesis validation layer。
dashboard `PASS` 仍不能取代真人 launcher click-through 或真 local model chat walkthrough。

## 更新規則

當 validation architecture 改變時，要一起檢查：

- `docs/validation/README.md` 是否需要更新 operational validation status。
- `scripts/dev/update_quality_dashboard.py` 是否改變 dashboard 契約。
- `artifacts/quality/latest.*` 是否需要重新 refresh。
- `tests/baselines/ui/` 是否真的要接受新的 approved reference。

不要偷偷擴大 dashboard 的意義。新增 check 時，要寫清楚它能證明什麼、不能證明什麼。
