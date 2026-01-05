# XBrainLab Agent Architecture Design

## 1. 核心理念 (Core Concept)

本架構採用 **"Headless Backend + Agent Bridge"** 模式。
- **Study (Backend)**: 負責所有業務邏輯與數據狀態，不依賴 UI。
- **Agent (Controller)**: 透過 Tool Call API 操作 Study，扮演「自動化使用者」的角色。
- **UI (View)**: 透過信號 (Signals) 監聽狀態變更，被動刷新畫面。

### UI Integration Strategy
UI 層 (`ui_pyqt`) 不直接呼叫 Agent 的內部方法，而是透過 `AgentWorker` 進行非同步溝通：
*   **`AgentWorker` (`agent_worker.py`)**:
    *   繼承 `QObject`，運行於獨立執行緒。
    *   持有 `AgentExecutor` 和 `Study` 的引用。
    *   **Signals**:
        *   `sig_agent_response(str)`: 回傳 LLM 的文字回應。
        *   `sig_study_updated()`: **關鍵信號**，當 Tool 執行成功後發送，通知 UI 刷新。
        *   `sig_error(str)`: 錯誤回報。

### Design Rationale: Why No Direct UI Manipulation? (設計決策：為何 Agent 不直接操作 UI？)

我們嚴格禁止 Agent 的 Tool 直接封裝 UI 操作（例如 `update_label`, `plot_chart`），而是必須操作 `Study` (Backend)，原因如下：

1.  **執行緒安全 (Thread Safety)**
    *   **UI 運行於主執行緒 (Main Thread)**，而 **Agent 運行於背景工作執行緒 (Worker Thread)**。
    *   在 PyQt 等 GUI 框架中，跨執行緒直接操作 UI 元件極易導致 **Race Condition** 或 **程式崩潰 (Crash)**。
    *   透過 `Signals` (如 `sig_study_updated`) 通知 UI 刷新，是確保穩定性的唯一正確途徑。

2.  **單一真理來源 (Single Source of Truth)**
    *   **`Study` 物件** 是系統狀態的唯一真理來源。
    *   若 Agent 直接修改 UI 而未更新 `Study`，將導致 **畫面顯示與後端數據不一致**。
    *   正確資料流應為：`Agent` -> 修改 `Study` -> `Study` 狀態變更 -> 通知 `UI` 重繪。

3.  **測試與維護性 (Testing & Maintainability)**
    *   **可測試性**：封裝後端邏輯 (`Study`) 讓我們能在 **Headless (無介面)** 環境下進行自動化測試與 CI/CD。若 Tool 綁定 UI，測試將變得極其困難。
    *   **解耦**：UI 佈局經常變動。將 Agent 綁定於穩定的業務邏輯 (`Study`) 上，可避免因 UI 改版而導致 Agent 功能失效。

## 2. 詳細運作流程 (Detailed Operational Flow)

### 2.1. 使用者請求階段 (Request Phase)
1.  **UI (`ChatPanel`)**: 使用者輸入 "幫我載入 data.set"。
2.  **UI (`MainWindow`)**: 呼叫 `agent_worker.generate(user_input)`。
3.  **Worker (`AgentWorker`)**:
    *   呼叫 `agent.components.memory.context.add_user_message(user_input)` 更新歷史。
    *   呼叫 `agent.core.agent.Agent.run()` 開始思考。

### 2.2. 思考與決策階段 (Reasoning Phase)
4.  **Agent (`agent.core.agent`)**:
    *   **RAG**: 呼叫 `agent.components.memory.rag.search(user_input)` 檢索 `agent/resources/knowledge_base`。
    *   **Prompt**: 讀取 `agent/resources/prompts`，並呼叫 `agent.components.memory.context.build_system_prompt()` 組裝。
    *   **LLM**: 將 (System Prompt + History) 送給 `agent.components.llm.backend` (OpenAI/Local)。
