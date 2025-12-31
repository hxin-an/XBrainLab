# XBrainLab 開發者指南 (Developer Guide)

本指南專為開發者設計，旨在深入解析 XBrainLab 的架構、程式碼組織以及 PyQt 實作細節。

## 1. 系統架構概覽 (System Architecture)

XBrainLab 採用 **Model-View-Controller (MVC)** 的變體架構，將數據邏輯 (Backend) 與使用者介面 (Frontend) 分離。

*   **Model (Backend)**: 負責數據處理、訓練邏輯。
    *   `dataset/`: 數據集管理。
    *   `load_data/`: 原始數據讀取 (Raw Data Loading)。
    *   `preprocessor/`: 訊號處理（濾波、ICA）。
    *   `training/`: 模型訓練核心。
    *   `model_base/`: 深度學習模型架構定義。
    *   `evaluation/`: 模型評估與指標計算。
    *   `visualization/`: 數據與結果視覺化邏輯。
    *   `remote/`: AI Agent 與遠端服務整合。
    *   `study.py`: **核心控制器**，管理整個實驗的生命週期 (Data -> Epochs -> Model)。
*   **View (Frontend/PyQt)**: 負責顯示與使用者互動。
    *   `ui_pyqt/`: 所有的 GUI 程式碼。
*   **Controller (Glue Code)**: 連接 UI 事件與後端邏輯。
    *   大部分實作在 `MainWindow` 與各個 `Panel` 類別中。

### 1.1 專案目錄結構詳解

```
XBrainLab/
├── dataset/                    # [Backend] 數據集生成與管理
│   ├── data_splitter.py        # 數據切分邏輯
│   ├── dataset.py              # Dataset 類別定義
│   ├── dataset_generator.py    # Dataset 生成器
│   ├── epochs.py               # Epochs 數據結構
│   └── option.py               # 數據集設定選項
├── evaluation/                 # [Backend] 模型評估邏輯
│   └── metric.py               # 評估指標計算
├── load_data/                  # [Backend] 原始數據讀取
│   ├── data_loader.py          # 通用數據加載器
│   ├── event_loader.py         # 事件加載與處理
│   └── raw.py                  # Raw 數據結構封裝
├── model_base/                 # [Backend] 基礎模型定義 (PyTorch)
│   ├── EEGNet.py               # EEGNet 模型
│   ├── SCCNet.py               # SCCNet 模型
│   └── ShallowConvNet.py       # ShallowConvNet 模型
├── preprocessor/               # [Backend] 訊號預處理
│   ├── base.py                 # 預處理器基類
│   ├── channel_selection.py    # 通道選擇
│   ├── edit_event.py           # 事件編輯
│   ├── export.py               # 數據匯出
│   ├── filtering.py            # 濾波器
│   ├── normalize.py            # 歸一化
│   ├── resample.py             # 重採樣
│   ├── time_epoch.py           # 時間切分
│   └── window_epoch.py         # 視窗切分
├── training/                   # [Backend] 模型訓練核心
│   ├── model_holder.py         # 模型持有者 (管理模型參數)
│   ├── option.py               # 訓練選項
│   ├── trainer.py              # 訓練迴圈執行者
│   └── training_plan.py        # 訓練計畫管理
├── visualization/              # [Backend] 視覺化繪圖邏輯 (Matplotlib)
│   ├── base.py                 # 繪圖基類
│   ├── plot_type.py            # 繪圖類型定義
│   ├── saliency_map.py         # 顯著圖計算
│   ├── saliency_spectrogram_map.py # 頻譜顯著圖
│   └── saliency_topomap.py     # 拓樸顯著圖
├── ui_pyqt/                    # [Frontend] PyQt 使用者介面
│   ├── main_window.py          # [入口] 程式主視窗
│   ├── agent_worker.py         # AI 助手後台工作線程
│   ├── chat_panel.py           # AI 助手聊天面板
│   ├── dashboard_panel/        # [UI] 儀表板 (數據導入、預處理)
│   │   ├── dataset.py          # 數據集管理面板
│   │   ├── import_label.py     # 標籤匯入對話框
│   │   ├── info.py             # 數據資訊面板
│   │   ├── preprocess.py       # 預處理流程面板
│   │   └── smart_parser.py     # 檔名解析器
│   ├── dataset/                # [UI] 數據集設定
│   │   ├── data_splitting.py   # 數據切分設定
│   │   ├── data_splitting_setting.py # 切分參數 UI
│   │   └── split_chooser.py    # 切分方法選擇器
│   ├── evaluation/             # [UI] 評估面板
│   │   ├── confusion_matrix.py # 混淆矩陣顯示
│   │   ├── evaluation_table.py # 評估結果表格
│   │   ├── model_output.py     # 模型輸出顯示
│   │   └── panel.py            # 評估主面板
│   ├── load_data/              # [UI] 數據讀取輔助 (預留擴展)
│   │   └── __init__.py         # 模組初始化
│   ├── training/               # [UI] 訓練面板
│   │   ├── model_selection.py  # 模型選擇元件
│   │   ├── panel.py            # 訓練主面板
│   │   ├── training_manager.py # 訓練管理器 UI
│   │   └── training_setting.py # 訓練參數設定 UI
│   ├── visualization/          # [UI] 視覺化面板
│   │   ├── export_saliency.py  # 顯著圖匯出 UI
│   │   ├── model_summary.py    # 模型摘要顯示
│   │   ├── montage_picker.py   # 電極配置選擇器
│   │   ├── panel.py            # 視覺化主面板
│   │   ├── plot_3d_head.py     # 3D 頭部繪圖
│   │   ├── plot_abs_plot_figure.py      # 抽象繪圖基礎類別
│   │   ├── plot_abs_topo_plot_figure.py # 抽象拓樸圖基礎類別
│   │   ├── plot_eval_record_figure.py   # 評估記錄繪圖
│   │   ├── saliency_3Dplot.py  # 3D 顯著圖
│   │   ├── saliency_map.py     # 顯著圖 UI
│   │   ├── saliency_setting.py # 顯著圖參數設定
│   │   ├── saliency_spectrogram.py # 頻譜顯著圖 UI
│   │   └── saliency_topomap.py # 拓樸圖 UI
│   ├── llm/                    # [UI] LLM 相關 UI (預留擴展)
│   │   └── (待開發)
│   └── widget/                 # [UI] 通用元件
│       ├── card.py             # 卡片式容器
│       ├── placeholder.py      # 佔位符
│       ├── plot_figure_window.py # 通用繪圖視窗
│       └── single_plot_window.py # 單圖視窗
├── remote/                     # [Agent] 遠端/AI Agent 相關邏輯
│   ├── agent.py                # Agent 核心邏輯
│   ├── agent_for_plot.py       # 專門處理繪圖的 Agent
│   ├── core/                   # Agent 核心模組
│   ├── prompts.py              # LLM 提示詞 (Prompts)
│   └── examples.csv            # Few-shot examples
├── utils/                      # 通用工具函式
│   ├── check.py                # 檢查工具
│   ├── logger.py               # 日誌系統
│   └── seed.py                 # 隨機種子設定
└── study.py                    # [核心] 狀態管理中心 (Controller)
```

