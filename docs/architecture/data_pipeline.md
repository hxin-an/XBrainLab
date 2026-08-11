# Data Pipeline Architecture

最後更新：`2026-08-11`

## 可信度

狀態：`partially-verified`

這份文件已對照目前 source code：

- `XBrainLab/backend/load_data/factory.py`
- `XBrainLab/backend/load_data/raw_data_loader.py`
- `XBrainLab/backend/services/label_import_service.py`
- `XBrainLab/backend/preprocessor/`
- `XBrainLab/backend/dataset/epochs.py`
- `XBrainLab/backend/dataset/dataset.py`
- `XBrainLab/backend/dataset/dataset_generator.py`
- `XBrainLab/backend/training/`
- `tests/integration/io/test_io_integration.py`
- `tests/integration/pipeline/test_checked_in_real_dataset_validation.py`
- `tests/integration/pipeline/test_public_cross_source_training_smoke.py`

它描述的是目前 pipeline 實際狀態，不是完整 scientific validation。

## 一句話架構

XBrainLab data pipeline 目前是：

```text
EEG file
  -> RawDataLoaderFactory
  -> Raw wrapper
  -> LabelImportService / event handling
  -> PreprocessController + preprocessor classes
  -> Epochs
  -> DatasetGenerator / Dataset masks
  -> TrainingPlanHolder / Trainer
  -> evaluation records / visualization inputs
```

最重要的判斷是：`import 成功`、`label/event 正確`、`dataset generation 成功`、`training smoke 成功` 是不同層級的 evidence，不能混成同一個 claim。

目前 import / training polish 還有三個明確邊界：BIDS electrode geometry 在 import 後以
generation-bound background preparation 發布，不阻塞資料載入；Training Setting 的 RAM/VRAM
結果是 draft recommendation preview，Start Training 仍執行 authoritative preflight；Epoch 的
baseline 是獨立 On/Off 設定，不改變 reviewed event/window handoff。

## 支援格式

目前 loader factory 註冊的格式是：

| Extension | Loader | 備註 |
| --- | --- | --- |
| `.set` | `load_set_file` | EEGLAB，先嘗試 raw，再 fallback epochs。 |
| `.gdf` | `load_gdf_file` | BIOSIG / GDF，含 Graz 2a duplicate channel normalization。 |
| `.fif` | `load_fif_file` | MNE native raw / epochs。 |
| `.fif.gz` | `load_fif_file` | MNE native compressed FIF。 |
| `.edf` | `load_edf_file` | European Data Format。 |
| `.bdf` | `load_bdf_file` | BioSemi BDF。 |
| `.cnt` | `load_cnt_file` | Neuroscan CNT。 |
| `.vhdr` | `load_brainvision_file` | BrainVision header entry。 |

格式是否「支援」要分層理解：

- loader 註冊：程式碼有對應 reader。
- checked-in fixture import：repo 內小檔案可被測試讀取。
- command import：`ApplicationService.execute(LoadDataCommand(...))` 可走同一格式。
- legacy command compatibility：`LoadDataCommand` / `AttachLabelsCommand` /
  `ImportLabelsCommand` 只保留舊入口相容，不是 product runtime 的主要資料匯入流程。
- dataset generation：能套 labels / preprocess / epoch / split。
- training smoke：能跑到一個小訓練閉環。
- thesis-grade reproducibility：尚未完成。

## Import Layer

import 的核心入口是 `RawDataLoaderFactory`。

```text
DatasetController.import_files(...)
  -> RawDataLoaderFactory.load(path)
  -> registered loader by extension
  -> Raw(filepath, mne_object)
  -> RawDataLoader.apply(study)
```

`RawDataLoaderFactory` 以副檔名 dispatch loader。如果副檔名沒有註冊，會 raise `UnsupportedFormatError`。如果 loader 失敗，會包成 `FileCorruptedError` 或由原始錯誤往外傳。

GDF 有一個目前比較重要的特殊處理：

- MNE 可能自動 rename duplicate GDF channel names。
- 對已知 Graz 2a pattern，XBrainLab 會嘗試恢復 canonical channel labels。
- 如果無法恢復，會留下 runtime detail / runtime signal，避免 channel-sensitive workflow 默默吃到 ambiguous names。

