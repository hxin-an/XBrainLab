# XBrainLab 測試指南 (Testing Guide)

本文件說明如何在 XBrainLab 專案中進行測試，包括環境設定、執行方式與撰寫規範。

## 1. 環境設定
確保你的 Python 環境已安裝 `pytest` 以及專案依賴 (如 `mne`, `torch`, `numpy`)。

```bash
pip install pytest
```

## 2. 執行測試
在專案根目錄下執行以下指令：

### 執行所有測試
```bash
pytest tests/ XBrainLab/
```

### 執行特定測試檔案
```bash
pytest tests/test_io_integration.py
```

### 執行特定測試案例
```bash
pytest tests/test_io_integration.py::TestIOIntegration::test_load_gdf_file_success
```

## 3. 測試案例字典 (Test Case Dictionary)

### 3.1 整合測試 (Integration Tests)
**檔案**: `tests/test_io_integration.py`
*   **用途**: 驗證真實檔案讀取功能 (I/O)。
*   **案例**:
    *   `test_load_gdf_file_success`: 讀取 `test_data_small/A01T.gdf`，驗證回傳物件為 `Raw` 且資料維度正確。
    *   `test_load_non_existent_file`: 讀取不存在路徑，驗證回傳 `None`。
    *   `test_load_invalid_extension`: 讀取錯誤格式檔案，驗證回傳 `None`。

**檔案**: `tests/test_metadata_integration.py`
*   **用途**: 驗證 Metadata 處理流程 (Load -> Parse -> Label -> Event)。
*   **案例**:
    *   `test_full_metadata_pipeline`: 模擬完整流程：讀取 GDF -> 解析檔名 (Subject/Session) -> 匯入 Label -> 轉換為 Event -> 更新 Raw 物件。

**檔案**: `tests/test_pipeline_integration.py`
*   **用途**: 驗證完整後端管線 (Load Data -> Preprocess -> Dataset -> Training)。
*   **案例**:
    *   `test_pipeline_integration`: 模擬從資料生成、預處理、資料集切分到模型訓練的完整流程，驗證各階段產出 (如 TrainRecord, EvalRecord) 是否正常。

**檔案**: `tests/test_real_data_pipeline.py`
*   **用途**: 驗證真實資料 (`A01T.gdf`) 的端對端流程。
*   **案例**:
    *   `test_real_data_pipeline`: 執行真實資料的載入、濾波、標準化、Epoching、資料集生成與模型訓練，確保無執行期錯誤且資料形狀正確。

**檔案**: `tests/test_ui_integration.py`
*   **用途**: 驗證 PyQt UI 元件的整合與互動功能。
*   **案例**:
    *   `test_mainwindow_launch`: 測試主視窗啟動與初始化。
    *   `test_navigation`: 測試 UI 導航與面板切換功能。
    *   `test_evaluation_panel_init`: 測試評估面板的初始化。
    *   `test_visualization_panel_init`: 測試視覺化面板的初始化。

### 3.2 單元測試 (Unit Tests)

#### **A. 資料讀取模組 (Data Loading)**
負責處理原始檔案讀取與物件封裝。

*   **`XBrainLab/load_data/tests/test_raw_data_loader.py`**
    *   **用途**: 測試檔案讀取器的邏輯分支與錯誤處理 (使用 Mock)。
    *   **案例**:
        *   `test_load_gdf_success`: 模擬 GDF 讀取成功。
        *   `test_load_gdf_failure`: 模擬讀取失敗。
        *   `test_load_set_raw_success`: 模擬 SET 檔作為 Raw 讀取。
        *   `test_load_set_fallback_to_epochs`: 模擬 SET 檔自動 fallback 機制。

*   **`XBrainLab/load_data/tests/test_label_loader.py`**
    *   **用途**: 測試標籤檔案讀取工具。
    *   **案例**:
        *   `test_load_txt_success`: 讀取純文字標籤。
        *   `test_load_txt_with_garbage`: 測試讀取包含非數值雜訊的文字檔。
        *   `test_load_mat_success`: 讀取 .mat 標籤。
        *   `test_load_non_existent_file`: 測試讀取不存在檔案的錯誤處理。
        *   `test_load_unsupported_format`: 測試不支援格式。

