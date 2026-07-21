# XBrainLab 驗證策略

最後更新：`2026-07-21`

這頁說明 evidence 能證明什麼，也說明不能證明什麼。

## 原則

不要把一種 evidence 放大成所有 claim。

| Evidence | 能支撐 | 不能支撐 |
| --- | --- | --- |
| CI green | branch 基本可 review，跨平台測試目前通過。 | product complete、human desktop acceptance。 |
| `mkdocs build --strict` | 文件站可建。 | 文件內容一定正確。 |
| architecture guard | 沒有已知 forbidden path regression。 | 所有 runtime flow 都已人工驗收。 |
| backend focused tests | command / state / result contract。 | UI 使用者體驗完整。 |
| automated UI walkthrough | 可觀察 UI baseline、截圖、按鈕狀態。 | 人手 Windows acceptance、DPI / dual-monitor、長時間 local model session。 |
| human-observable product smoke | 代表性使用者流程的視窗可見性、primary action 可見性、selected/applied scope、無 crash。 | 完整 release approval、所有資料格式與長時間模型 session。 |
| tool-call eval | tool selection / parameter / state transition 的 benchmark slice。 | EEG training quality、UI completion、產品完成。 |
| launcher smoke | launcher / startup baseline。 | signed installer、release approval。 |

## Latest Desktop MVP Handoff Evidence

2026-07-20 published automated handoff candidate 已重建 backend、UI、agent、資料與產品
walkthrough evidence。以下數字綁定候選 branch；commit `aaa47923cf5e` 的 fast dashboard
overall PASS，repo-root `settings.json` 保持可見、未 stage，並明確列為 protected local config。

- external label pairing 由 `data_interpretation_pairing.py` 統一供 candidate validation、apply
  與 wizard review 使用。Generic multi-file partial mapping、BIDS multi-run 缺少一個
  `events.tsv` 都會在 import 前 blocked；完整 run-specific mapping 才能 apply。
- human-like walkthrough 會實際擷取 Data Import Step 1 / 3 / 4 / 5，檢查 active step、distinct
  screenshot hash、step text glyph、main navigation 與 visible `RightPanel`。純色 step background
  不再能冒充文字已渲染。

本輪最新 product evidence：

- full unit：`9006 passed, 1 skipped`。
- full integration：`388 passed`。
- fast dashboard：Ruff、BasedPyright、architecture、startup、UI baseline、dialog、product
  walkthrough、BIDS UI matrix、UI unit `2069 passed`、real-data IO `31 passed` 全數 PASS；
  exact-commit overall 也是 PASS。
- Data Interpretation real lifecycle：`20/20`，固定涵蓋 14 種 format paths、7 個 public cases、
  5 個 public source families、7 個 pinned fixture fact contracts、7 個 external placement
  contracts、4 個 internal-event profiles、固定 11 個 reviewed label/event cases。
- strict cross-source runner `4/4`（PhysioNet、BBCI 是 2 個 class-grounded training cases；
  SCCN、CNT 是 2 個 IO/epoch-only cases）。SCCN `rt` / `square` 沒有 public protocol class
  ground truth，不算 supervised class 或 training evidence。
- latest human-like desktop walkthrough：`42/42` phases、`44` required screenshots、resource smoke PASS。
- real local Phi-4 mini ChatPanel：GPU runtime、`query_state` tool turn 與一般問答 turn PASS；
  關閉後 runtime / dispatcher 都是 `closed`、controller 已釋放、registered / running generation
  threads 都是 `0`。
- local raw tool-call candidate：`6/12`（50%）；host-assisted product policy `12/12`（100%）。後者
  包含 request admission、normalization、verification 與 capability blocking，不能報成 raw-model
  accuracy，也不能作 thesis claim。
- anti-overfit robustness set：raw `1/7`（14.3%）；host-assisted product policy `7/7`（100%），
  各跑 3 repeats 且結果 deterministic。這證明 host safety boundary，不代表 raw model 已學會
  blocked-action、missing-input 或 decision-boundary 判斷。
- RTX 5070 Ti bounded resource calibration：EEGNet、SCCNet、ShallowConvNet 三個單步 probe 的
  conservative estimate 均覆蓋 observed allocated peak；artifact 在
  `artifacts/resource_guard/calibration.json`。範圍固定為 batch 8、22 channels、301 samples，
  folds / repeats 序列執行，不誇大為所有設定的完整訓練峰值。
- quality dashboard 每個 check 與 overall 都已 PASS；Workspace Traceability 確認 tracked
  source clean，唯一 local change 是受保護且未 stage 的 `settings.json`。

以上仍不代表 Windows DPI、多螢幕、互動式 3D、長時間 local LLM session、full BIDS validator
acceptance 或 scientific model-quality claim。獨立 agent/runtime 與 test-quality reviewer 已在
修復後 re-gate 並 PASS；真實 Phi-4 mid-generation shutdown、real deferred-startup transition
與 Windows 互動式 3D 仍是明確 claim boundary，不可由自動化結果外推。

### 2026-07-21 Review / Preprocess / Visualization GUI Gate

- expanded backend / UI / capture regression：`1133 passed`；product walkthrough：`7 passed`。
- human-like product walkthrough：`42/42` required phases、`44` required screenshots、resource
  smoke PASS；table geometry findings 與 clipped rows 均為 `0`。目前 artifact 在
  `artifacts/ui/review-preprocess-polish/human-like-walkthrough/`。
- focused UI artifact 在 `artifacts/ui/ui-review-fixes/` 與
  `artifacts/ui/review-preprocess-polish/app-polish/`，涵蓋 Data Import Step 5、Smart Parser 四種
  parsing mode、filter / re-reference / normalize / resample、Signal Preview no-data / loaded /
  locked、固定 Preprocessing / Training History 與 Explanation Plots。
- attribution spectrogram 使用所有 class finite values 的共同 p99 display range；本輪真實 render
  為 linear `vmin=0`、shared `vmax=1.591498656489425e-4`、dynamic range 約 `55.16`，兩個 class
  共用 cividis normalization 與 colorbar。資料維度、finite values、frequency/time axis 與
  aggregation diagnostics 皆通過；artifact 在
  `artifacts/ui/review-preprocess-polish/visualization-render/`。
- required multi-dataset gate 維持 strict PASS：real lifecycle `20`、14 format paths、7 public
  cases / 5 source families，以及 strict cross-source `4/4`（2 training + 2 IO/epoch-only）。
- Preprocess 的 PyQtGraph teardown 另以相關 `267` tests 連續重跑三次，並以
  `tests/integration/ui/test_native_render_lifecycle.py` 的真實 EEG Time / PSD panel-switching
  subprocess stress 驗證。關閉 panel / MainWindow 前會停止 debounce、解除 `SignalProxy`，再呼叫
  PyQtGraph `PlotWidget.close()` 依 library contract 釋放 PlotItem / Axis / Label / scene，避免 deferred
  paint / resize event 存取已刪除的 native graphics item。Walkthrough cleanup 也會略過已由主視窗
  teardown 關閉的 PlotWidget，並保證 `app.quit()` 執行，避免二次 close 卡住 exit-code gate。

這些結果支撐 automated handoff candidate，不取代 Windows 真人 DPI、遠端桌面、互動式 3D
與長時間操作 acceptance。

### 2026-07-21 Agent Panel UI Gate

- focused unit / script gate：`455 passed`，覆蓋 composer auto-grow、manual-scroll preservation、
  runtime states、mode selector、response actions、typed confirmation correlation、manager lifecycle
  與 walkthrough contracts；12 列長 setting card 會捲到底並實際送出 correlated Cancel，連續
  160 字元、無空白的 path / hash / identifier 類值也會斷行且被 geometry guard 檢查；
  Ctrl+C / 右鍵 Copy 會移除顯示用 soft-wrap mark，clipboard 與原始值精確相同；hidden dock
  收到 runtime refresh 或 confirmation cleanup 後，empty state 仍不會與既有 transcript 並存。
- 完整 UI unit suite：`2089 passed`；同時移除舊 modal confirmation 測試假設，並保護
  partially constructed AgentManager 的 model-download / runtime shutdown。
- product integration：`tests/integration/ui/test_product_walkthrough.py` 完整 `7/7` 連續重跑
  3 次；async preprocessing 會等 panel busy lease 釋放後才查 ApplicationService state。
- focused screenshot matrix：`artifacts/ui/chatpanel-ui-ux-current/`，涵蓋 320 / 760 / 1280
  寬度、loading、empty、working / stopping、error / retry、長 clarification、setting change card
  與 12 列 max-content card、real MainWindow dock；teardown 會量測 close latency、GUI heartbeat
  與 QThread terminal signals。
- latest human-like product walkthrough：`42/42` phases、`44` required screenshots、resource smoke PASS；confirmation
  會實際按 Cancel / Apply，並驗證 request correlation、signal path 與 QThread teardown；
  fingerprint 包含 action card、confirmation contract 與 shared stylesheet owner。
