# XBrainLab 測試筆記 (Testing Notes)

這份文件用於記錄在探索程式碼與撰寫測試過程中的發現、測試計畫以及待辦事項。

## 1. 測試策略
*   **目標**: 透過撰寫測試來理解與驗證 XBrainLab 的核心邏輯。
*   **工具**: `pytest`
*   **流程**: 分析模組 -> 規劃測試案例 -> 撰寫測試 -> 記錄發現/Bug。

## 2. 模組測試記錄

### 2.1 Load Data (資料讀取)
*   **目標檔案**: `XBrainLab/load_data/`
*   **狀態**: [已完成] (已完成重構與測試：`raw_data_loader`, `label_loader`, `event_loader`)
*   **關鍵邏輯**:
    *   `raw_data_loader.py`: 統一處理 .set 與 .gdf 檔案讀取。
        *   依賴 `mne` 庫進行底層 I/O。
        *   `.set` 讀取有自動 fallback 機制 (Raw -> Epochs)。
    *   `Raw` 物件的結構與屬性。
        *   包裝 `mne` 物件。
        *   獨立維護 `raw_events` 以支援外部標籤匯入。
    *   `data_loader.py` (`RawDataLoader`):
        *   `Raw` 物件的容器 (List subclass)。
        *   負責檢查多個檔案間的一致性 (通道數、取樣率)。
    *   `label_loader.py` :
        *   專責處理標籤檔案 I/O (.txt, .mat)。
        *   統一回傳 1D numpy array，處理了各種 mat 檔的維度問題。
    *   `event_loader.py` (`EventLoader`):
        *   專注於邏輯轉換：將 Label List + Raw -> MNE Events。
        *   已移除冗餘的讀檔方法 (`read_txt`, `read_mat`)，遵循單一職責原則。
*   **觀察與潛在問題 (Observations)**:
    *   **記憶體用量**: Loader 使用 `preload=True`，會將所有數據載入記憶體，處理大檔案時可能有 OOM 風險。
    *   **錯誤處理**: 讀取失敗僅回傳 `None`，呼叫端需自行檢查。
    *   **編碼限制**: `.set` 讀取強制使用 `uint16_codec='latin1'`，可能不支援特殊編碼檔案。
    *   **格式支援**: 目前僅支援 `.gdf` 與 `.set`，缺乏對其他常見格式 (如 .edf, .bdf, .fif) 的支援。
*   **測試執行說明**:
    *   **指令**: `python -m pytest tests/test_io_integration.py`
    *   **測試內容**:
        1.  **正常讀取**: 嘗試讀取 `test_data_small/A01T.gdf`。
        2.  **異常處理**: 嘗試讀取不存在的檔案與錯誤格式的檔案。
    *   **判定標準**:
        *   正常讀取案例需回傳 `Raw` 物件，且通道數 > 0，資料形狀正確。
        *   異常案例需回傳 `None` 且不拋出未處理的例外 (Exception)。
    *   **Metadata 整合測試**:
        *   **指令**: `pytest tests/test_metadata_integration.py`
        *   **測試內容**:
            1.  **完整流程模擬**: 讀取 GDF -> 解析檔名 (Subject/Session) -> 匯入標籤 -> 轉換事件 -> 更新 Raw。
        *   **判定標準**:
            *   `Raw` 物件的 Subject/Session 屬性需正確更新。
            *   `Raw` 物件需包含正確數量的 Events，且 Event ID 與 Mapping 一致。


### 2.2 Dataset (資料集管理)
*   **目標檔案**: `XBrainLab/dataset/`
*   **狀態**: [已完成] (全數 1644 個測試通過)
*   **關鍵邏輯**:
    *   `Epochs`: 管理已分段的 EEG 數據，包含複雜的篩選邏輯 (`pick_subject`, `pick_session`, `pick_trial`, `pick_manual`)。
    *   `DatasetGenerator`: 核心生成器，負責根據配置 (`DataSplittingConfig`) 生成訓練用的 `Dataset` 物件。
        *   支援 `TrainingType.IND` (個別受試者) 與 `TrainingType.FULL` (全體受試者) 模式。
        *   處理 Cross-Validation 的數據切分與剩餘數據管理。
    *   `Dataset`: 代表一個具體的數據集實例，包含訓練、驗證、測試數據的索引，並擁有全域唯一的 ID (`Dataset.SEQ`)。
*   **修復與調整記錄**:
    *   **依賴移除**: 因應環境問題，將所有測試中的 `pytest-mock` (`mocker` fixture) 替換為標準庫 `unittest.mock.patch`。
    *   **測試還原**: 找回並修復了多個被意外刪除或註解的測試函式，包括 `test_epochs_pick_manual` 以及 `DatasetGenerator` 的多個邊界條件測試。
    *   **邏輯修正**: 修正了 `test_dataset_generator.py` 中輔助函式定義順序導致的 `NameError`。
    *   **驗證**: 透過詳細的除錯輸出確認了 `DatasetGenerator` 在 Cross-Validation 模式下數據切分的正確性。
*   **測試執行說明**:
    *   **指令**: `python -m pytest XBrainLab/dataset/tests/`
    *   **覆蓋範圍**: 涵蓋 `Epochs` 的篩選邏輯、`Dataset` 的屬性存取、以及 `DatasetGenerator` 的各種生成策略。