*   **`XBrainLab/load_data/tests/test_raw.py`**
    *   **用途**: 測試 `Raw` 類別屬性與方法，包含對 MNE Raw/Epochs 物件的封裝。
    *   **案例**:
        *   **基本屬性與方法**:
            *   `test_mne_raw_info`: 驗證 Raw 物件屬性 (nchan, sfreq, duration 等) 是否與內部 MNE 物件一致。
            *   `test_mne_raw_2_info`: 驗證替換 MNE 物件後的屬性更新是否正確。
            *   `test_add_preprocess`: 測試預處理歷史記錄功能。
            *   `test_parse_filename`: 測試檔名正則解析功能 (整合測試)。
            *   `test_file_info`: 測試檔案路徑與名稱取得功能。
            *   `test_labels_imported_status`: 測試標籤匯入狀態旗標的設定與讀取。
        *   **事件處理 (Event Handling)**:
            *   `test_raw_empty_event`: 測試無事件時的狀態與回傳值。
            *   `test_set_event`: 測試手動設定事件。
            *   `test_set_event_error`: 測試設定無效事件時的錯誤處理。
            *   `test_set_event_consistency`: 測試 Epochs 事件數量一致性檢查。
            *   `test_raw_stim_event`: 測試從 STIM 通道讀取事件。
            *   `test_raw_set_event_on_stim_event`: 測試在已有 STIM 事件的情況下，手動設定事件是否會影響原始事件的讀取。
            *   `test_raw_annotation_event`: 測試從 Annotations 讀取事件。
        *   **Epochs 支援**:
            *   `test_mne_epoch_info`: 測試當內部為 MNE Epochs 物件時的屬性正確性。
            *   `test_epoch`: 測試 Epochs 物件的事件讀取。
            *   `test_epoch_set_event`: 測試對 Epochs 物件手動設定事件的功能。
        *   **內部物件替換 (Internal Object Replacement)**:
            *   `test_set_mne_1`: 測試將內部物件替換為 MNE Raw (驗證屬性更新)。
            *   `test_set_mne_2`: 測試將內部物件替換為 MNE Epochs (驗證屬性更新)。
            *   `test_set_mne_after_set_event_1`: 測試在已有事件的情況下替換為 MNE Raw (驗證事件保留)。
            *   `test_set_mne_after_set_event_2`: 測試在已有事件的情況下替換為 MNE Epochs (驗證事件保留)。
            *   `test_set_mne_consistency`: 測試替換物件時的一致性檢查。
            *   `test_set_mne_and_wipe_events_1`: 測試替換為 MNE Raw 並強制清除原有事件。
            *   `test_set_mne_and_wipe_events_2`: 測試替換為 MNE Epochs 並強制清除原有事件。

*   **`XBrainLab/load_data/tests/test_event_loader.py`**
    *   **用途**: 測試 `EventLoader` 將外部標籤轉換為 MNE 事件的邏輯。
    *   **案例**:
        *   `test_event_loader_init`: 測試初始化與錯誤檢查 (無標籤時報錯)。
        *   `test_create_event_from_1d_list`: 測試從 1D 標籤列表 (如 .txt) 建立事件。
        *   `test_create_event_from_nx3_array`: 測試從 Nx3 陣列 (如 .gdf) 建立事件。
        *   `test_create_event_inconsistent`: 測試 Epochs 標籤數量不一致的錯誤處理。

*   **`XBrainLab/load_data/tests/test_data_loader.py`**
    *   **用途**: 測試 `RawDataLoader` 容器的資料管理與一致性檢查功能。
    *   **案例**:
        *   `test_raw_data_loader`: 測試基本的資料載入器建立與長度檢查。
        *   `test_raw_data_loader_validate`: 測試空資料載入器的驗證錯誤處理。
        *   `test_raw_data_loader_append`: 測試新增 Raw 物件與檔案檢索功能。
        *   `test_raw_data_loader_append_error`: 測試一致性驗證 (頻道數、採樣率、時長、型別不一致時的錯誤處理)。
        *   `test_apply`: 測試將 RawDataLoader 應用至 Study 物件的功能。

#### **B. 通用工具 (Utils)**
負責提供專案通用的輔助功能。

