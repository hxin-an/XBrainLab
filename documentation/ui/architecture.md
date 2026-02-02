# UI 架構詳細說明 (UI Architecture Details)

## 概述

UI 層負責將 Backend 的狀態以圖形化方式呈現給人類使用者。採用被動觀察者模式，不持有業務邏輯，只負責顯示與用戶輸入收集。

## 主要組件

### 1. MainWindow (主窗口)
應用程式的主界面容器：
- **佈局管理**：使用 QVBoxLayout/QHBoxLayout 組織子組件
- **菜單系統**：文件、編輯、視圖、幫助菜單
- **狀態欄**：顯示當前操作狀態與進度
- **工具欄**：常用功能快捷按鈕

### 2. Panels (面板)
專門處理特定功能的子界面：

#### DatasetPanel
數據集管理界面：
- **數據列表**：顯示已載入數據集的樹狀結構
- **預覽視圖**：波形圖與統計信息
- **操作按鈕**：載入、移除、預處理
- **屬性編輯器**：修改數據集元數據

#### TrainingPanel
模型訓練控制界面：
- **參數配置**：學習率、批次大小、epoch 數
- **進度顯示**：訓練曲線、損失圖表
- **控制按鈕**：開始/暫停/停止訓練
- **日誌輸出**：實時訓練日誌

#### EvaluationPanel
模型評估與視覺化界面：
- **指標顯示**：準確率、F1 分數等
- **顯著圖視圖**：熱力圖顯示模型關注區域
- **比較工具**：多模型性能對比
- **導出功能**：保存評估報告

#### AgentPanel
AI 助手互動界面：
- **對話歷史**：顯示 Agent 回應與用戶輸入
- **指令輸入**：自然語言命令輸入框
- **狀態指示**：Agent 運行狀態 (思考/執行/完成)
- **建議操作**：Agent 推薦的下步動作

### 3. Widgets (小組件)
可重用的 UI 元素：

#### PlotWidget
數據視覺化組件：
- 基於 Matplotlib 或 PyQtGraph
- 支持波形圖、頻譜圖、熱力圖
- 互動式縮放與選擇

#### TableWidget
表格顯示組件：
- 數據集列表、模型參數表
- 排序、過濾、編輯功能
- 導出到 CSV/Excel

#### ProgressWidget
進度指示組件：
- 訓練進度條
- 估計剩餘時間
- 取消操作支持

### 4. Controllers (UI 控制器)
連接 UI 與 Backend 的橋接層：

#### UIManager
UI 狀態管理：
- 面板切換邏輯
- 主題與佈局配置
- 用戶偏好保存

#### EventHandler
事件處理與 Backend 通信：
- 按鈕點擊事件
- 菜單選擇事件
- Backend 通知響應

## 觀察者模式實現

### 事件訂閱
UI 在初始化時訂閱 Backend 事件：
```python
backend.register_observer('data_loaded', self.on_data_loaded)
backend.register_observer('training_progress', self.on_training_progress)
```

### 拉取更新
收到通知後，主動從 Backend 拉取最新狀態：
```python
def on_data_loaded(self):
    datasets = backend.get_datasets()
    self.dataset_panel.update_list(datasets)
```

### 異步更新
使用 QTimer 或線程確保 UI 響應性：
- 長時間操作在背景線程執行
- 進度更新通過信號槽機制

## 佈局與樣式

### 響應式設計
- 支持窗口大小調整
- 動態隱藏/顯示面板
- 自適應高 DPI 顯示

### 主題系統
- 明暗主題切換
- 自定義顏色方案
- 字體與圖標配置

## 用戶體驗優化

### 快捷鍵
- Ctrl+O: 載入數據
- Ctrl+S: 保存項目
- F5: 刷新視圖
- Ctrl+Z: 撤銷操作

### 錯誤處理
- 用戶友好的錯誤對話框
- 操作確認提示
- 自動恢復機制

### 輔助功能
- 鍵盤導航支持
- 屏幕閱讀器兼容
- 高對比度模式

## 測試與調試

### UI 測試
- 單元測試：個別組件功能
- 整合測試：完整用戶流程
- 可訪問性測試

### 性能監控
- UI 渲染時間
- 記憶體使用
- 事件響應延遲

## 擴展機制

### 插件支持
- 自定義面板
- 新增視圖類型
- 第三方 UI 組件

### 配置驅動
- JSON/YAML 配置 UI 佈局
- 動態載入自定義主題
