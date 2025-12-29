# XBrainLab 程式碼風格指南 (Coding Style Guide)

為了落實「程式碼層級文件 (Inline Documentation)」，所有開發者請遵循以下規範。

## 1. Docstrings 規範

我們採用 **Google Style** 的 Docstring 格式。所有 `public` 的類別、方法與函數都必須撰寫 Docstring。

### 1.1 函數 (Functions)
必須包含 `Args` (參數) 與 `Returns` (回傳值)。

**正確範例**:
```python
def epoch_data(raw_data, events, tmin=-0.2, tmax=0.8):
    """將連續訊號切分為片段 (Epochs)。

    根據提供的事件列表與時間視窗，將原始數據切分為多個 trials。

    Args:
        raw_data (mne.io.Raw): 原始 MNE 數據物件。
        events (np.ndarray): 事件陣列，形狀為 (n_events, 3)。
        tmin (float, optional): 切段開始時間 (相對於事件)，單位為秒。預設為 -0.2。
        tmax (float, optional): 切段結束時間 (相對於事件)，單位為秒。預設為 0.8。

    Returns:
        mne.Epochs: 切段後的 Epochs 物件。

    Raises:
        ValueError: 如果 events 為空或格式不正確。
    """
    pass
```

### 1.2 類別 (Classes)
必須在類別層級說明該類別的用途，並列出重要屬性 (`Attributes`)。

**正確範例**:
```python
class DatasetGenerator:
    """負責將 Epochs 數據分割為訓練集與測試集。

    Attributes:
        epochs (mne.Epochs): 來源 Epochs 數據。
        config (DataSplittingConfig): 分割設定參數。
    """
    def __init__(self, epochs, config):
        # ...
```

## 2. 命名慣例 (Naming Conventions)

*   **變數與函數**: `snake_case` (e.g., `load_data`, `train_model`)
*   **類別**: `CamelCase` (e.g., `RawDataLoader`, `TrainingPanel`)
*   **常數**: `UPPER_CASE` (e.g., `DEFAULT_SAMPLING_RATE`)
*   **私有成員**: 前綴底線 `_variable` (e.g., `_validate_input`)

## 3. 類型提示 (Type Hinting)
強烈建議使用 Python 的 Type Hints，這能幫助 IDE 進行自動補全並減少錯誤。

```python
from typing import List, Optional

def get_channel_names(self) -> List[str]:
    return self.ch_names
```
