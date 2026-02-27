# Backend Architecture

## Overview

Backend 採用 **Controller-Service-State** 分層架構，核心設計原則：

- **Headless 可執行**: 完全不依賴 PyQt6，可在無 GUI 環境下運作
- **單一信任源**: `Study` 持有所有實驗狀態，內部委派至 `DataManager` + `TrainingManager`
- **Observer 解耦**: 透過 `Observable` 模式通知訂閱者
- **Facade 統一入口**: `BackendFacade` 為 Agent 與腳本提供簡化 API

## Study — 中央狀態容器

`Study` 是整個實驗的 Single Source of Truth，但不再直接持有所有狀態：

```
Study
├── data_manager: DataManager         # 資料生命週期管理
│   ├── loaded_data_list              # Raw EEG 檔案
│   ├── preprocessed_data_list        # 預處理後資料
│   ├── epoch_data                    # MNE Epochs
│   ├── datasets                      # PyTorch Datasets
│   └── dataset_generator             # Train/Val/Test 分割
│
└── training_manager: TrainingManager  # 訓練生命週期管理
    ├── model_holder                   # 模型 + 優化器
    ├── training_option                # 超參數
    ├── trainer                        # 訓練執行器
    └── saliency_params                # 視覺化參數
```

Study 透過 **Property Delegation** 暴露這些屬性，外部使用者（Controller）依然透過 `study.model_holder` 存取，無需知道內部委派。

## DataManager

從 Study 抽取的資料管理模組：

- 載入 → 預處理 → Epoching → Dataset 生成
- 資料備份與恢復（undo 支援）
- 鎖定機制（下游操作存在時防止修改上游資料）

## TrainingManager

從 Study 抽取的訓練管理模組：

- `set_model_holder` / `set_training_option` — 模型與超參數設定
- `generate_plan(datasets, output_dir)` — 根據資料集建立 `TrainingPlanHolder`
- `train` / `stop_training` / `is_training` — 訓練執行與控制
- `export_output_csv` — 結果匯出
- `get_saliency_params` / `set_saliency_params` — Saliency 視覺化參數

## Controllers

所有 Controller（除 ChatController）繼承 `Observable`：

| Controller | 事件 | 職責 |
|---|---|---|
| DatasetController | `data_changed`, `dataset_locked`, `import_finished` | 資料載入、移除、標籤管理 |
| PreprocessController | `preprocess_changed` | 濾波、重取樣、重參考 |
| TrainingController | `training_started`, `training_stopped`, `training_updated` | 訓練迴圈、進度監控 |
| EvaluationController | — | 評估指標計算 |
| VisualizationController | — | Saliency Map、Topomap |

## BackendFacade

為 Agent 與 Headless Scripts 提供簡化的高階 API：

```python
facade = BackendFacade()
facade.load_data(["/data/A01T.gdf"])
facade.apply_filter(low_freq=1.0, high_freq=40.0)
facade.set_model(model_name="EEGNet")
facade.configure_training(epoch=50, batch_size=64)
facade.run_training()
```

詳見 [完整後端文檔](../../documentation/backend/architecture.md)。