*   **`XBrainLab/utils/tests/test_filename_parser.py`**
    *   **用途**: 測試檔名解析工具 (`FilenameParser`)。
    *   **案例**:
        *   `test_parse_by_split`: 分隔符號切割。
        *   `test_parse_by_regex`: 正規表示式提取。
        *   `test_parse_by_named_regex`: 具名群組正規表示式提取 (Named Groups)。
        *   `test_parse_by_folder`: 資料夾結構推斷。
        *   `test_parse_by_fixed_position`: 固定位置提取。

*   **`XBrainLab/utils/tests/test_check.py`**
    *   **用途**: 測試型別驗證工具。
    *   **案例**:
        *   `test__get_type_name`: 測試取得類別全名。
        *   `test_validate_type`: 測試單一物件的型別檢查。
        *   `test_validate_list_type`: 測試列表內元素的型別檢查。
        *   `test_validate_issubclass`: 測試子類別繼承關係檢查。

*   **`XBrainLab/utils/tests/test_logger.py`**
    *   **用途**: 測試日誌記錄功能。
    *   **案例**:
        *   `test_setup_logger`: 測試 Logger 初始化與 Handler 設定。
        *   `test_logger_file_creation`: 測試日誌檔案建立與寫入。
        *   `test_logger_singleton_behavior`: 測試 Logger 的單例行為 (避免重複加入 Handler)。

*   **`XBrainLab/utils/tests/test_seed.py`**
    *   **用途**: 測試隨機種子設定與狀態管理。
    *   **案例**:
        *   `test_set_seed`: 測試設定隨機種子 (固定值與隨機生成)。
        *   `test_get_random_state`: 測試取得當前隨機狀態 (Torch, Numpy, Random)。
        *   `test_set_random_state`: 測試還原隨機狀態。

#### **C. 資料集管理 (Dataset)**
負責 Epochs 管理與資料集生成。

*   **`XBrainLab/dataset/tests/test_option.py`**
    *   **用途**: 測試 Dataset 相關的 Enum 定義。
    *   **案例**:
        *   `test_split_unit`: 測試 SplitUnit Enum 值。
        *   `test_training_type`: 測試 TrainingType Enum 值。
        *   `test_split_by_type`: 測試 SplitByType Enum 值。
        *   `test_val_split_by_type`: 測試 ValSplitByType Enum 值。

*   **`XBrainLab/dataset/tests/test_data_splitter.py`**
    *   **用途**: 測試資料分割邏輯 (DataSplitter) 與配置 (DataSplittingConfig)。
    *   **案例**:
        *   `test_splitter`: 測試 `DataSplitter` 的初始化、參數驗證與數值解析。
        *   `test_splitter_not_implemented`: 測試未實作的分割單位。
        *   `test_splitter_getter`: 測試屬性取得方法。
        *   `test_config`: 測試 `DataSplittingConfig` 的初始化與屬性。

*   **`XBrainLab/dataset/tests/test_dataset.py`**
    *   **用途**: 測試 `Dataset` 類別，負責管理訓練/驗證/測試集的遮罩與資料提取。
    *   **案例**:
        *   `test_dataset`: 測試 `Dataset` 的基本屬性、初始化、名稱取得 (`get_name`, `get_ori_name`)、選取狀態 (`set_selection`)、資料量統計 (`get_all_trial_numbers`) 與 UI 顯示資訊 (`get_treeview_row_info`)。
        *   `test_dataset_set_test_mask`: 測試設定測試集與驗證集遮罩，並驗證剩餘資料量。
        *   `test_dataset_discard`: 測試捨棄資料功能 (`discard_remaining_mask`)。
        *   `test_dataset_set_remaining_by_subject_idx`: 測試依受試者索引設定剩餘資料。
        *   `test_dataset_intersection_with_subject_by_idx`: 測試與特定受試者資料的交集。
        *   `test_dataset_get_data`: 測試取得訓練、驗證、測試資料集 (`get_training_data`, `get_val_data`, `get_test_data`)。