## Label / Event Layer

label import 的底層套用仍集中在 `LabelImportService`，但產品主流程先經過
Data Import 的 scan / preview / validate / apply recipe。

它支援兩種主要模式：

| 模式 | 說明 |
| --- | --- |
| batch mapping | data file path 對 label file path。 |
| sequence mapping | 已 review 的 per-file label sequence 依目標 EEG event order 套用。 |

`ApplicationService.execute(AttachLabelsCommand(...))` 目前會：

1. 從 dataset controller 取得 loaded data。
2. 依 filepath、filename、basename 找對應 label path。
3. 用 `load_label_file()` 讀 label。
4. 呼叫 `LabelImportService.apply_labels_batch()`。
5. 成功後 reset preprocess，因為 label/event 變更會讓下游狀態失效。

`AttachLabelsCommand` / `ImportLabelsCommand` 是 legacy command compatibility；product
runtime 不應把它們當成 Data Import wizard 的替代入口。

這裡的風險是：label/event 正確性不是 import 成功就能保證。它需要 event count、event ID mapping、timestamp/sequence mode 都對上。

### Internal Event Suggestion Evidence Preview

Data Import 的 `Labels inside EEG files` preview 目前不使用單一 dataset 或格式專屬 code
table 來硬猜 class label。後端先讀 EEG 內建 event / annotation，再用下列 evidence 分群；
UI 的 `Suggestion evidence` 欄只顯示短句，完整判斷規則以這裡為準。

| Suggestion evidence | 來源 | 用途 |
| --- | --- | --- |
| `Class-like text` | event description 包含 `left`、`right`、`hand`、`foot`、`feet`、`tongue`、`target`、`non-target`、`nontarget`、`standard`、`deviant` 或 `rest`。 | 建議列為 `Class label` candidate。 |
| `Repeated count` | 尚未有明確語意且仍是 `Review` 的 events；每個 code 的 per-file count 完全一致、每 file 至少 `5` 次、出現在至少 `total_files - 1` 個 selected EEG file；同一 count 的 code 數量在 `2` 到 `12` 之間。 | 建議這組 repeated event codes 可能是 class labels。 |
| `Repeated count + timing` | `Repeated count` 成立，且另外找到一個 event 的 count 等於 candidate group 的 count 總和。 | 建議 repeated group 是 labels，另一個 event 是 trial timing。 |
| `Matches class total` | 非 candidate event 的 count 等於 candidate group 總數。 | 建議列為 `Trial timing`，不當 class label。 |
| `Artifact text` / `Boundary/system text` / `Trial-start text` | description 明確包含 artifact、boundary/system 或 trial-start 類字詞。 | 放到 not-used / timing 類別。 |
| `same count/file`、`count varies/file`、`missing <file>` | per-file count 和 coverage。 | 顯示 coverage 是否穩定，幫助人工確認。 |

若多個 count group 符合，後端選 code 數量最多的群組；數量相同時選 per-file count 較高者。
未進 candidate 的 event 留在 `Other EEG events`；若沒有明確 artifact / boundary / trial-start
語意，維持 `Review`，由使用者確認。

Loaded label files 的 `EEG event order` target suggestion 使用同一批 event evidence，但只作為
UI 預選，不代表已確認：

1. 若 recipe / 使用者 choice 已保存 `target_event_codes`，優先使用保存值。
2. 若保存了非 `trial order` 的 anchor，使用該 anchor。
3. 若 `Class label` candidate group 的總 count 等於 label rows，預選整組 candidate events。
4. 否則若某個非 excluded event count 等於 label rows，預選該 event。
5. 仍無法判斷時不預選，UI 要求使用者選 `Target EEG events`。

這套規則只能產生可審查建議。GDF、EDF、BrainVision、EEGLAB、FIF 等來源都應走同一套
evidence contract；特定資料集若需要 code semantics，應由 sidecar、recipe、preset 或使用者
確認提供，而不是藏在通用 import heuristic。

## Preprocess Layer

preprocess 目前是 controller + processor classes 的組合。