- `scripts/dev/run_chatpanel_ui_dpi_gate.py` 以 `QT_SCALE_FACTOR=1`、`1.25`、`1.5`
  建立三個獨立 Qt subprocess，結果與選定截圖位於
  `artifacts/ui/chatpanel-dpi-current/`；三者 geometry / text-fit / interaction contract 全數 PASS。
  這仍是 Linux offscreen Qt evidence，不是 Windows native DPI 或多螢幕 acceptance。
- 主 UI approved baseline 已更新 Agent Panel reference；重新 capture 後 `7` 張 baseline
  全部符合門檻，最高 mean diff `0.864`、changed pixels `1.16%`。

## Roadmap Evidence Gate

| Phase | 需要的最低 evidence |
| --- | --- |
| Rebaseline | docs gate、branch/worktree inventory、known blocker board、handoff gate reset。 |
| Desktop MVP | Desktop MVP audit、architecture guard、focused command tests、UI refresh tests、Data Import format matrix、required multi-dataset gate、human-observable desktop smoke。 |
| Product Polish / Release Candidate | screenshot artifact review、UI visual consistency walkthrough、known limitations、troubleshooting docs、release-candidate preflight。 |
| Assistant MVP | assistant tool tests、blocked reason / structured result checks、verification boundary evidence、local LLM unavailable state。 |
| Thesis Evidence | frozen case suite、dataset protocol、scorer version、repeat count、failure taxonomy、statistical report。 |

## Handoff Candidate Gate

交給使用者手測前，必須先把 branch 判定為 handoff candidate。這個 gate 的目的不是取代
human Windows acceptance，而是避免使用者成為第一層 QA。

## Desktop MVP Delivery Flow Gate

Desktop MVP 期間，branch、validation、handoff 合併成一條流程：

```text
stabilize/desktop-mvp
  -> short task branch
      focused regression + same-class sweep + relevant validation
  -> merge back to stabilize/desktop-mvp
      happy path + edge/multi-dataset + artifact review
  -> user manual acceptance
      main merge decision
```

這個流程的目的不是增加儀式，而是避免兩種失敗：

- 長期分支堆太多內容，最後 merge 風險和 review 成本過高。
- 單點 bug 修完就交給使用者，導致使用者成為第一層 QA。

因此：

- task branch gate 只證明「這個小修復可合回 stabilization line」。
- handoff candidate gate 才證明「可以交給使用者手測」。
- main merge gate 要等使用者 acceptance 或明確同意的 release-candidate preflight。

## Desktop MVP Audit Gate

Desktop MVP 的第一輪修復不能只針對使用者指出的一個 symptom。使用者回報的 bug 是 audit
trigger；agent 要主動找產品 bug 和 code quality issue。

Audit 至少覆蓋：

| Area | 要找的問題 |
| --- | --- |
| Product workflow | import、label、metadata、epoch、preprocess、dataset split、training、evaluation、visualization 是否能完成主要路徑。 |
| UI / UX | 明顯跑版、白字白底、primary action 消失、不可點狀態誤導、loading/error/empty state 不清楚。 |
| Backend correctness | command result、state lifecycle、data mutation、label/event recipe、thread/figure cleanup。 |
| Architecture / clean code | duplicated truth、legacy/fallback creep、direct controller mutation、god object / long method / shotgun surgery。 |
| Test quality | mock-heavy 假保護、缺 non-mocked smoke、缺 screenshot / artifact、缺 multi-dataset edge。 |
| Performance/resource | UI-thread blocking、eager imports、background job cleanup、GPU/CPU/RAM guard、Matplotlib / Qt resource leaks。 |
| Docs / claim | current truth、known blockers、validation claim、artifact freshness 是否一致。 |

Audit 輸出必須產生 blocker queue，並把 blocking findings 修完或標成 blocked 後，才可以進入
handoff-ready 判定。若只完成單一修復，回報語意只能是 checkpoint。

handoff candidate 必須同時具備：

- focused regression：使用者指出的 bug 有測試、script 或 artifact 保護。
- same-class sweep：同類 UI / backend / state / data flow 問題已搜尋並處理。
- happy path：至少一條使用者可理解的 product workflow 或 UI-observable walkthrough 通過。
- edge / regression：依改動類型跑相鄰 workflow 或 multi-dataset / architecture / source guard。
- artifact review：可見 UI 改動有 screenshot / walkthrough artifact，且已人工檢查明顯跑版。
- branch hygiene：worktree clean 或 dirty files 已解釋；validated checkpoint 已 commit 並 push。
- claim boundary：明確列出仍不能宣稱的範圍。

未完成這些條件時，只能稱為 checkpoint 或 blocked，不可回報「可以手測」。

## Required Multi-Dataset Gate

給使用者手測、宣稱 handoff-ready、或整理 release-candidate preflight 前，
不同資料集來源是必測項目。只用 `A01T/A02T/A03T`，或只把同一份資料轉成多種副檔名，
都不夠支撐「主流資料可用」。

必跑 command：

```bash
poetry run python scripts/dev/fetch_public_eeg_fixtures.py --profile required-ci
poetry run python scripts/dev/fetch_public_eeg_fixtures.py \
  --profile required-ci --verify-only
poetry run python scripts/dev/report_dataset_validation_matrix.py --strict --format json
poetry run python scripts/dev/report_data_interpretation_format_matrix.py \
  --strict --format json --write-artifacts

QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys \
  tests/integration/ui/test_data_import_wizard_format_matrix.py -q

QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys \
  tests/integration/io/test_io_integration.py \
  tests/integration/io/test_public_bids_fixture.py \
  tests/integration/pipeline/test_public_cross_source_training_smoke.py -q

poetry run python scripts/dev/run_public_cross_source_training_smoke.py \
  --format json --strict
```

`report_dataset_validation_matrix.py --strict` 會把以下資料集多樣性當成 fail/pass gate：

- checked-in GDF + MAT：`A01T`、`A02T`、`A03T` 都要存在並有對應 label。
- compact multiformat：FIF、FIF.GZ、epoched FIF、EDF、BDF、BrainVision、EEGLAB SET 都要存在。
- public class-grounded training sources：固定 PhysioNet motor EDF、BBCI GDF 兩個 fixtures。
- public IO/epoch-only sources：固定 SCCN EEGLAB、MNE CNT 兩個 fixtures，不計入 training
  evidence。
- public BIDS EEG：必須有 downloaded tiny BIDS EEG root，包含 `events.tsv` / sidecar path。
- real Data Interpretation lifecycle：20 個必要案例都要走完
  `scan -> preview -> validate -> apply`，不能只靠非空檔案、header 或副檔名通過。
- real public source diversity：7 個 public cases 必須涵蓋至少 5 個真正不同的 source families；
  同一 A01T 的轉檔只算 format coverage，不算 source diversity。
- Tier format apply：固定的 14 種格式路徑都必須到達 apply，包含 GDF/MAT、FIF/FIF.GZ、
  epoched FIF、EDF、BDF、BrainVision、EEGLAB、CNT、BIDS EEG、CSV、TSV、TXT。required set
  是固定集合，不能藉由移除失敗案例縮小分母。
- external label placement：固定 7 個 contract 都必須保留 reviewed placement choices 並到達各自
  宣告的 evidence tier：
  MAT event order、CSV event order、CSV sample time、TSV interval、CSV event code、TXT event
  order、BIDS interval。CSV / TSV / TXT 使用有效的小型 generated fixtures，但不計入 public
  source diversity。
- reviewed internal events：PhysioNet run-dependent T1/T2、BBCI event selection、SCCN annotation
  selection、CNT event selection 是 4 個固定 reviewed-choice profiles；移除其中任何一個都會讓
  strict gate 失敗。PhysioNet case 另外要求 run-level mapping 被保存。這裡的 profile 不等於
  scientific class semantics；SCCN 與 CNT 只要求 IO/epoch-only。
- reviewed label/event 固定必要集合是 11 個案例，不能由本次結果動態計算分母：
  checked-in GDF+MAT、PhysioNet motor EDF、BBCI GDF、SCCN EEGLAB、MNE CNT、MNE-BIDS EEG、
  generated CSV event-order、CSV sample-time、TSV interval、CSV event-code、TXT event-order。
  其中 8 個要求 supervised tier、MNE-BIDS 要求 label-apply-only、SCCN 與 CNT 要求
  IO/epoch-only。任何 case ID 缺失、evidence tier 降級或 reviewed choice 未保存都會 strict
  FAIL。
- public fixture facts：7 個 public cases 固定檢查 sampling rate、channel count/type、
  canonical/source unit、sample count、embedded event count/labels 與 import warnings；任一欄
  漂移都會 strict FAIL。

