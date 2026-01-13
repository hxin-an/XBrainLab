# XBrainLab 開發路線圖 (Roadmap)

本文件概述了 XBrainLab 專案的開發計畫。專案將分為兩個並行的主要軌道 (Tracks) 進行：**系統重構**與 **AI Agent 增強**。

## Track A: 系統重構與優化 (System Refactoring)
**目標**：建立穩固的工程基礎，提升程式碼品質、穩定性與可維護性。

### 第一階段：基礎建設與清理 (Infrastructure & Cleanup)
- [ ] **專案清理**
    - [ ] 移除臨時檔案 (`reproduce_issue.py`, `test_output.txt`, `verify_path.py`)。
    - [ ] **整合 UI 目錄**：比較 `XBrainLab/ui` 與 `XBrainLab/ui_pyqt`，確認並移除冗餘目錄。
    - [ ] 清理 `documentation/` 中過時的文件，確保單一真實來源。
- [ ] **建立文件骨架**
    - [ ] 建立 `README.md`, `CONTRIBUTING.md`, `CHANGELOG.md` 等標準文件。
- [ ] **Poetry 遷移**
    - [ ] 初始化 `pyproject.toml` (Python 3.10+)。
    - [ ] 遷移並鎖定相依套件版本 (`poetry.lock`)。
- [ ] **Git 標準化**
    - [ ] 設定 Pre-commit Hooks (Ruff, Black)。
    - [ ] 強制執行 Conventional Commits。

### 第二階段：品質保證 (Quality Assurance)
- [ ] **測試結構重組**
    - [ ] 拆分 Unit Tests 與 Integration Tests。
    - [ ] 設定 `pytest.ini` 支援 Headless UI 測試。
- [ ] **單元測試修復**
    - [ ] 修復 `dataset` 與 `training` 模組的失敗測試。
    - [ ] 增加核心邏輯的測試覆蓋率。
- [ ] **CI 管線建置**
    - [ ] 建立 GitHub Actions (`ci.yml`) 自動執行 Linting 與 Testing。

### 第三階段：部署與文件完善 (Deployment & Docs)
- [ ] **Docker 化**
    - [ ] 建立支援 GPU 的 `Dockerfile`。
    - [ ] 驗證容器化部署流程。
- [ ] **技術文件補完**
    - [ ] 撰寫詳細的 Architecture, API Reference 與 Test Strategy 文件。

---

## Track B: AI Agent 增強 (AI Agent Enhancement)
**目標**：賦予 Agent 知識檢索與工具呼叫的能力，採用「先模擬，後整合」策略與 Track A 並行開發。

### 第一階段：定義與模擬 (Definition & Simulation)
- [ ] **工具定義**
    - [ ] 完善 `tool_definitions.md`，確立 Agent 與後端的介面合約。
- [ ] **Mock Tools 實作**
    - [ ] 實作 Mock 工具 (如 `MockDatasetTool`)，回傳假數據以驗證 Agent 對話邏輯。
- [ ] **RAG 知識庫建置**
    - [ ] 建立 `XBrainLab/llm/rag/knowledge_base/`，收集架構文件與 API 說明。

### 第二階段：認知能力驗證 (Cognitive Validation)
- [ ] **黃金測試集 (Golden Dataset)**
    - [ ] 建立「使用者指令 -> 預期 Tool Call」的標準測試案例。
- [ ] **離線評估 (Offline Evaluation)**
    - [ ] 在無 GUI 環境下測試 Agent 的意圖理解與參數提取準確率。
- [ ] **Prompt 優化**
    - [ ] 根據評估結果調整 System Prompt，降低幻覺 (Hallucination)。

### 第三階段：真實整合 (Integration)
*需等待 Track A 的後端重構穩定後進行*
- [ ] **Real Tools 實作**
    - [ ] 將 Mock Tools 替換為呼叫真實 `Study` 物件的 API。
- [ ] **端對端測試 (E2E Testing)**
    - [ ] 在 GUI 中驗證 Agent 操作的實際效果。
- [ ] **安全性機制**
    - [ ] 實作敏感操作 (如刪除數據) 的使用者確認流程。

### 第四階段：RAG 增強 (RAG Enhancement)
- [ ] **向量資料庫**
    - [ ] 實作本地 Vector DB (如 ChromaDB) 以加速檢索。
- [ ] **語意搜尋優化**
    - [ ] 優化檢索演算法，提升相關文檔的召回率 (Recall)。
