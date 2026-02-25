# 術語表 (Glossary)

本文件解釋 XBrainLab 專案中常用的領域術語，包含腦科學、AI 技術與軟體工程專有名詞。

## 用戶領域 (EEG / Neuroscience)
*   **Epoch**: 從連續腦波訊號中切分出的特定時間片段 (如 -0.2s 到 0.8s)，通常以事件 (Event) 為中心。
*   **Montage**: 電極在頭皮上的配置方式 (如 10-20 系統)。
*   **ICA (Independent Component Analysis)**: 獨立成分分析，一種訊號處理技術，常用於去除眼動 (EOG) 或肌肉 (EMG) 雜訊。
*   **Artifact**: 偽影/雜訊，指非腦源性的訊號干擾 (如眨眼、咬牙)。
*   **Stimulus (Event)**: 實驗中給予受試者的刺激 (如閃光、聲音)，在訊號中標記為 Event Code。

## AI 與 Agent 技術
*   **LLM (Large Language Model)**: 大型語言模型 (如 GPT-4, Qwen, Gemini)，是 Agent 的「大腦」。
*   **RAG (Retrieval-Augmented Generation)**: 檢索增強生成。Agent 在回答前先去「查資料」(檢索向量資料庫)，再根據查到的資料回答。這能減少幻覺。
*   **Few-Shot Learning**: 在 Prompt 中提供少量的範例 (Examples)，讓 LLM 照樣造句。我們使用 `gold_set.json` 作為範例庫。
*   **Chain of Thought (CoT)**: 思維鏈。強迫 LLM 在給出最終答案前，先寫出推論過程 (Thought)，能大幅提升準確率。
*   **Vector Database (Qdrant)**: 向量資料庫。用來儲存文件或範例的「語意向量」，讓 RAG 能夠用「意思」來搜尋資料，而不是只對關鍵字。

## 系統架構 (System Architecture)
*   **Headless Backend**: 「無頭」後端。指後端邏輯 (Backend) 能夠完全獨立於 UI 運作。這對自動化測試與 Agent 操作至關重要。
*   **Observer Pattern**: 觀察者模式。一種設計模式，當資料變更時，自動通知所有訂閱者 (UI) 更新，而不是讓 UI 一直去問 (Polling)。
*   **BackendFacade**: 後端門面。專門設計給 Agent 使用的單一入口介面，簡化了 Agent 對系統的操作複雜度。
*   **Controller**: 控制器。負責協調 UI 操作與 Backend 邏輯的中介層。
*   **Study**: 研究單元。本系統的核心資料物件 (Object)，一個 Study 代表一個完整的實驗專案，包含了載入的數據 (Dataset)、預處理流程、模型設定與訓練結果。所有的 UI 操作最終都是在修改 Study 的狀態。