`report_data_interpretation_format_matrix.py --strict` 同時輸出兩層證據：synthetic format
capability contract，以及 checked-in / SHA-pinned real files 的 ApplicationService lifecycle。
目前 lifecycle layer 是 20 個 cases：15 個 checked-in / SHA-pinned real-file cases，加上 5 個
generated external-label contract cases；固定涵蓋 14 種 format paths、7 個 public cases、5 個
public source families。它能證明列出的資料與明確 carrier schema 可完成 Data Interpretation
apply；generated carrier 不代表新的資料來源，也不能單獨證明任意 schema、epoch creation、
dataset split、training、evaluation、OOM recovery 或 scientific label semantics，這些仍由下方
integration tests 與 strict cross-source runner 分別支撐。

`test_data_import_wizard_format_matrix.py` 會把 synthetic format-boundary cases 送進
`ApplicationService scan -> preview -> validate`，再打開
`DataInterpretationPreviewDialog` 走完 `Choose EEG Data`、`Load Labels`、`Review Metadata`、
`Match Labels`、`Review and Import` 五個 step。它覆蓋 GDF+MAT、EDF、BDF、EEGLAB、BrainVision、
FIF、BIDS events、CSV / TSV / TXT labels，以及目前明確 blocked 的 XDF / LSL。

這個 UI gate 證明 wizard shell 對各 capability state 可用；public source diversity 與真正 apply
由兩份 strict report 的 real-workflow layer 證明。整組 gate 仍不能支撐 full BIDS validator
compliance、任意 proprietary format、長時間訓練穩定性或 scientific model-quality claim。

## Artifact 解讀

`artifacts/` 是機器產物和 evidence，不是 current truth。

MCP artifacts 若仍存在，只代表歷史探索或相容性證據。MCP 已從 active roadmap 移除，因此
handoff-ready、release-candidate、或 thesis evidence 不再需要 MCP walkthrough / adapter gate。

current truth 以這些文件為準：

- [current.md](../current.md)
- [planning/roadmap.md](../planning/roadmap.md)
- [architecture/README.md](../architecture/README.md)
- [validation/README.md](README.md)

## 2026-06-20 BIDS Epoch / Saliency Baseline / Resource Guard Gate

`stabilize/bids-epoch-saliency-baseline` implements the 2026-06-17 progress-report
decision for this slice:

- Strict BIDS folder import recipes keep onset / duration / label-field placement as
  epoch handoff hints, and Create Epochs can use duration windows or event-locked
  fallbacks depending on reviewed `events.tsv` duration values.
- Visualization starts the fast saliency baseline (`Gradient` + `Gradient * Input`)
  in the background after training or when a metric-only run is opened.
- SmoothGrad / SmoothGrad_Squared / VarGrad stay behind Saliency Settings; selecting
  or changing an advanced method recomputes that method instead of recomputing every
  saliency method.
- Import and training commands now have resource preflight: `LoadData` / Data Import
  apply check selected file sizes against available RAM, and `TrainCommand` checks
  dataset RAM and GPU-batch VRAM estimates before starting training.

Validation:

```bash
QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys \
  tests/unit/backend/application/test_application_service.py \
  tests/unit/backend/application/test_analysis_service.py \
  tests/unit/backend/application/test_training_service.py -q
# 87 passed

QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys \
  tests/unit/ui/test_visualization_panel_redesign.py \
  tests/unit/ui/dialogs/test_saliency_setting.py \
  tests/unit/ui/components/test_plot_figure_window.py -q
# 46 passed

QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys \
  tests/unit/backend/application/test_epoch_context.py \
  tests/integration/ui/test_dialog_acceptance.py::test_epoching_dialog_uses_import_interval_defaults \
  tests/unit/backend/application/test_application_service.py::test_apply_interpretation_honors_interval_end_field -q
# 5 passed

poetry run pytest --capture=sys tests/unit/backend/application/test_data_compatibility_service.py -q
# 8 passed

QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys \
  tests/unit/backend/application/test_data_interpretation_service.py \
  tests/unit/backend/application/test_application_service.py::test_apply_interpretation_honors_interval_end_field \
  tests/unit/backend/application/test_training_service.py -q
# 21 passed

poetry run python scripts/dev/report_dataset_validation_matrix.py --strict --format json
# strict_validation.ok: true

poetry run python scripts/dev/report_data_interpretation_format_matrix.py \
  --strict --format json --write-artifacts
# all_expected_capabilities_observed: true
# all_expected_capabilities_match: true
# real_workflows.summary.all_required_passed: true

QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys \
  tests/integration/ui/test_data_import_wizard_format_matrix.py -q
# 9 passed

QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys \
  tests/integration/io/test_io_integration.py \
  tests/integration/io/test_public_bids_fixture.py \
  tests/integration/pipeline/test_public_cross_source_training_smoke.py -q
# 36 passed

poetry run python scripts/dev/run_public_cross_source_training_smoke.py --format json --strict
# 4 passed, 0 missing, 0 failed
```

This supports a manual-test candidate after final dashboard/docs/branch hygiene pass.
It still does not claim human Windows acceptance, full BIDS validator compliance,
arbitrary public dataset certification, or scientific model-quality evidence.

## 2026-07-10 Historical Desktop MVP Checkpoint

> This checkpoint was invalidated by the 2026-07-11 re-audit. The listed runs remain
> historical evidence, but they do not support a current handoff-ready claim because
> the dashboard, walkthrough, and reviewer conclusions were not fully bound to the
> current HEAD.

本輪 audit 不是用單一 dashboard 取代產品驗收，而是分別修正 command/runtime、assistant/UI、
真實 EEG evidence 和 validation truth：

- 同一個 Study-scoped `ApplicationService` command/state/capability access 已序列化；UI 與 assistant
  command completion 共用 observer suppression 與 serialized `changed_state` refresh。
- assistant `One Step` / `Workflow` policy、existing-dialog decision boundary、worker/QTimer owner-thread
  teardown、failed shutdown retry ownership 有 focused regression。
- shared GDF semantics 將 1023 視為 rejected trial、32766 視為 system boundary；內部 event path
  與外部 MAT label path 使用同一套 artifact exclusion。A01T 內部事件路徑因此建立 273 個有效
  epochs，而不是把 rejected trials 算進 288 個 cue events。
- 真實 A01T GDF+MAT 已走完整 Data Interpretation wizard contract：scan、preview、validate、apply、
  preprocess、epoch、split、EEGNet one-epoch training、evaluate；另有 async CUDA OOM failure
  狀態與成功 retry 的整合測試。
- dataset matrix 不把 SCCN 或 MNE CNT 誤稱為 training pass；strict runner 固定回報
  2 個 class-grounded training sources + 2 個 IO/epoch-only sources。

當時通過的 checkpoint：

```text
Core assistant / refresh / lifecycle focused merge: 283 passed
Validation-truth focused suite: 70 passed
Data Splitting + walkthrough focused suite: 42 passed
Required IO + BIDS + cross-source + real GDF integration: 46 passed
Strict cross-source runner: 4 workflows passed; corrected claim is 2 training + 2 IO/epoch-only
Dataset matrix: strict_validation.ok = true
Data Interpretation format matrix: observed = true, match = true
```

這些結果只能說明當時的局部工程狀態。重新稽核找到 scientific correctness、UI command
concurrency、agent control-loop 與 validation traceability blockers；修復並在目前 HEAD 重建完整
gate 前，不支撐 handoff candidate，也不能取代 Windows 真人 click-through。

## 2026-07-11 Training Selection Integrity Checkpoint

目前 training runtime 不再在每個 epoch 評估 test split，也不再提供 test-based checkpoint
selection。每個 epoch 只更新 train / validation；validation metric 或 last epoch 固定模型後，才在
test loader 上建立一次 final `EvalRecord`。AUC 無法定義時保存為 `None` / UI `N/A`，不會用
`0.0` 參與 best-checkpoint ranking。舊的 `test_acc` / `test_auc` command value 會記錄 warning 並
明確 migration 到對應 validation strategy。Saliency 參數可以在訓練前保存，但未完成的 record
不會建立 loader 或重算 attribution；只有 checkpoint 與 final evaluation 已完成的 record 才能
重新計算。結構化 evaluation summary 會回傳實際的 test / validation / training provenance。

本 checkpoint 已通過：

```text
Training contract/regression batch: 464 passed, 1 skipped
Representative pipeline and public-source integration: 54 passed
Strict public cross-source smoke: 4 workflows passed; corrected claim is 2 training + 2 IO/epoch-only
Ruff: PASS
Configured Basedpyright: 0 errors
```

這一節只支撐 training selection correctness。當時阻斷完整 unit suite 的 Qt callback crash
已由下方 non-blocking view / Qt lifecycle checkpoint 修復；仍要等 agent 與 scientific blockers
關閉、完整 handoff gate 重建後，才能宣稱可交給使用者手測。

其中 `464` tests 的 timeline、loader identity、state-dict、weighted-loss、AUC edge 與
saliency-before-finish assertions 支撐 training-selection integrity。`54` integration tests 與
strict cross-source runner 只證明改動後的 EDF / GDF / EEGLAB SET / CNT workflow 相容性，
不能單獨證明 test isolation 或 scientific model quality。

