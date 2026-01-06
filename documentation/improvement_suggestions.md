# 改進建議 (Improvement Suggestions)

此文件用於記錄專案架構與程式碼的改進建議。

## 1. 資料載入邏輯優化 (Data Loading Logic Optimization)
- **日期**: 2026-01-06
- **現狀**: 目前在 `XBrainLab/ui/dashboard_panel/dataset.py` 的 `_import_files` 方法中，UI 層負責判斷檔案副檔名（`.set`, `.gdf`, `.fif` 等），然後根據副檔名呼叫後端對應的載入函數（如 `load_set_file`, `load_gdf_file`）。
- **建議**: 將「根據副檔名選擇載入器」的邏輯下沉至後端。可以在 `XBrainLab/backend/load_data/raw_data_loader.py` 或新的工廠類別中提供一個統一的介面，例如 `load_raw_data(filepath)`。
- **優點**: 
    1. **降低耦合**: UI 不需要知道後端支援哪些具體的檔案格式，只需要傳遞檔案路徑。
    2. **易於維護**: 未來新增支援的格式時，只需修改後端程式碼，無需修改 UI 邏輯。

## 2. 標籤對齊機制增強 (Robust Label Alignment)
- **日期**: 2026-01-06
- **現狀**: `EventLoader` 依賴「標籤數量」與「原始事件數量」完全一致來進行對齊。
- **缺點**: 無法處理硬體雜訊產生的多餘 Trigger 或訊號遺失，容易導致資料錯位或對齊失敗。
- **建議**: 
    1. 增加「事件過濾」功能，允許在對齊前篩選原始 Event ID。
    2. 提供視覺化對齊介面，讓使用者手動確認或修正對齊結果。

## 3. 記憶體效率優化 (Memory Efficiency)
- **日期**: 2026-01-06
- **現狀**: `raw_data_loader.py` 中使用 `preload=True` 強制將資料完全載入記憶體。
- **缺點**: 處理大型資料集時容易導致記憶體溢出 (OOM)。
- **建議**: 支援 MNE 的 Lazy Loading 機制 (`preload=False`)，僅在必要時載入數據。

## 4. 錯誤處理分層 (Granular Error Handling)
- **日期**: 2026-01-06
- **現狀**: 後端載入器捕捉所有異常並回傳 `None`，UI 無法區分錯誤類型。
- **建議**: 後端應拋出具體異常 (如 `FileCorruptedError`, `UnsupportedFormatError`)，由 UI 捕捉並顯示對應的錯誤訊息給使用者。

## 5. 智慧型標籤對齊 (Smart Label Alignment)
- **日期**: 2026-01-06
- **目標**: 在不大幅修改 UI 的前提下，解決標籤數量不一致的問題。
- **設計思路**:
    1. **利用現有流程**: 目前 `import_label` 流程中已經包含了 `EventFilterDialog` (事件過濾對話框)。
    2. **自動偵測 (Auto-Detection)**: 在開啟過濾對話框前，系統先計算「目標標籤數量」(來自外部檔案) 與「原始事件分佈」(來自 EEG 檔案)。
    3. **子集和演算法 (Subset Sum)**: 系統嘗試尋找一組原始 Event ID，其出現次數總和等於目標標籤數量。
        - 例如：原始資料有 `ID:1 (100次)`, `ID:255 (2次)`。外部標籤有 100 個。系統自動推斷應只保留 `ID:1`。
    4. **預設選取 (Pre-selection)**: 將推斷出的 Event ID 作為 `EventFilterDialog` 的預設選取項目。
- **優點**: 使用者體驗大幅提升（自動選對），且保留了手動修正的彈性，完全不需要新增新的 UI 視窗。

