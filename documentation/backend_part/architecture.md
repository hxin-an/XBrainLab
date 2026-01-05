# XBrainLab 系統架構與 API 文件 (System Architecture & API)

本文件詳細說明 XBrainLab 的系統設計、數據流向以及核心模組的 API 規格。

## 1. 數據流架構 (Data Flow Architecture)

本節描述腦波數據在系統中的流動與變形過程。

### 1.1 核心資料流 (Core Pipeline)

| 階段 | 資料物件 (Class) | 資料形狀 (Shape) | 關鍵操作 | 說明 |
| :--- | :--- | :--- | :--- | :--- |
| **1. 原始檔案** | `Raw` (MNE Raw) | `(n_channels, n_times)` | `load_data` | 從 .gdf/.set 讀取連續訊號。 |
| **2. 載入容器** | `RawDataLoader` | `List[Raw]` | `append()` | 管理多個受試者的 Raw 資料。 |
| **3. 預處理** | `Raw` (Modified) | `(n_channels, n_times)` | `Preprocessor.apply()` | 濾波、重採樣，資料形狀可能改變 (如降採樣)。 |
| **4. 切分 (Epoching)** | `Epochs` | `(n_epochs, n_channels, n_times)` | `TimeEpoch` / `WindowEpoch` | 根據事件將連續訊號切成片段。 |
| **5. 資料集生成** | `Dataset` (PyTorch) | `(n_samples, 1, n_channels, n_times)` | `DatasetGenerator.generate()` | 將 Epochs 轉換為 PyTorch Dataset，並增加 Channel 維度 (1)。 |
| **6. 批次載入** | `DataLoader` | `(batch_size, 1, n_channels, n_times)` | `DataLoader.__iter__()` | 訓練時的批次資料供應。 |



---

## 2. 核心模組 API (Core Modules API)

### 2.1 資料讀取模組 (XBrainLab/load_data)

#### `XBrainLab/load_data/raw.py`

##### `class Raw`
封裝 MNE 的 Raw 或 Epochs 物件，提供統一的介面來存取腦波數據與中繼資料。

*   **屬性 (Attributes)**:
    *   `filepath` (str): 檔案路徑。
    *   `mne_data` (mne.io.BaseRaw | mne.BaseEpochs): 內部的 MNE 資料物件。
    *   `preprocess_history` (list[str]): 預處理步驟記錄。
    *   `raw_events` (list[list[int]] | None): 原始事件列表。
    *   `raw_event_id` (dict[str, int] | None): 原始事件 ID 對照表。
    *   `subject` (str): 受試者名稱。
    *   `session` (str): 場次名稱。
    *   `labels_imported` (bool): 是否已匯入標籤。

*   **方法 (Methods)**:
    *   `__init__(self, filepath: str, mne_data: mne.io.BaseRaw | mne.BaseEpochs)`
        *   初始化 Raw 物件。
    *   `get_filepath(self) -> str`
        *   取得檔案路徑。
    *   `get_filename(self) -> str`
        *   取得檔案名稱 (不含路徑)。
    *   `get_subject_name(self) -> str`
        *   取得受試者名稱。
    *   `get_session_name(self) -> str`
        *   取得場次名稱。
    *   `set_subject_name(self, subject: str) -> None`
        *   設定受試者名稱。
    *   `set_session_name(self, session: str) -> None`
        *   設定場次名稱。
    *   `get_preprocess_history(self) -> list[str]`
        *   取得預處理歷史記錄。
    *   `add_preprocess(self, desc: str) -> None`
        *   新增一條預處理記錄。
    *   `parse_filename(self, regex: str) -> None`
        *   使用正則表達式解析檔名，並自動設定 Subject 與 Session。
    *   `set_labels_imported(self, imported: bool) -> None`
        *   設定標籤匯入狀態。
    *   `is_labels_imported(self) -> bool`
        *   取得標籤匯入狀態。
    *   `set_event(self, events: list[list[int]], event_id: dict[str, int]) -> None`
        *   手動設定事件列表與 ID 對照表。
    *   `set_mne(self, data: mne.io.BaseRaw | mne.BaseEpochs) -> None`
        *   替換內部的 MNE 物件。若新物件為 Epochs 且已有事件，會自動套用事件。
    *   `set_mne_and_wipe_events(self, data: mne.io.BaseRaw | mne.BaseEpochs) -> None`
        *   替換內部的 MNE 物件，並強制清除所有已載入的事件。
    *   `get_mne(self) -> mne.io.BaseRaw | mne.BaseEpochs`
        *   取得內部的 MNE 物件。
    *   `get_tmin(self) -> float`
        *   取得資料起始時間 (Raw 為 0.0)。
    *   `get_nchan(self) -> int`
        *   取得頻道數量。
    *   `get_sfreq(self) -> float`
        *   取得採樣頻率。
    *   `get_filter_range(self) -> tuple[float, float]`
        *   取得濾波範圍 (Highpass, Lowpass)。
    *   `get_epochs_length(self) -> int`
        *   取得 Epochs 數量 (Raw 為 1)。
    *   `get_epoch_duration(self) -> int`
        *   取得每個 Epoch 的樣本數長度。
    *   `is_raw(self) -> bool`
        *   判斷是否為連續訊號 (Raw)。
    *   `get_raw_event_list(self) -> tuple[list[list[int]], dict[str, int]]`
        *   直接從 MNE 物件 (STIM 通道或 Annotations) 讀取事件。
    *   `get_event_list(self) -> tuple[list[list[int]], dict[str, int]]`
        *   取得事件列表。若有手動設定的事件則優先回傳。
    *   `has_event(self) -> bool`
        *   判斷是否包含任何事件。
    *   `has_event_str(self) -> str`
        *   回傳 'yes' 或 'no' 表示是否有事件。
    *   `get_event_name_list_str(self) -> str`
        *   取得所有事件名稱的逗號分隔字串。
    *   `get_row_info(self) -> tuple[str, str, str, int, float, int, str]`
        *   取得用於 UI 顯示的摘要資訊 (檔名, Subject, Session, Channel, Sfreq, Epochs, HasEvent)。

