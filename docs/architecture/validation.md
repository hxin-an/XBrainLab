# Validation Architecture

最後更新：`2026-08-11`

## 範圍

這份文件描述 XBrainLab 的驗證架構：哪些測試、dashboard、artifact 可以支撐哪些工程或論文主張。

## Control-plane topology

```text
reviewed semantic descriptor -+
                              +--> planner --> source-bound DAG --> executor
git/path inference -----------+                           |             |
                                                          |             v
                                                canonical gate registry  receipt
                                                          |             |
                                                          v             v
                                                     exact argv ---> dossier verifier
                                                                        |
                                                                        v
                                                                 claim verdict

source-bound DAG --> CI owner map --> per-owner receipts --> CI capability verdict
```

Planner 只讀 coverage/dependency/cost metadata，不持有 argv。Executable command、timeout、
environment、artifact 和 outcome policy 仍只存在 handoff gate registry；CI matrix 只展開
`run_tests.py` 已註冊的 logical commands，不複製 test node 清單。Path inference 與 agent
semantic declaration只能做 scope/risk 聯集。未知 path、unresolved rule、stale plan、不同 source
SHA、缺 receipt、失敗 gate 或 evidence digest 漂移都 fail closed。

Claim-bearing plan 的 comparison base 不能只靠 mutable ref 名稱。CI 使用 PR/push event 提供的
target SHA；local handoff 先從 reviewed remote 刷新 target，再把同一 immutable SHA 傳給 plan、
run 與 verify。Candidate branch 也由當次執行明確提供，不存在歷史 branch default。First-push
事件沒有 predecessor target 時直接 fail closed，不以 root commit 縮窄 changed-path scope。

CI capability verdict 與 product/handoff claim verdict 是不同型別。前者逐一要求 selected gate
具有 execution owner、exact plan/source receipt 與 evidence。Registry owner 會在 final job 從
下載的 dossier 重新驗 command、timeout、source identity、log、artifact 與 record digest；只有
plan diff 與 Linux aggregate 這類 CI-native equivalent 可用檔案 manifest，且 final job 仍須重新
雜湊每個檔案。Receipt 本身不能替自己的 digest 作證。CI 另檢查 platform matrix；
它只說明 exact-head 自動化能力已完整執行，不宣稱人工 Windows acceptance、local-only exact
Granite/RAG 或完整 handoff 已完成。後者只能由 dossier-aware `verify` 產生；`report` 只做結構
檢查，永遠不能把未驗 dossier 的 receipt 升為 PASS。

這個拓撲把「選哪些驗證」、「如何執行」與「證據能支撐什麼」分開：deterministic tools 負責
scope、execution 與 oracle；model 只可在 deterministic gates 已通過後承擔 risk-selected visual /
exploratory review。Automated UI、agent review 與 human acceptance 是不同 claim，不能互相冒充。

Performance/resource 也分成兩層：CPU-safe `resource-contract` 可在一般 CI 保護 strict source/
publication contract；需要 GPU、非空 branch 與實機環境的 `resource-calibration` 只屬 handoff
registry，不會在 `ubuntu-latest` 假裝完成硬體校準。

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
| `artifacts/quality/latest.json` | local generated dashboard machine-readable artifact；git-ignored。 |
| `artifacts/quality/latest.md` | local generated dashboard human-readable artifact；git-ignored。 |
| `artifacts/quality/history.jsonl` | local generated dashboard history；ignored，不作 current evidence 入口。 |
| `artifacts/ui/` | dashboard transient UI capture output and named UI evidence subdirectories。 |

## Fast Quality Dashboard

`scripts/dev/update_quality_dashboard.py` 的預設 profile 是 `fast`。

截至 `2026-05-30`，fast dashboard 包含：

| Check key | 名稱 | 類別 | 支撐內容 |
| --- | --- | --- | --- |
| `ruff_lint` | Ruff Lint | quality | Python lint / style gate。 |
| `basedpyright_type_check` | Basedpyright Type Check | quality | static type health。 |
| `architecture_compliance` | Architecture Compliance | quality | repo-local architecture rule gate。 |
| `startup_smoke` | Startup Smoke | runtime | Qt app 能在 timeout 前初始化 `MainWindow`。 |
| `ui_baseline_capture` | UI Baseline Capture | ui | capture 核心 UI screenshots，並比對 approved baselines。 |
| `ui_dialog_acceptance` | UI Dialog Acceptance | ui | dialog-level acceptance tests。 |
| `ui_unit_suite` | UI Unit Suite | ui | UI unit suite。 |
| `io_integration` | Real-Data IO Integration | io | real-data import / ApplicationService IO integration。 |
| `ui_product_walkthrough` | UI Product Walkthrough | ui | human-like product route smoke and screenshot evidence boundary。 |

