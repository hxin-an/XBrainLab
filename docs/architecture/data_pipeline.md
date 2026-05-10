# Data Pipeline Architecture

最後更新：`2026-05-01`

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
- facade import：`BackendFacade.load_data()` 可走同一格式。
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

`BackendFacade.attach_labels(mapping)` 目前會：

1. 從 dataset controller 取得 loaded data。
2. 依 filepath、filename、basename 找對應 label path。
3. 用 `load_label_file()` 讀 label。
4. 呼叫 `LabelImportService.apply_labels_batch()`。
5. 成功後 reset preprocess，因為 label/event 變更會讓下游狀態失效。

這裡的風險是：label/event 正確性不是 import 成功就能保證。它需要 event count、event ID mapping、timestamp/sequence mode 都對上。

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
- `BackendFacade` 能跑多格式 import path。
- checked-in GDF+MAT fixtures 已有 dataset generation 和 one-epoch training smoke tests。
- public fixtures 的 cross-source training smoke 屬於 local-only evidence，不能當成 checked-in baseline。
- pipeline 已有工程 smoke，但還不是 thesis validation。

## 目前風險

- label/event correctness 是 data pipeline 的關鍵風險，不應只看 import 成功。
- `Epochs` 會 normalization event IDs 並影響 input `Raw`，後續重構要釐清 ownership。
- `DatasetGenerator` 支援多種 split，但文件還沒逐一映射到正式 thesis protocol。
- public fixture tests 可能因資料未下載而 skip，不能被寫成 always-on CI evidence。
- training smoke 目前看的是流程閉環和 metrics 存在，不看 scientific performance。

## 後續重構前要做

1. 把 import / label / preprocess / epoch / dataset / training 的 command boundary 畫清楚。
2. 決定哪些 data pipeline operation 要進 Application Service / Command API。
3. 定義 dataset testing 在穩定化階段的 scope：
   - checked-in fixtures
   - local-only public fixtures
   - optional downloaded fixtures
   - thesis experiments
4. 把 real-data IO、dataset generation、training smoke、reproducibility 分開記錄，不混成一個「支援資料集」claim。