#### `XBrainLab/load_data/data_loader.py`

##### `class RawDataLoader(list)`
繼承自 `list`，用於管理多個 `Raw` 物件的容器，通常對應於一個 Study。

*   **方法 (Methods)**:
    *   `__init__(self, raw_data_list: Optional[List[Raw]]=None)`
        *   初始化容器，可傳入初始的 Raw 列表。
    *   `get_loaded_raw(self, filepath: str) -> Raw`
        *   根據檔案路徑取得對應的 Raw 物件。
    *   `validate(self) -> None`
        *   檢查容器內所有 Raw 物件的一致性 (頻道數、採樣率、類型、Epoch 長度)。若為空或不一致則拋出 `ValueError`。
    *   `check_loaded_data_consistency(self, raw: Raw, idx: int = -1) -> None`
        *   檢查指定的 `raw` 物件是否與容器中索引為 `idx` 的物件一致。
    *   `append(self, raw: Raw) -> None`
        *   將 Raw 物件加入容器，加入前會自動執行一致性檢查。
    *   `apply(self, study: 'Study', force_update: bool = False) -> None`
        *   將此容器內的資料應用到指定的 `Study` 物件中。

#### `XBrainLab/load_data/event_loader.py`

##### `class EventLoader`
負責將外部標籤檔案 (如 .txt, .mat) 轉換為 MNE 相容的事件格式。

*   **屬性 (Attributes)**:
    *   `raw` (:class:`Raw`): 關聯的 Raw 資料物件。
    *   `label_list` (list[int] | None): 原始標籤列表。
    *   `events` (list[list[int]] | None): MNE 格式的事件陣列。
    *   `event_id` (dict[str, int] | None): 事件 ID 對照表。

*   **方法 (Methods)**:
    *   `__init__(self, raw: Raw)`
        *   初始化 EventLoader。
    *   `create_event(self, event_name_map: dict[int, str]) -> tuple`
        *   根據標籤列表與名稱對照表建立事件。
        *   **Args**: `event_name_map`: 標籤數值到事件名稱的對照表。
        *   **Returns**: `(events, event_id)`
    *   `apply(self) -> None`
        *   將建立好的事件應用到關聯的 Raw 物件中。

#### `XBrainLab/load_data/label_loader.py`

##### 模組函式
負責讀取標籤檔案。

*   **函式 (Functions)**:
    *   `load_label_file(filepath: str) -> np.ndarray`
        *   讀取標籤檔案 (.txt 或 .mat)。
        *   **Returns**: 1D array of labels.
    *   `_load_txt(path: str) -> np.ndarray`
        *   讀取文字檔標籤 (內部使用)。
    *   `_load_mat(path: str) -> np.ndarray`
        *   讀取 .mat 檔標籤 (內部使用)。