主要 processors 位於 `XBrainLab/backend/preprocessor/`：

- filtering
- resample
- rereference
- normalize
- channel selection
- edit event
- time epoch
- window epoch
- export

`PreprocessController` 的重要行為是：

```text
read study.preprocessed_data_list
  -> copy each Raw object
  -> processor.data_preprocess(...)
  -> study.set_preprocessed_data_list(result, force_update=True)
  -> notify preprocess_changed
```

這代表 preprocess layer 目前不是直接 in-place 修改 `Study` 裡正在被 UI 讀取的 list，而是先 copy，再把結果換回 `Study`。

## Epoch / Dataset Layer

`Epochs` 是 dataset generation 前的統一資料容器。

Time Epoching 在 `ApplicationService` 進入 MNE materialization 前先檢查所選事件與每段
recording 的邊界。若只有不超過所選事件 `1%` 的尾端／起始事件無法容納完整 window，系統會
建立其餘 epochs，並在 command message、diagnostics 與 preprocessing history 明確記錄排除
數量；這不是靜默丟棄。若排除比例超過 `1%`，或全部事件都會被排除，則阻擋並要求調整
window 或 event selection。直接呼叫底層 `TimeEpoch` 時仍預設禁止 boundary drop，避免繞過
Application Service 的安全判定。

Epoch context 是 fail-closed availability contract，不是 dialog defaults。每個 selected recording
都必須有可讀的 applied timing hint，並且 reviewed import `epoch_handoff` 必須存在、schema 合法、
`ready=true`，其 label source / placement 也要與 runtime hints 相符；任何缺漏、read failure 或
mismatch 都會阻擋 epoch setup。Duration / event-locked truth 由這份 handoff 綁定的 reviewed
placement 與 duration evidence 產生：reviewed interval 有正 duration 時使用 duration mode，跨
selected BIDS runs 採最長 observed duration；BIDS interval 沒有 positive duration 時回到需人工
決定 window 的 event-locked mode。非 BIDS interval 缺 duration 則 blocked，不用通用預設掩蓋。
Raw recordings 可以先以不同 sampling rates 匯入，讓使用者在 Preprocess 明確 resample；在所有
recordings 尚未共享同一 sampling grid 前，Epoch context 會以 recoverable precondition 阻擋建立
epochs 並提供 resampling guidance。已 epoched inputs 仍必須在 loader 邊界共享 sampling rate。

它會：

- 要求輸入資料已經是 epoch，不是 continuous raw。
- 彙整多個 `Raw` 的 subject、session、label、idx、data。
- 統一 event IDs。
- 提供按 subject / session / trial picking 的基礎。

注意：`Epochs` constructor 會對 input `Raw` 做 event normalization，文件中已明確註記這是 in-place 影響。因此這一層後續若要重構，需要小心資料複製與狀態 ownership。

`DatasetGenerator` 以 `DataSplittingConfig` 產生 `Dataset`。

目前支援的核心概念：

- individual training：按 subject 生成 dataset。
- full/group training：以 group/fold 方式生成 dataset。
- test split：trial / session / subject。
- validation split：trial / session / subject。
- cross-validation：用 remaining mask 逐 fold 推進。

`Dataset` 本身主要保存 masks：

- `train_mask`
- `val_mask`
- `test_mask`
- `remaining_mask`

這表示 dataset split 不複製整份 EEG data；它以 mask 指向同一個 `Epochs`。

Data Splitting 的確認邊界只保存 typed split specification、fingerprint 與對應 preview
receipt 和 epoch revision，不在 dialog accept 時建立 masks 或 training tensors。`TrainCommand`
進入 Application Service 後才會依保存的 specification materialize datasets、執行 leakage /
coverage audit，再進入 resource preflight；同一份 epoch revision 與 specification 的成功結果可
重用。若 materialization 或 audit 失敗，既有 dataset、trainer 與 training state 必須保留，不能
在確認設定時先清除。Start Training 會保存 quiescent trainer startup snapshot；即使既有 trainer
以 `append=True` 原地加入 plans 後才失敗，也只移除本次新增 plans。Rollback 先恢復 trainer 再恢復
dataset publication，避免 cleanup failure 留下互不相符的 dataset / trainer pair。