## 2. PyQt 核心機制與 XBrainLab 實作

### 2.1 Signal & Slot (信號與槽)
這是 PyQt 元件間溝通的橋樑。XBrainLab 大量使用此機制來解耦 UI 與邏輯。

*   **基本語法**: `sender.signal.connect(receiver.slot)`
*   **XBrainLab 範例**:
    在 `dataset_panel.py` 中，當使用者點擊「Load」按鈕：
    ```python
    # 1. 定義 Signal (通常是 PyQt 內建，如 clicked)
    self.btn_load.clicked.connect(self.on_click_load)

    # 2. 定義 Slot (處理函數)
    def on_click_load(self):
        file_path = self.get_file_path()
        # 呼叫後端
        self.study.load_data(file_path)
        # 發出自定義 Signal 通知其他 Panel 更新
        self.data_loaded.emit()
    ```

### 2.2 多執行緒 (Threading)
**關鍵規則**: 耗時操作（如讀取大檔案、訓練模型）**絕對不能**在主線程 (GUI Thread) 執行，否則介面會凍結。

*   **解決方案**: 使用 `QThread` 或 `QRunnable`。
*   **XBrainLab 實作**:
    在 `training_panel.py` 中，訓練過程通常包裝在一個 Worker Thread 中：
    ```python
    class TrainWorker(QThread):
        progress_updated = pyqtSignal(int)  # 用 Signal 更新進度條
        training_finished = pyqtSignal()    # 訓練完成信號
        error_occurred = pyqtSignal(str)    # 錯誤處理信號

        def __init__(self, trainer):
            super().__init__()
            self.trainer = trainer

        def run(self):
            try:
                # 這裡執行耗時的訓練迴圈
                self.trainer.run()
                self.progress_updated.emit(100)
                self.training_finished.emit()
            except Exception as e:
                self.error_occurred.emit(str(e))
    
    # 在主 Panel 中使用
    def start_training(self):
        self.worker = TrainWorker(self.trainer)
        self.worker.progress_updated.connect(self.update_progress_bar)
        self.worker.training_finished.connect(self.on_training_complete)
        self.worker.error_occurred.connect(self.show_error_dialog)
        self.worker.start()
    ```
    
    **重要**: 永遠使用 Signal/Slot 從 Worker Thread 更新 GUI，直接在 Worker 中操作 UI 元件會導致崩潰。