#### `XBrainLab/load_data/raw_data_loader.py`

##### 模組函式
負責讀取原始腦波檔案。

*   **函式 (Functions)**:
    *   `load_set_file(filepath: str) -> Raw | None`
        *   讀取 EEGLAB .set 檔案。
        *   **Returns**: `Raw` 物件或 `None`。
    *   `load_gdf_file(filepath: str) -> Raw | None`
        *   讀取 BIOSIG .gdf 檔案。
        *   **Returns**: `Raw` 物件或 `None`。

### 2.2 通用工具模組 (XBrainLab/utils)

#### `XBrainLab/utils/filename_parser.py`

##### `class FilenameParser`
提供多種策略來從檔案路徑中提取資訊 (如 Subject ID, Session ID)。

*   **靜態方法 (Static Methods)**:
    *   `parse_by_split(filename: str, separator: str, sub_idx: int, sess_idx: int) -> Tuple[str, str]`
        *   依照分隔符號切割檔名。
        *   **Returns**: `(subject, session)`
    *   `parse_by_regex(filename: str, pattern: str, sub_group: int, sess_group: int) -> Tuple[str, str]`
        *   使用一般正則表達式提取。
        *   **Returns**: `(subject, session)`
    *   `parse_by_folder(filepath: str) -> Tuple[str, str]`
        *   從資料夾結構推斷 (假設結構為 `.../Subject/Session/filename.gdf`)。
        *   **Returns**: `(subject, session)`
    *   `parse_by_fixed_position(filename: str, sub_start: int, sub_len: int, sess_start: int, sess_len: int) -> Tuple[str, str]`
        *   依照固定字元位置提取。
        *   **Returns**: `(subject, session)`
    *   `parse_by_named_regex(filename: str, pattern: str) -> Tuple[str, str]`
        *   使用具名群組正則表達式解析 (例如 `(?P<subject>...)`)。
        *   **Returns**: `(subject, session)`

#### `XBrainLab/utils/check.py`

##### 模組函式
提供執行期的型別檢查輔助函式。

*   **函式 (Functions)**:
    *   `_get_type_name(type_class: type) -> str`
        *   取得類別的完整名稱 (module.name)。
        *   **Returns**: `str`
    *   `validate_type(instance: object, type_class: type | tuple[type], message_name: str) -> None`
        *   驗證單一物件是否為指定型別。若不符則拋出 `TypeError`。
    *   `validate_list_type(instance_list: list, type_class: type | tuple[type], message_name: str) -> None`
        *   驗證列表中所有元素是否為指定型別。
    *   `validate_issubclass(class_name: type, type_class: type | tuple[type], message_name: str) -> None`
        *   驗證類別是否為指定型別的子類別。

#### `XBrainLab/utils/logger.py`

##### 模組函式
提供日誌記錄功能的設定與實例。

*   **函式 (Functions)**:
    *   `setup_logger(name: str = "XBrainLab", log_file: str = "logs/app.log", level: int = logging.INFO) -> logging.Logger`
        *   設定並回傳一個包含 Console 和 File Handler 的 Logger。
        *   **Returns**: `logging.Logger`

*   **全域變數 (Global Variables)**:
    *   `logger`: 預設的 Logger 實例。

#### `XBrainLab/utils/seed.py`

##### 模組函式
管理全域隨機種子，確保實驗可重現。

*   **函式 (Functions)**:
    *   `set_seed(seed: int | None = None) -> int`
        *   設定 Python, Numpy, Torch 的隨機種子。若未提供則隨機生成。
        *   **Returns**: 設定的種子值。
    *   `get_random_state() -> tuple`
        *   取得當前所有隨機產生器 (Torch, Random, Numpy) 的狀態。
        *   **Returns**: `tuple`
    *   `set_random_state(state: tuple) -> None`
        *   還原隨機狀態。

### 2.3 預處理模組 (XBrainLab/preprocessor)
負責對 Raw 資料進行各種訊號處理操作。

#### `XBrainLab/preprocessor/base.py`

##### `class PreprocessBase`
所有預處理器的基類。

*   **屬性 (Attributes)**:
    *   `preprocessed_data_list` (List[Raw]): 待處理的 Raw 資料列表。