## 2026-07-11 Non-Blocking View / Qt Lifecycle Candidate

一般 `QueryStateCommand(state)` 現在從正式 Command API 讀
`ApplicationViewPublication(state, capabilities, generation)`。command lock 空閒時會先重建並
發布背景 state；長 mutation 持鎖時不等待，立即回最後一份已驗證 publication。UI、assistant
decision context / tool policy 與 headless preflight 都讀同一 generation。Object-bearing
`data_lists` / history query 仍序列化，避免併發暴露 mutable domain objects。mutation 執行後若
無法驗證新 state，command 會 fail closed，不會回報假成功。

Qt QThreadPool result/error 改由 owner-child QObject receiver 接收；owner 被刪除時 Qt 會自動
移除 queued delivery。獨立 cleanup receiver 保留到 terminal `finished`，才解除 busy、observer
suppression 與 active worker ownership。這修復了 pytest-qt teardown / WSLg 時序下落在
`application_capabilities._handle_result` 的 native segmentation fault。

目前 candidate evidence（仍是 dirty-tree checkpoint，不能視為 final handoff）：

```text
Full unit: 6908 passed, 2 skipped
Full integration: 261 passed
UI integration: 68 passed
Architecture/source-guard batch: 195 passed
Human-like walkthrough: 40/40 phases, 42 screenshots
Repeated deleted-owner/close teardown stress: 50/50 passed
Ruff: PASS
Basedpyright: 0 errors, 0 warnings, 0 notes
```

這支撐 non-blocking state/capability view、背景 state 新鮮度、post-state fail-closed、Qt
deleted-owner safety，以及 BIDS bounds/run mapping、overlapping-window split protection、saliency
atomicity 的 regression。它仍不支撐 Windows 真人 acceptance、互動式 3D 或 thesis-grade agent
accuracy；branch clean / push 與獨立 reviewer gate也尚未關閉。

## 2026-07-15 Local Assistant Product Boundary

本輪用已快取的 `microsoft/Phi-4-mini-instruct`、RTX 5070 Ti 與離線 Hugging Face 模式，從真實
ChatPanel 跑兩個 turn：第一個透過 `query_state` 回報目前 workflow，第二個回答一般 EEG
preprocessing 問題。artifact 位於
`artifacts/ui/chatpanel-local-workflow/current/`，status 是 `passed`。

同一模型的 unassisted raw candidate 只通過 `6/12`。host layer 在相同 12 cases 的 product
policy score 是 `12/12`，表示 blocked request、缺參數、capability policy 和 normalization 能防止
不安全執行；它不表示模型自己做對 12 次。完整報告位於
`artifacts/agent_evals/current_candidate_strict/`，並標明 worktree dirty、exploratory、沒有 backend
execution。這組 evidence 只支撐 Assistant MVP 的安全邊界，不支撐論文級準確率。

七個獨立 anti-overfit cases 另跑 3 repeats：raw `1/7`，host-assisted `7/7`。dashboard 將它放在
獨立 robustness section，不把分母混進 12-case baseline。Raw failures 仍是穩定的錯誤決策，
因此 raw release gate 保持 open。

## 2026-07-15 RTX Resource Guard Calibration

`scripts/dev/calibrate_resource_guard.py --strict` 在 NVIDIA GeForce RTX 5070 Ti 上執行 bounded
CUDA probe，結果寫入 `artifacts/resource_guard/calibration.json`：

| Model | Estimated VRAM | Observed allocated delta | Covered |
| --- | ---: | ---: | --- |
| EEGNet | 86,326,780 B | 21,408,768 B | Yes |
| SCCNet | 87,106,590 B | 1,856,000 B | Yes |
| ShallowConvNet | 86,703,820 B | 24,632,832 B | Yes |

校準 scope 是 batch 8、22 channels、301 samples、4 classes；3 folds 與 5 repeats 不是同時放入
VRAM，peak scope 是 `one_fold_one_repeat_one_batch`。Probe 上限是 256 MiB 且不超過當時可用
VRAM 的 10%。這支持公式在該 bounded scope 沒有低估觀察到的 allocated peak，但不等於完整
training、任意 input length、任意 batch 或所有 CUDA allocator 狀態的絕對保證。

## 2026-06-20 Clean-Code Boundary Follow-Up

`refactor/saliency-resource-boundaries` keeps the BIDS epoch / saliency behavior
unchanged while tightening two recently touched boundaries:

- saliency method selection and parameter normalization now live in
  `backend.application.saliency_policy`, so `AnalysisCommandService` and the
  Visualization UI no longer carry separate copies of recommended / advanced method
  rules;
- saliency method names originate from the backend visualization support list, and
  the application policy / UI selectors now derive from that same list to prevent
  method-list drift;
- training resource preflight now receives explicit dataset / training-option context
  from `TrainingCommandService`; `resource_guard` no longer inspects controller or
  `Study` shapes directly.

Focused validation:

```bash
QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys \
  tests/unit/backend/application/test_saliency_policy.py \
  tests/unit/backend/application/test_resource_guard.py -q
# 7 passed

QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys \
  tests/unit/backend/application/test_analysis_service.py \
  tests/unit/backend/application/test_training_service.py -q
# 22 passed

QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys \
  tests/unit/ui/test_visualization_panel_redesign.py -q
# 24 passed

QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys \
  tests/unit/ui/dialogs/test_saliency_setting.py \
  tests/unit/ui/components/test_plot_figure_window.py \
  tests/unit/ui/dialogs/test_export_saliency.py -q
# 39 passed

QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys \
  tests/unit/backend/application/test_application_service.py::test_saliency_command_can_configure_params \
  tests/unit/backend/application/test_application_service.py::test_saliency_command_normalizes_flat_method_params \
  tests/unit/backend/application/test_application_service.py::test_visualize_and_saliency_commands_return_typed_query_payloads \
  tests/unit/ui/visualization/test_control_sidebar.py -q
# 21 passed

poetry run ruff check <touched files>
# PASS

poetry run basedpyright <touched files>
# 0 errors, 0 warnings, 0 notes

poetry run python tests/architecture_compliance.py
# PASS
```

## 2026-05-30 Release-Candidate Gate Follow-Up

Manual-test gating on `/mnt/d/workspace_v2/projects/lab/XBrainLab-integrated-manual`
treated non-blocking findings as work to clear, not as deferred polish. The current
branch fixed and validated these product-quality gaps:

- saliency 2D map / topomap / spectrogram rendering now keeps Qt/Matplotlib
  figure creation on the UI thread, avoiding native Qt backend crashes from
  background-thread figure creation while still showing visible render / error
  states;
- metrics and model-selection tables use dark active/inactive/disabled palettes and
  clear initial selection, preventing white selected rows from hiding text;
- data-splitting and epoching dialogs now have current screenshot evidence with
  dark readable controls and visible primary actions;
- stale current-tree `human-like-walkthrough` and `audit-visualization-render`
  artifacts were removed; historical records can still mention them, but current
  evidence now points to `data-import-wizard-steps`, `app-polish`, and
  `visualization-render`;
- training record figure helpers use figure-scoped rendering and close empty
  figures, preventing matplotlib figure accumulation during repeated visualization;
- `ApplicationService` lazy service wrappers now expose explicit command handlers
  instead of generic `__getattr__` forwarding;
- UI-only `GenerateDatasetCommand.generator` is hidden from automation schemas
  and rejected when supplied through automation payloads;
- Dataset import UI tests were updated to the `ReviewInterpretationCommand` command
  path, so the focused UI suite no longer protects the old scan/preview/validate
  sequence as the product behavior;
- evaluation and visualization approved UI baselines were refreshed after product
  review of the intentional no-data and wrapped-control layouts.

Validation:

```bash
QT_QPA_PLATFORM=offscreen poetry run python scripts/dev/update_quality_dashboard.py
# Overall status: PASS
# generated_at / commit: see local generated artifacts/quality/latest.md
# workspace: /mnt/d/workspace_v2/projects/lab/XBrainLab-integrated-manual
# checks: Ruff, Basedpyright, Architecture Compliance, Startup Smoke,
# UI Baseline Capture, UI Dialog Acceptance, UI Product Walkthrough,
# UI Unit Suite, Real-Data IO Integration all PASS

QT_QPA_PLATFORM=offscreen poetry run python scripts/dev/capture_epoching_dialog.py
# PASS; refreshed artifacts/ui/epoching-dialog/

QT_QPA_PLATFORM=offscreen poetry run python scripts/dev/capture_ui_polish_surfaces.py
# PASS; refreshed artifacts/ui/app-polish/

QT_QPA_PLATFORM=offscreen poetry run python scripts/dev/run_tests.py ui
# 1242 passed

poetry run basedpyright
# 0 errors, 0 warnings, 0 notes

poetry run mkdocs build --strict
# PASS

poetry run pytest --capture=sys \
  tests/integration/pipeline/test_full_pipeline.py::TestFullPipeline::test_train_and_evaluate_metrics \
  tests/integration/pipeline/test_study_training_e2e.py::TestStudyTrainCycle::test_full_cycle_eegnet -q
# 2 passed

QT_QPA_PLATFORM=offscreen poetry run python scripts/dev/capture_windows_launcher_walkthrough.py
# status: passed
```