`--include-slow-checks` 會額外加入 `Mypy Type Check`，但它不是預設 fast dashboard 契約的一部分。

### Overall Status

dashboard clean 比 command exit 0 更嚴格。

`compute_overall_status()` 的規則是：

1. 任何 check 是 `fail` -> overall 是 `fail`
2. 沒有 `fail`，但有 `warn` -> overall 是 `warn`
3. 全部都是 `pass` -> overall 才是 `pass`

dashboard command 只有在 overall `fail` 時才會回傳 non-zero；overall `warn` 仍可能 exit 0。所以判斷 clean 時要讀 `artifacts/quality/latest.json`，不能只看 shell return code。

dashboard 會在 checks 前後各收集一次 branch、full HEAD、dirty fingerprint 與 HEAD source-tree
fingerprint。任一 identity 缺失或執行期間改變時，`source_stability` 必須 fail；report 同時保留
`git_before` 與 `git_after`，不得把漂移後的結果當成同一份 exact-source evidence。

### Clean 定義

fast dashboard clean 必須同時滿足：

1. `artifacts/quality/latest.json` 的 `overall_status` 是 `pass`。
2. `checks[*].status` 全部是 `pass`。
3. `artifacts/quality/latest.md` summary table 沒有 `FAIL` 或 `WARN`。
4. `workspace` 等於本次執行的 `git rev-parse --show-toplevel`，不依賴 canonical docs 內的本機 path。
5. `generated_at` 是本次驗證時間，不是舊 artifact。

這可以支撐日常工程健康判斷，但不能證明 model quality、scientific reproducibility 或 thesis claim。

## UI Baseline

UI baseline validation 分成三步：

1. `scripts/dev/capture_ui_baseline.py` 對每個核心畫面擷取兩張連續、完整 repaint 後的 frame；若兩張
   之間超過 2% pixel 改變，視為尚未穩定並直接 fail，而不是拿半完成 frame 當證據。
2. 穩定 frame 寫入 top-level `artifacts/ui/*.png` transient captures。
3. `scripts/dev/update_quality_dashboard.py` 將這些 live captures 和 `tests/baselines/ui/`
   的 approved references 比對。

dashboard 會用 `CAPTURE_STEPS` 宣告的檔名作為 expected live capture paths。這些 top-level
captures 是 generated output，已由 `artifacts/ui/.gitignore` 排除；approved baseline truth
只放在 `tests/baselines/ui/`。

以下情況會 fail：

- `artifacts/ui/` 缺 expected artifact。
- capture 出來的圖片接近全黑。
- 同一畫面的兩張連續 frame 未在穩定門檻內一致。
- `tests/baselines/ui/` 缺 approved reference。
- candidate 和 reference 尺寸不同。
- pixel drift 超過門檻。

目前 script 中的門檻：

- `MAX_UI_MEAN_DIFF = 1.5`
- `MAX_UI_CHANGED_RATIO = 0.02`
- `PIXEL_DIFF_THRESHOLD = 12`

這份 evidence 能說明「核心 UI 畫面已完成 repaint，且沒有明顯偏離 approved reference」。它不能取代完整 UX review、accessibility review、Windows native DPI / multi-monitor acceptance，或所有互動狀態的 visual regression coverage。

### DPI aggregate 尚未關閉的 integrity gap

`scripts/dev/run_chatpanel_ui_dpi_gate.py` 目前的 aggregate 仍只保留各 scale 的
`source_fingerprint` 與 screenshot filename；它尚未在 aggregate 內記錄 screenshot SHA-256、
完整 exact-source identity，或驗證 100/125/150% records 的 cross-scale source fingerprint
一致性。這一輪 dashboard/evidence worker 的 bounded write scope 不包含該 generator 與
`tests/unit/scripts/test_run_chatpanel_ui_dpi_gate.py`，因此沒有跨界修改。完成前，DPI aggregate
只能算 checkpoint evidence，不能宣稱 tamper-evident、exact-source aggregate 或 Windows native
DPI acceptance。

## Pipeline Evidence

pipeline evidence 要分層，不要用單一大測試包全部。

| 層級 | 要回答的問題 | 代表 evidence |
| --- | --- | --- |
| fast dashboard | repo 今天是否健康？ | lint、type、architecture、startup、UI、real-data IO |
| real-data IO integration | real EEG formats / fixture paths 是否能進入 IO facade？ | `tests/integration/io/test_io_integration.py` |
| required multi-dataset gate | handoff 前是否跨不同資料集來源驗證？ | `fetch_public_eeg_fixtures.py`、`report_dataset_validation_matrix.py --strict`、public BIDS / cross-source smoke |
| tiny E2E pipeline smoke | `dataset -> train -> evaluate` 是否能閉環？ | tiny CPU training smoke，1-2 epoch，metrics 存在 |
| public fixture pipeline smoke | 有 protocol class semantics 的 public fixtures 是否能走到 training；其餘 reviewed events 是否能走到 epoch？ | public fixture commands / artifacts |
| scientific validation | 結果是否可重現且支撐 thesis claim？ | fixed protocol、baselines、statistics、threat analysis |