### 2.3 Preprocessor (預處理)
*   **目標檔案**: `XBrainLab/preprocessor/`
*   **狀態**: [已完成]
*   **關鍵邏輯**:
    *   濾波 (Filtering)、重採樣 (Resampling)。
    *   標準化 (Normalization): 實作了 Z-Score 與 Min-Max 標準化。
*   **測試執行說明**:
    *   **指令**: `python -m pytest XBrainLab/preprocessor/tests/`
    *   **覆蓋範圍**: 涵蓋 `ChannelSelection`, `EditEventName`, `Export`, `Filtering`, `Resample`, `TimeEpoch`, `WindowEpoch` 以及 `Normalize` (Z-Score, Min-Max) 的邏輯。

### 2.4 Evaluation (評估指標)
*   **目標檔案**: `XBrainLab/evaluation/`
*   **狀態**: [已完成]
*   **關鍵邏輯**:
    *   `Metric` Enum 定義。
*   **測試執行說明**:
    *   **指令**: `python -m pytest XBrainLab/evaluation/tests/`
    *   **覆蓋範圍**: 驗證 `Metric` Enum 的成員與值。

### 2.5 Model Base (模型基類)
*   **目標檔案**: `XBrainLab/model_base/`
*   **狀態**: [已完成]
*   **關鍵邏輯**:
    *   定義了 `EEGNet`, `SCCNet`, `ShallowConvNet` 等深度學習模型架構。
*   **測試執行說明**:
    *   **指令**: `python -m pytest XBrainLab/model_base/tests/`
    *   **覆蓋範圍**: 動態測試所有定義的模型，驗證其在不同參數 (n_classes, channel, samples, sfreq) 下的實例化與前向傳播 (Forward Pass) 是否正常。

### 2.6 Visualization (視覺化)
*   **目標檔案**: `XBrainLab/visualization/`
*   **狀態**: [已完成]
*   **關鍵邏輯**:
    *   `Visualizer` 基類與各種視覺化方法 (Saliency Map, Confusion Matrix 等)。
*   **測試執行說明**:
    *   **指令**: `python -m pytest XBrainLab/visualization/tests/`
    *   **覆蓋範圍**: 驗證 `Visualizer` 的 API 呼叫，確保能正確生成 Matplotlib 圖表物件。

### 2.7 Training (訓練流程)
*   **目標檔案**: `XBrainLab/training/`
*   **狀態**: [已完成]
*   **關鍵邏輯**:
    *   `Trainer`: 訓練流程控制。
    *   `TrainingPlanHolder`: 管理單一訓練計畫 (Model + Dataset + Option)。
    *   `EvalRecord` & `TrainRecord`: 記錄訓練與評估結果。
*   **測試執行說明**:
    *   **指令**: `python -m pytest XBrainLab/training/tests/`
    *   **覆蓋範圍**: 涵蓋訓練迴圈、模型評估 (`_test_model`, `_eval_model`)、記錄保存與匯出。已全面替換 `pytest-mock` 為 `unittest.mock`。

### 2.8 Integration Tests (整合測試)
*   **目標檔案**: `tests/test_pipeline_integration.py`
*   **狀態**: [已完成]
*   **關鍵邏輯**:
    *   模擬完整的後端執行流程：Load Data -> Preprocess -> Dataset -> Training -> Evaluation。
*   **測試執行說明**:
    *   **指令**: `python -m pytest tests/test_pipeline_integration.py`
    *   **測試內容**:
        1.  使用 `unittest.mock` 模擬 `Dataset` 與 `DataLoader`，避免真實檔案 I/O。
        2.  初始化 `ModelHolder` (EEGNet) 與 `TrainingOption`。
        3.  建立 `TrainingPlanHolder` 並執行 `Trainer.job()`。
        4.  驗證訓練過程是否產生 `TrainRecord` 與 `EvalRecord`，並檢查關鍵指標 (Loss, Accuracy, AUC) 是否存在。
    *   **注意事項**: 測試中 Patch 了 `validate_type` 以允許 Mock 物件通過型別檢查。

*   **目標檔案**: `tests/test_real_data_pipeline.py`
*   **狀態**: [已完成]
*   **關鍵邏輯**:
    *   使用真實的 GDF 資料 (`test_data_small/A01T.gdf`) 驗證端對端流程。
*   **測試執行說明**:
    *   **指令**: `python -m pytest tests/test_real_data_pipeline.py`
    *   **測試內容**:
        1.  **資料載入**: 讀取真實 GDF 檔案。
        2.  **預處理**: 執行 Filtering (4-38Hz), Normalize (Z-Score), TimeEpoch (0-4s)。
        3.  **資料集生成**: 使用 `DatasetGenerator` 進行 Individual 模式切分 (20% Val, 20% Test)。
        4.  **模型訓練**: 使用 `EEGNet` 執行 1 個 Epoch 的訓練。
    *   **特殊處理**:
        *   **事件去重**: 測試腳本中手動去除了時間點重複的事件，避免 MNE 報錯。
        *   **Mocking**: Patch 了 `Raw.get_raw_event_list` 以使用去重後的事件；Patch 了檔案寫入操作 (`torch.save`, `plt.savefig` 等) 以避免產生垃圾檔案。

## 3. 待修復問題 (Bugs & Issues)
*   (在此記錄發現的 Bug)

## 4. 架構與實作筆記 (待更新至 Developer Guide)
*   (在此記錄值得補充到開發者指南的細節)
