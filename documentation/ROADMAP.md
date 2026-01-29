# XBrainLab 開發路線圖 (Roadmap)

本文件概述 XBrainLab 的開發計畫。
**現狀評估**: 核心架構重構（Headless Backend, Observer Pattern）已完成。目前的重點轉向 **CI/CD 自動化** 與 **Agent 模型驗證**。

## Phase 1: 基礎穩固 (Foundation) - 已完成
*目標：解決穩定性問題，完成架構解耦。*

- **穩定性**: 修復 VRAM/RAM 洩漏、靜默失敗、依賴衝突。
- **架構優化**:
    - 實作 `BackendFacade` (Agent 專用接口)。
    - 完成 Backend 與 PyQt6 的解耦 (Observer Pattern)。
    - 消除循環依賴。
- **Agent 基礎**:
    - 實作 Mock/Real Tools。
    - 建立 `gold_set.json` (50+ cases) 與 Mock 評測。
    - 整合 Qdrant RAG (Local)。

---

## Phase 2: 驗證與自動化 (Verification & CI/CD) - 進行中

### 2. 真實場景驗證 (Real Verification)
- [ ] **End-to-End Benchmark**:
    - [ ] 清洗與驗證外部測試集 (`scripts/benchmark/data/external_validation_set.json`)。
    - [ ] 執行 `benchmark-llm` 針對該測試集進行評分 (Pass Rate)。
- [ ] **RAG 與 Few-Shot 範例庫 (Gold Set)**:
    - [ ] **Example Library 維護**: 擴充 RAG 專用的範例庫 (`XBrainLab/llm/rag/data/gold_set.json`)，作為 Few-Shot 的來源。
    - [ ] **RAG 準確率驗證**: 確保 `retriever` 能針對 Query 抓到正確的 Gold Set 範例。

### 3. Agent 強健性強化 (Agent Robustness)
*解決 "Agent 開發缺少的部分"：防止無限迴圈、格式錯誤與超時。*
- [ ] **無限迴圈防護**: 偵測並中斷 Agent 重複呼叫無效工具的 Loop。
- [ ] **JSON 容錯機制 (Auto-Retry)**: 當 LLM 輸出格式錯誤時，自動回傳錯誤提示並要求重試，而非直接崩潰。
- [ ] **超時保護 (Timeout)**: 設定執行 Watchdog (e.g., 60s)，防止 Local LLM 卡死資源。
- [ ] **Token 與 Context 管理**:
    - [ ] 實作 Sliding Window 與 Token Counter，防止 Context Overflow。
    - [ ] **Output Truncation**: 自動截斷過長的工具輸出 (e.g., >1000 chars)，避免擠壓 Context。
- [ ] **可觀測性 (Observability)**:
    - [ ] 紀錄完整 Session Trace (Thought -> Action -> Observation) 至 Log 檔。
- [ ] **思維鏈 (Chain of Thought)**:
    - [ ] 強制 Agent 在執行 Action 前輸出 "Thought" 區塊，提升複雜任務的邏輯準確率。


### 4. 模型適配驗證 (Model Verification Matrix)
*目標：測試模型 Pass Rate。硬體基準：RTX 5070 Ti (16GB VRAM)。*
*考慮隱私與多樣性，Qwen 僅保留 7B 作為通用基準，進階選用 Mistral。*

| 模型等級 | 推薦模型 | 來源 | 硬體需求 | 預估 Pass Rate | 適用場景 |
|---------|---------|-----|---------|----------------|---------|
| **輕量級** | Gemma-2-2B | Google | CPU / 2GB | ~70% | 開發測試、低階硬體 |
| **輕量級** | Phi-3.5-mini | MS | 4GB VRAM | ~85% | **微軟生態推薦** (高 CP 值) |
| **中等級** | Qwen2.5-7B | Alibaba | 6GB VRAM | 88% | 一般使用者 (最佳平衡) |
| **重量級** | Mistral-Nemo 12B | Mistral | 10GB VRAM | ~90% | **5070 Ti 推薦** (高效能/非中資) |
| **API** | Gemini 2.0 Flash | Google | Cloud | 95%+ | 穩定高速 (Backup) |
| **API** | Gemini 3.0 Flash | Google | Cloud | 96%+ | **首選 API** (2026 最新版) |

---

## Phase 3: 系統精煉 (Refinement) - 📅 規劃中
*目標：收尾剩餘的技術債，達到完全服務化。*

- [ ] **完全事件驅動**: 將剩餘的 Panel (Training/Preprocess) 遷移至 `QtObserverBridge`，移除所有輪詢。
- [ ] **服務層抽離**: 將 `LabelImportService` 等邏輯完全移出 Controller。

## Phase 4: 進階擴充 (Expansion) - 📅 規劃中
*目標：實現多專家協作 (Mixture of Experts) 與混合推論引擎。*

- [ ] **Hybrid Engine**: 實作動態切換 Local/API 模型的機制。
- [ ] **Dynamic System Prompts (Expert Teams)**:
    - [ ] **Intent Router**: 辨識使用者意圖 (e.g., Preprocess vs Training)。
    - [ ] **Specialist Agents**: 針對不同階段切換專屬 System Prompt (e.g., Signal Expert vs ML Engineer)。
- [ ] **Multi-Agent**:
    - [ ] 引入 `Tutor` 角色 (RAG from Textbook)。
    - [ ] 實作 Intent Router 進行角色切換。
- [ ] **Deployment**:
    - [ ] Docker 容器化 (GPU Support)。
    - [ ] 自動化 API 文檔生成。
