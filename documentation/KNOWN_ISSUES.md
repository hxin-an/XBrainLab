# 已知問題 (Known Issues)

本文件記錄目前專案中已知的 Bug、限制與待解決的問題。

## 🔴 高優先級 (High Priority)

### 資源管理 (Resource Management)
- [ ] **Training VRAM Leak (嚴重)**：
    - **問題描述**：在 `XBrainLab/backend/training/training_plan.py` 的 `train_one_epoch` 中，`y_true` 和 `y_pred` 變數在迴圈中不斷進行 `torch.cat` 串接，且這些 Tensor 位於 GPU 上 (若使用 GPU 訓練)。
    - **技術分析**：這會導致隨著 Batch 增加，GPU 記憶體佔用線性成長，對於大型 Dataset 極易導致 OOM (Out of Memory)。
    - **建議解法**：
        1. 在串接前使用 `.detach().cpu()` 將 Tensor 移至 CPU。
        2. 每個 Epoch 結束後呼叫 `torch.cuda.empty_cache()`。

- [ ] **Dataset RAM Usage (記憶體倍增)**：
    - **問題描述**：`Dataset.get_training_data` (及 val/test) 使用 Numpy Boolean Masking (`X = self.epoch_data.get_data()[self.train_mask]`) 來獲取資料。
    - **技術分析**：Numpy 的 Masking 操作會產生全新的 Array Copy。這意味著在訓練開始時，系統會將所有 EEG 數據在記憶體中複製一份 (甚至多份，若有多個 Dataset)。對於數 GB 的 EEG 數據，這極易導致 RAM 耗盡。
    - **建議解法**：改用 `torch.utils.data.Subset` 或自定義 `IndexDataset`，僅儲存索引 (Indices) 而非複製數據，在 `__getitem__` 時才從原始 `Epochs` 讀取。

### 架構 (Architecture) - 前後端耦合詳盡分析
本節列出經由全程式碼庫審計後發現的具體耦合違規，需在重構階段優先處理。

#### 1. Forward Coupling (UI 直接依賴 Backend 實作)
- **TrainingPanel (`XBrainLab/ui/training/panel.py`)**:
    - 直接呼叫 `self.study.get_datasets_generator` (應透過 Controller)。
    - 直接呼叫 `self.study.train` (阻塞 UI 執行緒)。
    - 直接存取 `self.study.training_plan_holder`。
- **EvaluationPanel (`XBrainLab/ui/evaluation/panel.py`)**:
    - 直接存取 `self.study.model_holder` 來獲取模型摘要。
    - 內部類別 `DummyRecord` 與 `ProxyRecord` 依賴 Backend 的 `EvalRecord`，導致 UI 與資料結構強耦合。
- **PreprocessPanel (`XBrainLab/ui/dashboard_panel/preprocess.py`)**:
    - 各 Dialog (如 `ResampleDialog`, `FilteringDialog`) 直接實例化 Backend 的 `Preprocessor` 類別 (如 `Preprocessor.Resample`)。
    - **嚴重性**：這意味著 UI 必須知道 Backend 的具體類別結構，若 Backend 重構 (如改為 Pipeline 模式)，UI 將全面崩潰。
- **VisualizationPanel (`XBrainLab/ui/visualization/panel.py`)**:
    - 直接呼叫 `self.study.get_averaged_record` (計算邏輯洩漏到 UI)。

#### 2. Reverse Coupling (Backend 依賴 UI)
- **RawDataLoader (`XBrainLab/backend/load_data/raw_data_loader.py`)**:
    - 雖然主要程式碼乾淨，但需檢查 `RawDataLoaderFactory` 是否在其他地方被 UI 引用時造成循環依賴。
    - 目前 Backend 核心邏輯似乎未直接 import `PyQt6`，這是好消息。

