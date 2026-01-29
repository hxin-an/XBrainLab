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

##  專案配置與目錄結構 (Project Configuration & Structure)

本專案採用標準化的配置檔案與目錄結構來管理開發流程、CI/CD 與程式碼品質。

### 1. 配置檔案 (Configuration Files)

| 路徑 | 對應工具 | 說明 |
| :--- | :--- | :--- |
| **`pyproject.toml`** | **Poetry** / **Ruff** / **Poe** | 專案核心設定檔。定義依賴 (Dependencies)、建置系統 (Build System)、Linter 規則以及任務腳本 (Task Runner)。 |
| **`poetry.lock`** | **Poetry** | 依賴鎖定檔。記錄確切的套件版本 Hash，確保所有開發者與 CI 環境的一致性 (Reproducibility)。 |
| **`.pre-commit-config.yaml`** | **Pre-commit** | Git Hooks 設定檔。定義 Commit 前執行的檢查 (Linting, Type Checking, Secret Detection)。 |
| **`pytest.ini`** | **Pytest** | 測試框架設定。定義測試搜尋路徑、Coverage 設定與 Warning 過濾規則。 |
| **`.secrets.baseline`** | **detect-secrets** | 用於儲存已審核的敏感字串白名單，防止機敏資訊誤傳至版本庫。 |
| **`.gitignore`** | **Git** | 定義 Git 應忽略的檔案 (如 `__pycache__`, `.env`, `.venv`)。 |

### 2. 配置目錄 (Configuration Directories)

| 目錄 | 用途 |
| :--- | :--- |
| **`.github/`** | GitHub Actions Workflow 定義檔，包含 CI/CD 自動化流程配置。 |
| **`documentation/`** | 專案文檔，包含 Roadmap, API 說明, 架構設計圖等。 |
| **`scripts/`** | 用於資料轉換、模型驗證、Benchmark 的輔助 Python 腳本。 |

##  開發工具與環境管理 (Development Tools)

### 為何選擇 Poetry 作為依賴管理？ (Why Poetry?)
本專案選擇 Poetry 取代傳統的 Conda/pip 組合，主要考量以下技術優勢：

1.  **確定性建置 (Deterministic Builds)**: Poetry 的 `lock` 機制能確保依賴關係的精確鎖定，解決了 "Dependencies Hell" 與環境不一致問題。
2.  **依賴解析 (Dependency Resolution)**: Poetry 擁有更先進的解析器，能自動處理複雜的傳遞依賴 (Transitive Dependencies) 衝突。
3.  **單一事實來源 (Single Source of Truth)**: 所有專案元數據、依賴設定、工具配置皆集中於 `pyproject.toml`，降低維護成本。

**關於 Conda 的使用建議**:
建議僅使用 Conda 管理 **Python 直譯器版本** (如建立一個純淨的 Python 3.10 環境)，具體的專案依賴包 (Libraries) 則全權交由 Poetry 在虛擬環境 (`venv`) 中管理，以避免全域環境污染。
