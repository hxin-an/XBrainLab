# Agent Tool Definitions (工具定義文檔)

本文檔定義了 XBrainLab Agent 可使用的所有工具 (Tools)。
這些工具是 Agent 與後端邏輯 (`Study`) 互動的唯一介面。

## 1. Dataset Tools workfows(數據集管理) 
## 文本 ＋ 工具

### `list_files`
*   **功能描述**: 列出指定目錄下的所有檔案名稱。Agent 應先使用此工具來探索資料夾結構，並自行判斷哪些是數據檔、哪些是標籤檔，以及它們的對應關係。
*   **Python 對應**: `XBrainLab.llm.tools.dataset_tools.ListFilesTool`
*   **參數**:
    *   `directory` (字串, 必填): 目錄的絕對路徑。
    *   `pattern` (字串, 選填): 篩選模式 (例如 "*.gdf", "*.mat")。

## meta data
*    **功能描述** ： 使用者可能在 folder 裡面放 metadata ，他跟我說 metadata 在哪裡
*    **Python 對應**： `XBrainLab.llm.tools.dataset_tools.MetaDataTool`
*    **參數**:
    *   `metadata_path` (字串, 必填): metadata 的絕對路徑。

### `load_data`
*   **功能描述**: 載入原始 EEG/GDF 數據檔案到 Study 中。
*   **Python 對應**: `XBrainLab.llm.tools.dataset_tools.LoadDataTool`
*   **後端方法**: `study.load_raw_data_list(file_path_list)`
*   **參數**:
    *   `file_paths` (字串陣列, 必填): 數據檔案的絕對路徑列表。

### `attach_labels`
*   **功能描述**: 將標籤檔案關聯到已載入的數據檔案。
*   **Python 對應**: `XBrainLab.llm.tools.dataset_tools.AttachLabelsTool`
*   **設計思路**: 由 Agent 事先透過 `list_files` 分析檔名，決定哪個數據檔對應哪個標籤檔，再呼叫此工具進行綁定。
*   **參數**:
    *   `mapping` (字典, 必填): 數據檔案名稱(Filename)與標籤檔案路徑(Filepath)的對應表。
        *   格式範例：`{"A01T.gdf": "/data/label/A01T.mat", "subject_2.set": "/data/label/S2_events.csv"}`
    *   `label_format` (字串, 選填): 指定標籤格式，通常可自動偵測。

### `clear_dataset`
*   **功能描述**: 清除所有已載入的數據並重置 Study 狀態。若需要重新開始或因狀態鎖定導致載入失敗時使用。
*   **Python 對應**: `XBrainLab.llm.tools.dataset_tools.ClearDatasetTool`
*   **後端方法**: `study.clean_raw_data(force_update=True)`
*   **參數**: 無

### `get_dataset_info`
*   **功能描述**: 獲取當前已載入數據集的摘要資訊（檔案列表、採樣率、通道數、事件表、是否已載入標籤）。
*   **Python 對應**: `XBrainLab.llm.tools.dataset_tools.GetDatasetInfoTool`
*   **後端方法**: 檢視 `study.loaded_data_list` 的屬性。
*   **參數**: 無

---

## 2. Preprocessing Tools (預處理 - 訊號處理)

### `apply_standard_preprocess`
*   **功能描述**: 應用標準的 EEG 預處理流程，包含帶通濾波、陷波濾波 (去除電源線雜訊)、重參考 (Re-referencing) 以及正規化。這是一個「懶人包」工具，適合快速建立 Baseline。
*   **Python 對應**: `XBrainLab.llm.tools.preprocess_tools.StandardPreprocessTool`
*   **參數**:
    *   `l_freq` (數值, 選填): 帶通濾波低頻截止 (預設 4)。
    *   `h_freq` (數值, 選填): 帶通濾波高頻截止 (預設 40)。
    *   `notch_freq` (數值, 選填): 電源線雜訊頻率 (預設 50 或 60，視情況而定)。
    *   `rereference` (字串, 選填): 重參考方法，如 "average" (CAR) 或特定通道。若不填則不執行。
    *   `resample_rate` (整數, 選填): 重採樣頻率。若不填則不執行。
    *   `normalize_method` (字串, 選填): 正規化方法 ("z-score" 或 "min-max")。

