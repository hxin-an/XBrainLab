# 已知問題 (Known Issues)

本文件記錄目前專案中已確認存在的 Bug、限制與待解決的問題。

## 高優先級 - 架構問題

### Architecture Coupling (架構耦合)

**問題 1: Backend 依賴 PyQt6**
- `DatasetController` 繼承 `QObject`，導致 Backend 依賴 PyQt6
- 影響：Backend 無法獨立運行、測試需 Qt 環境

**問題 2: Backend 反向引用 UI 層**
- `DatasetController` 引入 `XBrainLab.ui.services.label_import_service`（反向依賴）
- `LabelImportService` 錯誤地放在 `ui/services/` 而非 `backend/services/`

**問題 3: TrainingPanel 大量繞過 Controller**
- `TrainingPanel` 有 20+ 處直接訪問 `self.study`，完全繞過 `TrainingController`
- 範例：`self.study.datasets`, `self.study.model_holder`, `self.study.clean_datasets()`
- Controller 形同虛設

**問題 4: AggregateInfoPanel 直接訪問 Study**
- `ui/dashboard_panel/info.py:131` 直接訪問 `self.main_window.study`
- 違反信息隱藏原則

**問題 5: Dialog 層耦合**
- `TrainingSettingWindow` 訪問 `parent.study.training_option`
- 對話框應通過參數接收數據，而非訪問父組件內部狀態

**問題 6: Agent 層直接持有 Study**
- `LLMController` 直接持有 Study 引用並傳給所有 Tools
- 應該透過抽象接口（如 `BackendFacade`）而非具體 Study 類

**問題 7: 假解耦問題**（最隱蔽）
- 雖然部分 Panel（如 `VisualizationPanel`）註釋了 `self.study`
- 但仍通過 `main_window.study` 傳遞給 Controller
- **所有 Controller 都持有 Study 引用**
- **所有 Panel 都需要 main_window.study**
- **沒有真正解耦**

**影響**：Backend 無法獨立運行、測試需 Qt 環境、未來遷移困難、無法開發 CLI 工具或 API 服務

**建議**：
1. 實作事件系統（Observer Pattern）取代直接引用
2. 移動 `LabelImportService` 至 `backend/services/`
3. 重構所有 Panel，移除直接 Study 訪問
4. Controller 改為不持有 Study，改用事件訂閱

**預估工作量**：8-10 週全職工作

**狀態**：待重構 (高優先級 - 影響架構根基)

---

## 中優先級 - 代碼質量

### Error Handling Issues (錯誤處理問題)

**問題 1: 過於寬泛的異常捕獲**
- 發現 **16 處**使用 `except Exception:` 而非具體異常類型
- 位置：`ui/dashboard_panel/dataset.py` (3處), `backend/load_data/raw.py` (3處), `backend/utils/filename_parser.py` (4處) 等
- 影響：調試困難，無法針對性處理不同錯誤

**問題 2: 裸 except 子句**
- `backend/controller/preprocess_controller.py:81` 使用裸 `except:`
- 風險：會捕獲所有異常包括系統信號，可能導致程式無法正常停止
- 狀態：高優先級修復

**建議**：
```python
# 錯誤示範
try:
    operation()
except Exception:  # 太籠統
    pass

# 正確做法
try:
    operation()
except FileNotFoundError as e:
    logger.error(f"檔案不存在: {e}")
except PermissionError as e:
    logger.error(f"權限不足: {e}")
```

**狀態**：待改進（ROADMAP Track A Phase 2）

---

### Logging Insufficiency (日誌記錄不足)

**問題**：
- 只有 2 個 Backend 文件使用 `logging` 模組
- 大部分錯誤處理沒有記錄日誌，導致問題難以追蹤
- 缺少結構化日誌（無法區分不同模組、嚴重級別）

**影響**：
- 用戶報告 bug 時無法復現
- 生產環境問題難以調試
- 預處理操作缺少詳細步驟記錄（已在低優先級中提及）

**建議**：
1. 為每個模組添加 logger：`logger = logging.getLogger(__name__)`
2. 所有 except 塊記錄錯誤：`logger.error("...", exc_info=True)`
3. 關鍵流程記錄 info 級別日誌

**狀態**：待改進（ROADMAP Track A Phase 2）

---

### Architecture Documentation Inconsistency (架構文檔不一致)
**問題**：`documentation/agent/agent_architecture.md` 描述 Backend 應使用 Push Model (Signal 機制)，但實際代碼採用 Pull Model (輪詢機制)