*   **方法 (Methods)**:
    *   `__init__(self, preprocessed_data_list: List[Raw])`
        *   初始化並複製資料列表。
    *   `check_data(self) -> None`
        *   驗證資料是否有效 (非空且類型正確)。
    *   `get_preprocessed_data_list(self) -> List[Raw]`
        *   取得處理後的資料列表。
    *   `get_preprocess_desc(self, *args, **kargs) -> str`
        *   (抽象方法) 取得該預處理步驟的描述。
    *   `data_preprocess(self, *args, **kargs) -> List[Raw]`
        *   執行預處理的 Wrapper，會自動呼叫 `_data_preprocess` 並記錄歷史。
    *   `_data_preprocess(self, preprocessed_data: Raw, *args, **kargs) -> None`
        *   (抽象方法) 實際執行預處理邏輯。

#### `XBrainLab/preprocessor/channel_selection.py`

##### `class ChannelSelection(PreprocessBase)`
選擇特定頻道。

*   **輸入 (Input)**:
    *   `selected_channels` (List[str]): 要保留的頻道名稱列表。

#### `XBrainLab/preprocessor/edit_event.py`

##### `class EditEventName(PreprocessBase)`
修改事件名稱 (僅適用於 Epoch 資料)。

*   **輸入 (Input)**:
    *   `new_event_name` (dict[str, str]): 舊名稱到新名稱的映射。

##### `class EditEventId(PreprocessBase)`
修改事件 ID (僅適用於 Epoch 資料)。

*   **輸入 (Input)**:
    *   `new_event_ids` (dict[str, int]): 事件名稱到新 ID 的映射。

#### `XBrainLab/preprocessor/export.py`

##### `class Export(PreprocessBase)`
匯出資料為 .mat 格式。

*   **輸入 (Input)**:
    *   `filepath` (str): 存檔路徑。

#### `XBrainLab/preprocessor/filtering.py`

##### `class Filtering(PreprocessBase)`
頻率濾波。

*   **輸入 (Input)**:
    *   `l_freq` (float): 低頻截止點 (High-pass)。
    *   `h_freq` (float): 高頻截止點 (Low-pass)。

#### `XBrainLab/preprocessor/normalize.py`

##### `class Normalize(PreprocessBase)`
資料標準化。

*   **輸入 (Input)**:
    *   `norm` (str): 標準化方法 ("z score" 或 "minmax")。

#### `XBrainLab/preprocessor/resample.py`

##### `class Resample(PreprocessBase)`
重採樣。

*   **輸入 (Input)**:
    *   `sfreq` (float): 目標採樣頻率。

#### `XBrainLab/preprocessor/time_epoch.py`

##### `class TimeEpoch(PreprocessBase)`
根據事件標記進行切分 (Epoching)。

*   **輸入 (Input)**:
    *   `baseline` (list): 基線校正區間 (如 `[-0.2, 0]`)。
    *   `selected_event_names` (list): 要保留的事件名稱。
    *   `tmin` (float): 事件前時間 (秒)。
    *   `tmax` (float): 事件後時間 (秒)。

#### `XBrainLab/preprocessor/window_epoch.py`

##### `class WindowEpoch(PreprocessBase)`
使用滑動視窗進行切分。

*   **輸入 (Input)**:
    *   `duration` (float): 視窗長度 (秒)。
    *   `overlap` (float): 重疊長度 (秒)。

### 2.4 資料集管理模組 (XBrainLab/dataset)

#### `XBrainLab/dataset/epochs.py`

##### `class TrialSelectionSequence(Enum)`
定義資料集切分時的篩選順序。
*   成員：`SESSION`, `SUBJECT`, `Label`

##### `class Epochs`
儲存預處理後的 Epoch 資料，並提供多種篩選與查詢功能。

*   **屬性 (Attributes)**:
    *   `sfreq` (float): 採樣頻率。
    *   `subject_map` (dict[int, str]): 受試者索引對照表。
    *   `session_map` (dict[int, str]): 場次索引對照表。
    *   `label_map` (dict[int, str]): 標籤索引對照表。
    *   `event_id` (dict[str, int]): 事件名稱對照表。
    *   `ch_names` (list[str]): 頻道名稱列表。
    *   `channel_position` (list | None): 頻道位置資訊 (x, y, z)。
    *   `data` (np.ndarray): 腦波數據 (n_epochs, n_channels, n_times)。
    *   `subject` (np.ndarray): 每個 Epoch 的受試者索引。
    *   `session` (np.ndarray): 每個 Epoch 的場次索引。
    *   `label` (np.ndarray): 每個 Epoch 的標籤索引。