#### 3. Business Logic Leakage (業務邏輯洩漏至 UI)
- **VisualizationPanel**: `get_averaged_record` 包含大量數據平均計算邏輯，這屬於 Backend 的職責 (應移至 `ResultAggregator` 或類似 Service)。
- **EvaluationPanel**: `update_views` 中包含 Confusion Matrix 的計算準備邏輯。

### 穩定性與強健性 (Stability & Robustness)
- [ ] **Silent Failures (被吞掉的錯誤)**：
    - **問題**：在 `_test_model` (`training_plan.py`) 與 `AggregateInfoPanel.update_info` 中存在 `try...except: pass` 結構。
    - **影響**：當發生非預期錯誤 (如數據維度不符、屬性缺失) 時，程式不會報錯，而是靜默失敗 (如顯示 "-" 或 AUC 為 0)，導致除錯極其困難。
    - **建議解法**：至少應使用 `logger.warning()` 記錄錯誤堆疊，或明確指定要捕獲的 Exception 類型。

### 紅隊測試審計 (Red Team Audit) - 隱藏風險
- [ ] **Agent Unbounded Memory (記憶體洩漏/Context Overflow)**：
    - **問題**：`LLMController.history` 是一個無限增長的 List (`self.history.append(...)`)。
    - **影響**：
        1. **Context Window Overflow**：隨著對話進行，Token 數將迅速超過 LLM 上限，導致 API 報錯。
        2. **Memory Leak**：長時間運行下，歷史紀錄佔用記憶體。
    - **建議解法**：實作 `ContextManager`，設定最大 Token 數或對話輪數限制，並實作滑動視窗 (Sliding Window) 或摘要機制 (Summarization)。

- [ ] **Dependency Hell Risk (依賴衝突風險)**：
    - **問題**：雖然目前 `pyproject.toml` 看似乾淨，但 `requirements.txt` 中曾出現多個 CUDA 版本衝突。若使用者混用安裝方式，極易導致 PyTorch 無法使用 GPU。
    - **建議解法**：在 `pyproject.toml` 中明確鎖定 PyTorch 版本與 CUDA 版本的對應關係 (如使用 `extra-index-url`)，並在啟動時檢查 `torch.version.cuda`。

### 測試缺漏 (Testing Gaps)
- [ ] **Test File Fragmentation (測試檔案分散)**：
    - **問題**：測試檔案散落在 `XBrainLab/tests/` (集中式) 與各模組目錄下 (如 `XBrainLab/backend/evaluation/tests/`, `XBrainLab/ui/dashboard_panel/tests/`)。
    - **影響**：缺乏統一的測試入口與結構，導致 CI/CD 配置困難，且開發者難以找到對應的測試。
    - **建議解法**：將所有測試統一遷移至專案根目錄下的 `tests/` 資料夾，並按照源碼結構鏡像排列 (e.g., `tests/backend/`, `tests/ui/`)。

- [ ] **Insufficient UI Test Coverage (UI 測試覆蓋率不足)**：
    - **問題**：雖然有部分 UI 測試 (如 `test_dataset_panel.py`) 使用了 `pytest-qt`，但覆蓋率極低。核心複雜面板如 `TrainingPanel`、`VisualizationPanel` 缺乏互動測試。
    - **影響**：UI 重構或邏輯變更時極易引入 Regression Bug。
    - **建議解法**：
        1. 為所有 Panel 建立基礎的 `pytest-qt` 測試 (確保能 init 且無 crash)。
        2. 針對關鍵路徑 (如 "Start Training", "Import Data") 撰寫完整的 Integration Test。

### 1. Training Panel: Aggregate Information 跑版
- **問題描述**：讀取 Epoch 資料後，`AggregateInfoPanel` 的表格內容會跑版或被截斷。
- **技術分析**：`XBrainLab/ui/dashboard_panel/info.py` 中，`QTableWidget` 的高度是根據初始行數硬編碼的 (`total_height = len(keys) * 25 + 2`)。當內容長度改變（如從 Raw 轉為 Epoch，數值字串變長）或字型渲染差異時，`ResizeToContents` 可能導致寬度超出容器，或高度計算不準確導致捲軸出現/內容被切。
- **建議解法**：移除硬編碼高度，改用 `QVBoxLayout` 的自適應機制，或監聽 `itemChanged` 事件動態調整高度。

