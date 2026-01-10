# Agent Documentation

本目錄包含 XBrainLab Agent 的相關文檔，定義了 Agent 的架構、工具介面以及開發策略。

## 文件導覽

*   **[Tool Definitions (工具定義)](tool_definitions.md)**: 
    *   詳列 Agent 可用的所有工具 (Dataset, Preprocessing, Training, Visualization)。
    *   這是開發 Mock Tools 和 LLM System Prompt 的主要依據。

*   **[Agent Architecture (架構說明)](agent_architecture.md)**: 
    *   說明 Agent 與 Backend (`Study`) 之間的互動模式。

## 重要設計決策 (Key Design Decisions)

### 3.1 邏輯卸載 (Logic Offloading)
*   **傳統做法**: 寫複雜的 Python Script 去自動配對檔案、自動判斷參數。
*   **Agent 做法**: 提供簡單的工具 (`list_files`)，讓 LLM 自己看、自己判斷。
*   **優點**: Python 程式碼保持極簡 (KISS原則)，複雜的模糊邏輯交由 LLM 處理，且隨時可通過對話修正。

### 3.2 State Awareness (狀態感知)
*   **問題**: LLM 如何知道現在載入檔案了沒？濾波過了沒？
*   **解法**: 提供 `get_dataset_info` 或 `get_study_status` 工具。
*   **SOP**: Agent 在執行破壞性操作 (如 `start_training`) 前，應先呼叫 Info 工具確認當前狀態。

## 實作計畫 (Implementation Plan)

本計畫採用 **"Brain First" (大腦優先)** 策略，優先驗證 Agent 的認知與邏輯能力，最後才進行後端整合。

### 階段一：架構與定義 (Foundation) - [Completed]
1.  **規劃架構**: 確定 Headless Backend + Agent + RAG 架構。
2.  **定義 Tool Call**: 完成 `tool_definitions.md` 規格書，確立介面標準。

### 階段二：認知驗證 (Cognitive Validation) - [Current Focus]
1.  **建立評分機制 (Evaluation Setup)**: 
    *   建立 `tests/scenarios/`，包含「使用者指令」對應「預期標準答案」的測試集 (Golden Dataset)。
    *   專注於 **Happy Path** (正確路徑) 的測試。
2.  **基礎 Mock 實作 (Basic Mocking)**: 
    *   建立極簡的 Python Mock Tools (回傳 Dummy Result)，目的僅是讓 LLM 能跑完對話流程，不涉及複雜邏輯。
3.  **LLM 能力測試 (Capability Test)**: 
    *   跑通測試集，調優 System Prompt，確保 LLM 能在無後端情況下，針對標準指令生成正確的 Tool Call 序列。

### 階段三：知識與穩健性增強 (Knowledge & Robustness)
1.  **RAG 系統建置**: 導入向量資料庫，讓 Agent 能查閱文檔參數。
2.  **負面測試 (Negative Testing)**: 加入模糊指令、錯誤參數等測試案例，訓練 Agent 的錯誤恢復能力。
3.  **上下文管理 (Context Management)**: 優化長對話的狀態記憶，確保多輪操作的連貫性。

### 階段四：真實整合 (Integration)
1.  **等待前後端就緒**: 當 Backend `Study` class 功能穩定。
2.  **實作真實 Tool Call**: 將 Mock Tools 的 Dummy Return 替換為真實的 `study` 呼叫。