### 2.3 繪圖整合 (Matplotlib in PyQt)
我們使用 `matplotlib.backends.backend_qt5agg.FigureCanvasQTAgg` 將 Matplotlib 圖表嵌入 PyQt。
*   **封裝**: `ui_pyqt/widget/plot_figure_window.py` 是一個通用的繪圖視窗，可以接收任何 Matplotlib Figure 並顯示出來。
*   **XBrainLab 範例**:
    ```python
    from matplotlib.figure import Figure
    from XBrainLab.ui_pyqt.widget import PlotFigureWindow
    
    # 1. 在後端生成 Matplotlib Figure
    def create_plot():
        fig = Figure(figsize=(8, 6))
        ax = fig.add_subplot(111)
        ax.plot([1, 2, 3], [1, 4, 9])
        ax.set_title('My Plot')
        return fig
    
    # 2. 在 UI 中顯示
    def show_plot_window(self):
        fig = create_plot()
        plot_window = PlotFigureWindow(fig, title="Result")
        plot_window.show()
    ```

## 3. Study 類別：系統核心控制器

`Study` 類別是 XBrainLab 的核心控制器，管理整個 EEG 分析的生命週期。所有 UI Panel 都透過 `Study` 實例存取和修改數據狀態。

### 3.1 數據流 (Data Flow Pipeline)
```
Raw Files (.gdf, .set)
    ↓
[Step 1] load_data → loaded_data_list: List[Raw]
    ↓
[Step 2] preprocess → preprocessed_data_list: List[Raw]
    ↓
[Step 3] epoching → epoch_data: Epochs
    ↓
[Step 4] split → datasets: List[Dataset]
    ↓
[Step 5] training → trainer: Trainer
    ↓
[Step 6] evaluation → results & visualization
```

### 3.2 Study 主要方法
*   **數據載入階段**:
    *   `get_raw_data_loader()`: 獲取數據載入器
    *   `set_loaded_data_list(data_list)`: 設定原始數據
    *   `set_preprocessed_data_list(data_list)`: 設定預處理後數據並自動生成 Epochs
*   **數據集階段**:
    *   `get_datasets_generator()`: 獲取數據集生成器
    *   `set_datasets(datasets)`: 設定切分好的數據集
*   **訓練階段**:
    *   `set_training_option(option)`: 設定訓練參數
    *   `set_model_holder(holder)`: 設定模型
    *   `generate_plan()`: 生成訓練計畫（創建 Trainer）
    *   `start_training()`: 開始訓練
    *   `stop_training()`: 停止訓練
*   **視覺化階段**:
    *   `set_channels(channels)`: 設定通道資訊
    *   `set_saliency_params(params)`: 設定顯著圖參數

### 3.3 狀態管理原則
*   **單一數據源**: 所有 Panel 透過 `self.study` 存取數據，避免在 UI 層複製狀態。
*   **驗證機制**: Study 的 setter 方法會進行型別檢查和一致性驗證。
*   **階段鎖定**: `dataset_locked` 旗標防止在訓練期間修改數據集。

## 4. Agent 整合 (AI Assistant)

`remote/` 模組提供 AI Agent 功能，讓使用者透過自然語言操作系統。

### 4.1 Agent 架構
*   **`agent.py`**: 主 Agent 邏輯，處理指令解析與執行。
*   **`agent_for_plot.py`**: 專門處理繪圖請求的 Agent。
*   **`core/`**: Agent 核心模組
    *   `llm_engine.py`: LLM 呼叫封裝
    *   `rag_engine.py`: 檢索增強生成（RAG）
    *   `command_parser.py`: 指令解析器
*   **`prompts.py`**: LLM 提示詞模板。
*   **`examples.csv`**: Few-shot learning 範例。

### 4.2 UI 整合
*   **`ui_pyqt/agent_worker.py`**: Agent 執行的 Worker Thread。
*   **`ui_pyqt/chat_panel.py`**: 聊天介面 UI。

### 4.3 如何擴展 Agent 功能
1.  在 `prompts.py` 中定義新的提示詞模板。
2.  在 `agent.py` 中新增對應的指令處理邏輯。
3.  更新 `examples.csv` 提供範例。
4.  在 UI 中透過 `agent_worker.py` 呼叫。

## 5. 開發流程指南

### 5.1 如何新增一個功能頁面 (Panel)？
1.  **建立檔案**: 在 `ui_pyqt/` 下建立新的資料夾或檔案 (e.g., `my_feature_panel.py`)。
2.  **繼承 QWidget**:
    ```python
    class MyFeaturePanel(QWidget):
        def __init__(self, study):
            super().__init__()
            self.study = study # 注入 Study 實例以存取數據
            self.init_ui()
    ```