### `apply_bandpass_filter`
*   **功能描述**: 對 EEG 數據應用帶通濾波器 (Bandpass Filter)。
*   **Python 對應**: `XBrainLab.llm.tools.preprocess_tools.BandPassFilterTool`
*   **後端方法**: `study.add_preprocess_step(BandPassFilter(low, high))`
*   **參數**:
    *   `low_freq` (數值, 必填): 低頻截止頻率 (Hz)。
    *   `high_freq` (數值, 必填): 高頻截止頻率 (Hz)。

### `apply_notch_filter`
*   **功能描述**: 應用凹口濾波器 (Notch Filter)，通常用於去除電源線雜訊。
*   **Python 對應**: `XBrainLab.llm.tools.preprocess_tools.NotchFilterTool`
*   **後端方法**: `study.add_preprocess_step(NotchFilter(freq))`
*   **參數**:
    *   `freq` (數值, 必填): 要去除的中心頻率 (例如 50 或 60)。

### `resample_data`
*   **功能描述**: 將數據重採樣到新的採樣率。
*   **Python 對應**: `XBrainLab.llm.tools.preprocess_tools.ResampleTool`
*   **後端方法**: `study.add_preprocess_step(Resample(rate))`
*   **參數**:
    *   `rate` (整數, 必填): 新的採樣率 (Hz)。

### `normalize_data`
*   **功能描述**: 對數據進行正規化。
*   **Python 對應**: `XBrainLab.llm.tools.preprocess_tools.NormalizeTool`
*   **後端方法**: `study.add_preprocess_step(Normalize(method))`
*   **參數**:
    *   `method` (字串, 必填): 選擇 `"z-score"` 或 `"min-max"`。

### `set_reference`
*   **功能描述**: 對訊號進行重參考 (例如 CAR - Common Average Reference)，加上可 channel 
*   **Python 對應**: `XBrainLab.llm.tools.preprocess_tools.RereferenceTool`
*   **參數**:
    *   `method` (字串): "average" 或特定的通道名稱。

### `select_channels`
*   **功能描述**: 選擇特定通道並保留（例如只使用 'C3', 'C4', 'Cz'）。
*   **Python 對應**: `XBrainLab.llm.tools.preprocess_tools.ChannelSelectionTool`
*   **參數**:
    *   `channels` (字串陣列): 要保留的通道名稱列表。

---

## 2.1 Epoching Tools (預處理 - 切段)
### `epoch_data`
*   **功能描述**: 根據事件標記將連續的 EEG 數據切分為片段 (Epochs)。
*   **Python 對應**: `XBrainLab.llm.tools.preprocess_tools.EpochDataTool`
*   **參數**:
    *   `t_min` (浮點數): 相對於事件的開始時間 (例如 -0.1)。
    *   `t_max` (浮點數): 相對於事件的結束時間 (例如 1.0)。
    *   `event_id` (lists, 選填): 指定要用於切段的事件 ID 或名稱。
        *   若不填，通常會使用所有找到的事件。
        *   格式範例：`{"Left Hand": 769, "Right Hand": 770}` 或 直接傳入事件代碼列表。
    *   `baseline` (浮點數陣列, 選填): 基線校正區間，例如 [-0.1, 0]。


---

## 3. Training & Model Tools (訓練與模型)

### `set_model`
*   **功能描述**: 選擇要使用的深度學習模型架構。
*   **Python 對應**: `XBrainLab.llm.tools.training_tools.SetModelTool`
*   **後端方法**: `study.set_model_holder(ModelHolder(model_name))`
*   **參數**:
    *   `model_name` (字串, 必填): 模型名稱 (例如 `"EEGNet"`, `"ShallowConvNet"`, `"DeepConvNet"`)。

### `configure_training`
*   **功能描述**: 設定訓練超參數。
*   **Python 對應**: `XBrainLab.llm.tools.training_tools.ConfigureTrainingTool`
*   **後端方法**: `study.set_training_option(TrainingOption(...))`
*   **參數**:
    *   `epoch` (整數, 必填): 訓練輪數。
    *   `batch_size` (整數, 必填): 批次大小。
    *   `learning_rate` (數值, 必填): 學習率。
    *   `repeat` (整數, 選填): 實驗重複次數 (預設 1)。
    *   `device` (字串, 選填): `"cpu"` 或 `"cuda"`。預設為自動偵測。

