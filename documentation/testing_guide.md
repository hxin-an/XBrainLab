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
        *   `test_load_mat_success`: 讀取 .mat 標籤。
        *   `test_load_unsupported_format`: 測試不支援格式。

*   **`XBrainLab/load_data/tests/test_raw.py`**
    *   **用途**: 測試 `Raw` 類別屬性與方法。
    *   **案例**: `test_add_preprocess`, `test_set_event`, `test_mne_raw_info`。

*   **`XBrainLab/load_data/tests/test_data_loader.py`**
    *   **用途**: 測試 `RawDataLoader` 容器的一致性檢查。
    *   **案例**: `test_validate` (檢查多檔案規格一致性)。

#### **B. 中繼資料與解析 (Metadata & Parsing)**
負責解析檔名、處理事件與標籤轉換。

*   **`XBrainLab/utils/tests/test_filename_parser.py`**
    *   **用途**: 測試檔名解析工具 (`FilenameParser`)。
    *   **案例**:
        *   `test_parse_by_split`: 分隔符號切割。
        *   `test_parse_by_regex`: 正規表示式提取。
        *   `test_parse_by_folder`: 資料夾結構推斷。
        *   `test_parse_by_fixed_position`: 固定位置提取。

*   **`XBrainLab/load_data/tests/test_event_loader.py`**
    *   **用途**: 測試 `EventLoader`。
    *   **案例**:
        *   `test_create_event`: 將 Label List 轉換為 MNE Event Array。

#### **C. 資料集管理 (Dataset)**
負責 Epochs 管理與資料集生成。

*   **`XBrainLab/dataset/tests/`**
    *   **用途**: 測試 Epochs 篩選與 DatasetGenerator 切分邏輯。
    *   **案例**:
        *   `test_epochs_pick_*`: 測試依 Subject, Session, Trial 篩選。
        *   `test_dataset_generator_*`: 測試 Cross-Validation 與個別/全體受試者模式。

#### **D. 預處理 (Preprocessor)**
負責訊號處理與標準化。

*   **`XBrainLab/preprocessor/tests/test_preprocess.py`**
    *   **用途**: 測試各類預處理器。
    *   **案例**:
        *   `test_normalization_*`: 測試 Z-Score 與 Min-Max 標準化。
        *   `test_filtering`, `test_resample`: 測試濾波與重採樣。

#### **E. 評估指標 (Evaluation)**
*   **`XBrainLab/evaluation/tests/test_metric.py`**
    *   **用途**: 驗證 Metric Enum 定義。

#### **F. 模型基類 (Model Base)**
*   **`XBrainLab/model_base/tests/test_model_base.py`**
    *   **用途**: 動態測試所有深度學習模型 (EEGNet, SCCNet 等) 的實例化與 Forward Pass。

#### **G. 視覺化 (Visualization)**
*   **`XBrainLab/visualization/tests/`**
    *   **用途**: 測試 Visualizer API 與圖表生成。

#### **H. 訓練流程 (Training)**
*   **`XBrainLab/training/tests/`**
    *   **用途**: 測試訓練核心邏輯。
    *   **案例**:
        *   `test_trainer.py`: 測試 Trainer 流程控制。
        *   `test_training_plan.py`: 測試 TrainingPlanHolder 與模型評估。
        *   `test_train.py`, `test_eval.py`: 測試 TrainRecord 與 EvalRecord。

## 4. 測試撰寫規範

### 3.1 檔案命名
*   測試檔案應放置於 `tests/` 目錄下。
*   檔名必須以 `test_` 開頭，例如 `test_io_integration.py`。

### 3.2 測試類別與方法
*   測試類別建議以 `Test` 開頭。
*   測試方法必須以 `test_` 開頭。

### 3.3 範例：整合測試 (Integration Test)
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

### 3.4 範例：單元測試 (Unit Test)
針對獨立函式或類別，可以使用 Mock 來隔離依賴 (例如 Mock `mne` 或 `torch`)。

```python
def test_simple_function():
    assert 1 + 1 == 2
```