## Training Layer

training flow 目前是：

```text
Study.generate_plan(...)
  -> TrainingManager.generate_plan(datasets, ...)
  -> TrainingPlanHolder(...)
  -> Trainer(training_plan_holders)

Study.train(interact=False/True)
  -> TrainingManager.train(...)
  -> Trainer.run(...)
```

`Trainer` 支援：

- synchronous training：`interact=False`
- background thread training：`interact=True`
- interrupt
- training plan queue
- progress text

Training Setting 的 epochs、batch size、learning rate、optimizer 與 evaluation strategy 目前可由
backend deterministic recommendation contract 提供起始值。它依目前 epoch shape、split preview /
materialized summary 與所選 model family 產生保守 starting point。每個欄位都有
`recommended` / `manual` provenance；只有 trusted host 明確記錄的使用者 edit 會在 context
重新計算時逐欄位保留。不能從 submitted value 與 recommendation 不同就推測使用者曾編輯；
未 edited 欄位一律更新 recommendation。它不是 hyperparameter search，也不取代 Start
Training 前的 resource preflight；timed search 只有 future roadmap contract，沒有現行 service /
command / tool implementation。

Training completion now writes metric-only evaluation by default. Saliency maps
are computed only after `saliency` parameters are explicitly configured, so a
normal training run does not silently run SmoothGrad / VarGrad work at the end.

目前 tiny smoke 和 checked-in real-data smoke 都會 patch file outputs，例如 `torch.save`、`numpy.savetxt`、`matplotlib.pyplot.savefig`，避免測試污染 workspace。

## Evidence Matrix

| Evidence | 目前狀態 | 代表意思 | 不代表 |
| --- | --- | --- | --- |
| Real-data IO integration | `PASS` in fast dashboard | 多格式 real fixtures 可 import。 | 完整 training / thesis reproducibility。 |
| Checked-in GDF+MAT dataset generation | tests exist | A01T/A02T/A03T 可 attach labels、preprocess、epoch、generate dataset。 | 所有資料集來源都正確。 |
| Checked-in GDF+MAT training smoke | tests exist | A01T/A02T/A03T 可 one-epoch training smoke。 | accuracy 有意義或 protocol 可發表。 |
| Public cross-source workflow smoke | local-only tests exist | PhysioNet EDF、BBCI GDF 走 training smoke；SCCN EEGLAB、tiny CNT 保留為 import/preprocess boundary，沒有足夠 reviewed classes 時明確阻止 supervised epoch。 | fixture 一定存在於乾淨 clone，或 thesis-grade reproducibility 完成。 |
| Tiny E2E pipeline smoke | `2 passed in 7.54s` on 2026-05-01 | synthetic / Study train cycle 有基本閉環。 | real-world data 全面可信。 |

## 目前可信結論

- 多格式 loader 註冊清楚，且有 real-data IO integration coverage。
- `ApplicationService / Command API` 能跑多格式 import path；`BackendFacade` module 已移除，
  guard 會擋 product runtime 重新引入。
- checked-in GDF+MAT fixtures 已有 dataset generation 和 one-epoch training smoke tests。
- public fixtures 的 cross-source evidence 屬於 local-only evidence，不能當成 checked-in baseline；tiny CNT 不再被宣稱可支撐 class-balanced training smoke。
- pipeline 已有工程 smoke，但還不是 thesis validation。

## 目前風險

- label/event correctness 是 data pipeline 的關鍵風險，不應只看 import 成功。
- `Epochs` 會 normalization event IDs 並影響 input `Raw`，後續重構要釐清 ownership。
- `DatasetGenerator` 支援多種 split，但文件還沒逐一映射到正式 thesis protocol。
- public fixture tests 可能因資料未下載而 skip，不能被寫成 always-on CI evidence。
- training smoke 目前看的是流程閉環和 metrics 存在，不看 scientific performance。

## Data Import UX Redesign Gap Audit

這段是 2026-05-10 對照新版 Data Import UX target 後的 backend / UI audit。它描述目前
Data Import wizard baseline 和仍未完成的產品化差距，不是新增目標態。

