# XBrainLab 開發路線圖 (Roadmap)

本文件概述了 XBrainLab 專案的開發計畫。基於最新的**紅隊測試與架構審計**，我們調整了優先順序，將**系統穩定性**與**架構解耦**列為首要任務。

專案將分為兩個並行的主要軌道 (Tracks) 進行：**系統重構**與 **AI Agent 增強**。

## Track A: 系統重構與優化 (System Refactoring)
**目標**：修復關鍵資源洩漏，解耦前後端，提升代碼品質，並建立統一的測試基礎建設。

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
- [x] **類型安全提升 (Type Safety)**
    - [x] 修復所有 mypy 類型錯誤 (139 files, 0 errors)。
    - [x] 添加 None 安全檢查、LSP 合規性、類型聯合註解。

### 第二階段：代碼品質與短期解耦 (Code Quality & Quick Decoupling) - **[✅ Completed]**
*目標：償還技術債，阻止耦合擴散，建立開發規範*

#### P0 - 緊急修復 (本週)
- [x] **修復嚴重代碼與錯誤處理問題**
    - [x] 修正裸 `except:` (1 處)
    - [x] 移除 `TrainingPanel` 與 `AggregateInfoPanel` 對 `study` 的直接訪問 (緊急解耦)

#### P1 - 基礎建設 (1-2週)
- [x] **日誌與異常處理標準化**
    - [x] 建立結構化日誌系統 (`logging` module)
    - [x] 消除 16 處寬泛的 `except Exception`，改用具體異常 (替換為 Logger 記錄)
- [x] **UI/Backend 交互規範落實**
    - [x] 根據 `ADR-004`，確保新代碼嚴格遵循 Pull/Push 混合模式
    - [x] 重構 `Dialog` 層，禁止訪問 `parent.study`
- [x] **Strict Linting Enforcement (v0.5.2)**
    - [x] 解除所有 Circular Imports (PLC0415)
    - [x] 修復所有 E501, F811, N802 等代碼風格問題
    - [x] 啟用 `ruff`, `mypy`, `pre-commit` 作為強制性 CI 檢查


#### P2 - 後端解耦與服務化 (Backend Decoupling) - **[🚀 Next Up]**
- [x] **移除 Backend 對 PyQt6 的依賴**
    - [x] 重構 `DatasetController`: 移除 `QObject` 繼承，改用 Python 原生 Observer 模式或回調。
    - [x] 移動 `LabelImportService` 至 `backend/services/` 並移除 UI 依賴。
- [x] **Agent 架構準備**
    - [x] 建立 `BackendFacade`: 為 LLM 提供統一的無狀態調用接口。

#### P2 - 已完成項目
- [x] **實作 Controller 模式基礎**
    - [x] 建立 `TrainingController` (核心邏輯遷移)
- [x] **基礎建設清理**
    - [x] 移除冗餘目錄 (`ui_pyqt`)
    - [x] 完成 Poetry 遷移與 Git Hooks 設定

### 第三階段：事件驅動架構遷移 (Event-Driven Architecture Migration) - **[🚧 In Progress]**
*目標：移除輪詢延遲，解決 Agent 背景執行緒 UI 刷新問題*

- [x] **架構驗證 (Architecture Verification)**
    - [x] 設計 `QtObserverBridge` 模式 (Event-Driven Bridge)
    - [x] 驗證 `DatasetPanel` 遷移效果 (解決 White Screen Issue)
- [x] **系統遷移 (System-Wide Rollout)**
    - [x] **TrainingPanel**: 遷移 `QTimer` 輪詢至 `QtObserverBridge`
    - [x] **PreprocessPanel**: 監聽預處理完成事件
    - [x] **VisualizationPanel**: 監聽 Montage/Data 變更事件
    - [x] **EvaluationPanel**: 監聽評估結果事件
- [x] **基礎建設完善**
    - [x] 實作 `BasePanel` 統一集成 Bridge 邏輯 (`_create_bridge()` helper)
    - [ ] 更新 `Observable` 支援更豐富的 Payload
