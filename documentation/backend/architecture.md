# Backend 架構詳細說明 (Backend Architecture Details)

## 概述

Backend 是 XBrainLab 的核心層，負責所有數據處理、邏輯運算與狀態管理。採用 Headless 設計，完全獨立於 UI，可在無圖形界面環境下運行。

## 主要組件

### 1. Study (狀態管理)
Study 是系統的中央狀態容器，持有所有運行時數據。
- **屬性**：
  - `datasets`: 已載入的腦波數據集列表
  - `models`: 訓練完成的模型實例
  - `current_model`: 當前活躍模型
  - `training_history`: 訓練記錄與指標
- **方法**：
  - `add_dataset(dataset)`: 添加數據集
  - `remove_dataset(id)`: 移除數據集
  - `save_state()`: 保存狀態到磁盤
  - `load_state()`: 從磁盤載入狀態

### 2. Controllers (邏輯控制器)
負責具體業務邏輯的執行，每個控制器專注於特定領域。

#### DatasetController
處理數據集相關操作：
- `load_data(file_path)`: 載入數據文件 (.gdf, .mat 等)
- `preprocess_data(config)`: 應用預處理 (濾波、重參考)
- `validate_data()`: 數據品質檢查
- `export_data(format)`: 導出數據

#### TrainingController
管理模型訓練流程：
- `start_training(config)`: 啟動訓練任務
- `pause_training()`: 暫停訓練
- `resume_training()`: 恢復訓練
- `stop_training()`: 停止訓練
- `get_training_status()`: 獲取訓練狀態

#### EvaluationController
執行模型評估與解釋：
- `evaluate_model(test_data)`: 計算性能指標
- `generate_saliency_map(data)`: 生成顯著圖
- `assess_data_value(dataset)`: 評估數據價值

### 3. Services (服務層)
提供通用功能服務：

#### DataService
數據 I/O 與格式轉換：
- 支援多種腦波數據格式
- 數據驗證與清理
- 記憶體優化載入

#### ModelService
模型管理與推理：
- PyTorch 模型載入/保存
- GPU 資源管理
- 批量推理優化

#### NotificationService
實際上是基於 `Observable` 類的事件通知系統：
- 實現觀察者模式，支持事件訂閱與通知。
- 與 UI 的 `QtObserverBridge` 配合，實現線程安全的 Qt 信號轉發。
- 事件類型包括 `data_loaded`, `training_started`, `model_evaluated` 等。

### 4. BackendFacade (門面)
專為 Agent 設計的統一接口：
- `execute_command(command, params)`: 通用命令執行
- `get_system_status()`: 獲取系統狀態摘要
- `register_callback(event, callback)`: 註冊事件回調

## 數據流與狀態管理

### 數據載入流程
1. Facade 接收 `load_data` 命令
2. DatasetController 驗證文件格式
3. DataService 讀取並預處理數據
4. Study 更新 datasets 列表
5. NotificationService 廣播 `data_loaded` 事件

### 訓練流程
1. TrainingController 初始化模型
2. 迭代訓練循環：
   - 前向傳播
   - 計算損失
   - 反向傳播
   - 更新參數
3. 定期保存檢查點
4. 訓練完成後更新 Study

## 性能優化

- **記憶體管理**：實現數據分頁載入，避免大數據集 OOM
- **GPU 利用**：自動檢測 GPU，優化批次大小
- **並發處理**：使用多線程處理 I/O 密集任務
- **快取機制**：快取常用計算結果

## 測試策略

- **單元測試**：各控制器與服務的獨立測試
- **整合測試**：端到端流程驗證
- **性能測試**：記憶體洩漏與速度基準測試

## 擴展點

- **插件系統**：支援自定義控制器與服務
- **配置驅動**：通過 YAML 配置添加新功能
- **事件鉤子**：允許第三方代碼鉤入事件循環