This supports the branch as a stronger release-candidate preflight. It still does
not claim signed packaging, full human Windows click-through acceptance, arbitrary
BIDS validator compliance, or scientific model-quality conclusions.

## 2026-05-25 Mainstream EEG/BCI Format Gate

Mainstream format coverage was rechecked with checked-in compact fixtures plus
local-only public fixtures under `tests/fixtures/data/public/`. The public fixture
cache is intentionally ignored by git; `scripts/dev/fetch_public_eeg_fixtures.py`
downloads it and now verifies SHA-256 for downloaded files. Current
small representatives cover:

- checked-in GDF + MAT labels: BCI Competition IV 2a style `A01T/A02T/A03T`;
- checked-in compact multiformat derivatives: FIF, FIF.GZ, EDF, BDF, BrainVision,
  EEGLAB SET, and epoched FIF;
- public local-only fixtures: PhysioNet EDF, BBCI GDF, SCCN EEGLAB SET, MNE CNT,
  MNE BrainVision;
- downloaded local-only MNE-BIDS tiny EEG root with BrainVision data,
  `events.tsv`, `events.json`, `channels.tsv`, participants, sessions, scans,
  and electrode sidecars;
- scan/preview validation matrix entries for CSV, TSV, TXT, MAT, BIDS events,
  and explicitly blocked XDF/LSL.

The gate found one product issue: a generic `trial/class` TSV could be interpreted
as if `trial` were an EEG event code. Event-order placement now defaults that case
to `trial order` and asks the user to choose target EEG events instead of blocking
on a nonexistent event called `trial`.

Validation:

```bash
poetry run python scripts/dev/fetch_public_eeg_fixtures.py
# downloaded/validated public fixtures, including mne-bids-tiny-eeg

poetry run python scripts/dev/report_data_interpretation_format_matrix.py \
  --strict --format json --write-artifacts
# all_expected_capabilities_observed: true
# all_expected_capabilities_match: true

QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys \
  tests/integration/io/test_io_integration.py \
  tests/integration/io/test_public_bids_fixture.py \
  tests/integration/pipeline/test_public_cross_source_training_smoke.py -q
# 36 passed

poetry run python scripts/dev/run_public_cross_source_training_smoke.py \
  --format json --strict
# 4 passed, 0 missing, 0 failed

QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys tests/integration -q
# 215 passed

poetry run ruff check .
# PASS

poetry run basedpyright scripts/dev/fetch_public_eeg_fixtures.py \
  scripts/dev/report_data_interpretation_format_matrix.py \
  scripts/dev/report_dataset_validation_matrix.py \
  scripts/dev/run_public_cross_source_training_smoke.py \
  tests/unit/scripts/test_fetch_public_eeg_fixtures.py \
  tests/unit/scripts/test_report_data_interpretation_format_matrix.py \
  tests/unit/scripts/test_report_dataset_validation_matrix.py \
  tests/unit/scripts/test_run_public_cross_source_training_smoke.py \
  tests/integration/io/test_public_bids_fixture.py
# 0 errors, 0 warnings, 0 notes

poetry run mkdocs build --strict
# PASS

poetry run python tests/architecture_compliance.py
# Architecture compliant

poetry run python scripts/dev/update_quality_dashboard.py
# Overall status: PASS
```

This supports mainstream tier-1/tier-2 import breadth for the formats above. It
does not claim full BIDS validator compliance, XDF/LSL support, or scientific
replication quality for arbitrary public datasets.

## 2026-05-25 Manual-Test Audit Follow-Up

Manual testing exposed multiple issues that older automated evidence did not catch.
The follow-up audit found and fixed two validation gaps:

- Product walkthrough mocks and visualization capture scripts still confirmed Data
  Interpretation without choosing the new supervised label source. They now select
  internal EEG events when using synthetic internal labels, and visualization capture
  starts tiny training with an explicit confirmation boundary.
- BIDS scan had let `participants.tsv` / `*_channels.tsv` appear as label/event
  carriers. BIDS metadata tables are now reported as metadata context, while
  `events.tsv` remains the label/event carrier. Saved import recipes now preserve
  the BIDS summary used by epoch handoff and recipe reload review.

Focused validation from `/mnt/d/workspace_v2/projects/lab/XBrainLab-integrated-manual`:

```bash
QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys \
  tests/integration/ui \
  tests/unit/scripts/test_capture_data_interpretation_replay.py \
  tests/unit/scripts/test_capture_human_like_product_walkthrough.py \
  tests/unit/scripts/test_capture_visualization_render_walkthrough.py \
  tests/unit/scripts/test_capture_chatpanel_local_training_completion_walkthrough.py -q
# 100 passed

QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys \
  tests/unit/backend/application/test_data_interpretation_scan.py \
  tests/unit/backend/application/test_data_interpretation_candidate.py \
  tests/unit/backend/application/test_data_interpretation_label_carriers.py \
  tests/unit/backend/application/test_data_interpretation_service.py \
  tests/unit/backend/application/test_data_interpretation_review.py \
  tests/unit/backend/application/test_data_interpretation_recipe.py \
  tests/unit/backend/application/test_data_interpretation_formats.py \
  tests/integration/backend/test_application_service_workflow.py -q
# 80 passed

QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys \
  tests/unit/ui/dialogs/dataset/test_data_interpretation_preview_dialog.py \
  tests/integration/ui/test_dialog_acceptance.py \
  tests/unit/ui/test_evaluation_panel_redesign.py \
  tests/unit/ui/test_visualization_panel_redesign.py -q
# 106 passed

QT_QPA_PLATFORM=offscreen PYVISTA_OFF_SCREEN=true poetry run python \
  scripts/dev/capture_visualization_render_walkthrough.py \
  --output-dir artifacts/ui/visualization-render --timeout-seconds 540
# passed; 3 rendered saliency tabs and 3D blocked-state evidence captured

poetry run python scripts/dev/update_quality_dashboard.py
# Overall status: PASS

poetry run pytest --capture=sys tests/integration/io/test_io_integration.py -q
# 21 passed, 10 skipped

poetry run pytest --capture=sys \
  tests/integration/pipeline/test_full_pipeline.py::TestFullPipeline::test_train_and_evaluate_metrics \
  tests/integration/pipeline/test_study_training_e2e.py::TestStudyTrainCycle::test_full_cycle_eegnet -q
# 2 passed
```

This supports the integrated manual-test branch as a stronger automated preflight.
It still does not replace human Windows click-through acceptance.

## 2026-05-25 Subagent-Gated Data Import Closure

Subagent gates for Data Import, runtime UI, backend state, and test completeness
were treated as blockers. Several worker findings were stale on the current branch,
but Gate A exposed three live Data Import issues:

- ordinary folders containing `sub-*` EEG filenames could be misclassified as BIDS;
- Review and Import could split one missing `events.tsv` problem into multiple
  action items and route label-source issues to the wrong step;
- Smart Parse metadata only applied subject/session even though Review Metadata
  exposes subject/session/task/run.

The current branch now requires a stronger BIDS folder shape before auto-classifying
a folder as BIDS, canonicalizes missing `events.tsv` warnings into one Load Labels
action item, and preserves Smart Parse subject/session/task/run in the Data Import
metadata override recipe while keeping legacy subject/session consumers compatible.

Focused and broad validation after the gate fixes:

```bash
QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys \
  tests/unit/backend/application/test_data_interpretation_scan.py \
  tests/unit/backend/application/test_data_interpretation_candidate.py \
  tests/unit/backend/application/test_data_interpretation_review.py \
  tests/unit/backend/application/test_data_table_service.py \
  tests/unit/backend/controller/test_dataset_controller.py \
  tests/unit/ui/dataset/test_smart_parser.py \
  tests/unit/ui/dialogs/dataset/test_data_interpretation_preview_dialog.py -q
# 158 passed

QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys tests/integration -q
# 200 passed, 14 skipped

poetry run python scripts/dev/update_quality_dashboard.py
# Overall status: PASS

poetry run ruff check .
# PASS

poetry run basedpyright XBrainLab/backend/application/data_interpretation_scan.py \
  XBrainLab/backend/application/data_interpretation_candidate.py \
  XBrainLab/backend/application/data_interpretation_review.py \
  XBrainLab/backend/application/data_table_service.py \
  XBrainLab/backend/controller/dataset_controller.py \
  XBrainLab/ui/dialogs/dataset/smart_parser_dialog.py \
  XBrainLab/ui/dialogs/dataset/data_interpretation_preview_dialog.py
# 0 errors, 0 warnings, 0 notes

poetry run mkdocs build --strict
# PASS

poetry run python tests/architecture_compliance.py
# Architecture compliant
```