5.  **LLM**: 回傳 Tool Call 指令：`{"name": "load_data", "args": {"filepath": "data.set"}}`。

### 2.3. 執行與操作階段 (Execution Phase)
6.  **Agent (`agent.core.agent`)**: 解析 LLM 回應，發現有 Tool Call。
7.  **Executor (`agent.core.executor`)**:
    *   **Constraint Check**: 呼叫 `agent.core.state.check_state("load_data", study)`。若不通過，直接回傳錯誤給 LLM。
    *   **Dispatch**: 找到 `agent.components.tools.dataset.DatasetTools.load_data`。
    *   **Execute**: 執行 `tool.load_data("data.set")`。
8.  **Tool (`agent.components.tools`)**:
    *   呼叫 `study.get_raw_data_loader()`。
    *   執行實際載入邏輯，更新 `study` 內部狀態。
    *   回傳結果字串 "Successfully loaded..."。

### 2.4. 回饋與更新階段 (Feedback Phase)
9.  **Agent (`agent.core.agent`)**:
    *   將 Tool 結果加入對話歷史。
    *   (可選) 將結果再次送給 LLM 產生總結文字。
10. **Worker (`AgentWorker`)**:
    *   收到 Agent 執行完畢。
    *   發送 `sig_study_updated` 信號。
    *   發送 `sig_agent_response` (LLM 的回答文字)。
11. **UI (`MainWindow`)**:
    *   收到 `sig_study_updated` -> 呼叫 `current_panel.update_panel()` -> 畫面刷新。
    *   收到 `sig_agent_response` -> 顯示在聊天視窗。

## 3. 檔案結構規劃 (File Structure)

我們計劃進行重構，將後端邏輯集中到 `core` 目錄，並新增 `agent` 目錄。

```text
XBrainLab/
├── core/                   # [Refactor] 核心後端邏輯 (原散落在根目錄的模組移入此處)
│   ├── study.py            # [後端接口]
│   ├── dataset/            # 數據集管理
│   ├── load_data/          # 數據載入
│   ├── preprocessor/       # 預處理
│   ├── training/           # 訓練邏輯
│   └── ...
│
├── agent/                  # [NEW] Agent 核心邏輯 (與 UI 無關)
│   ├── __init__.py
│   │
│   ├── core/               # [核心層] 負責調度與決策
│   │   ├── agent.py        # (原 core.py) 主控邏輯
│   │   ├── executor.py     # Tool Call 執行器
│   │   ├── config.py       # 配置管理
│   │   └── state.py        # (原 constraints.py) 狀態檢查與工作流約束
│   │
│   ├── components/         # [組件層] 提供能力的模組
│   │   ├── llm/            # LLM Backend (OpenAI/Local)
│   │   ├── memory/         # Context Manager & RAG Logic
│   │   ├── vector_db/      # 向量資料庫 (ChromaDB)
│   │   └── tools/          # Tool Definitions (Dataset, Preprocess...)
│   │
│   ├── resources/          # [資源層] 靜態檔案
│   │   ├── prompts/        # System Prompts & Templates (i18n)
│   │   └── knowledge_base/ # RAG 文檔與向量庫 (原 agent/resources)
│   │
│   └── devops/             # [運維層] 測試與監控
│       ├── eval/           # 自動化評估 (Golden Dataset, Scorer)
│       └── logs/           # Agent Trace Logs
│
└── ui_pyqt/                # UI 層
    ├── agent_worker.py     # [Refactor] 連接 Agent 與 UI
    └── ...

├── tests/                  # [Refactor] 集中管理所有測試
│   ├── unit/               # 單元測試 (原散落在各模組的 tests 移入)
│   ├── integration/        # 整合測試
│   ├── data/               # [NEW] 測試用數據檔案
│   └── conftest.py         # Pytest Fixtures
```

## 4. 詳細組件設計 (Component Details)

