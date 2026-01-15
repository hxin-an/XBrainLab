# ADR-001: LangChain 採用評估 (Evaluation of LangChain Adoption)

## 背景 (Context)
目前 XBrainLab Agent 建立在 **自研架構 (Custom Architecture)** 之上：
- **Controller**: 手動管理 ReAct 迴圈與對話歷史。
- **Worker**: 在 `QThread` 中執行 LLM 推論。
- **PromptManager**: 處理字串基礎的 Prompt 建構。
- **Tools**: 自定義的 `BaseTool` 實作。

使用者詢問切換到 **LangChain** 是否更為合理。

## 分析 (Analysis)

### 1. LangChain
**優點 (Pros):**
- **RAG 就緒 (RAG Readiness)**: 擁有業界一流的 Document Loaders, Text Splitters, 和 Vector Stores (與 **Qdrant** 完美整合) 支援。這對我們即將到來的 "Phase 4" 至關重要。
- **模型無關 (Model Agnostic)**: 切換 `transformers`, `llama.cpp`, 或 `OpenAI` 幾乎零成本。
- **生態系 (Ecosystem)**: 擁有數千種預建工具與社群支援。
- **記憶體 (Memory)**: 標準化的 Buffer, Summary, 和 Graph memory 實作。

**缺點 (Cons):**
- **複雜度**: LangChain 的 "Chain" 抽象層有時會隱藏邏輯，導致 Prompt 問題難以除錯 ("Abstraction Hell")。
- **Qt 整合困難**: LangChain 是為 Python scripts 或 async servers (FastAPI) 設計的。將其 blocking 或 `asyncio` 迴圈整合進 PyQt `QThread` (Signal/Slot 架構) 需要小心處理，否則極易導致 UI 凍結。
- **依賴沉重**: 會顯著增加環境的大小。

### 2. 當前自研架構 (Current Custom Architecture)
**優點 (Pros):**
- **完全控制 (Full Control)**: 我們確切知道 Prompt 是如何建構的，以及模型何時被呼叫。
- **原生 Qt 支援 (Qt-Native)**: 從第一天起就是為了 `QThread` 和 Signals 設計，確保 GUI 流暢。
- **輕量級 (Lightweight)**: 僅依賴 `torch` 和 `transformers`。
- **可除錯性 (Debuggability)**: "所見即所得" 的 Prompt。

**缺點 (Cons):**
- **重複造輪子**: 我們必須手動實作 Sliding Window, RAG 檢索輔助, 和 Prompt 模板。
- **維護成本**: 必須自行維護 ReAct 迴圈邏輯。

## 建議：混合模式 (The Hybrid Approach)

與其完全重寫為 `LangChain AgentExecutor` (它會控制迴圈並可能與我們的 Qt Controller 衝突)，我們建議採用 **元件式採用 (Component-Based Adoption)**：

1.  **保留 Controller/Worker 迴圈**: 維持我們自研的 `LLMController` 和 `AgentWorker`，以確保嚴格的 Qt 執行緒安全與 UI 響應性。
2.  **採用 LangChain 於 RAG 與工具**:
    - 使用 `langchain` 進行 **文檔載入 (Document Loading)** (PDF/Markdown 解析) 和 **切割 (Splitting)**。
    - 使用 `langchain` 整合 **Qdrant** (ADR-003) 進行 **向量庫 (Vector Store)** 管理 (Local RAG)。
    - 如果模板變複雜，可在我們的 `PromptManager` 中使用 `langchain` 的 **PromptTemplates**。
3.  **保留直接模型推論**: 繼續在 Worker 中直接使用 `LLMEngine` (HuggingFace) 以獲得最大的效能控制 (4-bit, streaming)。

## 決策矩陣 (Decision Matrix)

| 特性 | 自研 (目前) | LangChain (完全切換) | 混合模式 (建議) |
| :--- | :--- | :--- | :--- |
| **UI 響應性** | ⭐⭐⭐⭐⭐ (原生 Qt) | ⭐⭐ (阻塞風險) | ⭐⭐⭐⭐⭐ (Qt 包裝) |
| **RAG 實作 (Qdrant)** | ⭐ (困難/手動) | ⭐⭐⭐⭐⭐ (原生支援) | ⭐⭐⭐⭐⭐ (引入 LangChain) |
| **Prompt 除錯** | ⭐⭐⭐⭐⭐ (透明) | ⭐⭐ (不透明 Trace) | ⭐⭐⭐⭐ (受控) |
| **重構成本** | N/A | High (重寫) | Low (增加依賴) |

## 下一步 (Next Steps)
如果核准，我們將：
1.  在 `pyproject.toml` 中新增 `langchain` 和 `langchain-community`。
2.  主要在即將到來的 **RAG Phase** 中使用 LangChain 元件。
3.  在核心 Agent 控制流中堅持使用當前的自研架構。