### 目前已有支撐

- Data Interpretation 已有 `scan -> preview -> validate -> apply -> recipe` command lifecycle。
- `scan_source_path()` 能掃單一 file、regular folder、strict BIDS folder，並找到 supported EEG files。
- 單一 EEG file scan 不會把 sibling EEG file 自動納入 selected scope；但會從同資料夾和
  `label/`、`labels/`、`event/`、`events/` 近鄰子資料夾找同 stem label carrier。
- label carrier discovery 目前支援 `.mat`、`.csv`、`.tsv`、`.txt` 和 BIDS `events.tsv`。
- label carrier planner 能從 MAT variables、CSV / TSV headers、BIDS events columns 推出
  label field / anchor candidates，並保存到 candidate / recipe choices。
- Strict BIDS label-field recommendation 不是固定偏好 `trial_type` 或 `value`。Planner 會在
  bounded row / byte limits 內逐一 profile selected runs，聚合欄位 coverage、non-empty / multi-value
  coverage、observed values、sidecar `Levels` 和 cross-run consistency；任一 selected table 的
  row / byte inspection 被截斷，或 evidence 不足時，都不自動推薦，explicit user selection 優先。
  Public payload 保存 reason code 與 bounded facts，完整 evidence
  留在 detail review。
- Strict BIDS folder import 會把 selected-scope `events.tsv` 當作 BIDS label/timing source並保留
  detected columns。`events.json` 是否存在與 selected label field 是否有可用 `Levels` 是兩個不同的
  structured facts；缺少 class semantics 會要求 review。missing onset / duration 仍會產生 warning 或
  blocked placement review；這仍不是 full BIDS inheritance / validator support。
- label carrier planner 也會為 active label carriers 建立 placement evidence：EEG event order、
  label time、label interval、label event code 四種模式各有可審查 review；目前 active
  `placement_review` 會保存到 candidate，供 UI / agent / recipe 使用。
- `data_interpretation_pairing.py` 是 external label carrier 對 selected EEG file 的共用 policy：
  candidate validation、apply mapping 與 wizard 即時 review 都讀同一個 resolver。單一 EEG / 單一
  carrier 可自動配對；多檔必須能以唯一 stem 或明確 target 完整覆蓋，partial mapping 會在 import
  前 blocked。Strict BIDS 也遵守同一規則；目前只認實際 run-specific carrier，不宣稱 events
  inheritance。
- multi-file UI 會以 common parent scan，並透過 `choices.selected_eeg_files` 限定實際 import
  scope；preview payload 已開始區分 selected scope 和 scan location。
- `ScanSourceCommand.label_sources` 可帶入 EEG source 之外的 label / event file 或 folder；
  `scan_source_path()` 會合併 auto-discovered 和 user-added carriers，並保留 carrier source。
- preview / validation payload 已輸出 `action_items`，每項包含 `target_step`、`issue`、`impact`、
  `next_action` 和 `severity`，供 UI、agent、headless 讀同一份 command result。
- import dialog 目前以 `QStackedWidget` step panels 呈現，一次只顯示一個 task panel：
  Choose EEG Data、Load Labels、Review Metadata、Match Labels、Review and Import。
- Dataset sidebar 主要入口已改成 `Import file`、`Import folder`、`Import BIDS folder`；
  `Import BIDS folder` 是 strict BIDS path，一般 `Import folder` 即使掃到 `events.tsv`
  仍走普通 label-file flow。
- apply path 能在完整且唯一的 file pairing 下自動套 label：timestamp labels、sample-index
  anchored MAT labels、trial-order sequence labels；不再默默跳過未配到 label 的 selected EEG。
- metadata edit、smart parse、remove files 已有 `DataTableCommandService` command path。

### 2026-05-10 已交付 slice