*   **方法 (Methods)**:
    *   `__init__(self, preprocessed_data_list: list[Raw])`
        *   初始化 Epochs 物件，合併多個 Raw 物件。
    *   `copy(self) -> Epochs`
        *   回傳物件的深層複製。
    *   `get_subject_list(self) -> np.ndarray`
        *   取得每個 Epoch 的受試者索引列表。
    *   `get_session_list(self) -> np.ndarray`
        *   取得每個 Epoch 的場次索引列表。
    *   `get_label_list(self) -> np.ndarray`
        *   取得每個 Epoch 的標籤索引列表。
    *   `get_subject_list_by_mask(self, mask: np.ndarray) -> np.ndarray`
        *   根據遮罩取得受試者索引列表。
    *   `get_session_list_by_mask(self, mask: np.ndarray) -> np.ndarray`
        *   根據遮罩取得場次索引列表。
    *   `get_label_list_by_mask(self, mask: np.ndarray) -> np.ndarray`
        *   根據遮罩取得標籤索引列表。
    *   `get_idx_list_by_mask(self, mask: np.ndarray) -> np.ndarray`
        *   根據遮罩取得原始 Epoch 索引列表。
    *   `get_subject_name(self, idx: int) -> str`
        *   根據索引取得受試者名稱。
    *   `get_session_name(self, idx: int) -> str`
        *   根據索引取得場次名稱。
    *   `get_label_name(self, idx: int) -> str`
        *   根據索引取得標籤名稱。
    *   `get_subject_map(self) -> dict`
        *   取得受試者索引對照表。
    *   `get_session_map(self) -> dict`
        *   取得場次索引對照表。
    *   `get_label_map(self) -> dict`
        *   取得標籤索引對照表。
    *   `get_subject_index_list(self) -> list`
        *   取得所有受試者的索引列表。
    *   `pick_subject_mask_by_idx(self, idx: int) -> np.ndarray`
        *   取得特定受試者的 Epoch 遮罩。
    *   `get_data_length(self) -> int`
        *   取得 Epochs 總數。
    *   `_generate_mask_target(self, mask: np.ndarray) -> dict`
        *   (內部) 生成篩選目標遮罩與計數器，依 Label/Subject/Session 分組。
    *   `_get_filtered_mask_pair(self, filter_preview_mask: dict) -> list`
        *   (內部) 取得計數最少的群組遮罩與計數器。
    *   `_update_mask_target(self, filter_preview_mask: dict, pos: np.ndarray) -> dict`
        *   (內部) 更新篩選目標的計數器。
    *   `_get_real_num(self, target_type: np.ndarray, value: float | list[int], split_unit: SplitUnit, mask: np.ndarray, clean_mask: np.ndarray, group_idx: int) -> int`
        *   (內部) 計算需篩選的 Epoch 數量。
    *   `_pick(self, target_type: np.ndarray, mask: np.ndarray, clean_mask: np.ndarray, value: float | list[int], split_unit: SplitUnit, group_idx: int) -> tuple[np.ndarray, np.ndarray]`
        *   (內部) 執行篩選邏輯的核心方法。
    *   `_pick_manual(self, target_type: np.ndarray, mask: np.ndarray, value: list[int]) -> tuple[np.ndarray, np.ndarray]`
        *   (內部) 執行手動篩選邏輯。
    *   `pick_subject(self, mask: np.ndarray, clean_mask: np.ndarray, value: float | list[int], split_unit: SplitUnit, group_idx: int) -> tuple[np.ndarray, np.ndarray]`
        *   根據受試者篩選 Epochs。
    *   `pick_session(self, mask: np.ndarray, clean_mask: np.ndarray, value: float | list[int], split_unit: SplitUnit, group_idx: int) -> tuple[np.ndarray, np.ndarray]`
        *   根據場次篩選 Epochs。
    *   `pick_trial(self, mask: np.ndarray, clean_mask: np.ndarray, value: float | list[int], split_unit: SplitUnit, group_idx: int) -> tuple[np.ndarray, np.ndarray]`
        *   根據 Trial 篩選 Epochs。
    *   `get_model_args(self) -> dict`
        *   取得用於模型初始化的參數 (n_classes, channels, samples, sfreq)。
    *   `get_data(self) -> np.ndarray`
        *   取得腦波數據。
    *   `get_label_number(self) -> int`
        *   取得標籤總數 (類別數)。
    *   `get_channel_names(self) -> list`
        *   取得頻道名稱列表。
    *   `get_epoch_duration(self) -> float`
        *   取得每個 Epoch 的持續時間 (秒)。
    *   `set_channels(self, ch_names: list[str], channel_position: list) -> None`
        *   設定頻道名稱與位置。
    *   `get_montage_position(self) -> list`
        *   取得頻道位置資訊 (Montage)。

