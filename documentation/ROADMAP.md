# XBrainLab 開發路線圖 (Roadmap)

本文件概述了 XBrainLab 專案的開發計畫。基於最新的**紅隊測試與架構審計**，我們調整了優先順序，將**系統穩定性**與**架構解耦**列為首要任務。

專案將分為兩個並行的主要軌道 (Tracks) 進行：**系統重構**與 **AI Agent 增強**。

## Track A: 系統重構與優化 (System Refactoring)
**目標**：修復關鍵資源洩漏，解耦前後端，並建立統一的測試基礎建設。

### 第一階段：關鍵穩定性修復 (Critical Stabilization) - **[✅ Completed]**
*解決 `KNOWN_ISSUES.md` 中的高風險資源與穩定性問題*
- [x] **修復 VRAM 洩漏**
    - [x] `training_plan.py`: 實作 `.detach().cpu()` 與 `empty_cache()` 機制。
- [x] **修復 RAM 記憶體倍增**
    - [x] `Dataset`: 改用 Index-based access (`Subset`) 取代 Numpy Masking 複製。
- [x] **消除靜默失敗 (Silent Failures)**
    - [x] 全局搜尋並修復 `try...except: pass`，確保錯誤被 Log 記錄。
- [x] **依賴衝突防護**
    - [x] `pyproject.toml`: 鎖定 PyTorch 與 CUDA 版本對應關係。

### 第二階段：架構重構與解耦 (Architecture & Decoupling) - **[✅ Completed]**
*解決前後端強耦合問題，為未來的擴展鋪路*
- [x] **實作 Controller 模式**
    - [x] 建立 `TrainingController`，移除 `TrainingPanel` 對 `Study` 的直接呼叫。
    - [x] 將 `VisualizationPanel` 的計算邏輯移至 Backend Service。
- [x] **UI/Backend 介面標準化**
    - [x] 定義明確的 Signal/Slot 介面，禁止 UI 直接實例化 Backend 類別 (如 `Preprocessor`)。
- [x] **基礎建設清理**
    - [x] 移除冗餘目錄 (`ui_pyqt`)。
    - [x] 完成 Poetry 遷移與 Git Hooks 設定。

### 第三階段：測試體系重組 (Test Infrastructure)
*解決測試檔案分散與 UI 測試不足的問題*
- [ ] **測試結構統一**
    - [ ] 建立根目錄 `tests/`，將散落的測試檔案 (`backend/tests`, `ui/tests`) 集中管理。
- [ ] **UI 自動化測試**
    - [ ] 引入 `pytest-qt`，為核心面板 (`TrainingPanel`, `VisualizationPanel`) 建立基礎互動測試。
    - [ ] 建立 "Import -> Preprocess -> Train" 的完整 E2E 測試路徑。
- [ ] **CI 管線建置**
    - [ ] 設定 GitHub Actions 自動執行測試與 Linting。

### 第四階段：部署與文件 (Deployment & Docs)
- [ ] **Docker 化**
    - [ ] 建立支援 GPU 的 `Dockerfile`。
- [ ] **技術文件補完**
    - [ ] 更新 `ARCHITECTURE.md` 反映重構後的設計。

---

## Track B: AI Agent 增強 (AI Agent Enhancement)
**目標**：修復 Agent 記憶體問題，並賦予其更強的工具使用能力。

### 第一階段：Agent 核心修復 (Core Fixes) - **[✅ Completed]**
- [x] **修復記憶體洩漏 (Unbounded Memory)**
    - [x] `LLMController`: 實作 Context Window 管理 (Sliding Window)。
- [x] **解決 UI 阻塞**
    - [x] 將 Agent 執行邏輯 (`AgentWorker`) 移至獨立的 `QThread`，並確立 MVC 架構。

### 第二階段：定義與模擬 (Definition & Simulation) - **[✅ Completed]**
- [x] **工具定義完善**
    - [x] 完成 `tool_definitions.md`，涵蓋 Dataset, Preprocess, Training, UI Control。
- [x] **Mock Tools 實作與重構**
    - [x] 實作全套 Mock Tools。
    - [x] **架構重構**：採用 `definitions/` (Base), `mock/` (Impl), `real/` (Placeholder) 的分層架構與工廠模式。
- [x] **測試驗證**
    - [x] 建立 `llm_test_cases.md` 並實作完整的單元測試 (`test_tools.py` 等)。

### 第三階段：認知能力驗證 (Cognitive Validation) - **[🚧 Pending]**
- [ ] **黃金測試集 (Benchmark)**
    - [ ] 建立標準測試案例 (Input -> Expected Tool Calls)。
- [ ] **離線評估腳本**
    - [ ] 開發自動化評測腳本，使用 Mock Tools 快速驗證模型推理能力。

### 第四階段：真實整合 (Integration) - **[🚧 Pending]**
- [ ] **Real Tools 實作**
    - [ ] 在 `llm/tools/real/` 中實作真實工具，連接 `Study` Backend。
- [ ] **RAG 增強**
    - [ ] 實作本地向量資料庫 (ChromaDB/FAISS) 以支援文件檢索。
