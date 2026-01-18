# 已知問題 (Known Issues)

本文件記錄目前專案中已確認存在的 Bug、限制與待解決的問題。

## 🔴 高優先級 (High Priority)

### Backend & Training
- [x] **Missing Training Parameters (訓練參數缺失)**：
    - **問題**：`configure_training` 工具不支援 `optimizer` (Adam/SGD) 與 `save_checkpoints_every` (Epochs) 參數。
    - **狀態**：已修復 (v0.3.5)。已更新 `TrainingOption` 與工具鏈。

- [x] **Training VRAM Leak (記憶體洩漏)**：
    - **問題**：`train_one_epoch` 中雖然已加入 `.detach().cpu()`，但在 Epoch 結束後未呼叫 `torch.cuda.empty_cache()`，長時訓練仍可能累積片段記憶體。
    - **狀態**：已修復 (v0.3.5)。已加入 `empty_cache`。

- [x] **Dataset RAM Usage (記憶體佔用)**：
    - **問題**：`Dataset.get_training_data` 使用 Numpy Boolean Masking 直接複製數據 (`X = data[mask]`)，導致記憶體倍增。
    - **狀態**：已修復 (v0.3.5)。已新增 Index helper 並警示使用者。

### Agent
- [x] **Agent Unbounded Memory (記憶體無限增長)**：
    - **問題**：`LLMController.history` 無上限增長，會導致 Context Window Overflow 或 Memory Leak。
    - **狀態**：已修復 (v0.3.5)。已實作 Sliding Window。

## 🟠 穩定性與架構 (Stability & Architecture)

- [x] **UI Silent Failures (靜默失敗)**：
    - **問題**：`AggregateInfoPanel.update_info` 與 `VisualizationPanel` 存在 `try...except: pass`，導致錯誤無法被發現。
    - **狀態**：已修復 (v0.3.5)。已加入 Logger。

- [ ] **Architecture Coupling (架構耦合)**：
    - **問題**：
        1. `DatasetController` 繼承 `QObject`，導致 Backend 依賴 PyQt6
        2. `DatasetController` 引入 `XBrainLab.ui.services.label_import_service`（反向依賴）
        3. 部分 UI Panel 繞過 Controller 直接存取 `study` 物件
    - **影響**：Backend 無法獨立運行、測試需 Qt 環境、未來遷移困難
    - **建議**：
        1. 將 `DatasetController` 改用觀察者模式
        2. 移動 `LabelImportService` 至 `backend/services/`
        3. 強制所有 UI 透過 Controller 存取 Backend
    - **狀態**：待重構。

## 🟡 文檔問題 (Documentation Issues)

- [ ] **Architecture Documentation Inconsistency (架構文檔不一致)**：
    - **問題**：`documentation/agent/agent_architecture.md` 描述 Backend 應使用 Push Model (Signal 機制)，但實際代碼採用 Pull Model (輪詢機制)
    - **具體差異**：
        - **文檔描述**：`Study` 應繼承 `QObject` 並發送 `data_loaded`, `training_finished` 等信號
        - **實際實現**：`Study` 為純 Python 類別，UI 使用 `QTimer` 每 100ms 輪詢 Backend 狀態
    - **影響**：新貢獻者可能被誤導，按文檔實現會破壞現有架構
    - **決策記錄**：Pull Model 的選擇已記錄於 `ADR-004-ui-refresh-mechanism.md`
    - **建議**：更新 `agent_architecture.md` 第 3.2 節以反映實際的輪詢機制
    - **狀態**：待更新文檔。

- [x] **Dependency Conflict (依賴衝突)**：
    - **問題**：`requirements.txt` 同時包含 `nvidia-*-cu11` 與 `nvidia-*-cu12`，且未鎖定 PyTorch 版本。
    - **狀態**：已修復 (v0.3.5)。已統一版本與移除衝突。

## 🟡 環境與測試 (Environment & Tests)

- [ ] **Test File Fragmentation (測試分散)**：
    - **問題**：測試檔案散落在 `XBrainLab/tests` 與各模組目錄中。
    - **狀態**：需統一移動至根目錄 `tests/`。

- [ ] **Headless Qt/Torch Conflict**：
    - **問題**：無頭模式下需強制預載 Torch 以避免 SIGABRT。
    - **狀態**：目前以 Workaround 處理 (`tests/conftest.py`)。

- [ ] **Complex UI Interaction Testing Gap (複雜 UI 互動測試缺口)**：
    - **問題**：現有測試多使用 Mock，缺少真實 Qt Widget 互動驗證（點擊順序、拖拉、對話框互動等）。
    - **影響**：使用者實際操作流程中的問題可能無法及早發現。
    - **建議**：引入 `pytest-qt` 深度測試核心 Panel，建立完整 E2E 測試（Import → Preprocess → Train）。
    - **狀態**：待補強（ROADMAP Track A Phase 3）。