The skipped integration cases are public EEG fixtures that are not downloaded in
this workspace. This gate supports the branch as a stronger manual-test candidate;
it still does not prove arbitrary BIDS coverage or replace Windows human
click-through acceptance.

## 2026-05-25 Gate E Test-Coverage Follow-Up

Gate E reviewed integration-test completeness and failed the branch as originally
gated: backend command tests were strong, but product-visible Data Import and
wizard state still had too much mock-heavy coverage. Two regressions were then
made reproducible and fixed:

- Loading an external label folder from the Load Labels step could refresh the
  carrier list but leave Match Labels in `Labels inside EEG files` mode. A new UI
  integration test uses real `ApplicationService` scan / preview / validate plus
  the real wizard rescan handler and asserts Match Labels switches to loaded
  label files.
- Epoch dialog event selection had regressed after checked-event support: normal
  selection-only dialogs could no longer accept a selected event, while import
  handoff dialogs still must reject stale selection when all recommended events
  are unchecked.

The fast quality dashboard now includes `UI Product Walkthrough`, which runs the
existing product walkthrough plus the real Data Import wizard runtime regression.

Focused validation:

```bash
QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys \
  tests/integration/ui/test_product_walkthrough.py \
  tests/integration/ui/test_data_import_wizard_runtime.py -q
# 5 passed

QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys \
  tests/integration/ui/test_dialog_acceptance.py::test_epoching_dialog_accepts_selected_event_and_baseline_toggle \
  tests/unit/ui/components/test_dialogs.py::test_epoching_dialog_init \
  tests/unit/ui/test_dialogs_extra.py::TestEpochingDialog::test_import_handoff_uses_checked_events_not_stale_selection -q
# 3 passed

QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys \
  tests/unit/backend/application \
  tests/integration/backend/test_application_service_workflow.py -q
# 209 passed

QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys \
  tests/unit/scripts/test_capture_visualization_render_walkthrough.py \
  tests/unit/ui/dialogs/dataset/test_data_interpretation_preview_dialog.py \
  tests/unit/ui/test_dialogs_extra.py -q
# 132 passed

QT_QPA_PLATFORM=offscreen PYVISTA_OFF_SCREEN=true poetry run python \
  scripts/dev/capture_visualization_render_walkthrough.py \
  --output-dir artifacts/ui/visualization-render --timeout-seconds 540
# passed

poetry run python scripts/dev/update_quality_dashboard.py
# Overall status: PASS
```

Remaining coverage boundary: public cross-source fixtures are still optional /
skipped when absent outside the required strict gate. PhysioNet EDF and BBCI GDF
are class-grounded training-smoke fixtures. SCCN EEGLAB is IO/preprocess/epoch-only
because the public fixture does not define `rt` / `square` as supervised protocol
classes; compact MNE CNT is also IO/preprocess/epoch-only because it has too few
usable epochs for a class-balanced training split. The
default dashboard still does not claim human Windows click-through acceptance or
full local-LLM runtime acceptance.

## 2026-05-22 Epoch Dialog Label Transparency

Manual UI review found that Epoch dialog text labels could render with visible
label-background blocks on some Qt/desktop themes because the dialog and shared
dialog info/warning label styles did not set transparent label backgrounds. Epoch
dialog label rules and shared dialog info/warning label styles now explicitly use
`background-color: transparent`.

Focused validation:

```bash
QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys \
  tests/unit/ui/test_dialogs_extra.py \
  tests/unit/ui/components/test_dialogs.py \
  tests/unit/ui/dialogs/test_dialogs_structure.py \
  tests/unit/ui/preprocess/test_preprocess_panel.py -q
# 74 passed

QT_QPA_PLATFORM=offscreen poetry run python scripts/dev/run_tests.py ui
# 1161 passed
```

## 2026-05-21 Load Labels Restore Regression

Manual testing found that removing a label file in Load Labels and loading it back
could leave Match Labels stale: the Load Labels page showed the source, while Match
Labels still filtered the carrier as removed. The fix restores excluded carriers
when the same known label file or folder is loaded again, refreshes the Match Labels
state, and returns the wizard to the outer scan loop before entering Match Labels
when a brand-new label source requires rescanning.

A follow-up manual test found that removing one label file from an already-loaded
label folder, then loading the same file back, could show the carrier twice because
the file was also added as a second source. The restore path now treats files already
covered by a loaded folder as the same source: it restores the carrier but does not
add a duplicate file-level label source.

Another manual test found the same visual duplicate when the loaded source itself was
the exact label file: Load Labels rendered both the carrier row and the loaded file
source row. The UI now collapses an exact file source when a visible carrier row has
the same normalized path, while keeping loaded folder sources visible as the source
scope.

Another follow-up found that a loaded folder rendered file rows and the folder-scope
row with identical `Remove` buttons, making single-file removal indistinguishable
from unloading the whole folder. File carrier rows now use `Remove file`, while the
folder source is shown as a separate source bar with `Remove all from this folder`.
Regression coverage verifies that removing one file from a loaded folder leaves
sibling label files and the loaded folder source intact.

A folder named `label` also looked like another label file when its basename was used
as the row title. Loaded folder sources now render as `Label source: ...` above the
file list, so the list itself contains only actual label files. Cleanup also detaches
old source-row widgets from the dialog tree before `deleteLater()`, preventing stale
hidden remove buttons from being picked up after remove -> reload cycles.

The same validation pass exposed a reproducible UI-suite crash in the preprocessing
preview: `PlotWidget.clear()` deleted persistent PyQtGraph crosshair/title items and
later resize events touched deleted Qt objects. Preprocess preview clearing now removes
transient plot data only and keeps persistent crosshair items alive.

Focused validation:

```bash
QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys \
  tests/unit/ui/dialogs/dataset/test_data_interpretation_preview_dialog.py \
  tests/unit/ui/test_ui_misc.py \
  tests/unit/ui/dialogs/test_preview_widget.py \
  tests/unit/ui/preprocess/test_preprocess_plotter.py \
  tests/unit/ui/preprocess/test_preprocess_panel.py -q
# 273 passed

poetry run python scripts/dev/run_tests.py ui
# 1160 passed

poetry run ruff check \
  XBrainLab/ui/dialogs/dataset/data_interpretation_preview_dialog.py \
  XBrainLab/ui/panels/preprocess/preview_widget.py \
  XBrainLab/ui/panels/preprocess/plotters/preprocess_plotter.py \
  tests/unit/ui/dialogs/dataset/test_data_interpretation_preview_dialog.py \
  tests/unit/ui/dialogs/test_preview_widget.py \
  tests/unit/ui/preprocess/test_preprocess_plotter.py
# All checks passed!

poetry run basedpyright
# 0 errors, 0 warnings, 0 notes
```

## 2026-05-16 Manual-Test Integration Preflight

Manual-test branch `integrate/all-branches-manual-test` was refreshed after a
multi-agent read-only audit found capability, label-placement, historical MCP, and UI status
risks. The follow-up patch fixed preprocessing-aware raw-load blockers, destructive
command confirmation metadata, event-code versus timestamp label placement, internal
EEG label choice persistence, conversion-fallback pairing status, MCP HTTP conflict
confirmation metadata, and dashboard typecheck failures.

Validation run from `/mnt/d/workspace_v2/projects/lab/XBrainLab-integrated-manual`:

- `poetry run python scripts/dev/update_quality_dashboard.py`: `PASS`.
- `poetry run ruff check .`: `PASS`.
- `poetry run basedpyright`: `PASS`.
- `poetry run mkdocs build --strict`: `PASS`.
- `poetry run python tests/architecture_compliance.py`: `PASS`.
- Data Import / Epoch / UI focused suite: `178 passed`.
- ApplicationService / automation / agent surface suite: `153 passed`.
- Historical MCP unit and integration suite: `18 passed`.
- `poetry run pytest --capture=sys tests/integration/io/test_io_integration.py -q`:
  `21 passed, 10 skipped` because optional public fixtures are not present.
- Pipeline smoke:
  `tests/integration/pipeline/test_full_pipeline.py::TestFullPipeline::test_train_and_evaluate_metrics`
  and
  `tests/integration/pipeline/test_study_training_e2e.py::TestStudyTrainCycle::test_full_cycle_eegnet`:
  `2 passed`.

This supports a runnable automated preflight for hand testing. It still does not
prove human Windows click-through acceptance, full BIDS validation, every public EEG
format fixture, or final UI approval for Match Labels / Review and Import.

## 2026-05-14 Artifact Live-Capture Deduplication Checkpoint