## 6. 進階標籤對齊與格式支援 (Advanced Label Alignment & Format Support)
- **日期**: 2026-01-06
- **目標**: 突破僅能依賴「硬體 Trigger 數量」進行對齊的限制，支援更多元的標籤來源與複雜情境。
- **建議方案**:
    1. **支援時間戳記標籤 (Timestamp-based Import)**:
        - **現狀**: 目前 `label_loader` 只讀取標籤數值，丟棄了可能存在的時間資訊。
        - **改進**: 支援讀取 `(timestamp, label)` 格式的檔案（如 CSV, TSV）。
        - **邏輯**: 若標籤檔包含時間，則忽略 EEG 原始 Trigger，直接在指定時間點建立新事件。這對於「軟體打標」或「事後標註」的資料集非常重要。
    2. **序列對齊演算法 (Sequence Alignment Algorithms)**:
        - **現狀**: 若數量不符，目前只能「強制匯入」（從頭填入），一旦中間少了一個 Trigger，後續全部錯位。
        - **改進**: 引入 **最長公共子序列 (LCS)** 或 **動態時間校正 (DTW)** 演算法。
        - **邏輯**: 系統自動計算標籤序列與 Event ID 序列的最佳匹配路徑，能自動跳過中間多餘的雜訊 Trigger，或標記出中間遺失的標籤，而非單純的截斷或錯位。

## 7. 標籤對齊的最後一道防線：互動式視覺化修正 (Interactive Visual Correction)
- **日期**: 2026-01-06
- **目標**: 當所有自動化演算法（智慧過濾、LCS/DTW）都失敗或結果不確定時，提供使用者手動介入的終極手段。
- **設計思路**:
    1. **視覺化呈現**: 在時間軸上同時顯示「原始 EEG Trigger」與「匯入的標籤序列」。
    2. **互動操作**: 允許使用者透過拖拉 (Drag & Drop) 或點擊來手動「對齊」某個關鍵點（Anchor Point）。
        - 例如：使用者知道第 1 個標籤對應第 5 個 Trigger，手動連線後，系統重新計算後續的自動對齊。
    3. **即時預覽**: 修改對齊後，即時顯示對齊後的誤差（如時間差），讓使用者確認是否合理。
- **必要性**: 對於極度混亂或長時間中斷的資料，演算法很難達到 100% 正確，人工介入是必要的保險機制。

## 8. 訓練模組記憶體管理優化 (Training Module Memory Optimization)
- **日期**: 2026-01-06
- **現狀**: `backend/training/training_plan.py` 中的 `to_holder` 函數將整個資料集轉換為 Tensor 並一次性移動到 GPU (`.to(dev)`)。
- **缺點**: 
    - **GPU OOM**: 當資料集較大時，顯示卡記憶體會瞬間被塞滿，導致程式崩潰。
    - **擴充性差**: 無法訓練超過 GPU 記憶體大小的模型/資料。
- **建議**: 
    - 重構 `to_holder` 與 `DataLoader` 機制。
    - 資料應保留在 CPU (System RAM)。
    - 僅在 `train_one_epoch` 的迴圈內部，針對當前 **Batch** 執行 `.to(device)`。
    - 實作自定義的 `torch.utils.data.Dataset`，支援 Lazy Loading (配合前面的資料載入優化)。

## 9. 訓練進度回報機制 (Real-time Training Progress)
- **日期**: 2026-01-06
- **現狀**: 訓練跑在背景執行緒，但缺乏主動回報進度 (Signals) 的機制。UI 可能依賴輪詢 (Polling) 或無法即時更新 Loss/Accuracy 曲線。
- **建議**: 
    - 在 `Trainer` 或 `TrainingPlanHolder` 中引入 Callback 機制或 PyQt Signal (需注意執行緒安全)。
    - 每個 Epoch 結束時主動發送 `(epoch, train_loss, val_loss)` 事件給 UI。

## 10. 預處理模組解耦 (Preprocessing Decoupling)
- **日期**: 2026-01-06
- **現狀**: UI 類別 (如 `ResampleDialog`) 直接實例化後端類別 (`Preprocessor.Resample`)。
- **缺點**: UI 與後端強耦合，後端修改建構子會導致 UI 崩潰。
- **建議**: 
    - 引入 `PreprocessorFactory` 或類似的中介層。
    - UI 只負責收集參數 (Config)，將參數傳遞給後端執行，不直接持有後端物件。