**具體差異**：
- **文檔描述**：`Study` 應繼承 `QObject` 並發送 `data_loaded`, `training_finished` 等信號
- **實際實現**：`Study` 為純 Python 類別，UI 使用 `QTimer` 每 100ms 輪詢 Backend 狀態

**影響**：新貢獻者可能被誤導，按文檔實現會破壞現有架構

**決策記錄**：Pull Model 的選擇已記錄於 `ADR-004-ui-refresh-mechanism.md`

**建議**：更新 `agent_architecture.md` 第 3.2 節以反映實際的輪詢機制

**狀態**：待更新文檔（可立即修復）

---

## 中優先級 - 測試覆蓋

### Complex UI Interaction Testing Gap (複雜 UI 互動測試缺口)
**問題**：現有測試多使用 Mock，缺少真實 Qt Widget 互動驗證（點擊順序、拖拉、對話框互動等）

**影響**：使用者實際操作流程中的問題可能無法及早發現

**建議**：引入 `pytest-qt` 深度測試核心 Panel，建立完整 E2E 測試（Import → Preprocess → Train）

**狀態**：待補強 (ROADMAP Track A Phase 3)

---

### Cross-Component State Sync Testing Gap (跨元件狀態同步測試缺口)
**問題**：缺少驗證多個 Panel 間狀態一致性的整合測試（例如切換 Tab 時某個 Panel 狀態不同步）

**影響**：Pull Model 架構下，狀態輪詢邏輯錯誤可能導致 UI 顯示不一致

**建議**：增加跨 Panel 的狀態同步驗證測試

**狀態**：待補強 (ROADMAP Track A Phase 3)

---

### Environment-Dependent Testing Gap (環境相依測試缺口)
**問題**：缺少 CI/CD 自動化管線，無法驗證不同 OS（Windows/Linux）、Python 版本、GPU vs CPU 環境下的行為差異

**影響**：跨平台問題只能在使用者報告後才發現

**建議**：設定 GitHub Actions 自動執行測試與 Linting

**狀態**：待建置 (ROADMAP Track A Phase 3)

---

### Headless Qt/Torch Conflict
**問題**：無頭模式下需強制預載 Torch 以避免 SIGABRT

**狀態**：目前以 Workaround 處理 (`tests/conftest.py`)

---

## 中優先級 - 測試覆蓋

### Real Tools Integration Testing (真實工具整合測試)
**問題**：Real Tools 單元測試已通過 (19/19)，但尚未通過 LLM Agent Benchmark 驗證

**影響**：無法確保 Agent 在實際對話流程中正確調用 Backend

**建議**：執行 `benchmark-llm` 並確保核心 Happy Path 測試通過

**狀態**：待驗證 (ROADMAP Track B Phase 4)

---

### Label Attachment Simplified Implementation (Label 附加簡化實作 - MVP 設計限制)
**問題**：`RealAttachLabelsTool` 採用簡化實作，未整合完整的 `EventLoader` 對齊邏輯

**對比**：UI 已有完整實作（`EventFilterDialog` + `smart_filter`），可選擇特定 Event ID 並自動推薦

**具體限制**：
1. **假設**：Label 序列按時間順序對應 Raw 資料的**所有** Trigger
2. **無法選擇特定 Event**：不支援只對齊特定 Event ID (如只用 Left Hand 的 769)
3. **缺少序列對齊**：Label 數量與 Trigger 數量不匹配時，直接賦值可能導致錯誤
4. **缺少長度驗證**：沒有檢查 Label 數量是否與 Trigger 匹配

**適用場景** (約 70%)：
- Label 檔案已是完整 `(n,3)` MNE 格式
- Label 數量完全等於 Raw 資料的 Trigger 總數
- 使用標準公開資料集 (如 BCI Competition IV)

**繞過方案** (部分標註資料集)：
- 在 `epoch_data(event_id=["769"])` 階段過濾特定事件
- 分兩步操作：先載入全部 Label，再選擇性處理

**設計決策**：保持 Agent Tool MVP 簡單性，避免增加 `selected_event_ids` 等複雜參數

**狀態**：接受的設計限制（Design Limitation），不計畫增強。UI 路徑已有完整功能

---

### Montage Tool Incomplete Implementation (Montage 工具實作不完整)
**問題**：`RealSetMontageTool` 已實作自動通道matches邏輯，但未經過充分測試驗證

