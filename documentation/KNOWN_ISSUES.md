# 已知問題 (Known Issues)

本文件記錄目前專案中已確認存在的 Bug、限制與待解決的問題。

**最後更新**: 2026-02-25 (v0.5.3)

---

## ✅ 最近已修復 (Resolved in v0.5.x)

以下問題已在最近版本中修復，經過驗證確認解決：

- **架構解耦**:
    - `DatasetController` 已移除 PyQt6 依賴，轉為純 Python `Observable` 模式。
    - `TrainingPanel` 與 `AggregateInfoPanel` 已重構，不再直接依賴 `Study` 上帝物件。
    - `LabelImportService` 已移動至 Backend Services 層。
    - 循環依賴 (Circular Imports) 已全數解決。
    - **NEW**: `DataManager` 已從 `Study` 抽取，管理資料生命週期。
- **穩定性與資源**:
    - **VRAM 洩漏**: 訓練後已加入 `empty_cache()`。
    - **RAM 飆升**: Dataset 改用索引存取 (`Subset`) 取代複製。
    - **靜默失敗**: 全面移除裸 `except:`，改用 `logger.error`。
    - **NEW**: 下載器已重構為 Multiprocessing，支援真正的取消。
- **UI/體驗**:
    - **Chat Panel**: 重構為 Copilot 風格，支援串流與動態寬度。
    - **刷新機制**: 遷移至 Observer Pattern，解決 Agent 操作後 UI 不更新的問題。
- **Agent 架構 (v0.5.3)**:
    - **NEW**: `ContextAssembler` 已整合，動態工具過濾 (`is_valid(state)`) 運作正常。
    - **NEW**: `VerificationLayer` 已整合，結構驗證運作正常。
    - **NEW**: Agent Timeout 機制已加入 (60 秒超時)。
    - **NEW**: Ruff 0 錯誤, Mypy 0 錯誤, 2375+ 測試通過。
- **執行緒安全 & 資源管理 (v0.5.3)**:
    - **NEW**: `Trainer` / `TrainingPlanHolder` 中斷旗標從裸 `bool` 升級為 `threading.Event`，解決跨執行緒競爭條件。
    - **NEW**: `get_eval_pair()` 重構——延遲 GPU 模型建立至 state_dict 確認有效後，避免孤立 GPU 記憶體分配。
    - **NEW**: `facade.configure_training()` 的 `output_dir` 從壞掉的 `getattr(study, ...)` 改為明確參數。
- **程式碼衛生 & CI/CD (v0.5.3)**:
    - **NEW**: 89 處 logger f-string 轉為 %-style lazy formatting。
    - **NEW**: GitHub Actions CI Pipeline：lint + test + coverage，跨平台 (Linux/Windows/macOS)。
    - **NEW**: Ruff 版本統一為 ^0.14.0 (poetry / pre-commit / CI)。
    - **NEW**: `torchinfo` lazy import 修正 (optional dep 不再破壞 CI 測試收集)。

---

## ⚠️ 高優先級 (High Priority)