*   **`XBrainLab/dataset/tests/test_epochs.py`**
    *   **用途**: 測試 `Epochs` 類別的篩選、屬性存取與遮罩生成邏輯。
    *   **案例**:
        *   `test_epochs_args_error`: 測試初始化參數錯誤驗證。
        *   `test_epochs_subject/session/label_attributes`: 測試屬性列表的正確性。
        *   `test_epochs_copy`: 測試物件深層複製功能。
        *   `test_epochs_get_by_mask`: 測試透過遮罩取得資料。
        *   `test_epochs_get_by_index`: 測試透過索引取得名稱 (Subject/Session/Label)。
        *   `test_epochs_info`: 測試資料維度、數據內容一致性與模型參數資訊。
        *   `test_epochs_set_channel`: 測試頻道設定與 Montage。
        *   `test_epochs_generate_mask_target*`: 測試篩選遮罩的生成邏輯 (含 Partial)。
        *   `test_epochs_get_real_num*`: 測試數量計算邏輯 (Number, Ratio, KFold)。
        *   `test_epochs_pick*`: 測試各種篩選方法 (Pick by Subject, Session, Trial, Manual)。
        *   `test_epochs_pick_subject`: 測試依受試者篩選的整合測試。
        *   `test_epochs_pick_session`: 測試依場次篩選的整合測試。

*   **`XBrainLab/dataset/tests/test_dataset_generator.py`**
    *   **用途**: 測試 `DatasetGenerator` 的資料集切分與生成邏輯。
    *   **案例**:
        *   `test_dataset_generator_split_test*`: 測試測試集切分 (含 List, Empty, Failed, Independent, Interrupted)。
        *   `test_dataset_generator_split_validation*`: 測試驗證集切分 (含 Failed, Not Implemented, Interrupt)。
        *   `test_dataset_generator_handle_individual*`: 測試個別受試者模式 (含 Cross-Validation)。
        *   `test_dataset_generator_handle_full*`: 測試全體受試者模式 (含 Cross-Validation)。
        *   `test_dataset_generator_generate*`: 測試最終資料集生成 (含 Not Implemented, Exists)。
        *   `test_dataset_generator_name_prefix`: 測試資料集命名規則 (Subject- vs Group)。
        *   `test_dataset_generator_failed`: 測試生成失敗時的狀態處理。
        *   `test_dataset_generator_prepare_reuslt`: 測試結果準備與未選取資料集的過濾。
        *   `test_dataset_generator_apply`: 測試將生成的資料集應用至 Study 物件。

#### **D. 預處理 (Preprocessor)**
負責訊號處理與標準化。

*   **`XBrainLab/preprocessor/tests/test_base.py`**
    *   **用途**: 測試預處理器基類 (`PreprocessBase`)。
    *   **案例**:
        *   `test_base`: 測試 `PreprocessBase` 的初始化與抽象方法約束 (確保子類別必須實作特定方法)。
        *   `test_inherit`: 測試繼承自 `PreprocessBase` 的子類別實作與歷史記錄功能。

*   **`XBrainLab/preprocessor/tests/test_preprocess.py`**
    *   **用途**: 測試各類具體預處理器 (Preprocessor)。
    *   **案例**:
        *   `test_channel_selection`: 測試頻道選擇功能，驗證頻道數減少與歷史記錄。
        *   `test_edit_event_name_raw`: 測試在 Raw 資料上編輯事件名稱 (應報錯)。
        *   `test_edit_event_name_epoch`: 測試在 Epoch 資料上編輯事件名稱 (含錯誤處理、成功更新、部分更新)。
        *   `test_edit_event_id_raw`: 測試在 Raw 資料上編輯事件 ID (應報錯)。
        *   `test_edit_event_id_epoch`: 測試在 Epoch 資料上編輯事件 ID (含錯誤處理、成功更新、合併 ID)。
        *   `test_export`: 測試資料匯出功能 (Raw/Epoch)，驗證 .mat 檔案內容 (x, y, history)。
        *   `test_filtering`: 測試濾波器設定與應用，驗證濾波範圍與歷史記錄。
        *   `test_resample`: 測試重採樣功能 (含事件時間點更新與 Epoch 重採樣)。
        *   `test_epoch_wrong_type`: 測試對 Epoch 資料進行切分 (應報錯)。
        *   `test_epoch_wrong_events`: 測試無事件標記時的切分 (應報錯)。
        *   `test_sliding_epoch_error`: 測試滑動視窗切分時的多事件錯誤。
        *   `test_time_epoch_no_epochs`: 測試依事件切分時無匹配事件。
        *   `test_time_epoch_without_baseline`: 測試依事件切分 (無基線校正)，驗證數據形狀與內容。
        *   `test_time_epoch_with_baseline`: 測試依事件切分 (含基線校正)，驗證數據形狀與內容。
        *   `test_window_epoch`: 測試滑動視窗切分，驗證數據形狀與內容。
        *   `test_normalization_z_score`: 測試 Z-Score 標準化，驗證 Mean=0, Std=1。
        *   `test_normalization_minmax`: 測試 Min-Max 標準化，驗證 Min=0, Max=1。