- [ ] **完全解耦 (Complete Decoupling)**
    - [x] **服務層遷移**: `LabelImportService` 已移至 Backend (v0.5.0)
    - [ ] **移除全局依賴**: MainWindow 不再持有 `Study` 引用 (Dependency Injection)
    - [x] **Agent 層解耦**: `BackendFacade` 介面已建立 (v0.5.0)

### 第四階段：測試與驗證體系 (Testing & Verification Infrastructure) - **[Planned]**
*目標：確保各層級穩定性*

- [x] **UI/Integration Testing**
    - [x] 引入 `pytest-qt`
    - [x] 建立 E2E 測試 (Import -> Train -> Result) — `test_study_training_e2e.py` 26 個測試
- [x] **Backend Independence Verification**
    - [x] 驗證 Backend 可在無 Qt 環境執行 (Headless Test) — `validate_headless.py` (v0.5.6)
    - [ ] 建立 CLI 工具原型以驗證解耦成果

### 第五階段：部署與維護 (Deployment & Maintenance) - **[Planned]**
- [ ] **容器化**: 建立支援 GPU 的 `Dockerfile`
- [x] **文檔體系**: 建立 API 文檔自動生成 (MkDocs Material) — 初始化完成
- [ ] **系統清理**: 移除 Dead Code 與冗餘文件

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

### 第三階段：認知驗證與基準測試 (Cognitive Validation) - **[✅ Completed]**
- [x] **黃金測試集 (Gold Set)**
    - [x] 擴充至 50+ 測試案例，覆蓋 Dataset, Preprocess, Training, UI。
- [x] **自動化評測 (Benchmark Script)**
    - [x] 實作 `simple_bench.py`，支援分類準確率報告與詳細失敗分析。
    - [x] 達成 88.0% 通過率。
- [x] **架構重構**
    - [x] 實作 `ContextAssembler` 以支援動態 System Prompt 與 Context。

### 第四階段：RAG 整合與工具實作 (RAG Integration & Real Tools) - **[🚧 In Progress]**
**目標**：讓 Agent 具備操作真實軟體的能力 (Coordinator Persona)。

#### 4.1 真實工具實作 (Real Tools) - **[✅ Completed]**
- [x] **基礎架構**: 在 `llm/tools/real/` 實作連接 Backend 的 Adapter。
- [x] **單元測試**: 19/19 Real Tools 測試通過。
- [x] **整合驗證**: `verify_real_tools.py` 驗證通過 (使用真實 EEG 資料)。
- [x] **功能補完**: 實作 `optimizer` 與 `checkpoint` 支援 (解決已知的 High Priority Issue)。
- [ ] **流程控制 (Flow Control)**
    - [ ] **Human-in-the-loop (HIL)**: 實作 Montage Verification 的人工介入機制 (v0.3.9 implemented, pending coverage)。

#### 4.2 Agent 架構增強 (Agent Enhancement)
**已識別的架構缺口**：
- [x] **錯誤處理與恢復機制 (P0 - Critical)**
    - [x] 實作 `_max_loop_breaks = 3` 限制（防止 ReAct Loop 無限迴圈）
    - [x] 實作 Tool 失敗重試機制 (`_max_tool_failures = 3`)
    - [ ] 實作對話 Timeout 機制（Benchmark 有 300s，正常對話需要）
    - [ ] 實作 Graceful Degradation（LLM 無回應時降級策略）
- [x] **Observability & Logging (P1 - High)**
    - [x] 實作 Structured Logging（追蹤完整 ReAct Loop 鏈路）— `AgentMetricsTracker`
    - [x] 實作 Token 計數與 Latency 追蹤 — `TurnMetrics`
    - [x] 實作 Conversation ID 關聯多輪對話 — `metrics.conversation_id`
    - [x] 記錄 Tool 執行時間與成功率 — `ToolExecution` dataclass