- [ ] **Cross-Component State Sync Testing Gap (跨元件狀態同步測試缺口)**：
    - **問題**：缺少驗證多個 Panel 間狀態一致性的整合測試（例如切換 Tab 時某個 Panel 狀態不同步）。
    - **影響**：Pull Model 架構下，狀態輪詢邏輯錯誤可能導致 UI 顯示不一致。
    - **建議**：增加跨 Panel 的狀態同步驗證測試。
    - **狀態**：待補強（ROADMAP Track A Phase 3）。

- [ ] **Environment-Dependent Testing Gap (環境相依測試缺口)**：
    - **問題**：缺少 CI/CD 自動化管線，無法驗證不同 OS（Windows/Linux）、Python 版本、GPU vs CPU 環境下的行為差異。
    - **影響**：跨平台問題只能在使用者報告後才發現。
    - **建議**：設定 GitHub Actions 自動執行測試與 Linting。
    - **狀態**：待建置（ROADMAP Track A Phase 3）。

## � Agent & LLM Tools (Agent 與 LLM 工具)

- [ ] **Real Tools Integration Testing (真實工具整合測試)**：
    - **問題**：Real Tools 單元測試已通過 (19/19)，但尚未通過 LLM Agent Benchmark 驗證。
    - **影響**：無法確保 Agent 在實際對話流程中正確調用 Backend。
    - **建議**：執行 `benchmark-llm` 並確保核心 Happy Path 測試通過。
    - **狀態**：待驗證（ROADMAP Track B Phase 4）。
- [ ] **Label Attachment Simplified Implementation (Label 附加簡化實作 - MVP 設計限制)**：
    - **問題**：`RealAttachLabelsTool` 採用簡化實作，未整合完整的 `EventLoader` 對齊邏輯。
    - **對比**：UI 已有完整實作（`EventFilterDialog` + `smart_filter`），可選擇特定 Event ID 並自動推薦。
    - **具體限制**：
        1. **假設**：Label 序列按時間順序對應 Raw 資料的**所有** Trigger
        2. **無法選擇特定 Event**：不支援只對齊特定 Event ID (如只用 Left Hand 的 769)
        3. **缺少序列對齊**：Label 數量與 Trigger 數量不匹配時，直接賦值可能導致錯誤
        4. **缺少長度驗證**：沒有檢查 Label 數量是否與 Trigger 匹配
    - **適用場景** (約 70%)：
        - Label 檔案已是完整 `(n,3)` MNE 格式
        - Label 數量完全等於 Raw 資料的 Trigger 總數
        - 使用標準公開資料集 (如 BCI Competition IV)
    - **繞過方案** (部分標註資料集)：
        - 在 `epoch_data(event_id=["769"])` 階段過濾特定事件
        - 分兩步操作：先載入全部 Label，再選擇性處理
    - **設計決策**：保持 Agent Tool MVP 簡單性，避免增加 `selected_event_ids` 等複雜參數
    - **狀態**：接受的設計限制（Design Limitation），不計畫增強。UI 路徑已有完整功能。
- [ ] **Montage Tool Incomplete Implementation (Montage 工具實作不完整)**：
    - **問題**：`RealSetMontageTool` 已實作自動通道匹配邏輯，但未經過充分測試驗證。
    - **具體狀況**：
        - 自動匹配邏輯已完成（大小寫不敏感、前綴清理）
        - Human-in-the-loop 機制已實作（部分匹配時回傳 "Request: Verify Montage"）
        - 缺少針對各種通道命名格式的測試覆蓋
    - **影響**：Agent 設定 Montage 時可能因通道名稱格式差異導致匹配失敗。
    - **建議**：增加測試案例覆蓋常見通道命名格式（EEG-Fz, Fp1, FP1 等）。
    - **狀態**：功能已實作，待測試補強（ROADMAP Track B Phase 4）。

## �🟢 功能與體驗 (Features & UX)

### Model Training & Epoch Duration (模型訓練與 Epoch 長度)
**問題**：某些模型（EEGNet, ShallowConvNet）使用池化層，若 Epoch 長度過短會導致維度錯誤。

**建議**：
- 確保 Epoch 長度（`tmax - tmin`）足夠長
- 採樣率 250Hz 時建議最小 0.5-1.0 秒
- 遇到 "non-positive dimension" 錯誤時增加 Epoch 長度

### Preprocessing Logging (預處理日誌缺失)
**問題**：預處理操作（濾波、重採樣等）缺少詳細日誌記錄。

**影響**：使用者需依賴 History 或最終狀態檢查來驗證結果。

**待改進**：為所有 `PreprocessBase` 子類別實作日誌封裝。

---

## 📝 參考資料 (References)

詳細的架構決策與設計討論請參考：
- **Pull vs Push Model 決策**：`documentation/decisions/ADR-004-ui-refresh-mechanism.md`
- **LangChain 採用評估**：`documentation/decisions/ADR-001-langchain-adoption.md`
- **Multi-Agent 願景**：`documentation/decisions/ADR-002-multi-agent-vision.md`
- **向量資料庫選擇**：`documentation/decisions/ADR-003-vector-store-qdrant.md`