#### `XBrainLab/dataset/dataset_generator.py`

##### `class DatasetGenerator`
負責根據設定 (Config) 將 Epochs 切分為訓練、驗證與測試集，並生成 Dataset 物件列表。

*   **屬性 (Attributes)**:
    *   `epoch_data` (:class:`Epochs`): 來源 Epochs 資料。
    *   `config` (:class:`DataSplittingConfig`): 切分設定。
    *   `datasets` (list[:class:`Dataset`]): 生成的 Dataset 列表。
    *   `interrupted` (bool): 是否中斷生成。
    *   `preview_failed` (bool): 預覽是否失敗。
    *   `done` (bool): 生成是否完成。
    *   `test_splitter_list` (list[:class:`DataSplitter`]): 測試集切分規則列表。
    *   `val_splitter_list` (list[:class:`DataSplitter`]): 驗證集切分規則列表。

*   **方法 (Methods)**:
    *   `__init__(self, epoch_data: Epochs, config: DataSplittingConfig, datasets: Optional[List[Dataset]] = None)`
        *   初始化 DatasetGenerator。
    *   `generate(self) -> List[Dataset]`
        *   執行資料集生成流程。
    *   `handle_IND(self) -> None`
        *   處理個別受試者 (Individual) 模式的生成。
    *   `handle_FULL(self) -> None`
        *   處理全體受試者 (Full Data) 模式的生成。
    *   `handle(self, name_prefix: str, dataset_hook: Optional[callable] = None) -> None`
        *   (內部) 執行資料集生成的通用邏輯。
    *   `split_test(self, dataset: Dataset, group_idx: int, mask: np.ndarray, clean_mask: np.ndarray) -> np.ndarray`
        *   切分測試集。
    *   `split_validate(self, dataset: Dataset, group_idx: int) -> None`
        *   切分驗證集。
    *   `reset(self) -> None`
        *   重置生成器狀態。
    *   `apply(self, study: 'Study') -> None`
        *   將生成的資料集應用到 Study。
    *   `set_interrupt(self) -> None`
        *   設定中斷旗標以停止生成。
    *   `prepare_reuslt(self) -> list`
        *   生成資料集並移除未選取的項目。
    *   `is_clean(self) -> bool`
        *   檢查生成狀態是否乾淨 (無中斷或失敗)。

#### `XBrainLab/dataset/dataset.py`

##### `class Dataset`
代表一個具體的資料集實例，包含訓練、驗證與測試集的遮罩。

*   **屬性 (Attributes)**:
    *   `SEQ` (int): 用於生成資料集 ID 的序號 (Class Attribute)。
    *   `name` (str): 資料集名稱。
    *   `dataset_id` (int): 資料集 ID。
    *   `remaining_mask` (np.ndarray): 剩餘可用資料的遮罩。
    *   `train_mask` (np.ndarray): 訓練集遮罩。
    *   `val_mask` (np.ndarray): 驗證集遮罩。
    *   `test_mask` (np.ndarray): 測試集遮罩。
    *   `is_selected` (bool): 是否被選取。

*   **方法 (Methods)**:
    *   `__init__(self, epoch_data: Epochs, config: DataSplittingConfig)`
        *   初始化 Dataset。
    *   `get_training_data(self) -> tuple[np.ndarray, np.ndarray]`
        *   取得訓練集資料 (X, y)。
    *   `get_val_data(self) -> tuple[np.ndarray, np.ndarray]`
        *   取得驗證集資料 (X, y)。
    *   `get_test_data(self) -> tuple[np.ndarray, np.ndarray]`
        *   取得測試集資料 (X, y)。
    *   `set_test(self, mask: np.ndarray) -> None`
        *   設定測試集遮罩。
    *   `set_val(self, mask: np.ndarray) -> None`
        *   設定驗證集遮罩。
    *   `set_remaining_to_train(self) -> None`
        *   將剩餘未分配的資料設為訓練集。
    *   `get_epoch_data(self) -> Epochs`
        *   取得關聯的 Epochs 資料。
    *   `get_name(self) -> str`
        *   取得格式化的資料集名稱 (ID-Name)。
    *   `get_ori_name(self) -> str`
        *   取得原始資料集名稱。
    *   `get_all_trial_numbers(self) -> tuple`
        *   取得訓練、驗證、測試集的樣本數。
    *   `get_treeview_row_info(self) -> tuple`
        *   取得用於 UI TreeView 顯示的資訊。
    *   `set_selection(self, select: bool) -> None`
        *   設定資料集是否被選取。
    *   `set_name(self, name: str) -> None`
        *   設定資料集名稱。
    *   `has_set_empty(self) -> bool`
        *   檢查是否有任一集合為空。
    *   `get_remaining_mask(self) -> np.ndarray`
        *   取得剩餘資料遮罩。
    *   `discard_remaining_mask(self, mask: np.ndarray) -> None`
        *   將指定遮罩的資料從剩餘資料中移除。
    *   `get_train_len(self) -> int`
        *   取得訓練集樣本數。
    *   `get_val_len(self) -> int`
        *   取得驗證集樣本數。
    *   `get_test_len(self) -> int`
        *   取得測試集樣本數。