### 1. VerificationLayer 信心度檢查未啟用
- **位置**: [`controller.py:374`](file:///c:/lab/XBrainLab/XBrainLab/llm/agent/controller.py#L374)
- **問題**: `confidence=None` 永遠被傳入 `verify_tool_call()`，導致信心度閾值檢查永遠被跳過。
- **影響**: Agent 無法根據 LLM 信心度拒絕低信心度的工具呼叫。
- **建議**: 整合 LLM logprobs 或實作 confidence 估算機制。
- **狀態**: <span style="color:orange">待修復</span>

### 2. VerificationLayer 腳本驗證未實作
- **位置**: [`verifier.py:84`](file:///c:/lab/XBrainLab/XBrainLab/llm/agent/verifier.py#L84)
- **問題**: 程式碼註解標記為 "Future"，但 `ScriptValidator` 策略模式未實作。
- **影響**: 無法驗證工具參數的邏輯正確性 (如 `high_freq < low_freq` 檢測)。
- **建議**: 實作 Validator 策略模式。
- **狀態**: <span style="color:orange">待實作</span>

### 3. 程式啟動速度過慢
- **問題**: 啟動時需載入 PyTorch、LLM 模型、RAG 等重型依賴，導致 5-15 秒啟動延遲。
- **影響**: 使用者體驗不佳，看不到任何回饋。
- **建議**:
    1. 新增 Splash Screen (低成本高效益)
    2. 延遲載入 (Lazy Import) 重型模組
- **狀態**: <span style="color:orange">待優化</span>

---

## 🚧 中優先級 (Medium Priority)

### 1. `Study` 仍持有 Training 狀態 (God Object 殘留)
- **位置**: [`study.py`](file:///c:/lab/XBrainLab/XBrainLab/backend/study.py)
- **問題**: 雖已抽取 `DataManager`，但 `training_option`, `model_holder`, `trainer` 仍內嵌於 `Study`。
- **建議**: 考慮抽取 `TrainingManager` 類別。
- **狀態**: <span style="color:blue">技術債 (可選)</span>

### 2. `TrainingPlanHolder.train_one_epoch` 過於複雜
- **位置**: [`training_plan.py:425-492`](file:///c:/lab/XBrainLab/XBrainLab/backend/training/training_plan.py#L425)
- **問題**: 65 行大方法，包含訓練迴圈、評估、記錄更新等多重職責。
- **建議**: 抽取 `EpochRunner` 類別 (已標記為 Optional，未實作)。
- **狀態**: <span style="color:blue">技術債 (可選)</span>

### 3. RAG Embedding 同步執行
- **位置**: [`retriever.py:156`](file:///c:/lab/XBrainLab/XBrainLab/llm/rag/retriever.py#L156)
- **問題**: `embed_query()` 在主執行緒執行，可能阻塞 UI。
- **影響**: 首次 RAG 查詢可能造成短暫卡頓。
- **建議**: 移至背景執行緒執行。
- **狀態**: <span style="color:blue">技術債 (低優先)</span>

### 4. 測試覆蓋缺口
- **UI 互動**: 缺乏真實 Widget 點擊與互動的 E2E 測試 (`pytest-qt`)。
- ~~**環境相依**: 缺乏 CI/CD 流水線驗證 Windows/Linux 差異。~~ ✔️ 已解決：CI 跨平台矩陣已建立。

---

## ℹ️ 低優先級 / 設計限制 (Design Limitations)

### 1. JSON 偵測邏輯脆弱
- **位置**: [`controller.py:238`](file:///c:/lab/XBrainLab/XBrainLab/llm/agent/controller.py#L238)
- **問題**: 使用簡單字串匹配偵測 JSON，可能誤判非 JSON 輸出。
- **現狀**: 目前運作良好，僅在極端情況可能觸發不必要的重試。

### 2. Label Attachment Simplified (標籤綁定簡化)
- **限制**: `RealAttachLabelsTool` 假設 Label 檔案與 Raw Data 完全對應 (1-to-1, 順序一致)。
- **原因**: 保持 MVP Agent 簡單性。複雜情況應由使用者在 UI 處理。

### 3. Montage Tool (Montage 設定)
- **限制**: 自動匹配邏輯已實作，但對各種通道命名變體的測試覆蓋不足。
- **現狀**: 已加入 Human-in-the-loop 機制 (請求使用者確認) 作為補償。

### 4. Preprocessing Logging
- **限制**: 預處理步驟缺乏詳細的參數日誌 (如 Filter 具體頻率)，僅有操作記錄。

---

## 📊 品質指標 (Quality Metrics)

| 指標 | 狀態 | 備註 |
| --- | --- | --- |
| **Linting (Ruff)** | ✅ 0 錯誤 | 全部通過 |
| **Type Check (Mypy)** | ✅ 0 錯誤 | 全部通過 |
| **Unit Tests** | ✅ 2913 通過 | 0 失敗, 22 skipped |
| **Pre-commit** | ✅ 全部通過 | 包含 secrets 掃描 |
| **架構遷移** | ✅ 完成 | Assembler + Verifier 已整合 |
| **CI/CD** | ✅ 運作中 | Linux + Windows + macOS |