- [x] **Configuration Management (P2 - Medium)**
    - [x] **配置持久化 (Config Persistence)**
        - [x] 實作 `LLMConfig.save_to_file()`/`load_from_file()` 持久化 settings.json
        - [x] 支援配置項目：inference_mode, temperature, top_p, max_new_tokens (v0.5.6)
    - [x] **配置驗證 (Config Validation)**
        - [x] API Key 格式檢查與有效性測試 — `ModelSettingsDialog`
        - [x] 參數範圍驗證 — QDoubleSpinBox/QSpinBox range constraints (v0.5.6)
    - [x] **Settings UI Panel**
        - [x] 使用 `ModelSettingsDialog` (QDialog) — 含 Local/Gemini/Generation 三區塊
        - [x] Model Selector Dropdown（Local + Gemini）
        - [x] API Key 輸入欄位（含 EchoMode.Password）
        - [x] 參數調整控件：Temperature (QDoubleSpinBox), Top-P, Max Tokens (QSpinBox) (v0.5.6)
        - [x] Activate/Cancel 按鈕（觸發 config.save_to_file()）
    - [ ] **與 4.7 整合**：Settings UI 變更後呼叫 `LLMController.switch_engine()`
- [ ] **Context Management (P2 - Medium)**
    - [ ] 實作 Token Budget Management（檢查 Context 是否超限）
    - [ ] 實作 Context Prioritization（根據相關性排序）
    - [ ] 改善 Context Expiration 機制（自動清理過期 Context）

#### 4.3 Benchmark 改進
**測試集隔離策略**：
- [ ] **歷史隔離模式**
    - [ ] 修改 `simple_bench.py` 為每個測試案例建立獨立 Controller（避免歷史污染）
    - [ ] 優化：重用 AgentWorker 避免重複加載模型
- [ ] **測試集分工**
    - [ ] 將 Benchmark 預設改為 `external_validation_set.json` (175 題 OOD 測試)
    - [ ] 保留 `gold_set.json` (50 題) 用於 RAG Few-Shot 範例
- [x] **Multi-Turn 對話測試**
    - [x] 建立 `conversation_test_set.json` — 20 scenarios, 4 categories (v0.5.6)
    - [x] 實作多輪對話評測邏輯 — `multiturn_bench.py` (v0.5.6)

#### 4.4 向量資料庫 (Vector Store) - **[✅ Completed]**
- [x] **選型**: 採用 **Qdrant** (Local Mode)。
- [x] **資料策略**:
    - [x] **測試集準備**: 建立 `external_validation_set.json` (175 題)。
    - [x] **RAG 索引**: 索引 `gold_set.json` (50 題) 作為 Few-Shot 範例。
    - [x] **文件索引**: 索引 `documentation/agent/*.md` (Tool Definitions, API Docs)。
- [x] **索引實作**
    - [x] 建立 RAG 模組結構 (`XBrainLab/llm/rag/`)
    - [x] 實作 `indexer.py` (`index_gold_set`, `index_documentation`)
    - [x] 實作 Metadata Filter (by `tool_name`, `category`)

#### 4.5 RAG 引擎 (Retrieval-Augmented Generation) - **[✅ Completed]**
- [x] **檢索器實作** (`XBrainLab/llm/rag/retriever.py`)
    - [x] 實作 Semantic Search Retriever（基於 Qdrant）
    - [x] 實作 Metadata Filtering (根據 Tool Category)
    - [x] 實作 Hybrid Retrieval (Semantic + BM25 Keyword) — `bm25.py` + hybrid alpha (v0.5.6)
    - [x] 實作 `get_similar_examples(query, top_k=3)` 方法
- [x] **Prompt 整合**
    - [x] 在 `ContextAssembler` 整合 RAG 檢索結果
    - [x] 實作 Few-Shot Context 格式化（將檢索案例注入 Prompt）
    - [ ] 實作 Retrieval Confidence Threshold（低信心時跳過檢索）
- [x] **Controller 整合**
    - [x] 在 `LLMController` 初始化時載入 RAG Retriever
    - [x] 在 `handle_user_input()` 時觸發檢索並注入 Context

#### 4.6 RAG 評估與觀測 (Evaluation & Observability) - **[🔄 Partial]**
- [ ] **檢索指標 (Retrieval Metrics)**
    - [ ] 實作 Hit Rate（正確工具是否在 Top-K）
    - [ ] 實作 MRR (Mean Reciprocal Rank)
    - [ ] 建立 Retrieval Quality Dashboard（記錄到 `logs/rag_metrics.json`）
