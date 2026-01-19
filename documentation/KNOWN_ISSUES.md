# 已知問題 (Known Issues)

本文件記錄目前專案中已確認存在的 Bug、限制與待解決的問題。

## 高優先級 - 架構問題

### Architecture Coupling (架構耦合)

**問題 1: Backend 依賴 PyQt6**
- [x] **已修復 (v0.4.6)**: `DatasetController` 已改用純 Python `Observable` 模式，移除 `QObject` 繼承。

**問題 2: Backend 反向引用 UI 層**
- [x] **已修復 (v0.4.6)**: `LabelImportService` 已移動至 `backend/services/`。

**問題 3: TrainingPanel 大量繞過 Controller**
- [x] **已修復 (v0.4.5)**: `TrainingPanel` 已完全透過 `TrainingController` 交互，移除了所有 `self.study` 引用。

**問題 4: AggregateInfoPanel 直接訪問 Study**
- [x] **已修復 (v0.4.4)**: 已重構為透過參數傳遞數據。

**問題 5: Dialog 層耦合**
- [x] **已修復 (v0.4.6)**: 審計並重構了所有 Dialog，確認無 `parent.study` 訪問。已加入 `tests/architecture_compliance.py` 防止回歸。

**問題 6: Agent 層直接持有 Study**
- `LLMController` 直接持有 Study 引用並傳給所有 Tools
- 應該透過抽象接口（如 `BackendFacade`）而非具體 Study 類

**問題 7: 假解耦問題**（最隱蔽）
- 部分 Panel（如 `VisualizationPanel`）註釋了 `self.study`
- **所有 Controller 都持有 Study 引用** (必需，用於訪問資料)
- **所有 Panel 都需要 main_window.study** (已大幅改善，多數 Panel 改用 Controller)
- **[x] Circular Imports 修復 (v0.5.2)**: 解決了 `Study` 與 Controllers 之間的循環依賴，使用 `TYPE_CHECKING` 與 lazy imports 確保靜態分析 (Ruff/MyPy) 通過。

**狀態**：部分解決 (循環依賴已修復，但 Study 仍作為上帝物件存在)

---

## 高優先級 - 進行中工作 (In-Progress Work)

### Push Model to Pull Model Migration (推送模型遷移) ✅ COMPLETED
**問題**：架構文檔描述 Backend 應使用 Push Model (Signal 機制)，但實際開發中途暫停

**解決方案 (v0.5.1)**：
- 所有 Backend Controller 已遷移至 `Observable` 模式
    - `PreprocessController`, `TrainingController`, `VisualizationController`, `EvaluationController`
- UI Panels 使用 `QtObserverBridge` 自動訂閱事件
    - `PreprocessPanel` → `preprocess_changed`
    - `TrainingPanel` → `training_started`, `training_stopped`, `config_changed`
- QTimer 保留用於：Plot 去抖動、Training 進度輪詢（非狀態輪詢）

**狀態**：✅ 已完成 (2026-01-19)

---

### Real Tool Call Verification (真實工具呼叫驗證)
**問題**：Real Tools 單元測試已通過，但**尚未在實際 LLM Agent 對話中驗證**

**具體狀況**：
- `tests/unit/llm/tools/real/` 測試全部通過 (19/19)
- 未執行 `poetry run benchmark-llm` 進行端對端驗證
- Agent 在實際對話流程中呼叫 Backend 的行為未確認

**影響**：無法保證 Agent 能正確調用後端功能完成使用者任務

**建議**：
1. 執行 `benchmark-llm` 並確保核心 Happy Path 測試通過
2. 手動測試關鍵對話流程（Load → Preprocess → Train）

**狀態**：待驗證 (ROADMAP Track B Phase 4)

---

### Agent Tool Call Outstanding Features (Agent 工具呼叫待完成功能)
**問題**：Agent 的 Tool Call 機制尚有未完成的功能與優化

**具體項目**：
1. **Tool Output Visibility**: Tool 執行結果在 Chat 中的顯示方式可再優化
2. **Error Recovery**: Tool 執行失敗時的恢復機制不夠健壯
3. **Parameter Validation**: 部分工具的參數驗證可加強

**影響**：使用者體驗不佳，可能遇到難以理解的錯誤訊息

**狀態**：待優化 (ROADMAP Track B)

---