### 2. Training: Empty Validation Data Hang
- **問題描述**：若 `set_training` 時 Validation Data 為空，程式會卡住 (Hang)。
- **技術分析**：在 `XBrainLab/backend/training/training_plan.py` 中，`train_one_epoch` 會檢查 `if valLoader:`。若為空則跳過驗證。但 `train_record` 可能預期每回合都有驗證結果。若 `get_training_evaluation` 嘗試存取不存在的驗證紀錄，或 UI 端的 `TrainingPanel` 在等待驗證 loss 更新（而它永遠不會來），就可能導致邏輯死鎖或無限等待。
- **建議解法**：在 `DatasetGenerator` 階段強制檢查，若 Val 為空則發出警告；或在 `Trainer` 中處理無驗證資料的特殊狀態，確保 `train_record` 寫入 `NaN` 或佔位符以通知 UI。

### 3. Training: Validation Loss 異常上升
- **問題描述**：Validation Loss 隨訓練進行呈現異常上升趨勢。
- **技術分析**：`_test_model` 中的 Loss 計算邏輯 (`running_loss /= len(dataLoader)`) 是正確的平均值。異常上升通常是 **Overfitting (過擬合)** 的強烈訊號，或是訓練/驗證資料分佈不一致 (Data Mismatch)。
- **建議解法**：這可能不是程式 Bug，而是模型/數據問題。建議檢查：
    1. 是否使用了 Early Stopping？
    2. Dropout/BatchNorm 在 `model.eval()` 下的行為是否符合預期？
    3. 驗證資料集是否過小導致變異數過大？

### 4. UI: 鎖定機制 (Locking Mechanism) 不完善
- **問題描述**：介面鎖定功能有漏洞，部分元件未被正確鎖定或解鎖狀態錯誤。
- **技術分析**：目前鎖定邏輯可能分散在各 Panel 或 `MainWindow` 中，缺乏統一的 **State Manager**。若僅透過遍歷 Widget 呼叫 `setEnabled(False)`，很容易漏掉動態生成的元件，且難以正確還原「原本就該 disable」的元件狀態。
- **建議解法**：實作統一的 `InterfaceStateManager`，記錄鎖定前的狀態快照 (Snapshot)，並以白名單/黑名單方式管理可互動元件。

### 5. Visualization Panel: 圖片無法顯示
- **問題描述**：已選擇 Plan 和 Run，但圖片區域仍顯示 "Please select run"。
- **技術分析**：`VisualizationPanel.on_update` 依賴 `plan_combo` 和 `run_combo` 的文字內容。若 `refresh_combos` 觸發時機晚於 `on_update`，或 `Saliency3DPlotWidget.update_plot` 內部發生靜默錯誤 (Silent Failure) 且未拋出異常，UI 就不會更新。
- **建議解法**：
    1. 在 `update_plot` 中加入 `try-except` 並彈出錯誤視窗。
    2.檢查 `refresh_combos` 是否正確觸發了 `currentTextChanged` 信號。

### 6. Agent: Data Load API 失效與 Mock 需求
- **問題描述**：Agent 呼叫 Data Load API 有動作但無效果，且會阻塞 UI。
- **技術分析**：
    1. **阻塞**：`LLMController` 在主執行緒執行工具，導致 UI 凍結。
    2. **失效**：可能是後端 `Study.load_data` 執行失敗但錯誤被吞掉，或 UI 未接收到 `refresh_panels` 信號。
- **建議解法**：
    1. **Mocking**：優先實作 `MockDatasetTool` 等 Mock 工具，回傳假成功訊息，以驗證 Agent 邏輯。
    2. **Threading**：將工具執行移至 Worker Thread。