- [ ] **生成指標 (Generation Metrics)**
    - [ ] 測量 Faithfulness（Agent 是否遵守檢索到的參數）
    - [ ] 測量 Parameter Accuracy（參數正確率）
    - [ ] 對比「有 RAG vs 無 RAG」的效果提升
- [ ] **多模型 Benchmark（不同算力適配）**
    - [ ] 在 `external_validation_set.json` (175 題) 測試不同大小的模型：
      - **輕量級 (CPU/低階 GPU)**: Gemma-2B *(與前人比較基準)*
      - **中等級 (中階 GPU)**: Qwen2.5-7B *(當前預設)*, Phi-3.5-mini-instruct (3.8B)
      - **重量級 (高階 GPU)**: Llama-3.1-8B-Instruct
      - **API 基準 (免費)**: Gemini-2.0-Flash, Gemini-2.5-Flash *(共 9000 RPD 免費配額)*
    - [ ] 記錄各模型的 Pass Rate、平均推論時間、VRAM 使用量
    - [ ] 建立「模型選擇指南」文件（根據硬體推薦模型）
- [ ] **評估框架**
    - [ ] 引入 **Ragas** 或 **Arize Phoenix**
    - [ ] 建立自動化評分 Pipeline（擴充 `scripts/agent/benchmarks/simple_bench.py`）
    - [ ] 支援指定模型進行 Benchmark：`--model qwen2.5-3b`

#### 4.7 混合推論引擎 (Hybrid Inference Engine) - **[✅ Mostly Done]**
**目標**：重構 LLM Backend 架構，支援多種推論後端的動態切換。

**模型選擇考量** (重要：Agent 不接觸 EEG 原始資料，只處理文字指令):

| 模型等級 | 推薦模型 | 來源 | 硬體需求 | Pass Rate | 推論速度 | 適用場景 |
|---------|---------|-----|---------|-----------|----------|---------|
| **輕量級** | Gemma-2B | Google | CPU / 2GB VRAM | ~70% | 快 | 測試、低階硬體、前人比較基準 |
| **中等級** | Qwen2.5-7B *(預設)* | 阿里巴巴 | 8GB VRAM | 88% | 中等 | 一般使用 |
| **中等級** | Phi-3.5-mini | Microsoft | 4GB VRAM | ~85% | 快 | 中階 GPU |
| **重量級** | Llama-3.1-8B | Meta | 16GB+ VRAM | ~92% | 慢 | 高準確率需求 |
| **API (免費)** | Gemini-2.0-Flash | Google | 無需 GPU | 94%+ | 快 | 免費高效選項 |
| **API (免費)** | Gemini-2.5-Flash | Google | 無需 GPU | 95%+ | 極快 | 最新免費模型 (9000 RPD) |

*註：檔案路徑可能透過 API 傳輸，但 EEG 資料本體保留在本地 Backend，從不傳給 LLM。*
*Pass Rate 為預估值，需透過 4.6 的多模型 Benchmark 實際測量。*
*Gemini API 免費層約提供 9000 RPD (Requests Per Day) 配額。*

- [x] **Backend 抽象層**
    - [x] 重構 `BaseBackend` 抽象類別（統一介面 `core/backends/base.py`）
    - [x] 確保 `LocalBackend`, `OpenAIBackend`, `GeminiBackend` 實作相同介面
    - [x] 統一 `generate_stream(messages)` 方法簽名
- [x] **Engine Factory Pattern**
    - [x] 根據 `config.inference_mode` 動態建立對應 Backend
    - [x] 支援 Lazy Loading（延遲載入模型）
- [ ] **Hot-Swap 機制**
    - [ ] 在 `LLMController` 實作 `switch_engine(new_mode: str)` 方法
    - [ ] 安全關閉舊 Backend（釋放 VRAM/連線）
    - [ ] 無縫切換到新 Backend（保留對話歷史）
- [ ] **Fallback Strategy（降級策略）**
    - [ ] 實作 `try_with_fallback()` 裝飾器
    - [ ] API 失敗時自動切換 Local Backend
    - [ ] 記錄降級事件到 Structured Log
