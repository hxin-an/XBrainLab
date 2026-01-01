# XBrainLab 完整系統架構文件 (Complete System Architecture Document)

**版本**: 2.0  
**最後更新**: 2025-01-XX  
**框架**: PyQt6 (非 Tkinter)  
**Python 版本**: 3.9+

---

## 📑 目錄

1. [系統概覽](#1-系統概覽)
2. [整體架構圖](#2-整體架構圖)
3. [前端架構 (UI Layer)](#3-前端架構-ui-layer)
4. [後端架構 (Core Logic Layer)](#4-後端架構-core-logic-layer)
5. [前後端連接機制](#5-前後端連接機制)
6. [資料流程](#6-資料流程)
7. [關鍵類別與職責](#7-關鍵類別與職責)
8. [模組依賴關係](#8-模組依賴關係)
9. [檔案結構](#9-檔案結構)
10. [設計模式](#10-設計模式)

---

## 1. 系統概覽

### 1.1 系統定位
XBrainLab 是一個基於 **PyQt6** 的桌面應用程式，專注於 EEG 訊號分析與深度學習模型訓練，整合 MNE-Python、PyTorch 等科學計算框架。

### 1.2 核心特性
- ✅ **完全前後端分離**：UI (PyQt6) 與核心邏輯 (純 Python) 完全解耦
- ✅ **狀態管理中樞**：`Study` 類別作為後端協調器
- ✅ **事件驅動架構**：使用 PyQt Signal/Slot 機制
- ✅ **多執行緒支援**：訓練過程在 Worker Thread 執行，避免 UI 凍結
- ✅ **模組化設計**：每個功能面板獨立開發與測試

### 1.3 技術棧

| 層級 | 技術 | 用途 |
|------|------|------|
| **UI Framework** | PyQt6 | 圖形介面 |
| **訊號處理** | MNE-Python | EEG 資料處理 |
| **深度學習** | PyTorch | 模型訓練與推論 |
| **科學計算** | NumPy, SciPy | 數值運算 |
| **視覺化** | Matplotlib | 圖表繪製 |
| **測試框架** | pytest, pytest-qt | 單元測試與 UI 測試 |

---

## 2. 整體架構圖

```
┌──────────────────────────────────────────────────────────────────────┐
│                         XBrainLab System                             │
│                      (PyQt6 Desktop Application)                     │
└──────────────────────────────────────────────────────────────────────┘
                                   │
                    ┌──────────────┴──────────────┐
                    │                             │
        ┌───────────▼───────────┐     ┌──────────▼──────────┐
        │   Frontend (UI Layer) │     │  Backend (Core)     │
        │      PyQt6 Widgets    │────→│   Pure Python       │
        └───────────────────────┘     └─────────────────────┘
                    │                             │
        ┌───────────┴───────────┐     ┌──────────┴──────────┐
        │                       │     │                     │
    ┌───▼────┐  ┌───▼────┐  ┌───▼────┐  ┌───▼────┐  ┌───▼────┐
    │MainWin │  │ Agent  │  │ Study  │  │Training│  │Dataset │
    │ dow    │  │ Worker │  │ (Hub)  │  │ Plan   │  │ Gen    │
    └────────┘  └────────┘  └────────┘  └────────┘  └────────┘
        │           │            │           │           │
    ┌───▼────┐  ┌───▼────┐  ┌───▼────┐  ┌───▼────┐  ┌───▼────┐
    │Dash    │  │Train   │  │load_   │  │prepro- │  │model_  │
    │board   │  │ing     │  │data    │  │cessor  │  │base    │
    └────────┘  └────────┘  └────────┘  └────────┘  └────────┘
```

---

## 3. 前端架構 (UI Layer)

### 3.1 主視窗結構

```
XBrainLab/ui_pyqt/
├── main_window.py          ← 主視窗 (QMainWindow)
│   └── MainWindow
│       ├── init_ui()       ← 初始化 UI 元件
│       ├── setup_menubar() ← 設定選單列
│       └── tab_widget      ← 包含所有面板的 QTabWidget
│
├── dashboard_panel/        ← 資料管理面板
│   ├── __init__.py
│   ├── data_management.py  ← 資料載入與列表顯示
│   ├── preprocess.py       ← 預處理設定
│   └── dataset_gen.py      ← 資料集生成
│
├── training/               ← 訓練控制面板
│   ├── panel.py            ← 訓練主面板
│   ├── training_setting.py ← 訓練參數設定對話框
│   └── training_plan.py    ← 訓練計畫顯示
│
├── evaluation/             ← 評估結果面板
│   └── panel.py            ← 評估指標與混淆矩陣
│
├── visualization/          ← 視覺化面板
│   └── panel.py            ← 顯著性圖、頻譜圖等
│
└── agent/ (待開發)         ← LLM Agent 面板
    └── panel.py
```

### 3.2 關鍵 UI 類別

#### **MainWindow** (`main_window.py`)

```python
class MainWindow(QMainWindow):
    """
    主視窗：應用程式入口
    
    職責：
    1. 初始化所有面板
    2. 管理 Study 物件 (後端核心)
    3. 處理全域事件 (檔案開啟、關閉等)
    4. 協調各面板之間的通訊
    """
    
    def __init__(self):
        self.study = Study()  # ← 後端核心物件
        
        # 初始化各面板，傳入 study 引用
        self.dashboard_panel = DashboardPanel(self, self.study)
        self.training_panel = TrainingPanel(self, self.study)
        self.evaluation_panel = EvaluationPanel(self, self.study)
        self.visualization_panel = VisualizationPanel(self, self.study)
        
        # 添加到 Tab Widget
        self.tab_widget.addTab(self.dashboard_panel, "📊 Dashboard")
        self.tab_widget.addTab(self.training_panel, "🎯 Training")
        # ...
```

**設計特點**：
- ✅ 所有面板共享同一個 `Study` 實例
- ✅ 面板之間不直接通訊，透過 `Study` 狀態變化
- ✅ 使用 PyQt Signal 進行跨執行緒通訊

#### **DashboardPanel** (`dashboard_panel/`)

```python
class DashboardPanel(QWidget):
    """
    資料管理面板
    
    職責：
    1. 載入 EEG 資料檔案 (GDF/SET)
    2. 顯示已載入檔案列表
    3. 設定預處理參數 (濾波、重採樣、Epoching)
    4. 生成資料集
    """
    
    def __init__(self, parent, study: Study):
        self.study = study
        
        # 子元件
        self.data_management = DataManagementWidget(study)
        self.preprocess_widget = PreprocessWidget(study)
        self.dataset_gen_widget = DatasetGenWidget(study)
    
    def load_data_clicked(self):
        """載入資料按鈕點擊事件"""
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Select EEG File", "", "EEG Files (*.gdf *.set)"
        )
        
        if file_path:
            # 呼叫後端載入資料
            loader = self.study.get_loader()
            raw = load_raw_file(file_path)
            loader.append(raw)
            
            # 更新 UI 列表
            self.refresh_file_list()
```

**設計特點**：
- ✅ UI 只負責顯示與事件處理
- ✅ 資料處理邏輯在後端 (`Study`, `load_data`)
- ✅ UI 更新與資料載入分離

#### **TrainingPanel** (`training/panel.py`)

```python
class TrainingPanel(QWidget):
    """
    訓練控制面板
    
    職責：
    1. 設定訓練參數 (epochs, batch_size, lr)
    2. 選擇模型 (EEGNet, SCCNet, ShallowConvNet)
    3. 生成訓練計畫
    4. 啟動/停止訓練
    5. 顯示訓練進度與即時指標
    """
    
    def __init__(self, parent, study: Study):
        self.study = study
        self.training_worker = None  # 訓練執行緒
        
        # UI 元件
        self.progress_bar = QProgressBar()
        self.loss_plot = MatplotlibWidget()
        self.acc_plot = MatplotlibWidget()
    
    def start_training(self):
        """啟動訓練 (在新執行緒中)"""
        # 1. 生成訓練計畫
        self.study.generate_plan()
        
        # 2. 創建 Worker Thread
        self.training_worker = TrainingWorker(self.study)
        
        # 3. 連接 Signal/Slot
        self.training_worker.progress_updated.connect(self.update_progress)
        self.training_worker.metrics_updated.connect(self.update_plots)
        self.training_worker.finished.connect(self.training_finished)
        
        # 4. 啟動執行緒
        self.training_worker.start()
    
    def update_progress(self, epoch, total_epochs, loss, acc):
        """更新進度條與即時指標 (在主執行緒中)"""
        self.progress_bar.setValue(int(epoch / total_epochs * 100))
        self.loss_plot.add_point(epoch, loss)
        self.acc_plot.add_point(epoch, acc)
```

**設計特點**：
- ✅ 訓練在 Worker Thread 執行，避免 UI 凍結
- ✅ 使用 Signal/Slot 安全地更新 UI
- ✅ 支援訓練中斷 (`self.training_worker.stop()`)

#### **TrainingWorker** (`training/panel.py`)

```python
class TrainingWorker(QThread):
    """
    訓練執行緒
    
    職責：
    1. 在背景執行訓練迴圈
    2. 定期發送進度更新 Signal
    3. 處理訓練中斷請求
    """
    
    # 定義 Signals
    progress_updated = pyqtSignal(int, int, float, float)  # epoch, total, loss, acc
    metrics_updated = pyqtSignal(dict)
    finished = pyqtSignal()
    
    def __init__(self, study: Study):
        super().__init__()
        self.study = study
        self.is_running = True
    
    def run(self):
        """執行緒主邏輯"""
        try:
            trainer = self.study.trainer
            
            for epoch in range(trainer.total_epochs):
                if not self.is_running:
                    break
                
                # 執行一個 epoch
                loss, acc = trainer.train_one_epoch()
                
                # 發送更新 Signal
                self.progress_updated.emit(
                    epoch + 1, 
                    trainer.total_epochs, 
                    loss, 
                    acc
                )
            
            self.finished.emit()
            
        except Exception as e:
            # 發送錯誤訊息
            self.error_occurred.emit(str(e))
    
    def stop(self):
        """中斷訓練"""
        self.is_running = False
```

---

## 4. 後端架構 (Core Logic Layer)

### 4.1 模組結構

```
XBrainLab/
├── study.py                ← 核心協調器
│
├── load_data/              ← 資料載入模組
│   ├── raw_data_loader.py  ← 檔案讀取器
│   ├── raw.py              ← Raw 資料封裝
│   ├── label_loader.py     ← 標籤讀取
│   └── event_loader.py     ← 事件轉換
│
├── preprocessor/           ← 預處理模組
│   ├── base.py             ← 預處理器基類
│   ├── preprocess.py       ← 具體預處理器
│   │   ├── BandpassFilter
│   │   ├── Resample
│   │   ├── TimeEpoch
│   │   ├── Normalization
│   │   └── ...
│   └── option.py           ← 預處理選項 Enum
│
├── dataset/                ← 資料集管理模組
│   ├── epochs.py           ← Epochs 封裝
│   ├── dataset.py          ← Dataset 類別
│   ├── dataset_generator.py ← 資料集生成器
│   └── data_splitter.py    ← 分割策略
│
├── training/               ← 訓練模組
│   ├── trainer.py          ← 訓練器主類別
│   ├── training_plan.py    ← 訓練計畫 (ModelHolder)
│   ├── option.py           ← 訓練選項 (TrainingOption)
│   └── model_holder.py     ← 模型容器
│
├── model_base/             ← 深度學習模型
│   ├── EEGNet.py
│   ├── SCCNet.py
│   └── ShallowConvNet.py
│
├── evaluation/             ← 評估模組
│   └── metric.py           ← 評估指標 Enum
│
├── visualization/          ← 視覺化模組
│   ├── base.py             ← Visualizer 基類
│   └── visualizer.py       ← 具體視覺化器
│
└── utils/                  ← 工具模組
    ├── check.py            ← 型別驗證
    ├── logger.py           ← 日誌記錄
    ├── seed.py             ← 隨機種子管理
    └── filename_parser.py  ← 檔名解析
```

### 4.2 核心類別：Study

```python
class Study:
    """
    後端核心協調器
    
    職責：
    1. 管理整個分析流程的狀態
    2. 協調各模組之間的互動
    3. 提供統一的 API 給前端呼叫
    4. 維護資料流轉的一致性
    """
    
    def __init__(self):
        # === 資料載入相關 ===
        self.raw_list: List[Raw] = []           # 已載入的原始資料
        self.loader: RawDataLoader = None       # 資料載入器
        
        # === 預處理相關 ===
        self.preprocessors: List[PreprocessBase] = []  # 預處理器列表
        self.epochs: Epochs = None              # Epochs 物件
        
        # === 資料集相關 ===
        self.datasets: List[Dataset] = []       # 生成的資料集
        self.dataset_generator: DatasetGenerator = None
        
        # === 訓練相關 ===
        self.training_option: TrainingOption = None  # 訓練參數
        self.model_holder: ModelHolder = None        # 模型容器
        self.trainer: Trainer = None                 # 訓練器
        
        # === 評估相關 ===
        self.evaluation_results: dict = {}      # 評估結果
        
        # === 視覺化相關 ===
        self.visualizer: Visualizer = None      # 視覺化器
    
    # ========== 資料載入 API ==========
    def get_loader(self) -> RawDataLoader:
        """取得資料載入器"""
        if self.loader is None:
            self.loader = RawDataLoader()
        return self.loader
    
    def set_loaded_data_list(self, raw_list: List[Raw], force=False):
        """設定已載入的資料列表"""
        # 驗證一致性 (頻道數、採樣率)
        if not force:
            self._validate_raw_list(raw_list)
        
        self.raw_list = raw_list
    
    # ========== 預處理 API ==========
    def add_preprocessor(self, preprocessor: PreprocessBase):
        """添加預處理器"""
        self.preprocessors.append(preprocessor)
    
    def apply_preprocessing(self):
        """應用所有預處理器"""
        for raw in self.raw_list:
            for preprocessor in self.preprocessors:
                raw = preprocessor.apply(raw)
        
        # 自動生成 Epochs (如果包含 TimeEpoch 預處理)
        self._generate_epochs_if_needed()
    
    # ========== 資料集 API ==========
    def get_dataset_generator(self) -> DatasetGenerator:
        """取得資料集生成器"""
        if self.dataset_generator is None:
            self.dataset_generator = DatasetGenerator(self.epochs)
        return self.dataset_generator
    
    def set_datasets(self, datasets: List[Dataset]):
        """設定生成的資料集"""
        self.datasets = datasets
    
    # ========== 訓練 API ==========
    def set_training_option(self, option: TrainingOption):
        """設定訓練參數"""
        self.training_option = option
    
    def set_model_holder(self, holder: ModelHolder):
        """設定模型容器"""
        self.model_holder = holder
    
    def generate_plan(self):
        """生成訓練計畫"""
        # 驗證必要條件
        if not self.datasets:
            raise ValueError("No datasets available")
        if not self.training_option:
            raise ValueError("Training option not set")
        if not self.model_holder:
            raise ValueError("Model not selected")
        
        # 創建 Trainer
        self.trainer = Trainer(
            datasets=self.datasets,
            training_option=self.training_option,
            model_holder=self.model_holder
        )
    
    def train(self):
        """啟動訓練"""
        if not self.trainer:
            raise ValueError("Training plan not generated")
        
        self.trainer.run()
    
    def stop_training(self):
        """停止訓練"""
        if self.trainer:
            self.trainer.interrupt()
    
    # ========== 評估 API ==========
    def evaluate(self):
        """評估模型"""
        if not self.trainer:
            raise ValueError("No trained model")
        
        self.evaluation_results = self.trainer.evaluate()
        return self.evaluation_results
    
    # ========== 視覺化 API ==========
    def get_visualizer(self) -> Visualizer:
        """取得視覺化器"""
        if self.visualizer is None:
            self.visualizer = Visualizer(self.trainer)
        return self.visualizer
```

**設計特點**：
- ✅ 單一入口點：所有後端操作都透過 `Study`
- ✅ 狀態管理：追蹤整個流程的當前狀態
- ✅ 驗證機制：每個步驟都檢查前置條件
- ✅ 錯誤處理：提供清晰的錯誤訊息

---

## 5. 前後端連接機制

### 5.1 連接模式：共享 Study 實例

```python
# main_window.py
class MainWindow(QMainWindow):
    def __init__(self):
        # 1. 創建唯一的 Study 實例
        self.study = Study()
        
        # 2. 傳遞給所有面板
        self.dashboard_panel = DashboardPanel(self, self.study)
        self.training_panel = TrainingPanel(self, self.study)
        self.evaluation_panel = EvaluationPanel(self, self.study)
```

**優點**：
- ✅ 所有面板看到相同的資料狀態
- ✅ 無需複雜的訊息傳遞機制
- ✅ 易於測試 (可以獨立測試 Study)

### 5.2 資料流向

```
User Action (UI) → Signal/Slot → Panel Method → Study API → Backend Module
                                                      ↓
                                             Update Study State
                                                      ↓
                                              UI Refresh (Pull)
```

**範例：載入資料流程**

```python
# 1. UI 事件
def load_data_clicked(self):
    file_path = QFileDialog.getOpenFileName(...)
    
    # 2. 呼叫後端 API
    loader = self.study.get_loader()
    raw = load_raw_file(file_path)
    loader.append(raw)
    
    # 3. 設定到 Study
    self.study.set_loaded_data_list(loader.raw_list)
    
    # 4. 更新 UI
    self.refresh_file_list()

# 5. UI 從 Study 拉取最新狀態
def refresh_file_list(self):
    self.file_list_widget.clear()
    for raw in self.study.raw_list:
        item = QListWidgetItem(raw.get_filename())
        self.file_list_widget.addItem(item)
```

### 5.3 跨執行緒通訊：Signal/Slot

```python
# TrainingWorker (Worker Thread)
class TrainingWorker(QThread):
    progress_updated = pyqtSignal(int, int, float, float)
    
    def run(self):
        # 在 Worker Thread 執行
        for epoch in range(100):
            loss, acc = self.train_one_epoch()
            
            # 發送 Signal (線程安全)
            self.progress_updated.emit(epoch, 100, loss, acc)

# TrainingPanel (Main Thread)
class TrainingPanel(QWidget):
    def start_training(self):
        self.worker = TrainingWorker(self.study)
        
        # 連接 Signal 到 Slot (在 Main Thread 執行)
        self.worker.progress_updated.connect(self.update_progress)
        self.worker.start()
    
    def update_progress(self, epoch, total, loss, acc):
        # 在 Main Thread 中安全地更新 UI
        self.progress_bar.setValue(int(epoch / total * 100))
        self.loss_label.setText(f"Loss: {loss:.4f}")
```

---

## 6. 資料流程

### 6.1 完整分析流程

```
1. Load Data
   ├─ User: Select GDF/SET file
   ├─ UI: DashboardPanel.load_data_clicked()
   ├─ Backend: load_data.load_raw_file()
   └─ Study: set_loaded_data_list()

2. Preprocessing
   ├─ User: Configure filters, resampling, epoching
   ├─ UI: PreprocessWidget.apply_clicked()
   ├─ Backend: preprocessor.apply()
   └─ Study: apply_preprocessing()

3. Generate Dataset
   ├─ User: Set train/test split ratio
   ├─ UI: DatasetGenWidget.generate_clicked()
   ├─ Backend: dataset_generator.generate()
   └─ Study: set_datasets()

4. Configure Training
   ├─ User: Select model, set hyperparameters
   ├─ UI: TrainingSettingDialog.accept()
   ├─ Backend: TrainingOption()
   └─ Study: set_training_option(), set_model_holder()

5. Generate Training Plan
   ├─ User: Click "Generate Plan"
   ├─ UI: TrainingPanel.generate_plan_clicked()
   ├─ Backend: Trainer()
   └─ Study: generate_plan()

6. Train Model
   ├─ User: Click "Start Training"
   ├─ UI: TrainingPanel.start_training()
   ├─ Backend (Worker Thread): Trainer.run()
   └─ Study: train()

7. Evaluate Model
   ├─ User: Switch to Evaluation tab
   ├─ UI: EvaluationPanel.refresh()
   ├─ Backend: Trainer.evaluate()
   └─ Study: evaluate()

8. Visualize Results
   ├─ User: Select visualization type
   ├─ UI: VisualizationPanel.plot_clicked()
   ├─ Backend: Visualizer.generate()
   └─ Study: get_visualizer()
```

### 6.2 資料物件轉換

```
Raw File (GDF/SET)
    ↓ load_raw_file()
Raw Object (封裝 MNE Raw)
    ↓ apply_preprocessing()
Preprocessed Raw
    ↓ TimeEpoch preprocessor
Epochs Object (封裝 MNE Epochs)
    ↓ DatasetGenerator
Dataset Objects (train/val/test split)
    ↓ Trainer
PyTorch DataLoader
    ↓ Model.forward()
Predictions
    ↓ Evaluator
Metrics (ACC, AUC, Kappa)
    ↓ Visualizer
Plots (Saliency Map, Confusion Matrix)
```

---

## 7. 關鍵類別與職責

### 7.1 前端關鍵類別

| 類別 | 檔案 | 職責 |
|------|------|------|
| `MainWindow` | `ui_pyqt/main_window.py` | 主視窗，管理所有面板與 Study 物件 |
| `DashboardPanel` | `ui_pyqt/dashboard_panel/` | 資料管理、預處理、資料集生成 |
| `TrainingPanel` | `ui_pyqt/training/panel.py` | 訓練控制、進度顯示、即時指標 |
| `TrainingWorker` | `ui_pyqt/training/panel.py` | 訓練執行緒，避免 UI 凍結 |
| `EvaluationPanel` | `ui_pyqt/evaluation/panel.py` | 評估結果顯示、混淆矩陣 |
| `VisualizationPanel` | `ui_pyqt/visualization/panel.py` | 顯著性圖、頻譜圖等視覺化 |
| `TrainingSettingDialog` | `ui_pyqt/training/training_setting.py` | 訓練參數設定對話框 |

### 7.2 後端關鍵類別

| 類別 | 檔案 | 職責 |
|------|------|------|
| `Study` | `study.py` | 核心協調器，管理整個流程狀態 |
| `Raw` | `load_data/raw.py` | 封裝 MNE Raw/Epochs 物件 |
| `RawDataLoader` | `load_data/raw_data_loader.py` | 載入與驗證多個 Raw 物件 |
| `PreprocessBase` | `preprocessor/base.py` | 預處理器抽象基類 |
| `BandpassFilter` | `preprocessor/preprocess.py` | 帶通濾波器 |
| `TimeEpoch` | `preprocessor/preprocess.py` | 依事件切分 Epochs |
| `Epochs` | `dataset/epochs.py` | 封裝 Epochs 資料與元資料 |
| `DatasetGenerator` | `dataset/dataset_generator.py` | 生成訓練/驗證/測試資料集 |
| `Dataset` | `dataset/dataset.py` | 單一資料集 (含遮罩) |
| `TrainingOption` | `training/option.py` | 訓練參數配置 |
| `ModelHolder` | `training/model_holder.py` | 模型容器 (型別、參數) |
| `Trainer` | `training/trainer.py` | 訓練器主邏輯 |
| `TrainingPlanHolder` | `training/training_plan.py` | 單一訓練計畫執行器 |
| `EEGNet` | `model_base/EEGNet.py` | EEGNet 模型實作 |
| `Visualizer` | `visualization/visualizer.py` | 視覺化生成器 |

---

## 8. 模組依賴關係

### 8.1 依賴圖

```
ui_pyqt (前端)
    ↓ 依賴
study (協調器)
    ↓ 依賴
┌────────┬─────────────┬─────────────┬──────────────┐
│        │             │             │              │
load_data  preprocessor  dataset     training    visualization
    ↓          ↓            ↓            ↓             ↓
  utils     utils        utils       model_base    evaluation
```

### 8.2 前端依賴規則

**✅ 允許的依賴**：
- `ui_pyqt` → `study`
- `ui_pyqt` → `load_data` (僅用於型別提示)
- `ui_pyqt` → `preprocessor` (僅用於型別提示)

**❌ 禁止的依賴**：
- 後端模組 → `ui_pyqt` (後端完全不依賴前端)
- `ui_pyqt` 面板之間的直接依賴 (透過 `Study` 通訊)

### 8.3 後端依賴規則

**✅ 允許的依賴**：
- 任何模組 → `utils`
- `study` → 所有後端模組
- `training` → `model_base`, `dataset`, `evaluation`
- `dataset` → `load_data`, `preprocessor`

**❌ 循環依賴**：
- 嚴格禁止任何循環依賴

---

## 9. 檔案結構

```
XBrainlab_with_agent/
├── XBrainLab/                  # 主程式碼目錄
│   ├── __init__.py
│   ├── study.py                # 核心協調器 ★
│   │
│   ├── ui_pyqt/                # 前端 UI (PyQt6) ★
│   │   ├── __init__.py
│   │   ├── main_window.py      # 主視窗
│   │   ├── dashboard_panel/    # 資料管理面板
│   │   │   ├── data_management.py
│   │   │   ├── preprocess.py
│   │   │   └── dataset_gen.py
│   │   ├── training/           # 訓練面板
│   │   │   ├── panel.py
│   │   │   ├── training_setting.py
│   │   │   └── training_plan.py
│   │   ├── evaluation/         # 評估面板
│   │   │   └── panel.py
│   │   ├── visualization/      # 視覺化面板
│   │   │   └── panel.py
│   │   └── tests/              # UI 測試
│   │
│   ├── load_data/              # 資料載入模組
│   │   ├── raw_data_loader.py
│   │   ├── raw.py
│   │   ├── label_loader.py
│   │   ├── event_loader.py
│   │   └── tests/
│   │
│   ├── preprocessor/           # 預處理模組
│   │   ├── base.py
│   │   ├── preprocess.py
│   │   ├── option.py
│   │   └── tests/
│   │
│   ├── dataset/                # 資料集管理模組
│   │   ├── epochs.py
│   │   ├── dataset.py
│   │   ├── dataset_generator.py
│   │   ├── data_splitter.py
│   │   └── tests/
│   │
│   ├── training/               # 訓練模組
│   │   ├── trainer.py
│   │   ├── training_plan.py
│   │   ├── option.py
│   │   ├── model_holder.py
│   │   └── tests/
│   │
│   ├── model_base/             # 深度學習模型
│   │   ├── EEGNet.py
│   │   ├── SCCNet.py
│   │   ├── ShallowConvNet.py
│   │   └── tests/
│   │
│   ├── evaluation/             # 評估模組
│   │   ├── metric.py
│   │   └── tests/
│   │
│   ├── visualization/          # 視覺化模組
│   │   ├── base.py
│   │   ├── visualizer.py
│   │   └── tests/
│   │
│   └── utils/                  # 工具模組
│       ├── check.py
│       ├── logger.py
│       ├── seed.py
│       ├── filename_parser.py
│       └── tests/
│
├── tests/                      # 整合測試
│   ├── test_io_integration.py
│   ├── test_pipeline_integration.py
│   ├── test_real_data_pipeline.py
│   ├── test_training_integration.py
│   └── test_e2e_training.py
│
├── test_data_small/            # 測試資料
│   └── A01T.gdf
│
├── documentation/              # 文檔
│   ├── testing_guide.md
│   ├── testing_improvements.md
│   └── architecture.md         # 本文件 ★
│
├── run.py                      # 啟動腳本
├── pytest.ini                  # pytest 配置
└── requirements.txt            # Python 依賴
```

---

## 10. 設計模式

### 10.1 單例模式 (Singleton)

**應用**：`Study` 物件在整個應用程式中只有一個實例

```python
class MainWindow(QMainWindow):
    def __init__(self):
        self.study = Study()  # 唯一實例
        
        # 所有面板共享
        self.panel1 = Panel1(self.study)
        self.panel2 = Panel2(self.study)
```

### 10.2 觀察者模式 (Observer)

**應用**：PyQt Signal/Slot 機制

```python
# Subject (被觀察者)
class TrainingWorker(QThread):
    progress_updated = pyqtSignal(int)  # Signal
    
    def run(self):
        self.progress_updated.emit(50)  # 通知觀察者

# Observer (觀察者)
class TrainingPanel(QWidget):
    def __init__(self):
        worker.progress_updated.connect(self.on_progress)  # 訂閱
    
    def on_progress(self, value):  # Slot
        self.progress_bar.setValue(value)
```

### 10.3 策略模式 (Strategy)

**應用**：預處理器系統

```python
class PreprocessBase(ABC):
    @abstractmethod
    def apply(self, raw: Raw) -> Raw:
        pass

class BandpassFilter(PreprocessBase):
    def apply(self, raw: Raw) -> Raw:
        # 濾波邏輯
        return filtered_raw

class Resample(PreprocessBase):
    def apply(self, raw: Raw) -> Raw:
        # 重採樣邏輯
        return resampled_raw

# 使用
study.add_preprocessor(BandpassFilter(8, 30))
study.add_preprocessor(Resample(250))
study.apply_preprocessing()  # 依序應用所有策略
```

### 10.4 門面模式 (Facade)

**應用**：`Study` 類別作為後端的統一介面

```python
class Study:
    """門面：隱藏複雜的後端邏輯"""
    
    def load_data(self, file_path):
        # 內部協調多個模組
        loader = RawDataLoader()
        raw = load_raw_file(file_path)
        loader.append(raw)
        self.set_loaded_data_list(loader.raw_list)

# UI 只需呼叫簡單的門面方法
study.load_data("data.gdf")
```

### 10.5 工廠模式 (Factory)

**應用**：模型創建

```python
class ModelHolder:
    """模型工廠"""
    
    def create_model(self):
        if self.model_type == "EEGNet":
            return EEGNet(**self.model_params)
        elif self.model_type == "SCCNet":
            return SCCNet(**self.model_params)
        # ...
```

---

## 11. 前後端互動範例

### 範例 1：載入資料

```python
# === 前端 (UI) ===
class DashboardPanel(QWidget):
    def load_data_clicked(self):
        # 1. 顯示檔案選擇對話框
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Select EEG File", "", "*.gdf *.set"
        )
        
        if not file_path:
            return
        
        # 2. 呼叫後端 API
        try:
            loader = self.study.get_loader()
            raw = load_raw_file(file_path)  # 後端函數
            loader.append(raw)
            self.study.set_loaded_data_list(loader.raw_list)
            
            # 3. 更新 UI
            self.refresh_file_list()
            QMessageBox.information(self, "Success", "Data loaded successfully")
            
        except Exception as e:
            QMessageBox.critical(self, "Error", str(e))
    
    def refresh_file_list(self):
        # 從 Study 拉取最新狀態
        self.list_widget.clear()
        for raw in self.study.raw_list:
            item = QListWidgetItem(raw.get_filename())
            self.list_widget.addItem(item)


# === 後端 (Core) ===
def load_raw_file(file_path: str) -> Raw:
    """載入 EEG 檔案"""
    if file_path.endswith('.gdf'):
        mne_raw = mne.io.read_raw_gdf(file_path, preload=True)
    elif file_path.endswith('.set'):
        mne_raw = mne.io.read_raw_eeglab(file_path, preload=True)
    else:
        raise ValueError(f"Unsupported format: {file_path}")
    
    return Raw(mne_raw, file_path)
```

### 範例 2：訓練模型

```python
# === 前端 (UI) ===
class TrainingPanel(QWidget):
    def start_training(self):
        # 1. 生成訓練計畫
        try:
            self.study.generate_plan()
        except Exception as e:
            QMessageBox.critical(self, "Error", str(e))
            return
        
        # 2. 創建 Worker Thread
        self.training_worker = TrainingWorker(self.study)
        
        # 3. 連接 Signals
        self.training_worker.progress_updated.connect(self.update_progress)
        self.training_worker.finished.connect(self.training_finished)
        self.training_worker.error_occurred.connect(self.training_error)
        
        # 4. 啟動訓練
        self.training_worker.start()
        
        # 5. 更新 UI 狀態
        self.start_button.setEnabled(False)
        self.stop_button.setEnabled(True)
    
    def update_progress(self, epoch, total, loss, acc):
        """在主執行緒中更新 UI (線程安全)"""
        self.progress_bar.setValue(int(epoch / total * 100))
        self.epoch_label.setText(f"Epoch: {epoch}/{total}")
        self.loss_label.setText(f"Loss: {loss:.4f}")
        self.acc_label.setText(f"Acc: {acc:.2%}")
        
        # 更新圖表
        self.loss_plot.add_point(epoch, loss)
        self.acc_plot.add_point(epoch, acc)


# === Worker Thread ===
class TrainingWorker(QThread):
    progress_updated = pyqtSignal(int, int, float, float)
    finished = pyqtSignal()
    error_occurred = pyqtSignal(str)
    
    def __init__(self, study: Study):
        super().__init__()
        self.study = study
    
    def run(self):
        """在背景執行訓練 (非主執行緒)"""
        try:
            trainer = self.study.trainer
            
            for epoch in range(trainer.total_epochs):
                # 訓練一個 epoch
                loss, acc = trainer.train_one_epoch()
                
                # 發送進度更新 (線程安全)
                self.progress_updated.emit(
                    epoch + 1,
                    trainer.total_epochs,
                    loss,
                    acc
                )
            
            self.finished.emit()
            
        except Exception as e:
            self.error_occurred.emit(str(e))


# === 後端 (Core) ===
class Trainer:
    def train_one_epoch(self) -> Tuple[float, float]:
        """訓練一個 epoch"""
        total_loss = 0.0
        correct = 0
        total = 0
        
        for batch_data, batch_labels in self.train_loader:
            # Forward
            outputs = self.model(batch_data)
            loss = self.criterion(outputs, batch_labels)
            
            # Backward
            self.optimizer.zero_grad()
            loss.backward()
            self.optimizer.step()
            
            # 統計
            total_loss += loss.item()
            _, predicted = outputs.max(1)
            correct += predicted.eq(batch_labels).sum().item()
            total += batch_labels.size(0)
        
        avg_loss = total_loss / len(self.train_loader)
        accuracy = correct / total
        
        return avg_loss, accuracy
```

---

## 12. 測試架構

### 12.1 測試層級

```
┌─────────────────────────────────────┐
│     E2E Tests (端對端測試)           │  ← tests/test_e2e_training.py
│  測試完整使用者流程                  │
└─────────────────────────────────────┘
            ↓ 依賴
┌─────────────────────────────────────┐
│  Integration Tests (整合測試)        │  ← tests/test_*_integration.py
│  測試模組之間的互動                  │
└─────────────────────────────────────┘
            ↓ 依賴
┌─────────────────────────────────────┐
│    Unit Tests (單元測試)             │  ← XBrainLab/*/tests/test_*.py
│  測試單一函數/類別                   │
└─────────────────────────────────────┘
```

### 12.2 測試統計

| 測試類型 | 測試數量 | 檔案數 | 說明 |
|---------|---------|--------|------|
| 單元測試 (Unit) | ~2100 | 27 | 測試單一函數/類別 |
| 整合測試 (Integration) | ~200 | 6 | 測試模組互動 |
| UI 測試 (UI) | ~20 | 16 | 測試 UI 元件 |
| E2E 測試 (E2E) | ~8 | 1 | 測試完整流程 |
| **總計** | **~2328** | **50** | |

### 12.3 測試覆蓋率

- **後端核心模組**: 85%+
- **資料處理模組**: 90%+
- **訓練模組**: 80%+
- **UI 模組**: 40%+
- **整體覆蓋率**: ~65%

### 12.4 最近的測試改進

根據 `documentation/testing_improvements.md`，最近的改進包括：

1. **真實物件測試取代 Mock**
   - 新增 `tests/test_training_integration.py`
   - 使用真實的 `TrainingOption`, `ModelHolder`
   - 驗證屬性存在與類型

2. **端對端測試**
   - 新增 `tests/test_e2e_training.py`
   - 測試訓練進度更新不重複彈窗
   - 測試 UI 與後端整合

3. **修復的 Bug**
   - `ModelHolder.model_name` → `target_model.__name__`
   - `optim_params` 不應包含 `lr`
   - `training_setting` → `training_option`
   - 進度條類型轉換問題

---

## 13. 待開發模組

### 13.1 Agent 模組 (LLM 助手)

**位置**：`XBrainLab/ui_pyqt/agent/` (待實作)

**架構設計**：
```
┌─────────────────────────────────────┐
│     AgentPanel (UI)                 │
│     - 聊天介面                       │
│     - 命令建議按鈕                   │
└────────────┬────────────────────────┘
             │ HTTP/WebSocket
┌────────────▼────────────────────────┐
│     Agent Server (FastAPI)          │
│     ├── LLMAgent                    │
│     ├── ToolExecutor                │
│     └── RAG Engine                  │
└────────────┬────────────────────────┘
             │ 呼叫
┌────────────▼────────────────────────┐
│     Study (後端核心)                 │
└─────────────────────────────────────┘
```

**重要原則**：
- Agent 透過 `Study` API 操作後端
- Agent 不直接操作 UI
- 保持前後端分離原則
- 使用 Tool Call 架構（參考待討論的 LLM 整合方案）

---

## 14. 總結

### 14.1 架構優勢

✅ **前後端完全分離**
- UI 與核心邏輯完全解耦
- 後端可獨立測試與開發
- 支援 Script 模式 (無 UI 運行)

✅ **狀態管理清晰**
- `Study` 作為唯一真相來源 (Single Source of Truth)
- 所有面板共享同一狀態
- 易於追蹤與除錯

✅ **並行處理支援**
- 訓練在 Worker Thread 執行
- UI 保持響應
- Signal/Slot 線程安全

✅ **模組化設計**
- 每個模組職責單一
- 低耦合高內聚
- 易於擴展新功能

✅ **測試完善**
- 單元測試覆蓋核心邏輯
- 整合測試驗證模組互動
- E2E 測試確保使用者流程正確

### 14.2 架構限制

⚠️ **UI 測試覆蓋不足**
- 目前 UI 測試僅 40%
- 需增加更多互動測試
- 正在改進中（參考 testing_improvements.md）

⚠️ **錯誤處理不夠統一**
- 部分模組使用 Exception
- 部分使用返回值
- 需建立統一的錯誤處理機制

⚠️ **日誌系統待完善**
- 目前日誌記錄不夠詳細
- 需增加更多關鍵點的日誌

### 14.3 未來改進方向

1. **增加 LLM Agent 模組**
   - 自然語言操控介面
   - 自動化常見操作
   - Tool Call 架構整合

2. **改進 UI 測試**
   - 增加 UI 整合測試
   - 模擬完整使用者流程
   - 使用真實物件取代 Mock

3. **統一錯誤處理**
   - 建立錯誤碼系統
   - 統一錯誤訊息格式

4. **增強日誌系統**
   - 詳細記錄每個操作
   - 支援日誌等級設定

5. **性能優化**
   - 大資料集處理優化
   - 記憶體使用優化

---

## 附錄

### A. 重要檔案快速索引

| 功能 | 關鍵檔案 |
|------|---------|
| 應用程式入口 | `run.py` |
| 主視窗 | `XBrainLab/ui_pyqt/main_window.py` |
| 核心協調器 | `XBrainLab/study.py` |
| 資料載入 | `XBrainLab/load_data/raw_data_loader.py` |
| 預處理 | `XBrainLab/preprocessor/preprocess.py` |
| 資料集生成 | `XBrainLab/dataset/dataset_generator.py` |
| 訓練器 | `XBrainLab/training/trainer.py` |
| 模型定義 | `XBrainLab/model_base/*.py` |
| 測試指南 | `documentation/testing_guide.md` |
| 測試改進 | `documentation/testing_improvements.md` |
| 架構文件 | `documentation/architecture.md` (本文件) |

### B. 常用命令

```bash
# 啟動應用程式
python run.py

# 執行所有測試
pytest tests/ XBrainLab/ -v

# 執行特定測試
pytest XBrainLab/training/tests/test_trainer.py -v

# 執行整合測試
pytest tests/test_training_integration.py -v

# 執行端對端測試
pytest tests/test_e2e_training.py -v

# 查看測試覆蓋率
pytest --cov=XBrainLab --cov-report=html

# 執行 UI 測試
pytest XBrainLab/ui_pyqt/tests/ -v
```

### C. 相關文檔

- **測試指南**: `documentation/testing_guide.md`
- **測試改進報告**: `documentation/testing_improvements.md`
- **LLM Agent 設計**: (待討論)

### D. 版本歷史

- **v2.0** (2025-01): 
  - 修正為 PyQt6 架構
  - 新增測試改進說明
  - 新增端對端測試範例
  - 準備 LLM Agent 整合

- **v1.0** (2024): 初始版本

---

**文件結束**

如有任何問題或需要更新，請聯繫專案維護者。