### 4.1. Core Layer (`agent/core/`)
*   **`agent.py`**: Agent 的大腦。負責接收 User Input，協調 RAG 檢索、Prompt 組裝、LLM 呼叫，並處理 Tool Call 的回傳結果。
*   **`executor.py`**: 執行器。負責解析 LLM 的 Tool Call 指令，進行參數驗證，並分派給對應的 Tool 函數。
*   **`state.py`**: 狀態守門員。實作 `check_state(tool_name, study)`，確保在執行某個 Tool 之前，Study 的狀態是合法的（例如：必須先載入數據才能訓練）。
*   **`config.py`**: 配置中心。管理 API Keys、模型選擇 (GPT-4/Llama)、RAG 路徑、語言設定 (i18n) 等。

### 4.2. Components Layer (`agent/components/`)
*   **`llm/`**:
    *   **`base.py`**: 定義抽象基類 `LLMBackend`，規範 `generate()` 介面。
    *   **`openai.py`**: 實作 OpenAI/Gemini API 呼叫，支援 Streaming。
    *   **`local.py`**: 實作本地模型呼叫 (Ollama/Llama.cpp)。
*   **`memory/`**:
    *   **`context.py`**: 短期記憶。管理對話歷史 (History)，負責 Token 計算與截斷 (Truncation)，並組裝最終的 System Prompt。
    *   **`rag.py`**: 知識檢索。整合 `LangChain` 與 `ChromaDB`，根據 User Input 檢索最相關的文檔片段。
*   **`tools/`**:
    *   **`base.py`**: Tool 基類，定義 `get_definitions()` (JSON Schema) 與 `execute()`。
    *   **`dataset.py`**: 封裝 `study.load_data`, `study.clear_dataset` 等操作。
    *   **`preprocess.py`**: 封裝 `study.filter`, `study.ica` 等操作。
    *   **`visualization.py`**: 封裝繪圖操作 (e.g., `plot_raw`, `plot_psd`)，回傳圖片路徑或 Base64 給 UI 顯示。
    *   **`evaluation.py`**: 封裝模型評估操作 (e.g., `evaluate_model`, `confusion_matrix`)。

### 4.3. Resources & DevOps
*   **`resources/prompts/`**: 存放 YAML 格式的 Prompt 模板，支援多語言 (e.g., `system_en.yaml`)。
*   **`devops/eval/`**: 自動化評估系統。包含 Golden Dataset (標準問答集) 與 Scorer (評分器)。
*   **`devops/logs/`**: 結構化的 Trace Log，記錄完整的 "Input -> Prompt -> Output -> Tool" 流程。

## 5. 版本迭代計畫 (Roadmap & Implementation)

### Phase 1: 核心重構與基礎 (Core Refactoring & Setup) - "Ready"
*   **目標**：完成檔案結構重構與環境準備，確保現有功能不受影響。
*   **詳細任務**：
    1.  **檔案結構重構**：建立 `agent/core`, `agent/components` 等目錄，並將 `study.py` 移至 `core/` (需修改所有 import 路徑)。
        *   **Thread Safety**: 在 `Study` 中引入 `threading.Lock` 或 `QMutex`，確保所有修改狀態的操作（如 `load_data`）都是線程安全的。
    2.  **環境與依賴設定**：
        *   建立 `requirements_agent.txt`，隔離 Agent 相關依賴 (`langchain`, `chromadb`, `ollama`)。
    3.  **單元測試 (Core)**：
        *   確保重構後的 `core/study.py` 通過所有既有測試。

