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
│   ├── load_data/              # [UI] 數據讀取輔助
│   │   ├── gdf.py              # GDF 讀取輔助
│   │   └── helper.py           # 讀取輔助函式
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
│   │   ├── saliency_map.py     # 顯著圖 UI
│   │   └── saliency_topomap.py # 拓樸圖 UI
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
        progress_updated = pyqtSignal(int) # 用 Signal 更新進度條

        def run(self):
            # 這裡執行耗時的訓練迴圈
            trainer.run()
            self.progress_updated.emit(100)
    ```

### 2.3 繪圖整合 (Matplotlib in PyQt)
我們使用 `matplotlib.backends.backend_qt5agg.FigureCanvasQTAgg` 將 Matplotlib 圖表嵌入 PyQt。
*   **封裝**: `ui_pyqt/widget/plot_figure_window.py` 是一個通用的繪圖視窗，可以接收任何 Matplotlib Figure 並顯示出來。

## 3. 開發流程指南

### 3.1 如何新增一個功能頁面 (Panel)？
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

### 3.2 除錯技巧 (Debugging)
*   **Console Output**: PyQt 的錯誤通常會印在 Terminal。如果按鈕沒反應，先看 Terminal 有沒有報錯。
*   **Print Debugging**: 在 Slot 函數開頭 `print("Function called")` 是確認 Signal 是否連接成功最快的方法。
*   **常見錯誤**:
    *   `AttributeError: 'NoneType' object has no attribute...`: 通常是 `init_ui` 順序錯了，或是存取了還沒初始化的變數。
    *   `RuntimeError: wrapped C/C++ object has been deleted`: 試圖存取已經被關閉或銷毀的視窗元件。

## 4. 程式碼風格與規範
*   **變數命名**: `snake_case` (e.g., `load_data_button`).
*   **類別命名**: `CamelCase` (e.g., `MainWindow`).
*   **UI 變數**: 建議加上前綴表明類型，如 `btn_load` (Button), `lbl_status` (Label), `txt_input` (LineEdit)。

---
*文件維護者: hxin*
*最後更新: 2025-12-27*