#### **E. 評估指標 (Evaluation)**
*   **`XBrainLab/evaluation/tests/test_metric.py`**
    *   **用途**: 驗證 `Metric` Enum 的定義與成員值。
    *   **案例**:
        *   `test_metric_enum_values`: 驗證 ACC, AUC, KAPPA 的字串值。
        *   `test_metric_enum_members`: 驗證 Enum 成員數量與存在性。

#### **F. 模型基類 (Model Base)**
*   **`XBrainLab/model_base/tests/test_model_base.py`**
    *   **用途**: 動態測試所有深度學習模型 (EEGNet, SCCNet 等) 的實例化與 Forward Pass。
    *   **案例**:
        *   `test_model_base`: 針對不同參數組合 (n_classes, channel, samples, sfreq) 測試所有模型的建構與推論是否正常。

#### **G. 視覺化 (Visualization)**
*   **`XBrainLab/visualization/tests/test_base.py`**
    *   **用途**: 測試 `Visualizer` 基類的功能。
    *   **案例**:
        *   `test_visualizer`: 測試 `Visualizer` 初始化、抽象方法錯誤處理與 Saliency Map 存取。
*   **`XBrainLab/visualization/tests/test_visualizer.py`**
    *   **用途**: 測試 Visualizer API 與圖表生成。
    *   **案例**:
        *   `test_map`: 測試 SaliencyMap 與 SaliencyTopoMap 的生成與維度檢查。
        *   `test_eval_plot`: 測試其他評估圖表 (如 Confusion Matrix) 的生成。

#### **H. 訓練流程 (Training)**
*   **`XBrainLab/training/tests/`**
    *   **用途**: 測試訓練核心邏輯與流程控制。
    *   **案例**:
        *   **`test_trainer.py`**:
            *   `test_trainer`: 測試初始化與中斷控制。
            *   `test_trainer_run`: 測試訓練迴圈 (互動/非互動模式)。
            *   `test_trainer_job`: 測試多個訓練計畫的執行順序。
            *   `test_trainer_get_plan`: 測試訓練計畫的檢索功能。
        *   **`test_training_plan.py`**:
            *   `test_training_plan_holder_check_data`: 測試初始化參數驗證。
            *   `test_training_plan_holder_get_loader`: 測試 DataLoader 建立與資料一致性。
            *   `test_training_plan_holder_get_eval_loader`: 測試評估 DataLoader 的建立。
            *   `test_training_plan_holder_get_eval_model`: 測試評估模型的獲取。
            *   `test_training_plan_holder_get_eval_pair_not_implemented`: 測試未實作評估模式的錯誤處理。
            *   `test_training_plan_holder_get_eval_model_by_lastest_model`: 測試使用最新模型進行評估。
            *   `test_training_plan_holder_set_interrupt`: 測試中斷旗標設定。
            *   `test_training_plan_holder_trivial_getter`: 測試簡單屬性存取方法。
            *   `test_training_plan_holder_one_epoch`: 測試單一 Epoch 訓練流程 (Forward/Backward/Update)。
            *   `test_training_plan_holder_train_one_repeat`: 測試單次重複實驗流程 (含 Checkpoint)。
            *   `test_training_plan_holder_train_one_repeat_status`: 測試單次重複實驗的狀態追蹤。
            *   `test_training_plan_holder_train_one_repeat_empty_training_data`: 測試空訓練資料的錯誤處理。
            *   `test_training_plan_holder_train_one_repeat_eval`: 測試單次重複實驗的評估流程。
            *   `test_training_plan_holder_train_one_repeat_already_finished`: 測試已完成訓練的處理。
            *   `test_training_plan_holder_train`: 測試完整訓練流程 (含狀態更新與評估)。
            *   `test_training_plan_holder_train_status`: 測試訓練狀態管理。
            *   `test_training_plan_holder_train_error`: 測試訓練錯誤處理。
            *   `test_test_model_metrics`: 測試模型評估指標 (ACC, AUC, Loss) 計算邏輯。
        *   **`test_training_plan_test_model.py`**:
            *   `test_to_holder`: 測試將測試資料轉換為 Holder 格式 (含 Shuffle 測試)。
            *   `test_to_holder_empty`: 測試空資料的轉換處理。
            *   `test_test_model`: 測試模型測試流程 (含損失計算)。
            *   `test_eval_model`: 測試模型評估流程 (含指標計算)。
        *   **`test_model_holder.py`**: 測試模型容器的建立、管理與檢索功能。
        *   **`test_option.py`**: 測試訓練參數設定與驗證邏輯。

