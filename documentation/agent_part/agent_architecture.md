# Agent Architecture (Agent 架構設計)

## 1. 系統綜覽 (System Overview)

XBrainLab 的 Agent 系統採用 **"Headless Backend + Intelligent Bridge + RAG"** 的設計模式。
Agent 扮演「操作員」的角色，它不直接持有數據，而是透過標準化的 **Tools** 介面來操作後端的 **Study** 物件，並通過 **RAG** 檢索知識庫來增強決策能力。

```text
[Human User]
     ↕ (Chat Interface)
[UI / Chat Panel]
     ↕ (JSON Stream)
[Agent Worker (Controller)]
     │
     ├──↔ (Query) ───────────── [RAG Engine] (Retrieval-Augmented Generation)
     │                          (Knowledge Base: Docs, Examples, Code)
     │
     ├──↔ (Prompt + Context) ── [LLM (GPT-4o/Gemini/Local Models)]
     │                          (Brain: Reasoning & Planning)
     │
     └──→ (Execute Tool) ─────→ [Tool Registry]
                                (Hands: Execution Layer)
                                     │
                                     ├── [Dataset Tools]
                                     ├── [Preprocess Tools]
                                     ├── [Training Tools]
                                     └── [Visualization Tools]
                                              ↕ (Modify/Read)
                                       [Study Object]
                                       (Body: Backend State)
                                              │
                                              └──→ (Logs/Status) → [UI]
```

## 2. 核心元件 (Core Components)

### 2.1 Agent Worker (Controller)
*   **職責**: 負責協調 User, LLM, RAG 與 Tools 之間的訊息傳遞。
*   **核心模組**: `XBrainLab/llm/agent/controller.py`
*   **功能**:
    *   維護對話歷史 (Message History)。
    *   **RAG 整合**: 將 User Query 傳送至 RAG Engine，獲取相關文檔或範例，並注入 System Prompt。
    *   解析 LLM 回傳的 Tool Call 請求。
    *   在 Python 環境中執行對應的 Tool Class。

### 2.2 LLM (The Brain)
*   **職責**: 理解使用者意圖，結合 RAG 提供的背景知識，規劃操作步驟。
*   **核心模組**: `XBrainLab/llm/core/engine.py` (支援 Local Models 如 Phi-3, Qwen2.5)
*   **能力**:
    *   **上下文理解**: 結合 RAG 檢索到的 API 文檔，降低幻覺 (Hallucination)。
    *   **邏輯推理**: 判斷哪些檔案是一組。
    *   **流程規劃**: 決定預處理的順序。

### 2.3 RAG Engine (The Library)
*   **職責**: 為 LLM 提供特定領域的知識 (Domain Knowledge) 與最新的工具定義。
*   **核心模組**: *待實作 (Planned: XBrainLab/llm/rag/)*
*   **資料來源**:
    *   **Documentation**: `documentation/` 下的架構文檔與工具定義。
    *   **Codebase**: `XBrainLab/backend/` 下的原始碼 (如 `study.py`)。
    *   **Examples**: 過往的成功操作案例 (Few-shot learning)。

### 2.4 Tool Registry (The Interface)
*   **定義**: 位於 `XBrainLab/llm/tools/`
    *   `base.py`: 工具基類。
    *   `dataset_tools.py` (Mock): 數據集操作。
    *   `preprocess_tools.py` (Mock): 訊號處理。
    *   `training_tools.py` (Mock): 訓練控制。
    *   `visualization_tools.py` (Mock): 圖表繪製。

### 2.5 Study Object (The State)
*   **定義**: `XBrainLab/backend/study.py`。
*   **職責**: 
    *   是整個實驗的 **"Single Source of Truth"**。
    *   持有 Raw Data, Epochs, Training Configuration, Model Weights。

## 3. 專案結構快照 (Project Structure Snapshot - LLM Module Only)

以下展示 `XBrainLab/llm/` 模組的內部結構。**注意：RAG 模組將擁有自己專屬的文件資料夾 (`knowledge_base/`)，以確保檢索範圍的精確性。**

```
XBrainLab/llm/                <-- Agent 核心模組
├── agent/                    <-- 控制層
│   ├── controller.py         <-- 協調者 (Worker)
│   ├── parser.py             <-- 輸出解析
│   └── prompts.py            <-- 提示詞模板
│
├── core/                     <-- LLM 引擎層
│   ├── config.py             <-- 模型設定
│   └── engine.py             <-- 推論引擎 (支援 HuggingFace Local Models)
│
├── tools/                    <-- 工具介面層 (Mock/Real)
│   ├── base.py               <-- Tool Base Class
│   ├── dataset_tools.py      <-- [待實作] Dataset Tools
│   ├── preprocess_tools.py   <-- [待實作] Preprocess Tools
│   ├── training_tools.py     <-- [待實作] Training Tools
│   └── visualization_tools.py <-- [待實作] Visualization Tools
│
└── rag/                      <-- [規劃中] RAG 檢索模組
    ├── engine.py             <-- 檢索邏輯
    └── knowledge_base/       <-- **RAG 專屬知識庫** (存放供 Agent 檢索的文件)
        ├── tool_definitions.md  <-- 工具規格 (從 documentation 同步或遷移)
        ├── api_reference.md     <-- 後端 API 說明
        └── few_shot_examples.md <-- 操作範例
```