#### `XBrainLab/dataset/data_splitter.py`

##### `class DataSplitter`
定義單一分割規則 (例如：依 Session 切分，保留 20%)。

*   **屬性 (Attributes)**:
    *   `split_type` (SplitByType | ValSplitByType): 切分依據 (Session/Subject/Trial)。
    *   `value_var` (str): 切分數值字串。
    *   `split_unit` (SplitUnit): 切分單位 (Ratio/Number/KFold)。
    *   `is_option` (bool): 是否為有效選項。
    *   `text` (str): split_type 的字串表示。

*   **方法 (Methods)**:
    *   `get_value(self) -> float | list[int]`
        *   解析並取得切分數值。
    *   `is_valid(self) -> bool`
        *   檢查設定是否有效。
    *   `get_raw_value(self) -> str`
        *   取得原始數值字串。
    *   `get_split_unit(self) -> SplitUnit`
        *   取得切分單位。
    *   `get_split_unit_repr(self) -> str`
        *   取得切分單位的字串表示 (Class.Name)。
    *   `get_split_type_repr(self) -> str`
        *   取得切分依據的字串表示 (Class.Name)。

##### `class DataSplittingConfig`
彙整整體的資料切分設定。

*   **屬性 (Attributes)**:
    *   `train_type` (TrainingType): 訓練模式 (Full/Individual)。
    *   `is_cross_validation` (bool): 是否啟用交叉驗證。
    *   `val_splitter_list` (list[DataSplitter]): 驗證集切分規則列表。
    *   `test_splitter_list` (list[DataSplitter]): 測試集切分規則列表。

*   **方法 (Methods)**:
    *   `get_splitter_option(self) -> tuple[list[DataSplitter], list[DataSplitter]]`
        *   取得驗證集與測試集的切分規則列表。
    *   `get_train_type_repr(self) -> str`
        *   取得訓練模式的字串表示。

#### `XBrainLab/dataset/option.py`

##### Enums
*   `SplitUnit`: `RATIO`, `NUMBER`, `MANUAL`, `KFOLD`
*   `TrainingType`: `FULL`, `IND`
*   `ValSplitByType`: `DISABLE`, `SESSION`, `TRIAL`, `SUBJECT`

### 2.5 評估模組 (XBrainLab/evaluation)
提供評估模型效能的指標。

#### `XBrainLab/evaluation/metric.py`

##### `class Metric(Enum)`
定義支援的評估指標。
*   成員：
    *   `ACC`: Accuracy (%)
    *   `AUC`: Area under ROC-curve
    *   `KAPPA`: kappa value

### 2.6 模型基類模組 (XBrainLab/model_base)
包含所有深度學習模型的實作。

#### `XBrainLab/model_base/EEGNet.py`
*   `class EEGNet`: EEGNet 模型實作。

#### `XBrainLab/model_base/SCCNet.py`
*   `class SCCNet`: SCCNet 模型實作。

#### `XBrainLab/model_base/ShallowConvNet.py`
*   `class ShallowConvNet`: ShallowConvNet 模型實作。

### 2.7 訓練模組 (XBrainLab/training)
負責模型的訓練、驗證與測試流程管理。

#### `XBrainLab/training/model_holder.py`

##### `class ModelHolder`
封裝模型類別與參數，負責模型的實例化。

*   **方法 (Methods)**:
    *   `get_model(self, extra_params: dict) -> torch.nn.Module`
        *   建立並回傳模型實例。
    *   `get_model_desc_str(self) -> str`
        *   取得模型描述字串 (Name + Params)。