目前的判讀：

- Real-data IO integration 只證明特定資料或 fixture 能走過預期 IO path。
- Required multi-dataset gate 是手測 / release-candidate handoff 前的必跑項目；它要求
  checked-in GDF+MAT、compact multiformat、2 個 class-grounded public training sources、
  2 個 public import/preprocess boundary sources，以及 public BIDS EEG fixture。只測同一資料集的不同
  副檔名不算通過。
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
| required multi-dataset gate | 不同 dataset source 的 import / label / BIDS、class-grounded training 與 import/preprocess boundary | full BIDS validator compliance、所有資料集、SCCN/CNT scientific class semantics、model quality |
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

- local model catalog / preflight / health check 已建立。
- product runtime 只接受 exact `ibm-granite/granite-3.3-2b-instruct` pinned revision；Phi-4
  Mini、Phi-3.5 Mini 與其他 legacy model 不可選取，也不得作為 fallback。
- Granite runtime、prompt smoke、structured-output smoke 和 GPU ChatPanel boundary 的 current
  狀態只能從同一 exact-SHA generated evidence 判讀；canonical docs 不保存會隨本機 cache
  變動的容量總數或 availability 結論。
- Qwen cache 已刪除；中國公司或中國來源模型不列入 local validation 候選。
- local agent runtime 是獨立的 candidate evidence，不塞進 fast dashboard 以免每次工程檢查都載入
  7B 級模型。
- assistant product runtime 已完成 local-only cleanup：remote backend modules 已從 product
  package 移除，legacy API/Gemini selection 會 migrate local 或 fail closed。
- `openai` / `google-genai` 不在 default dependencies，只保留於 optional
  `legacy-remote-llm` dependency group。
- 長時間 ChatPanel、Windows native DPI / multi-monitor 與真人 click-through 尚未跑；目前
  host-assisted Granite product workflow 不能取代 frozen benchmark 或完整 product acceptance。

Strict local Granite walkthrough artifact 必須分開記錄 requested model 與 actually loaded model，
並綁定 pinned revision、path-redacted cache snapshot manifest digest、commit/tree/dirty source
identity、host assistance、screenshot hashes 與 terminal shutdown。Passed artifact 的 sealed field
被改寫、current model/source identity 已 stale、screenshot bytes 被改寫，或 shutdown 未完成時，
validator 必須 fail closed。這仍是 host-assisted product workflow evidence，不是 raw-model
accuracy 或 thesis benchmark。

新 `strict_evidence` identity block 不記錄 absolute checkout、model cache 或 screenshot path；
但既有 Guided package base schema 仍用 canonical absolute local paths 做 artifact-root validation。
該 package validator 不在這輪 bounded write scope，因此完整 Guided JSON 目前只能留作 local
evidence，不可直接對外發布；要移除這個限制必須連同 Guided artifact schema / validator 一起改。

後續 local-only validation 應該覆蓋：

- local model cache 是否存在。
- optional dependencies 是否可安裝。
- CPU / GPU fallback 是否可預期。
- generation timeout / stop / reload 是否穩定。
- local model tool-call output 是否能被 parser / verifier 穩定接住。

已可重跑的 local runtime checks：

```bash
poetry run -- python scripts/dev/plan_local_model_download.py --format markdown
poetry run -- python scripts/dev/inspect_local_assistant_runtime.py \
  --format markdown --prompt-smoke --structured-smoke
poetry run -- python scripts/dev/inspect_local_assistant_runtime.py \
  --model ibm-granite/granite-3.3-2b-instruct \
  --format markdown --prompt-smoke --structured-smoke
```

這些 checks 只能支撐 local runtime smoke，不等於 thesis-grade tool-call eval。

## Historical Evidence

這份 architecture 文件不保存 dated pass counts、舊 branch 路徑或曾經的 dashboard verdict。
歷史執行紀錄在 [worklog](../records/worklog.md)；目前是否通過只能讀取與候選 branch、full
commit SHA、dirty state 和 profile 相符的 generated evidence。歷史 `PASS` 不能替代目前的
handoff gate、真人 Windows click-through 或 thesis validation。

## 更新規則

當 validation architecture 改變時，要一起檢查：

- `docs/validation/README.md` 是否需要更新 operational validation status。
- `scripts/dev/update_quality_dashboard.py` 是否改變 dashboard 契約。
- `artifacts/quality/latest.*` 是否需要重新 refresh。
- `tests/baselines/ui/` 是否真的要接受新的 approved reference。

不要偷偷擴大 dashboard 的意義。新增 check 時，要寫清楚它能證明什麼、不能證明什麼。