#### **I. 核心控制 (Study)**
*   **`XBrainLab/tests/test_study.py`**
    *   **用途**: 測試 `Study` 類別作為系統控制中樞的功能，驗證各模組的整合與狀態管理。
    *   **案例**:
        *   `test_study_load_data`: 測試獲取 RawDataLoader。
        *   `test_study_set_loaded_data_list`: 測試設定載入資料與錯誤處理 (Force Update)。
        *   `test_study_set_preprocessed_data_list`: 測試設定預處理資料與 Epoch 生成邏輯。
        *   `test_study_get_datasets_generator`: 測試獲取 DatasetGenerator。
        *   `test_study_set_datasets`: 測試設定資料集與錯誤處理。
        *   `test_study_set_training_option`: 測試設定訓練參數。
        *   `test_study_set_model_holder`: 測試設定模型容器。
        *   `test_study_generate_plan`: 測試生成訓練計畫 (Trainer 初始化) 與參數檢查。
        *   `test_study_training`: 測試訓練啟動與停止。
        *   `test_study_export_output_csv`: 測試匯出推論結果。
        *   `test_study_set_channels`: 測試設定頻道資訊。
        *   `test_study_saliency_params`: 測試設定 Saliency Map 參數。

## 4. 測試撰寫規範

### 4.1 檔案命名
*   測試檔案應放置於 `tests/` 目錄下。
*   檔名必須以 `test_` 開頭，例如 `test_io_integration.py`。

### 4.2 測試類別與方法
*   測試類別建議以 `Test` 開頭。
*   測試方法必須以 `test_` 開頭。

### 4.3 範例：整合測試 (Integration Test)
針對需要讀取真實檔案或依賴多個模組的功能，請撰寫整合測試。

```python
import os
import pytest
from XBrainLab.load_data.raw_data_loader import load_gdf_file
from XBrainLab.load_data import Raw

# 使用專案提供的測試資料
TEST_DATA_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'test_data_small'))
GDF_FILE = os.path.join(TEST_DATA_DIR, 'A01T.gdf')

class TestIOIntegration:
    def test_load_gdf_file_success(self):
        """測試讀取正常的 GDF 檔案"""
        if not os.path.exists(GDF_FILE):
            pytest.skip("Test data not found")

        raw = load_gdf_file(GDF_FILE)
        
        # 驗證回傳型別
        assert isinstance(raw, Raw)
        # 驗證數據內容
        assert raw.get_nchan() > 0
```

### 4.4 範例：單元測試 (Unit Test)
針對獨立函式或類別，可以使用 Mock 來隔離依賴 (例如 Mock `mne` 或 `torch`)。

```python
def test_simple_function():
    assert 1 + 1 == 2
```

## 5. 測試覆蓋率

### 5.1 檢視測試覆蓋率
```bash
pytest --cov=XBrainLab --cov-report=html tests/ XBrainLab/
```

### 5.2 覆蓋率目標
*   **核心模組** (Load Data, Dataset, Training): 建議覆蓋率 > 80%
*   **輔助模組** (Utils, Preprocessor): 建議覆蓋率 > 70%
*   **UI 模組**: 建議覆蓋率 > 50%

## 6. 持續整合 (CI)
本專案應整合 GitHub Actions 或類似 CI 工具，在每次 Push 或 Pull Request 時自動執行測試，確保程式碼品質。