**具體狀況**：
- 自動匹配邏輯已完成（大小寫不敏感、前綴清理）
- Human-in-the-loop 機制已實作（部分匹配時回傳 "Request: Verify Montage"）
- 缺少針對各種通道命名格式的測試覆蓋

**影響**：Agent 設定 Montage 時可能因通道名稱格式差異導致匹配失敗

**建議**：增加測試案例覆蓋常見通道命名格式（EEG-Fz, Fp1, FP1 等）

**狀態**：功能已實作，待測試補強 (ROADMAP Track B Phase 4)

---

## 低優先級 - Agent & LLM Tools

### Real Tools Integration Testing (真實工具整合測試)
**問題**：Real Tools 單元測試已通過 (19/19)，但尚未通過 LLM Agent Benchmark 驗證

**影響**：無法確保 Agent 在實際對話流程中正確調用 Backend

**建議**：執行 `benchmark-llm` 並確保核心 Happy Path 測試通過

**狀態**：待驗證 (ROADMAP Track B Phase 4)

---

### Label Attachment Simplified Implementation (Label 附加簡化實作 - MVP 設計限制)
**問題**：`RealAttachLabelsTool` 採用簡化實作，未整合完整的 `EventLoader` 對齊邏輯

**對比**：UI 已有完整實作（`EventFilterDialog` + `smart_filter`），可選擇特定 Event ID 並自動推薦

**具體限制**：
1. **假設**：Label 序列按時間順序對應 Raw 資料的**所有** Trigger
2. **無法選擇特定 Event**：不支援只對齊特定 Event ID (如只用 Left Hand 的 769)
3. **缺少序列對齊**：Label 數量與 Trigger 數量不匹配時，直接賦值可能導致錯誤
4. **缺少長度驗證**：沒有檢查 Label 數量是否與 Trigger 匹配

**適用場景** (約 70%)：
- Label 檔案已是完整 `(n,3)` MNE 格式
- Label 數量完全等於 Raw 資料的 Trigger 總數
- 使用標準公開資料集 (如 BCI Competition IV)

**設計決策**：保持 Agent Tool MVP 簡單性，避免增加複雜參數

**狀態**：接受的設計限制（Design Limitation），不計畫增強。UI 路徑已有完整功能

---

### Montage Tool Incomplete Implementation (Montage 工具實作不完整)
**問題**：`RealSetMontageTool` 已實作自動通道匹配邏輯，但未經過充分測試驗證

**具體狀況**：
- 自動匹配邏輯已完成（大小寫不敏感、前綴清理）
- Human-in-the-loop 機制已實作（部分匹配時回傳 "Request: Verify Montage"）
- 缺少針對各種通道命名格式的測試覆蓋

**影響**：Agent 設定 Montage 時可能因通道名稱格式差異導致匹配失敗

**建議**：增加測試案例覆蓋常見通道命名格式（EEG-Fz, Fp1, FP1 等）

**狀態**：功能已實作，待測試補強 (ROADMAP Track B Phase 4)

---

## 功能與體驗改進

### Model Training & Epoch Duration (模型訓練與 Epoch 長度)
**問題**：某些模型（EEGNet, ShallowConvNet）使用池化層，若 Epoch 長度過短會導致維度錯誤

**建議**：
- 確保 Epoch 長度（`tmax - tmin`）足夠長
- 採樣率 250Hz 時建議最小 0.5-1.0 秒
- 遇到 "non-positive dimension" 錯誤時增加 Epoch 長度

---

### Preprocessing Logging (預處理日誌)
**狀態**：部分實作

**已有**：
- Backend 已有 Logger 基礎設施 (`backend/utils/logger.py`)
- 多處已集成日誌（如 `DatasetController`, 錯誤處理等）

**缺少**：
- 預處理操作的**詳細步驟日誌**（濾波參數、重採樣率等）
- 未統一封裝在 `PreprocessBase` 層級

**影響**：使用者需依賴 History 面板或最終狀態來驗證操作

**建議**：為所有預處理操作添加結構化日誌輸出

---

## 參考資料 (References)

詳細的架構決策與設計討論請參考：
- **Pull vs Push Model 決策**：`documentation/decisions/ADR-004-ui-refresh-mechanism.md`
- **LangChain 採用評估**：`documentation/decisions/ADR-001-langchain-adoption.md`
- **Multi-Agent 願景**：`documentation/decisions/ADR-002-multi-agent-vision.md`
- **向量資料庫選擇**：`documentation/decisions/ADR-003-vector-store-qdrant.md`