Artifact hygiene removed tracked top-level `artifacts/ui/*.png` live-capture files that duplicated
approved `tests/baselines/ui/` references byte-for-byte and made future top-level dashboard captures
local-only through `artifacts/ui/.gitignore`. Current UI walkthrough evidence remains in named
`artifacts/ui/*/` subdirectories, while approved regression references remain in
`tests/baselines/ui/`.

Focused validation from that slice covered dashboard markdown / UI baseline helper tests, strict
docs build, architecture compliance, and whitespace checks. This supports artifact retention hygiene;
it does not prove visual freshness, runtime correctness, or human desktop acceptance.

## 2026-05-14 Agent Confirmation Boundary Payload Evidence Checkpoint

Agent confirmation payloads now include a `decision_boundary` field so UI clients can distinguish
ordinary tool confirmation from backend semantic-apply confirmation. The focused controller test
asserts both the default `tool_confirmation` path and `semantic_apply` for Data Interpretation apply.
This supports clearer agent/UI confirmation behavior; it does not prove full agent tool-call quality.

## Reality-Gap Audit

當 human walkthrough 發現 dashboard / automated smoke 沒抓到的問題時，不能只修單點 bug。
必須反向更新 validation strategy：

- 記錄是哪一種 evidence 漏掉問題。
- 補一個能重跑的 test、walkthrough artifact 或 product smoke。
- 明確區分 backend truth、UI presentation truth、human-observable truth。
- 對 launcher / desktop 問題，至少記錄 Qt platform、screen geometry、window geometry、exit code。

目前需要補強的代表性 smoke：

```text
launcher
-> main window visible on current screen
-> Import file / Import folder
-> Load label folder from a different location
-> Review Metadata
-> Match Labels
-> Review and Import
-> preview shows selected scope separately from scan location
-> primary Import / Apply action remains visible
-> apply loads exactly selected EEG files and loaded label carriers
```

2026-05-10 automated coverage now includes focused backend tests for external `label_sources`,
selected scope vs scan location, structured action items, dialog primary-action visibility,
left-side Cancel / right-side wizard navigation behavior, no nested table scroll regression,
one-panel-per-step wizard navigation, task-panel layout checks, Dataset sidebar first-layer action
cleanup, and a product-flow unit smoke for import -> load label folder -> review metadata ->
match labels -> review/import. Updated offscreen screenshots live under
`artifacts/ui/data-import-wizard-steps/`. This is not a replacement for human Windows desktop
acceptance or a full BIDS support claim.

2026-05-11 follow-up coverage adds the final first-version Match Labels source model:
`Labels inside EEG files` hides loaded-label pairing, while `Loaded label files` exposes file
pairing plus label field, placement method, target event / time, label unit, duration field and
check status. Focused tests now cover placement / duration preservation for epoch handoff,
inside-EEG source selection suppressing external label-file choices, and removing a loaded label
source from `Load Labels`. Follow-up coverage also verifies that auto-detected label carriers can
be removed from `Load Labels` and are excluded from the backend candidate through
`excluded_label_carriers`. Background test coverage now adds single-file selected-scope regressions
for sibling EEG files and service apply. Follow-up tests verify that class maps inferred from
external label carriers are not shown or saved when the user chooses `Labels inside EEG files`.
Offscreen screenshots include:

- `artifacts/ui/data-import-wizard-steps/04-match-labels-final-loaded-label-files.png`
- `artifacts/ui/data-import-wizard-steps/04-match-labels-internal-suggested-events-full.png`
- `artifacts/ui/data-import-wizard-steps/04-match-labels-bids-events.png`
- `artifacts/ui/data-import-wizard-steps/04-match-labels-conversion-fallback.png`

2026-05-13 Tier 1/Tier 2 Data Import coverage adds:

- single-file selected-scope tests that still detect same-stem label carriers from nearby
  `label/` subfolders without importing sibling EEG files;
- strict BIDS `events.tsv` coverage for missing sidecar, missing duration fallback,
  missing selected-scope events blocking, and regular-folder `events.tsv` staying in
  the general label-file flow;
- internal-event evidence coverage for response/comment filtering and run-dependent `T1` / `T2`
  warnings;
- external label placement coverage that blocks invalid selected target events and preserves
  selected event filters into reviewed label import recipe state;
- UI coverage for strict BIDS event review cards, class-value summaries, and refreshed
  canonical wizard screenshots via `scripts/dev/capture_data_import_wizard_steps.py`.

Latest focused validation for this slice:

```bash
QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys \
  tests/unit/backend/application/test_data_interpretation_scan.py \
  tests/unit/backend/application/test_data_interpretation_label_carriers.py \
  tests/unit/backend/application/test_data_interpretation_candidate.py \
  tests/unit/backend/application/test_data_interpretation_recipe.py \
  tests/unit/backend/application/test_data_interpretation_review.py \
  tests/unit/backend/application/test_application_service.py -q
# 109 passed

QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys \
  tests/unit/ui/dialogs/dataset/test_data_interpretation_preview_dialog.py \
  tests/unit/scripts/test_capture_data_interpretation_replay.py -q
# 69 passed
```

2026-05-14 Epoch handoff coverage adds a focused bridge from Data Import review choices into the
Create Epochs dialog:

- reviewed internal EEG labels record recommended class events for epoching;
- reviewed external label files record placement method, label field, target event selection,
  time field, duration/end field, class map and duration statistics as runtime epoch hints;
- interval labels using an end-time column are converted to durations before apply;
- reviewed event-code label carriers remap matching EEG events instead of falling back to sequence
  apply;
- Create Epochs consumes the import hint for suggested events, time window and baseline defaults,
  while keeping the old epoch dialog API compatible;
- Create Epochs section titles use card headers instead of Qt group-box legends, avoiding title /
  border overlap in the dark theme.

Focused validation for this slice:

```bash
poetry run ruff check \
  XBrainLab/backend/application/epoch_context.py \
  XBrainLab/backend/application/data_interpretation_apply.py \
  XBrainLab/backend/application/data_interpretation_service.py \
  XBrainLab/backend/load_data/label_loader.py \
  XBrainLab/ui/dialogs/preprocess/epoching_dialog.py \
  tests/unit/backend/application/test_epoch_context.py \
  tests/unit/backend/application/test_application_service.py \
  tests/integration/ui/test_dialog_acceptance.py
# All checks passed!

poetry run basedpyright \
  XBrainLab/backend/application/epoch_context.py \
  XBrainLab/backend/application/data_interpretation_apply.py \
  XBrainLab/backend/application/data_interpretation_service.py \
  XBrainLab/backend/load_data/label_loader.py \
  XBrainLab/ui/dialogs/preprocess/epoching_dialog.py \
  tests/unit/backend/application/test_epoch_context.py \
  tests/unit/backend/application/test_application_service.py \
  tests/integration/ui/test_dialog_acceptance.py
# 0 errors, 0 warnings, 0 notes

QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys \
  tests/unit/backend/application/test_epoch_context.py \
  tests/unit/backend/application/test_application_service.py \
  tests/unit/backend/application/test_preprocess_service.py \
  tests/integration/ui/test_dialog_acceptance.py \
  tests/unit/ui/components/test_dialogs.py::test_epoching_dialog_init \
  tests/unit/ui/test_dialogs_extra.py::TestEpochingDialog \
  tests/unit/ui/test_sidebars_and_components.py::TestPreprocessSidebar::test_open_epoching_accepted \
  tests/unit/ui/test_sidebars_and_components.py::TestPreprocessSidebar::test_open_epoching_uses_epoch_capability_not_preprocess_block \
  tests/unit/ui/test_sidebars_and_components.py::TestPreprocessSidebar::test_open_epoching_uses_query_data_list_before_stale_controller \
  tests/unit/ui/preprocess/test_preprocess_panel.py::test_preprocess_panel_epoching \
  tests/unit/backend/load_data/test_label_loader.py \
  tests/unit/backend/load_data/test_label_loader_coverage.py -q
# 101 passed
```

Screenshot evidence:

- `artifacts/ui/epoching-dialog/epoching-interval-import.png`
- `artifacts/ui/epoching-dialog/epoching-internal-events.png`

2026-05-22 manual-test follow-up:

- Create Epochs now keeps its action footer fixed while the content area scrolls above it, so
  dense import hints / event lists do not push the Time Window card below the visible dialog.
- Data Import Review and Import now groups repeated file-scoped action items with the same target
  step, issue and next action into one review card / tree row, while preserving ordinary non-file
  review rows as separate items.
- Follow-up grouping now treats file-scoped review items as the same problem even when the file
  name appears in the issue/title rather than only in the impact text. The UI shows one card with
  affected files instead of one repeated card per EEG file.
- Load Labels rescan follow-up now resumes the wizard at Review Metadata after a user loads a
  new label source and presses Next, instead of rebuilding the dialog back at Choose EEG Data.
- Load Labels now supports in-place label-source rescan through the same command API, so the
  visible dialog stays open while refreshed label carriers are loaded and the wizard advances to
  Review Metadata without a close/reopen flash.