### Phase 2: Agent 原型 (Agent Prototype) - "Hello World"
*   **目標**：實現最小可行性 Agent，打通 UI -> Agent -> Study 的迴圈。
*   **詳細任務**：
    1.  **LLM Backend 實作**：
        *   優先實作 `LocalBackend` (使用 `ollama` 或 `llama-cpp-python`)。
        *   **Basic System Prompt**: 撰寫基礎 System Prompt。
    2.  **Tool Call API 設計 (v1)**：
        *   實作 `DatasetTools` (Load/Clear)。
        *   定義 JSON Schema 生成邏輯。
    3.  **AgentExecutor 實作**：
        *   **Robust JSON Parser**: 處理 Local Model 的格式問題。
        *   **Type Validation**: 自動轉型參數。
        *   **Timeout & Exception Handling**: 基礎的錯誤防護。
    4.  **UI 整合**：
        *   **Settings Dialog**: 設定 Backend/API Key。
        *   **Busy Indicator**: 顯示執行狀態。
        *   連接 `sig_study_updated` 信號。
    5.  **Basic Eval System (v0.1)**：
        *   驗證 Local Model 能否正確執行 `load_data`。

### Phase 3: 知識增強 (Knowledge & Context) - "Intelligent"
*   **目標**：讓 Agent 具備領域知識，並能進行多輪對話。
*   **詳細任務**：
    1.  **RAG System 實作**：
        *   使用 `ChromaDB` 作為向量資料庫 (Vector Store)。
        *   使用 `LangChain` 的 `RecursiveCharacterTextSplitter` 進行文檔切塊 (Chunking)。
        *   實作 `Retriever`：根據 User Query 檢索 Top-3 相關文檔。
    2.  **Context Manager 實作**：
        *   實作 `Sliding Window` 機制，保留最近 N 輪對話。
        *   **Token Limit Protection**: 計算當前 Prompt 的 Token 數量，若超過模型限制 (e.g. 8k)，主動截斷最舊的歷史訊息或減少 RAG 檢索數量，防止 API 報錯。
        *   **Prompt Assembly**：動態組裝 `System Prompt + RAG Context + Study State Summary + History`。
    3.  **Backend 擴充**：
        *   實作 `OpenAIBackend` (作為 Local Model 的替代方案)。

### Phase 4: 工具擴充與管控 (Tools & Control) - "Capable & Safe"
*   **目標**：大幅擴充 Agent 的能力邊界，並確保操作安全。
*   **詳細任務**：
    1.  **擴充 Tools**：
        *   實作 `PreprocessTools` (Filter, ICA)。
        *   實作 `TrainingTools` (Config, Train)。
        *   實作 `VisualizationTools` (Plotting)。
        *   實作 `EvaluationTools` (Metrics, Confusion Matrix)。
    2.  **Workflow Constraints (v1)**：
        *   在 `agent/core/state.py` 定義狀態檢查表。
        *   例如：`train_model` 前檢查 `study.dataset` 是否為空。
        *   若檢查失敗，回傳 "Pre-condition failed: Data not loaded" 給 LLM，引導其修正。
    3.  **安全性機制 (Safety Guardrails)**：
        *   實作 **Human-in-the-loop**：針對 `clear_dataset` 等破壞性操作，回傳 `ConfirmationRequest` 信號，等待 UI 確認後再執行。

### Phase 5: 體驗與運維 (Experience & DevOps) - "Polished"
*   **目標**：提升使用者體驗，並建立長期維護與評估機制。
*   **詳細任務**：
    1.  **Streaming Response**：
        *   修改 `LLMBackend` 支援 `yield` 輸出。
        *   `AgentWorker` 新增 `sig_token` 信號，即時更新 UI。
    2.  **Advanced Eval System**：
        *   **擴充 Golden Dataset**：覆蓋 RAG 問答與複雜操作流程。
        *   **Scorer 升級**：
            *   **Response Quality**: 使用 LLM-as-a-Judge 評分回答的友善度。
        *   **CI 整合**：在 GitHub Actions 中加入 Eval 步驟，防止 Regression。
    3.  **錯誤自我修正 (Self-Correction)**：
        *   實作 Retry Loop：當 Tool 報錯時，將 Error Message 回傳給 LLM，讓其嘗試修正參數並重試 (Max Retries = 3)。
  