### Chat Panel Development Status (Chat Panel 開發狀態)
**問題**：Chat Panel UI 已完成 Copilot 風格重設計，但仍有待優化項目

**已完成**：
- [x] MessageBubble 類別封裝
- [x] 85% 寬度上限與動態調整
- [x] 串流支援與去除尾行空白
- [x] QToolButton 置中發送按鈕
- [x] 無邊框下拉選單
- [x] **模組拆分 (v0.5.1)**: 已將 `chat_panel.py` 拆分至 `ui/chat/` 目錄
- [x] **LLM→Panel Pipeline 驗證 (v0.5.1)**: 信號流程已驗證正確 (`generation_started`, `chunk_received`)
- [x] **Streaming Support (v0.5.2)**: 完整支援打字機效果串流顯示，修復了 UI 凍結與顯示延遲
- [x] **Tool Call 顯示 (v0.5.2)**: 實作 "Tool Executing..." 狀態顯示，並正確處理工具輸出 visibility

**待優化**：
- [ ] Markdown 渲染支援
- [ ] Code Block 語法高亮
- [ ] 圖片/附件顯示
- [ ] 訊息編輯/刪除功能
- [ ] 對話歷史持久化

**狀態**：MVP 完成，進階功能待開發

---

## 中優先級 - 代碼質量

### Error Handling Issues (錯誤處理問題)

**問題 1: 過於寬泛的異常捕獲**
- [x] **已修復 (v0.4.6)**: 已將關鍵模組的 `except Exception` 替換為 `logger.error(..., exc_info=True)`。

**問題 2: 裸 except 子句**
- [x] **已修復 (v0.4.5)**: `PreprocessController` 中的裸 `except:` 已移除。

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
- [x] **已修復 (v0.4.5)**: 實作了 `logger.py` 並在 UI/Backend 核心流程中取代了 `print`。

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

**狀態**：
- [x] **已修復 (v0.5.0)**: 架構演進為 **Observer Bridge** 模式。Backend 使用純 Python `Observable`，UI 使用 `QtObserverBridge` 轉發信號。這實現了文檔描述的 "Push Model" 精神，同時保持了 Backend 解耦。`ADR-004` 已更新。

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

---

## Agent/Facade MVP Limitations (Agent MVP 限制與妥協)

為了加速開發 Agent 最小可行產品 (MVP)，我們在設計上做出了以下妥協：

### 1. Label Attachment Simplification (標籤綁定簡化)
- **限制**: `BackendFacade.attach_labels` 目前預設 Agent 能夠提供準確的檔案對應 (`mapping`)。
- **妥協**: 不在後端實作複雜的模糊匹配邏輯，維持 MVP 範疇。
- **假設**: 標籤檔案與數據檔案為 1-to-1 關係，且標籤事件數量與 Trigger 數量完全一致 (適用於 BCIC IV 等標準資料集)。
- **影響**: 若資料集標註不完整或需要複雜的 Event ID 過濾，目前的 Facade 可能無法處理，需人工介入預處理。

### 2. Facade Completeness (Facade 完整性)
- **限制**: `BackendFacade` 雖然涵蓋了大多數 Controller 功能，但部分邊緣功能 (如複雜的 `ChannelSelection` 回滾邏輯、特定的 Plotting 參數) 尚未暴露。
- **妥協**: 只暴露 Agent `tool_definitions.md` 中定義的核心功能。
- **影響**: Agent 無法執行 UI 上某些進階操作。

### 3. Native Function Calling Support (原生 Tool Call 支援)
- **限制**: 系統目前不使用 LLM 的原生 Function Calling API (如 OpenAI `tools` 或 Gemini `function_declarations`)。
- **實作**: 採用 **ReAct (Reason + Act)** 模式，依賴 Prompt Engineering 引導模型輸出 JSON，並使用 Regex 解析。
- **影響**: 對於較弱的模型 (如 Gamma-2B)，JSON 格式錯誤率可能較高。
- **對策**: 透過 RAG (Retrieval Augmented Generation) 檢索正確的 Few-Shot 範例 (`gold_set.json`) 來穩定輸出格式，而非依賴模型微調能力。這是 "Option A (RAG)" 優於等待 "Native Tool Call" 的主要原因。

顯示有問題有時侯不會顯示所有字 而是要透過拉寬拉短才會顯示所有字
LOAD DATA 有成功 LOAD 但需要切換 PANEL 才會顯示