## 14. 預處理模組的潛在風險 (Preprocessing Module Risks)
- **日期**: 2026-01-06
- **現狀**: 
    1. **記憶體暴衝 (Memory Spike)**: 所有預處理器 (如 `Resample`, `ICA`) 在初始化 (`__init__`) 時都會執行 `deepcopy(data_list)`。這意味著僅僅**開啟**預處理對話框，系統就會嘗試複製整個資料集，極易導致記憶體溢出 (OOM)。
    2. **ICA 自動化過度**: `ICA` 預處理器目前嘗試自動偵測並移除 EOG 成分。這在沒有視覺化確認的情況下非常危險，可能誤刪神經訊號。
    3. **Resample 事件對齊風險**: `Resample` 類別手動計算重取樣後的事件時間點 (`new_events = events * ratio`)。這容易產生捨入誤差，建議改用 MNE 原生的 `raw.resample(events=events)` 功能。
    4. **UI 凍結**: 所有預處理操作都在主執行緒中同步執行，處理大檔案時會導致介面完全卡死。
- **建議**: 
    - **移除 Deepcopy**: 預處理器不應在初始化時複製資料。應改為在執行階段 (`apply`) 才決定是否複製或原地修改 (In-place)。
    - **ICA 流程重構**: 改為「計算權重 -> 視覺化選擇成分 -> 應用」的三階段流程。
    - **Resample 重構**: 使用 MNE 原生事件處理。
    - **非同步執行**:     - 預處理操作應移至 `QThread` 或 `Worker` 中執行，並回報進度。

## 15. 訓練模組的深度缺陷分析 (Deep Dive into Training Module Defects)
- **日期**: 2026-01-06
- **現狀**: 經由詳細代碼審查，發現訓練模組存在多個致命的設計缺陷，不僅限於 GPU 記憶體問題。
    1. **RAM 記憶體洩漏 (RAM Leak)**: `TrainRecord` 類別在每次發現更好的模型 (Best Val Loss/Acc/AUC, Best Test Loss/Acc/AUC) 時，都會執行 `deepcopy(model.state_dict())`。這意味著每個 Repeat 至少會在記憶體中保留 6 份模型權重副本。若模型較大或 Repeat 次數多，系統 RAM 會迅速耗盡。
    2. **Saliency Map 計算災難**: `_eval_model` 函數在訓練結束後，會針對**所有**測試資料計算 Saliency Map (包含 SmoothGrad, VarGrad 等)。這些梯度與 Map 全部被儲存在 List 中並保留在記憶體。這是一個極度耗時且耗記憶體的過程，且目前無法關閉。
    3. **磁碟空間爆炸**: `export_checkpoint` 在每個 Checkpoint Epoch 都會儲存所有 "Best Models" 以及當前 Epoch 模型。若 Checkpoint 頻率設得較高，會產生大量重複的模型檔案，迅速佔滿硬碟。
    4. **AUC 計算效能低落**: 每個 Epoch 結束時，系統會在 CPU 上使用 `sklearn.metrics.roc_auc_score` 計算 AUC。這需要將 GPU 上的預測結果搬移回 CPU 並累積。對於大型資料集，這會顯著拖慢訓練速度。
- **建議**: 
    - **優化模型儲存**: 僅保留一份「當前最佳」的 State Dict，或將非必要的模型即時寫入磁碟並釋放記憶體。
    - **Saliency Map 按需計算**: 移除訓練流程中自動計算 Saliency Map 的邏輯。改為在 UI 上提供「分析模型」按鈕，讓使用者針對特定樣本進行視覺化分析。
    - **Checkpoint 策略優化**: 僅保留最近 N 個 Checkpoint，或僅儲存最佳模型。
    - **串流式指標計算**: 改用 `torchmetrics` 等支援 GPU 加速與串流計算 (Streaming Calculation) 的套件來計算 AUC，避免大量資料搬移。