### `start_training`
*   **功能描述**: 根據配置好的數據與模型開始訓練流程。
*   **Python 對應**: `XBrainLab.llm.tools.training_tools.StartTrainingTool`
*   **後端方法**: `study.start_training()`
*   **參數**: 無
    *   *注意：這可能是一個長時間運行的過程。*

---

## 4. Dataset Configuration (數據集劃分策略)

### `generate_dataset`
*   **功能描述**: 從已切段的 epochs 生成訓練數據集。定義如何劃分數據 (訓練/測試) 以及是否進行個體或群體訓練。
*   **Python 對應**: `XBrainLab.llm.tools.dataset_tools.GenerateDatasetTool`
*   **參數**:
    *   `test_ratio` (浮點數): 用於測試的數據比例 (例如 0.2)。
    *   `val_ratio` (浮點數): 訓練數據中用於驗證的比例 (例如 0.2)。
    *   `split_strategy` (字串): 劃分策略，["trial", "session", "subject"] 擇一。
    *   `training_mode` (字串): "individual" (每位受試者訓練一個模型) 或 "group" (全體受試者訓練一個模型)。

---

## 5. Visualization Tools (分析與視覺化)

### `plot_training_curve`
*   **功能描述**: 繪製訓練過程的曲線圖 (Loss, Accuracy, AUC)。
*   **Python 對應**: `XBrainLab.llm.tools.visualization_tools.PlotTrainingCurveTool`
*   **參數**:
    *   `metric` (字串, 必填): 要繪製的指標，選擇 ["loss", "accuracy", "auc"] 之一。

### `plot_confusion_matrix`
*   **功能描述**: 繪製分類結果的混淆矩陣 (Confusion Matrix)。
*   **Python 對應**: `XBrainLab.llm.tools.visualization_tools.PlotConfusionMatrixTool`
*   **參數**: 無

### `plot_feature_map`
*   **功能描述**: 繪製特徵重要性分析圖 (Saliency Map)。這通常用於解釋深度學習模型關注的特徵。
*   **Python 對應**: `XBrainLab.llm.tools.visualization_tools.PlotFeatureMapTool`
*   **參數**:
    *   `map_type` (字串, 必填): 選擇 `"heatmap"` (時間-通道熱力圖) 或 `"topomap"` (大腦拓樸圖)。
    *   `method` (字串, 選填): 計算梯度的方法，例如 `"Gradient"`, `"SmoothGrad"` 等。預設為 `"Gradient"`。
    *   `absolute` (布林值, 選填): 是否取絕對值 (只看重要性強度，不看正負)。預設為 True。

---

## Tool Call 工作流範例 (Example)

**使用者**: "請載入 BCIC IV 2a 數據集的 A01T 到 A03T（資料夾 /data/bcic/），對應標籤在 label 資料夾。請用濾波 4-40Hz，訓練 EEGNet。"

**Agent 推理與 Tool Call 序列**:

1.  **Exploration**: 
    - Call `list_files(directory="/data/bcic/", pattern="*.gdf")` -> 獲得 `['A01T.gdf', 'A02T.gdf', 'A03T.gdf']`
    - Call `list_files(directory="/data/bcic/label", pattern="*.mat")` -> 獲得 `['A01T.mat', 'A02T.mat', 'A03T.mat']`
2.  **Logic**: Agent 分析發現檔名一致 ("A01T" 對應 "A01T")。
3.  **Data Loading**:
    - Call `load_data(file_paths=["/data/bcic/A01T.gdf", ...])`
4.  **Label Attachment**:
    - Call `attach_labels(mapping={"A01T.gdf": "/data/bcic/label/A01T.mat", ...})`
5.  **Preprocessing**: Call `apply_bandpass_filter(low_freq=4, high_freq=40)`
6.  **Model**: Call `set_model(model_name="EEGNet")`
7.  **Training**: Call `configure_training(...)` -> `generate_dataset(...)` -> `start_training()`

