# Data Pipeline Architecture

最後更新：`2026-05-14`

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

label import 目前集中在 `LabelImportService`。

它支援兩種主要模式：

| 模式 | 說明 |
| --- | --- |
| batch mapping | data file path 對 label file path。 |
| legacy sequential | 一串 labels 依每個檔案 epoch/event count 分配。 |

`ApplicationService.execute(AttachLabelsCommand(...))` 目前會：

1. 從 dataset controller 取得 loaded data。
2. 依 filepath、filename、basename 找對應 label path。
3. 用 `load_label_file()` 讀 label。
4. 呼叫 `LabelImportService.apply_labels_batch()`。
5. 成功後 reset preprocess，因為 label/event 變更會讓下游狀態失效。

這裡的風險是：label/event 正確性不是 import 成功就能保證。它需要 event count、event ID mapping、timestamp/sequence mode 都對上。

Data Interpretation 的 `apply_interpretation` 目前會把使用者 review 過的 label choices
轉成同一套 label import record / recipe trace：

- external label file 的 `EEG event order` mode 會保存並套用使用者選定的 target EEG
  event，而不是把 label sequence 套到所有 events；numeric selection 例如 `768` 會同時
  match `Stimulus/S 768` 類 event name alias。
- `Label time`、`Label interval`、`Label event code` 的 active review 會保存 label field、
  placement field、duration / end / stop / offset field、selected event / code coverage 與
  check summary，供 recipe reload 與 epoch setup 使用。
- 選擇 `Labels inside EEG files` 時，apply 不會讀 loaded label files。若使用者確認了
  run-dependent internal mapping，例如 PhysioNet EEGMMI `T1` / `T2` 在不同 run 的語意，
  mapping 會直接套到對應 loaded EEG file 的 internal events，並寫入 label import record。
- applied interpretation 會把 `selected_event_names`、placement mode、label source 與
  limitation summary 暴露在 state snapshot 的 `epoch_handoff`，讓後續 Epoch UI 可以預填
  或限制 target events / interval timing。

Data Interpretation scan 會把可支援和不可支援的 label/event sidecar 分開呈現。`.mat`、
`.csv`、`.tsv`、`.txt` 和 BIDS-like `events.tsv` 是本輪支援的 external carrier；pickle
sidecar 是 blocked，proprietary `.log` 和未知 sidecar 只會標 limited / unsupported，不會被
默默當成可訓練 label。BIDS-like carrier review 只在 BIDS-like scan context 內套用：缺
`onset` 是 blocked；缺 `events.json`、缺 duration / end field 或 duration 欄位歧義會成為
warning / action item。這不是 full BIDS validator support。

### Internal Event Evidence Preview

Data Import 的 `Labels inside EEG files` preview 目前不使用單一 dataset 或格式專屬 code
table 來硬猜 class label。後端先讀 EEG 內建 event / annotation，再用下列 evidence 分群：

- 文字語意：若 event description 不是純數字，且包含 `left`、`right`、`hand`、`foot`、
  `feet`、`tongue`、`target`、`non-target`、`nontarget`、`standard`、`deviant`
  或 `rest`，可列為 `Class label` candidate。
- Count pattern：只從尚未有明確語意、目前仍是 `Review` 的 events 中找候選群組。每個
  code 的 per-file count 必須完全一致，且每個 file 至少 `5` 次；該 code 必須出現在至少
  `total_files - 1` 個 selected EEG file；同一 count 的 code 數量必須在 `2` 到 `12`
  之間。若多個群組符合，選 code 數量最多者；數量相同時選 per-file count 較高者。
- Timing evidence：若某個非 candidate event 在每個 file 的 count 等於 candidate 群組所有
  code 的 count 總和，將該 event 標為 `Trial timing`，reason 為
  `Count matches candidate label group`。
- Other events：未進 candidate 的 event 留在 `Other EEG events`。只有 description 明確包含
  `artifact`、`artefact`、`reject`、`bad` 時才標為 artifact；明確包含 `boundary`、`edge`、
  `new segment`、`sync`、`system` 時才標為 ignore；明確包含 `trial start`、`starttrial` 或
  `start trial` 時才標為 trial timing。否則維持 `Review`。

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

目前 tiny smoke 和 checked-in real-data smoke 都會 patch file outputs，例如 `torch.save`、`numpy.savetxt`、`matplotlib.pyplot.savefig`，避免測試污染 workspace。

## Evidence Matrix

| Evidence | 目前狀態 | 代表意思 | 不代表 |
| --- | --- | --- | --- |
| Real-data IO integration | `PASS` in fast dashboard | 多格式 real fixtures 可 import。 | 完整 training / thesis reproducibility。 |
| Checked-in GDF+MAT dataset generation | tests exist | A01T/A02T/A03T 可 attach labels、preprocess、epoch、generate dataset。 | 所有資料集來源都正確。 |
| Checked-in GDF+MAT training smoke | tests exist | A01T/A02T/A03T 可 one-epoch training smoke。 | accuracy 有意義或 protocol 可發表。 |
| Public cross-source training smoke | local-only tests exist | event-rich public fixtures 可走一個 training smoke。 | fixture 一定存在於乾淨 clone，或 thesis-grade reproducibility 完成。 |
| Tiny E2E pipeline smoke | `2 passed in 7.54s` on 2026-05-01 | synthetic / Study train cycle 有基本閉環。 | real-world data 全面可信。 |

## 目前可信結論

- 多格式 loader 註冊清楚，且有 real-data IO integration coverage。
- `ApplicationService / Command API` 能跑多格式 import path；`BackendFacade` module 已移除，
  architecture guard 會拒絕 product runtime 或 test 重新 import / construct 它。