- [x] **API Client 增強**
    - [x] 完善 `OpenAIBackend`（支援 GPT-4o, DeepSeek）
    - [x] 完善 `GeminiBackend`（支援 Gemini 2.0 Flash）
    - [ ] 實作 Retry 機制（指數退避）

**與 4.2 關係**：
- 讀取 4.2 ConfigManager 提供的配置
- 提供 API 給 4.2 Settings UI 呼叫（switch_engine）
- 不處理 UI 層邏輯

### 第五階段：多 Agent 擴充 (Multi-Agent Expansion) - **[📅 Planned]**
**目標**：引入專家 Agent 以支援教學與進階分析。

- [ ] **虛擬多 Agent (Persona Switching)**
    - [ ] 實作 Intent Router 區分 `Coordinator` vs `Tutor`.
- [ ] **領域知識 RAG**
    - [ ] 索引 EEG 概念與教科書摘要供 Tutor 使用。

## RAG 內容策略 (Content Strategy)

### RAG 資料索引政策 (Indexing Policy)

| 資料類型 | 是否索引 | 用途 | 優先級 | 說明 |
| :--- | :--- | :--- | :--- | :--- |
| **Tool Definitions** | ✅ 是 | 工具參數規格查詢 | **P0** | `tool_definitions.md`, API Docs |
| **gold_set.json** | ✅ 是 | Few-Shot 相似案例檢索 | **P0** | 50 題精選範例，支援 Analogical Reasoning |
| **User Manuals** | ✅ 是 | 教學問題回答 | P1 | `README.md`, FAQ |
| **EEG Glossary** | ✅ 是 | 領域知識查詢 | P2 | `GLOSSARY.md` - Tutor Persona 使用 |
| **external_validation_set.json** | ❌ 否 | Benchmark 測試集 | **P0** | **絕對不可索引 - Data Leakage** |
| **歷史對話記錄** | ⚠️ 條件性 | 成功工作流範例 | P3 | 需用戶同意 + 去識別化 |

### RAG vs Prompt Pool 差異

我們採用的是 **RAG Few-Shot（動態範例檢索）**，非傳統 Prompt Pool：

| 維度 | Prompt Pool | 我們的設計 (RAG Few-Shot) |
|------|------------|--------------------------|
| **範例來源** | 手寫固定模板 | 動態檢索 gold_set.json |
| **選擇依據** | 任務分類（if-else） | 語義相似度 (Semantic Search) |
| **靈活性** | 低（固定 N 個模板） | 高（50 個案例排列組合） |
| **適應性** | 需人工更新模板 | 自動找最相關案例 |

**範例流程**：
```
User: "Load two files from /home/data/"
  ↓
1. Semantic Search in gold_set RAG
  ↓
  檢索到: "Load sub01.gdf and sub02.gdf from /tmp/"
  ↓
2. Few-Shot Context Injection
  ↓
  Prompt: "Similar Example: ..."
  ↓
3. Agent 推理
  ↓
  Tool: load_data, Parameters: {"paths": [...]}
```

### Benchmark 測試集分工

| 資料集 | 用途 | 題數 | 索引到 RAG? | 評分用? |
|--------|------|------|------------|--------|
| `gold_set.json` | **RAG 訓練範例** | 50 | ✅ 是 | ❌ 否 |
| `external_validation_set.json` | **OOD 評分測試** | 175 | ❌ 否 | ✅ 是 |

**設計優勢**：
1. **避免資料浪費**：50 題精心標註的範例用於 Few-Shot Learning
2. **嚴格 OOD 測試**：175 題未見過的問題測試泛化能力
3. **符合 ML 最佳實踐**：Training Set (RAG) ≠ Test Set (Benchmark)

### 知識類別對應

| 知識類別 | 來源 | 使用者 | 優先級 | RAG 策略 |
| :--- | :--- | :--- | :--- | :--- |
| **工具與API** | `tool_definitions.md`, API Docs | **Coordinator** | **P0** (Phase 4) | Metadata Filter by `tool_name` |
| **操作範例** | `gold_set.json` (50題) | **Coordinator** | **P0** (Phase 4) | Semantic Search + Few-Shot |
| **領域知識** | EEG Concepts, Glossary | **Tutor**, **Analyst** | P2 (Phase 5) | Full-text Search |
