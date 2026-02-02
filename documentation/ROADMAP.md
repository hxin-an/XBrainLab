# XBrainLab 專案發展路線圖 (Roadmap)

本文件定義 XBrainLab 的長程願景與工程執行計畫。我們將「穩定性」、「工具智商」與「混合運算」視為核心支柱。

---

## 📅 長期願景 (Strategic Vision)

我們將 Agent 的演化分為三個階段，逐步從「工具操作員」進化為「研究合作夥伴」。

### Stage 1: Agent as an Operator (工具操作員) - 現階段
*   **定位**：能聽懂自然語言指令，並正確、無誤地操作現有的腦波分析軟體功能。
*   **目標**：讓使用者不再需要點擊繁瑣的選單，一句話跑完 Load -> Preprocess 標準流程。

### Stage 2: Agent as a Junior Analyst (初階分析師)
*   **定位**：不只會跑流程，還能根據數據結果（如 Saliency Map）提供初步的數值解讀與摘要。
*   **核心能力**：
    *   **Feature Extraction**：Backend 自動計算 Peak Latency, Top Regions。
    *   **Data Interpretation**：LLM 根據統計指標生成 Key Findings。

### Stage 3: Agent as a Research Partner (研究夥伴)
*   **定位**：結合外部知識庫 (RAG)，針對實驗假設提供深度解釋與科學建議。
*   **核心能力**：
    *   **Knowledge Retrieval**：讀取論文，理解術語上下文。
    *   **Hypothesis Verification**: 回答「數據是否支持我的假設」。

---

## Phase 2: 平行開發階段 (Parallel Tracks) - Q1 2026

**核心策略**：打地基。由兩組並行工作線組成，一邊清理技術債，一邊建立 AI 的準確度標準。

### Track A: 工程重構與穩定性 (Engineering Refactoring)
*目標：解決 UI 冗長、架構耦合與真實工具 (Real Tool) 斷鏈問題。*

#### A-1. UI 架構瘦身 (UI Slimming)
- [ ] **ChatPanel 重構**: 將 `MessageBubble` 邏輯抽離，提升可讀性。
- [ ] **Dashboard抽象化**: 建立 `BasePanel` 父類別 (DRY Principle)。
- [ ] **Logic Decoupling**: 確保 UI 僅負責渲染，業務邏輯移至 Controller。

#### A-2. 程式碼規範 (Standardization)
- [ ] **Type Hinting**: 全面補齊 Python Type Hints。
- [ ] **Error Handling**: 統一 Exception 機制。

#### A-3. 真實工具鏈修復 (Real Tool Repair)
- [ ] **Saliency Tool**: 確保 Agent 能呼叫並執行 Saliency 計算 (先求有)。
- [ ] **Param Validation**: 確保複雜參數正確傳遞。

#### A-4. 易用性與會話管理 (Usability & Session)
- [ ] **New Conversation**: 實作「開新對話」功能，一鍵清除 Context Window 與畫面歷史，重置 Agent 狀態。

---

### Track B: 智能評測與架構 (Intelligence & Architecture)
*目標：建立「可量化」的 AI 指標，並實作混合運算架構原型。*

#### B-1. 深度評測體系 (Deep Evaluation Ecosystem)
- [ ] **RAG 準確度**: 測試 Retriever Precision & Context Relevance。
- [ ] **記憶與上下文**: 測試 Context Window 極限與 Output Truncation 影響。
- [ ] **Model Matrix**: 根據硬體 (Gemma/Qwen/Llama/Gemini) 建立推薦清單。

#### B-2. 混合運算架構 (Hybrid Architecture Prototype)
- [ ] **Local/Remote Split**: 定義 Local (UI) 與 Remote (Compute) 的通訊接口。
- [ ] **Router Agent**: 簡單的 Intent Classifier。

---

## Phase 3: 功能賦能與工具升級 (Feature Empowerment) - Q2 2026 (Early)

**核心策略**：提升工具的「智商」。在 AI 介入解讀前，後端工具必須先能產出「可被解讀」的數據。

### 3-1. 智慧型工具鏈 (Smart Tool Chain)
*填補 "Run Tool" 與 "Interpret Result" 之間的鴻溝。*
- [ ] **Saliency Stats Extraction**: 修改 Backend，除了畫圖外，額外計算 Peak Channel, Latency, Frequency Band Power 等數值統計。
- [ ] **JSON Data Contract**: 定義 Agent 專用的資料回傳格式 (Schema)，確保 Agent 讀得懂統計數據。
- [ ] **Auto-Training Logic**: 在 Python 層實作 "Loss Monitoring" 與 "Auto-Retry" 邏輯，而非依賴 Agent 瞎猜。

### 3-2. 混合引擎實裝 (Hybrid Engine Production)
*將 Prototype 轉為正式功能。*
- [ ] **Remote Worker Deployment**: 實作 SSH/gRPC 自動連線機制。
- [ ] **Model Switcher GUI**: 讓使用者能在 GUI 上滑順切換 Local/Cloud 模型。

---

## Phase 4: 自動化洞察 (Automated Insights) - Q2 2026 (Late)

**核心策略**：Agent 正式上工，扮演分析師角色。

- [ ] **Saliency Interpretation**: Agent 讀取 Phase 3 產出的 JSON Summary，生成文字報告。
- [ ] **Research Context Integration**: 結合 RAG (Phase 3 沒做，移到這裡)，讓報告包含文獻佐證。
- [ ] **Long-term Memory (Vector Store)**:
    - [ ] **User Preference**: 記住使用者的習慣 (e.g. 偏好的 Filter 參數)。
    - [ ] **Cross-Session Context**: 允許 Agent 比較不同實驗 Session 的數據差異。
- [ ] **Multimodal VQA**: (Optional) 讓 Agent 視覺模型進行雙重確認。
