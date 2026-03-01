# ADR-009: 混合雙通道 Agent 架構與 MCP 整合 (未來規劃)

**日期**: 2026-03-01
**狀態**: 規劃中 (Planned for Track B)
**決策者**: 核心開發團隊

## 背景 (Context)

XBrainLab 目摽是為神經科學家提供一個強大的 AI 輔助 EEG 分析平台。在先前的重構中 (ADR-004, ADR-006)，我們成功實作了：
1. **Headless BackendFacade**: 將 UI (PyQt6) 與核心分析邏輯 (MNE/PyTorch) 完全解耦。
2. **事件驅動架構 (QtObserverBridge)**: 透過狀態變更廣播機制，讓 UI 能自動響應後端變化。
3. **隔離的 Agent 引擎**: 將 ReAct Loop、Tool Registry 與 Verification Layer 抽離至獨立的 `AgentWorker`。

隨著業界生態向「Bring Your Own Tools (BYOT)」與跨平台 AI 助理（如 Claude Desktop, Cursor, LobeChat）方向演進，綑綁單一本地模型（如 Qwen2.5）與自製的聊天介面 (ChatPanel) 無法滿足所有使用場景。使用者期望能使用他們熟悉且更強大的雲端 LLM 工具，並無縫呼叫 XBrainLab 的專業分析能力。

## 決策 (Decision)

我們決定將 XBrainLab 的架構演進為 **「混合雙通道 Agent 架構 (Hybrid Dual-Channel Agent Architecture)」**：

1. **核心原則：The Brain / The Eyes 分離**
   - **The Brain**: `BackendFacade`, `ToolRegistry` 與底層 `Study` 狀態保持不變，作為唯一的 Truth Source。
   - **The Eyes**: PyQt6 GUI 將轉型為一個純粹的 **「反應式儀表板 (Reactive Dashboard)」**，專注於高效能繪圖與互動視覺化。

2. **通道 1：原生內建 AI (Native Channel)**
   - 保留現有的 `ChatPanel` 與本地/API 模型 (Qwen/Gemini) 作為預設體驗。
   - 確保未擁有外部 AI 訂閱的跨領域使用者，開箱即可使用完整的 AI 輔助功能。

3. **通道 2：外部 MCP 伺服器 (External MCP Channel) [新增]**
   - 實作基於 **Model Context Protocol (MCP)** 的伺服器端點 (如 `interfaces/mcp_server.py`)。
   - 將 XBrainLab 的 19+ 個資料處理與分析工具，動態註冊並暴露給相容 MCP 的外部客戶端 (例如 Claude Desktop)。
   - 當外部 LLM 透過 MCP 呼叫工具時，請求將經過與原生通道一樣的 `VerificationLayer` 嚴格把關，再送入 `BackendFacade` 執行。

## 影響與後果 (Consequences)

### 正面影響 (Pros)
- **生態系整合**: 讓全世界最頂尖的 LLM (如 Claude-3.5-Sonnet) 能直接取得並操作 EEG 領域的專業工具，大幅拉高天花板。
- **UI 維護成本降低**: 外部 AI 工具提供更好的 Markdown 繪製、對話歷史管理甚至語音輸入，我們無需在 `ChatPanel` 重造輪子。
- **架構優越性體現**: 證明了我們近期推動的解耦工程 (Decoupling) 是極具前瞻性的。事件驅動的設計讓 GUI 不管是被內部 Qwen 還是外部 Claude 驅動，都能即時更新狀態。

### 負面影響與挑戰 (Cons)
- **併發控制 (Concurrency)**: 如果使用者同時在原生 ChatPanel 下令，又在外部 Claude 下令，必須在 `BackendFacade` 或 Agent 層實作嚴格的執行鎖 (Execution Lock) 或任務序列化，防止 Race Conditions 毀損 `Study` 狀態。
- **環境通訊 (IPC)**: MCP 伺服器與 PyQt6 GUI 必須共享同一個記憶體空間（例如在同一個 Python Process 中以 Background Thread 啟動 MCP），才能讓 GUI 及時收到 `Study` 的狀態變更事件。
- **無狀態與有狀態設計的衝突**: MCP 預設偏向無狀態工具呼叫，但我們的工具 (如 `apply_bandpass_filter`) 是有狀態的 (mutates `Study`)。需要清晰定義對外部的介面。

## 實作路徑 (Implementation Path)

本決策已被納入 `ROADMAP.md` 的 Track B (AI Agent 增強) 階段。
第一步將實作一個 Proof-of-Concept (POC)：建立只包含 `list_files` 與 `load_data` 兩個工具的 MCP Server 腳本，透過 Claude Desktop 驗證對 `Study` 狀態的遠端操作可行性。