- checked-in GDF+MAT fixtures 已有 dataset generation 和 one-epoch training smoke tests。
- public fixtures 的 cross-source training smoke 屬於 local-only evidence，不能當成 checked-in baseline。
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
- `scan_source_path()` 能掃單一 file、folder、BIDS-like root，並找到 supported EEG files。
- label carrier discovery 目前支援 `.mat`、`.csv`、`.tsv`、`.txt` 和 BIDS `events.tsv`。
- label carrier planner 能從 MAT variables、CSV / TSV headers、BIDS events columns 推出
  label field / anchor candidates，並保存到 candidate / recipe choices。
- label carrier planner 也會為 active label carriers 建立 placement evidence：EEG event order、
  label time、label interval、label event code 四種模式各有可審查 review；目前 active
  `placement_review` 會保存到 candidate，供 UI / agent / recipe 使用。
- multi-file UI 會以 common parent scan，並透過 `choices.selected_eeg_files` 限定實際 import
  scope；preview payload 已開始區分 selected scope 和 scan location。
- `ScanSourceCommand.label_sources` 可帶入 EEG source 之外的 label / event file 或 folder；
  `scan_source_path()` 會合併 auto-discovered 和 user-added carriers，並保留 carrier source。
- preview / validation payload 已輸出 `action_items`，每項包含 `target_step`、`issue`、`impact`、
  `next_action` 和 `severity`，供 UI、agent、headless、MCP 讀同一份 command result。
- import dialog 目前以 `QStackedWidget` step panels 呈現，一次只顯示一個 task panel：
  Choose EEG Data、Attach Labels、Review Metadata、Match Labels、Review and Import。
- Dataset sidebar 主要入口已改成 `Import file`、`Import folder`、`Import BIDS folder`；BIDS
  入口仍是 BIDS-like scan hint，不代表完整 BIDS support。
- apply path 能在部分情況自動套 label：timestamp labels、sample-index anchored MAT labels、
  trial-order sequence labels。
- metadata edit、smart parse、remove files 已有 `DataTableCommandService` command path。

### 2026-05-10 已交付 slice

| Target UX need | Current implementation | Remaining boundary |
| --- | --- | --- |
| Attach label file / folder independent from EEG source | `ScanSourceCommand.label_sources`、dialog `Add label file` / `Add label folder`、service rescan loop、recipe `label_sources` preservation。 | Label source add currently rescans and reopens the wizard with the attached source; later polish can keep the user on the same visual step after rescan. |
| Selected scope vs scan location | dialog shows selected scope separately from scan location in source summary cards; candidate metadata is filtered by selected EEG files. | More screenshot evidence is still useful for multi-file fixture walkthroughs. |
| Match Labels task-oriented UI | 第一層分成 label source、file pairing、label values、placement task panel、class names、check；不再把 `Anchor` / `Time` / `Granularity` / `Role` / `Label unit` 當主 UI。 | Advanced event/class diagnostics still live in the same dialog instead of a collapsed details surface. |
| Mainstream label placement evidence | backend preview 會依資料結構支援 EEG event order、label time、label interval、label event code；UI 讀 `placement_reviews` 顯示 check，而不是靠前端硬猜。 | 仍不宣稱 full BIDS；BIDS inheritance、跨 datatype 和 run-dependent semantics 需要另外確認。 |
| Actionable Review and Import checklist | preview / validation emits structured action items; UI renders grouped review cards with issue、impact、next action and target step. | The hidden compatibility tree still backs legacy payload tests / remap selectors, but it is no longer the first-layer review layout. |
| Import without labels / limited mode | `Skip labels for now` is saved in choices and produces a supervised-limited action item. | Downstream dataset/training capability policy should consume this limited state more explicitly. |
| UI / agent / MCP alignment | ApplicationService, tool definitions, real/mock tools, state snapshot, stdio MCP and HTTP MCP tests use the same extended command surface. | Broader tool-call eval waits until product stabilization. |

### Remaining gaps

| Target UX need | Current gap | 實作方向 |
| --- | --- | --- |
| Metadata review step + Smart Parse | dialog button opens the Smart Parser helper and writes overrides into choices, but parser rule provenance is still basic. | Record parser rule / manual edit provenance more explicitly in recipe trace. |
| Internal event semantics | internal EEG events 已有 candidate label events / not-used events / coverage / evidence preview，但系統仍不能自行宣稱數字 code 的真實 class name。 | Class semantics 仍要靠 sidecar、recipe、preset 或使用者確認；epoch anchor / response / artifact 的 downstream contract 還要和 epoch UI 對齊。 |
| Wizard polish | Current implementation is a task-oriented step-panel dialog with step-specific cards, left-side Cancel, right-side navigation/apply, and screenshot evidence under `artifacts/ui/data-import-wizard-steps/`. | Human Windows desktop acceptance is still needed; offscreen screenshots are product evidence but not release approval. |
| Grouped checklist hierarchy | action items are structured and rendered as target-step review cards. | Very long review text may still need a detail drawer or row expansion after human walkthrough. |
| Downstream limited state | Skip-label choice is preserved and reviewable, but downstream supervised workflow blocking still needs a dedicated capability signal. | Capability policy 要能表示 imported raw-only / supervised-limited 狀態，並阻擋 supervised dataset / training claim。 |

### 建議下一個 backend slice

不要先大改整個 importer。下一個有效切片應是：

1. 讓 downstream capability policy 讀 skip-label / supervised-limited state。
2. 補 event extraction summary，讓 internal GDF / BIDS events 的 class cues 更容易人工確認。
3. 把 metadata Smart Parse provenance 寫進 recipe trace。
4. 補 screenshot / walkthrough artifact：EEG files 在 `eeg/`、labels 在 sibling `labels/`，使用者能
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