3.  **註冊到 MainWindow**:
    打開 `ui_pyqt/main_window.py`，在 `init_tabs` 方法中加入：
    ```python
    self.my_panel = MyFeaturePanel(self.study)
    self.tabs.addTab(self.my_panel, "My Feature")
    ```

### 5.2 除錯技巧 (Debugging)
*   **Console Output**: PyQt 的錯誤通常會印在 Terminal。如果按鈕沒反應，先看 Terminal 有沒有報錯。
*   **Print Debugging**: 在 Slot 函數開頭 `print("Function called")` 是確認 Signal 是否連接成功最快的方法。
*   **Logger**: 使用 `XBrainLab.utils.logger` 記錄重要事件和錯誤：
    ```python
    from XBrainLab.utils.logger import logger
    logger.info("Processing started")
    logger.error(f"Failed to load file: {e}")
    ```
*   **常見錯誤**:
    *   `AttributeError: 'NoneType' object has no attribute...`: 通常是 `init_ui` 順序錯了，或是存取了還沒初始化的變數。
    *   `RuntimeError: wrapped C/C++ object has been deleted`: 試圖存取已經被關閉或銷毀的視窗元件。
    *   `QObject::connect: Cannot queue arguments of type...`: Signal/Slot 的參數型別不匹配，需要使用 `qRegisterMetaType`。

### 5.3 測試
*   **單元測試**: 詳見 `documentation/testing_guide.md`
*   **執行測試**: `pytest tests/ XBrainLab/`
*   **UI 測試**: 使用 `pytest-qt` 進行 PyQt 元件測試（見 `tests/test_ui_integration.py`）

## 6. 開發環境設定

### 6.1 初始設定
```bash
# 1. 建立虛擬環境
python -m venv venv
source venv/bin/activate  # Linux/Mac
# venv\Scripts\activate  # Windows

# 2. 安裝依賴
pip install -r requirements.txt

# 3. 安裝開發依賴
pip install pytest pytest-qt pytest-cov

# 4. 設定 Python Path (開發模式)
pip install -e .
```

### 6.2 執行應用程式
```bash
# 主程式
python run.py

# 或使用 debug 模式
python -m XBrainLab.ui_pyqt.main_window
```

### 6.3 專案依賴
*   **核心**: `mne`, `numpy`, `scipy`
*   **深度學習**: `torch`, `torchvision`
*   **UI**: `PyQt5`, `matplotlib`
*   **測試**: `pytest`, `pytest-qt`
*   **AI Agent**: `openai`, `langchain` (optional)

## 7. 程式碼風格與規範
*   **變數命名**: `snake_case` (e.g., `load_data_button`).
*   **類別命名**: `CamelCase` (e.g., `MainWindow`).
*   **UI 變數**: 建議加上前綴表明類型，如 `btn_load` (Button), `lbl_status` (Label), `txt_input` (LineEdit)。
*   **型別提示**: 盡量使用 Type Hints 提升可讀性：
    ```python
    def process_data(raw: Raw, filters: List[str]) -> Epochs:
        ...
    ```
*   **Docstring**: 使用 Google Style 或 NumPy Style docstring。
*   **Import 順序**: 標準庫 → 第三方庫 → 本地模組。

## 8. 錯誤處理模式

### 8.1 後端錯誤處理
```python
from XBrainLab.utils.logger import logger

def load_data(file_path: str) -> Raw:
    try:
        raw = mne.io.read_raw_gdf(file_path, preload=True)
        logger.info(f"Successfully loaded {file_path}")
        return Raw(raw)
    except FileNotFoundError:
        logger.error(f"File not found: {file_path}")
        return None
    except Exception as e:
        logger.error(f"Failed to load {file_path}: {e}")
        raise
```

### 8.2 UI 錯誤處理
```python
from PyQt5.QtWidgets import QMessageBox

def on_load_button_clicked(self):
    try:
        file_path = self.get_file_path()
        raw = self.study.load_data(file_path)
        if raw is None:
            self.show_error_dialog("Failed to load file")
        else:
            self.update_ui()
    except Exception as e:
        logger.error(f"UI Error: {e}")
        self.show_error_dialog(str(e))

def show_error_dialog(self, message: str):
    QMessageBox.critical(self, "Error", message)
```

## 9. 相關文件
*   **測試指南**: `documentation/testing_guide.md`
*   **架構設計**: `documentation/architecture.md`
*   **程式碼風格**: `documentation/coding_style.md`
*   **UI 開發指南**: *(待撰寫)*

---
*文件維護者: hxin*
*最後更新: 2025-12-30*