| Target UX need | Current implementation | Remaining boundary |
| --- | --- | --- |
| Attach label file / folder independent from EEG source | `ScanSourceCommand.label_sources`、dialog `Add label file` / `Add label folder`、service rescan loop、recipe `label_sources` preservation。 | Label source add currently rescans and reopens the wizard with the attached source; later polish can keep the user on the same visual step after rescan. |
| Selected scope vs scan location | dialog shows selected scope separately from scan location in source summary cards; candidate metadata is filtered by selected EEG files. | More screenshot evidence is still useful for multi-file fixture walkthroughs. |
| Match Labels task-oriented UI | 第一層分成 label source、file pairing、label values、placement task panel、class names、check；不再把 `Anchor` / `Time` / `Granularity` / `Role` / `Label unit` 當主 UI。Strict BIDS 顯示實際 EEG / `events.tsv` pairing，並以 selected-run row/sidecar evidence、coverage 與 consistency 提供保守 label-field recommendation；不再重複顯示獨立 BIDS review card。 | Recommendation 仍需 review；advanced event/class diagnostics live in the detailed import report instead of the first-layer task panel. |
| Mainstream label placement evidence | backend preview 會依資料結構支援 EEG event order、label time、label interval、label event code；UI 讀 `placement_reviews` 顯示 check，而不是靠前端硬猜。Blocked placement review 現在會成為 candidate blocker，不會只變成 confirmation。 | 仍不宣稱 full BIDS；BIDS inheritance、跨 datatype 和更複雜 run-level semantics 需要另外確認。 |
| Actionable Review and Import checklist | preview / validation emits structured action items; UI renders only blockers / required decisions as first-layer cards with issue、impact、next action and target step. | `View import report` exposes report-only warnings、format capability、recipe trace and remap selectors; it is secondary detail, not the first-layer review layout. |
| Import without labels / limited mode | `Continue without labels` is saved in choices and produces an authoritative `supervised_ready=false` handoff with structured blockers. Dataset/training capability policy consumes that handoff, so raw inspection/preprocessing can continue while supervised dataset/training remains blocked. | This does not infer missing class semantics or promise supervised readiness for unsupported sidecars. |
| UI / agent / headless alignment | ApplicationService, tool definitions, real/mock tools, and state snapshot use the same extended command surface. | Broader tool-call eval waits until product stabilization. MCP is no longer active roadmap. |

### Remaining gaps

| Target UX need | Current gap | 實作方向 |
| --- | --- | --- |
| Metadata review step + Smart Parse | dialog button opens the Smart Parser helper and writes overrides into choices, but parser rule provenance is still basic. | Record parser rule / manual edit provenance more explicitly in recipe trace. |
| Internal event semantics | internal EEG events 已有 candidate label events / not-used events / coverage / evidence preview；response、comment、artifact、boundary 類 markers 不會預設當 class label。PhysioNet-style `T1` / `T2` run-dependent semantics 會產生 review warning。 | Class semantics 仍要靠 sidecar、recipe、preset 或使用者確認；epoch anchor / response / artifact 的 downstream contract 還要和 epoch UI 對齊。 |
| Wizard polish | Current implementation is a task-oriented step-panel dialog with step-specific cards, left-side Cancel, right-side navigation/apply, and screenshot evidence under `artifacts/ui/data-import-wizard-steps/`. | Human Windows desktop acceptance is still needed; offscreen screenshots are product evidence but not release approval. |
| Grouped checklist hierarchy | action items are structured and rendered as target-step review cards. | Very long review text may still need a detail drawer or row expansion after human walkthrough. |

### 建議下一個 backend slice

不要先大改整個 importer。下一個有效切片應是：

1. 補 event extraction summary，讓 internal GDF / BIDS events 的 class cues 更容易人工確認。
2. 把 metadata Smart Parse provenance 寫進 recipe trace。
3. 補 screenshot / walkthrough artifact：EEG files 在 `eeg/`、labels 在 sibling `labels/`，使用者能
   attach labels 並完成 preview / validate / apply。

## 後續重構前要做

1. 把 import / label / preprocess / epoch / dataset / training 的 command boundary 畫清楚。
2. 決定哪些 data pipeline operation 要進 Application Service / Command API。
3. 定義 dataset testing 在穩定化階段的 scope：
   - checked-in fixtures
   - local-only public fixtures
   - optional downloaded fixtures
   - thesis experiments
4. 把 real-data IO、dataset generation、training smoke、reproducibility 分開記錄，不混成一個「支援資料集」claim。