- Review and Import now refreshes its Import Summary from current wizard state when the final
  step is shown, so manual subject/session/task/run edits made in Review Metadata are reflected
  before applying.
- Load Labels now removes the containing user-loaded folder source when the removed label file is
  the only active carrier from that folder, so duplicate auto/folder label paths do not require a
  second removal. Multi-file folders keep the folder source and only exclude the selected file.
- Evaluation Metrics Summary now forces a dark selected-row palette, including inactive selection
  state, so selected rows do not fall back to unreadable white system selection colors.
- Visualization 3D Plot now blocks known-unstable Wayland / remote OpenGL PyVistaQt sessions before
  creating `QtInteractor`, so opening the last saliency tab shows a product message instead of
  risking a native crash.

Focused validation:

```bash
QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys \
  tests/unit/ui/test_dialogs_extra.py::TestEpochingDialog::test_content_scrolls_above_fixed_footer \
  tests/unit/ui/test_dialogs_extra.py::TestEpochingDialog::test_label_backgrounds_are_transparent \
  tests/unit/ui/components/test_dialogs.py::test_epoching_dialog_init \
  tests/unit/ui/dialogs/dataset/test_data_interpretation_preview_dialog.py::test_review_and_import_groups_repeated_file_action_items -q
# 4 passed

QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys \
  tests/unit/ui/test_dialogs_extra.py \
  tests/unit/ui/components/test_dialogs.py \
  tests/unit/ui/dialogs/dataset/test_data_interpretation_preview_dialog.py \
  tests/unit/ui/test_ui_misc.py -q
# 266 passed

QT_QPA_PLATFORM=offscreen poetry run python scripts/dev/run_tests.py ui
# 1171 passed

QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys \
  tests/unit/ui/dialogs/dataset/test_data_interpretation_preview_dialog.py -q
# 71 passed

QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys \
  tests/unit/ui/test_dialogs_extra.py \
  tests/unit/ui/components/test_dialogs.py \
  tests/unit/ui/dialogs/dataset/test_data_interpretation_preview_dialog.py \
  tests/unit/ui/test_ui_misc.py -q
# 268 passed

QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys \
  tests/unit/ui/dialogs/dataset/test_data_interpretation_preview_dialog.py \
  tests/unit/ui/test_ui_misc.py::TestDatasetActionHandler::test_import_data_rescans_after_add_label_folder_product_flow -q
# 74 passed

QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys \
  tests/unit/ui/test_dialogs_extra.py \
  tests/unit/ui/components/test_dialogs.py \
  tests/unit/ui/dialogs/dataset/test_data_interpretation_preview_dialog.py \
  tests/unit/ui/test_ui_misc.py -q
# 272 passed

QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys \
  tests/unit/ui/dialogs/dataset/test_data_interpretation_preview_dialog.py -q
# 76 passed
```

## Backend Test Hygiene Inventory

2026-05-11 compact inventory for the backend/test hygiene branch:

| Cluster | Classification | Current evidence | Action in this branch |
| --- | --- | --- | --- |
| Data Interpretation backend lifecycle | Strong behavior tests | `tests/unit/backend/application/test_data_interpretation_service.py` covers scan -> preview -> validate -> apply, external label sources, selected file scope, metadata apply, label import recipe state. `tests/integration/backend/test_application_service_workflow.py` covers non-mocked ApplicationService interpretation -> recipe reload -> dataset workflow. | Strengthened selected-scope and service apply coverage; added relative selected-file normalization coverage. |
| Scan / candidate / review / recipe contracts | Useful unit contract tests | `test_data_interpretation_scan.py`, `test_data_interpretation_candidate.py`, `test_data_interpretation_review.py`, `test_data_interpretation_recipe.py`, `test_data_interpretation_label_carriers.py`. | Preserves BIDS/file/folder scan behavior, selected scope, external label source provenance, structured action items, recipe reload/remap, label source mode, placement, duration, and class-map source. |
| Product runtime BackendFacade guard | Strong architecture guard | `tests/architecture_compliance.py` now has a pytest gate that scans `XBrainLab/ui`, `XBrainLab/llm`, and `XBrainLab/mcp` for `BackendFacade` imports / construction. `tests/unit/test_architecture_compliance.py` covers both violation and allowed `get_application_service(study)` cases. | Product runtime packages must enter via `ApplicationService / Command API`; `BackendFacade` module is physically removed and must not return. |
| UI command route | Mock-heavy but useful command contract tests | `tests/unit/ui/test_ui_misc.py` asserts import file/folder/BIDS/reload route through `ScanSourceCommand`, `PreviewInterpretationCommand`, `ValidateInterpretationCommand`, and `ApplyInterpretationCommand` without controller import fallback. `tests/unit/ui/dataset/test_dataset_sidebar.py` and `test_panel.py` guard real-Study fallback refusal. | Backend/test continuation adds command-route coverage only. The current dirty worktree still contains earlier Load Labels / Match Labels UX edits, so product UI acceptance must be judged separately from these route tests. |
| Assistant command parity | Useful contract tests | `tests/unit/llm/tools/test_application_surface.py`, `tests/unit/llm/tools/real/test_real_tools.py`, `tests/unit/llm/tools/test_definitions.py`, and `tests/unit/llm/agent/test_tool_call_normalizer.py` cover exposed Data Interpretation command names, confirmation boundary, blocked reasons, schema exposure, and state truth. Historical MCP tests may still exist, but they are no longer active handoff gates. | Real agent tools now assert `ApplicationService` command objects instead of patching `BackendFacade`; tool schema and real/mock tool surfaces carry `label_sources` and the shared choice schema. |
| Real-data fixture validation | Strong integration evidence when fixtures are present | Real-data tests now resolve fixtures under `tests/fixtures/data/`; scripts use the same path. | Replaced obsolete `tests/data/` path references so deleted tracked fixture files do not turn IO/pipeline tests into false skips. The replacement fixture tree must be included in the PR rather than left untracked. |
| Legacy direct controller tests | Mock-heavy but useful compatibility tests | Legacy controller fallback tests remain in UI suites to guard mock/legacy contexts and real-Study refusal. | Not deleted; retained because they protect compatibility while architecture guards prevent product fallback bypass. |
| Obsolete / duplicated clusters | Obsolete path cluster | The obsolete cluster is the deleted `tests/data/` fixture location, replaced by `tests/fixtures/data/`. No test cluster was deleted without replacement. | Consumers and docs were moved to `tests/fixtures/data/`; real-data gates must use that path. |
| Missing coverage outside this scope | Explicitly out of current backend/test cleanup scope | Full internal event-name extraction for every EEG format, Windows human desktop acceptance, and final Epoch UI consumption of `duration_field`. | Documented as future validation/product work, not claimed by this branch. |

## 2026-07-10 UI Worker And Shutdown Lifecycle Gate

This checkpoint closes lifecycle races found after the first Desktop MVP handoff audit:

- Data Interpretation review, reload, apply, and recipe save use QThreadPool continuations. The
  original click handler returns immediately; there is no custom nested `QEventLoop` wait.
- Async command cleanup captures an immutable refresh-suppression owner id before work starts.
  A queued result can therefore clean up after its QWidget is deleted without dereferencing the
  deleted wrapper. Normal callbacks are also suppressed after MainWindow begins closing.
- MainWindow disables all command surfaces, installs an ApplicationService admission fence, and
  then checks training/assistant ownership. Commands queued before the fence are checked again
  after acquiring the command lock. Failed fence release has bounded retry and an explicit
  Retry/Close recovery path.
- Data Splitting preview records running/succeeded/failed/cancelled state. Unexpected worker
  exceptions cannot leave `Calculating` forever or make Confirm rerun generation on the GUI thread;
  Esc/X wait for the real worker and slow cancellation remains visibly in progress.

Validation:

```bash
QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys \
  tests/unit/backend/application \
  tests/unit/ui/test_application_capabilities.py \
  tests/unit/ui/test_refresh_coordinator.py \
  tests/unit/ui/test_data_splitting.py \
  tests/unit/ui/dataset/test_data_splitting.py \
  tests/unit/ui/dataset/test_interpretation_async_flow.py \
  tests/unit/ui/test_main_window_sync.py \
  tests/unit/ui/test_ui_misc.py \
  tests/unit/ui/test_local_bootstrap_validation.py \
  tests/unit/test_architecture_compliance.py -q
# 746 passed

QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys tests/unit/ui -q
# 1375 passed

poetry run basedpyright XBrainLab
# 0 errors

poetry run python tests/architecture_compliance.py
# Architecture compliant
```

This does not replace Windows human acceptance for closing during real training, Alt+F4 while a
real Data Splitting preview is stopping, or long-running native-library teardown.

## 常用 docs gate

```bash
poetry run mkdocs build --strict
git diff --check
```

如果改 CSS / layout，還要留下 built site screenshot 或可視覺審核 artifact。