#### `XBrainLab/training/option.py`

##### `class TrainingOption`
封裝訓練相關參數 (Epoch, Batch Size, LR, Optimizer 等)。

##### `class TestOnlyOption`
封裝僅測試模式的參數。

#### `XBrainLab/training/trainer.py`

##### `class Trainer`
管理多個訓練計畫 (TrainingPlanHolder) 的執行。

*   **方法 (Methods)**:
    *   `run(self, interact: bool = False) -> None`
        *   啟動訓練執行緒。
    *   `set_interrupt(self) -> None`
        *   設定中斷旗標。
    *   `get_progress_text(self) -> str`
        *   取得當前進度文字。

#### `XBrainLab/training/training_plan.py`

##### `class TrainingPlanHolder`
管理單一訓練任務的完整生命週期 (包含多次重複實驗)。

*   **方法 (Methods)**:
    *   `train(self) -> None`
        *   執行完整的訓練流程 (多次 Repeat)。
    *   `train_one_repeat(self, train_record: TrainRecord) -> None`
        *   執行單次重複實驗 (包含多個 Epoch)。
    *   `train_one_epoch(self, ...) -> None`
        *   執行單一 Epoch 的訓練。
    *   `get_loader(self) -> tuple`
        *   取得 DataLoader (Train, Val, Test)。

### 2.8 核心控制模組 (XBrainLab/study.py)
整合所有子模組，提供統一的操作介面。

#### `class Study`
儲存實驗所需的所有資訊與狀態。

*   **屬性 (Attributes)**:
    *   `loaded_data_list` (list[Raw]): 載入的原始資料列表。
    *   `preprocessed_data_list` (list[Raw]): 預處理後的資料列表。
    *   `epoch_data` (Epochs): 切分後的 Epoch 資料。
    *   `datasets` (list[Dataset]): 生成的資料集列表。
    *   `model_holder` (ModelHolder): 模型容器。
    *   `training_option` (TrainingOption): 訓練參數。
    *   `trainer` (Trainer): 訓練控制器。

*   **方法 (Methods)**:
    *   `get_raw_data_loader(self) -> RawDataLoader`
        *   取得資料載入器。
    *   `set_loaded_data_list(self, loaded_data_list: List[Raw], force_update: bool = False)`
        *   設定載入的資料。
    *   `preprocess(self, preprocessor: Type[PreprocessBase], **kargs)`
        *   執行預處理步驟。
    *   `get_datasets_generator(self, config: DataSplittingConfig) -> DatasetGenerator`
        *   取得資料集生成器。
    *   `set_datasets(self, datasets: List[Dataset], force_update: bool = False)`
        *   設定生成的資料集。
    *   `set_training_option(self, training_option: TrainingOption, force_update: bool = False)`
        *   設定訓練參數。
    *   `set_model_holder(self, model_holder: ModelHolder, force_update: bool = False)`
        *   設定模型。
    *   `generate_plan(self, force_update: bool = False)`
        *   生成訓練計畫 (初始化 Trainer)。
    *   `train(self, interact: bool = False)`
        *   開始訓練。
    *   `stop_training(self)`
        *   停止訓練。
    *   `export_output_csv(self, filepath: str, plan_name: str, real_plan_name: str)`
        *   匯出推論結果。
    *   `set_saliency_params(self, saliency_params: dict)`
        *   設定 Saliency Map 計算參數。

### 2.9 視覺化模組 (XBrainLab/visualization)
負責生成各種評估圖表與腦波視覺化。

#### `XBrainLab/visualization/base.py`

##### `class Visualizer`
所有視覺化器的基類。

*   **方法 (Methods)**:
    *   `get_plt(self, method: str, absolute: bool = False) -> plt.Figure`
        *   (抽象方法) 生成圖表。
    *   `get_saliency(self, method: str, label_idx: int) -> np.ndarray`
        *   取得指定方法的 Saliency Map。

#### `XBrainLab/visualization/saliency_map.py`
*   `class SaliencyMap`: 生成 Saliency Map 熱力圖。

#### `XBrainLab/visualization/saliency_topomap.py`
*   `class SaliencyTopoMap`: 生成 Saliency Topo Map (腦波圖)。

#### `XBrainLab/visualization/saliency_spectrogram_map.py`
*   `class SaliencySpectrogramMap`: 生成 Saliency Spectrogram (頻譜圖)。



