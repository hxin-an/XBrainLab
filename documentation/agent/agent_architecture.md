# Agent Architecture (Agent 架構設計)

## 1. 系統綜覽 (System Overview)

XBrainLab 的 Agent 系統採用 **"Headless Backend + Intelligent Bridge + RAG"** 的設計模式。
Agent 扮演「操作員」的角色，它不直接持有數據，而是透過標準化的 **Tools** 介面來操作後端的 **Study** 物件，並通過 **RAG** 檢索知識庫來增強決策能力。

```mermaid
graph TD
    %% Nodes
    User([User 👤])

    subgraph MainThread ["Main Thread (UI & Controller)"]
        direction TB
        UI[UI: ChatPanel]

        subgraph ControllerScope ["Controller Logic"]
            direction TB
            Controller[Controller: LLMController]
            PromptMgr[PromptMgr: PromptManager]
            Parser[Parser: CommandParser]

            subgraph PromptGen ["Prompt Construction "]
                direction TB
                Sys[System Prompt]
                Tools[Tool Definitions]
                Hist["History (Sliding Window)"]
                FullPrompt[Final Prompt Stack]

                Sys & Tools & Hist --> FullPrompt
            end

            Controller -- "delegates" --> PromptMgr
            PromptMgr -.-> PromptGen
        end

        ToolReg[Tool Registry]
    end

    subgraph WorkerThread ["QThread: Worker"]
        direction TB
        Worker[Worker: AgentWorker]
        LLM[Engine: LLMEngine]
    end

    subgraph Backend ["Backend System"]
        direction TB
        Study[Study Object]
    end

    %% Data Flow
    User --> |"1. Input Text"| UI
    UI --> |"2. signal: send_message"| Controller

    Controller -.-> |"Builds"| PromptGen
    FullPrompt --> |"3. signal: sig_generate(prompt)"| Worker

    Worker --> |"4. Generate(prompt)"| LLM
    LLM --> |"5. Stream Tokens"| Worker
    Worker --> |"6. signal: finished(text)"| Controller

    Controller --> |"7. Parse Response"| Parser
    Parser --> |"8. Intent (JSON)"| Controller

    Controller --> |"9. Execute Tool"| ToolReg
    ToolReg --> |"10. Call Method"| Study

    Study -.-> |"11. signal: data_changed"| UI

    %% Professional Dark Mode Styles
    classDef container fill:#1e1e1e,stroke:#3c3c3c,stroke-width:2px,color:#d4d4d4;
    classDef component fill:#2d2d2d,stroke:#5c5c5c,stroke-width:1px,color:#e0e0e0;
    classDef accent fill:#0d47a1,stroke:#64b5f6,stroke-width:2px,color:#ffffff;
    classDef logic fill:#263238,stroke:#455a64,stroke-width:1px,stroke-dasharray: 3 3,color:#b0bec5;

    class MainThread,WorkerThread,Backend,ControllerScope container;
    class UI,Controller,Parser,ToolReg,Worker,LLM,Study,Sys,Tools,Hist component;
    class FullPrompt,User accent;
    class PromptGen logic;
```

## 2. 核心元件 (Core Components)

### 2.1 Agent Controller (The Brain Stem)
*   **職責**: 負責協調 User, LLM, RAG 與 Tools 之間的訊息傳遞與狀態管理。
*   **核心模組**: `XBrainLab/llm/agent/controller.py`
*   **功能**:
    *   維護對話歷史 (Message History)。
    *   **RAG 整合**: 將 User Query 傳送至 RAG Engine，獲取相關文檔或範例，並注入 System Prompt。
    *   解析 LLM 回傳的 Tool Call 請求。
    *   在 Python 環境中執行對應的 Tool Class。
    *   **執行緒管理**: 啟動並管理 Worker 執行緒。

### 2.2 Agent Worker (The Engine)
*   **職責**: 在獨立執行緒中執行耗時的 LLM 推論。
*   **核心模組**: `XBrainLab/llm/agent/worker.py`
*   **功能**:
    *   載入 LLM 模型。
    *   執行 `generate_stream` 進行推論。
    *   透過 Signal 回傳生成的文字 Chunk 與最終結果。

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
*   **架構**: 採用 **Factory Pattern** 與 **分層設計**。
    *   `definitions/`: 定義工具介面 (Base Classes)。
    *   `mock/`: 模擬實作 (用於測試與評估)。
    *   `real/`: 真實實作 (連接 Backend)。
    *   `__init__.py`: 負責根據設定 (Mock/Real) 實例化對應的工具集。

### 2.5 Study Object (The State)
*   **定義**: `XBrainLab/backend/study.py`。
*   **職責**:
    *   是整個實驗的 **"Single Source of Truth"**。
    *   持有 Raw Data, Epochs, Training Configuration, Model Weights。

## 3. 資料流與互動機制 (Data Flow & Interaction Mechanism)

本系統採用 **MVC (Model-View-Controller)** 變體設計，利用 Qt 的 **Signal/Slot** 機制實現非同步通訊，確保 UI 流暢度。

### 3.1 角色職責 (Roles)

*   **UI 層 (The Face)**: `MainWindow`, `ChatPanel`
    *   **職責**: 只負責「顯示」與「接收輸入」。完全不處理 LLM 邏輯，不知道 Prompt 存在。
*   **Controller 層 (The Brain)**: `LLMController`
    *   **職責**: 核心指揮官。負責記憶對話 (State)、決策 (ReAct Loop)、解析工具指令，以及調度 Worker。
*   **Worker 層 (The Hand/Engine)**: `AgentWorker`
    *   **職責**: 執行引擎。負責執行最耗資源的 LLM 推論 (Inference)。運作於獨立的 `QThread` 中。

### 3.2 詳細資料傳輸流程 (Detailed Data Flow)

#### **階段一：使用者輸入 (UI -> Controller)**
1.  **使用者**在 `ChatPanel` 輸入指令（如：「幫我載入數據」）。
2.  `ChatPanel` 發出 `send_message` 信號。
3.  `MainWindow` 接收信號，轉發給 `agent_controller.handle_user_input()`。
    *   *此階段僅傳遞字串，UI 執行緒不會阻塞。*

#### **階段二：思考與推論 (Controller <-> Worker)**
4.  **Controller** 將使用者訊息加入 `self.history` (短期記憶)。
5.  **Controller** 組合完整的 Prompt (System Prompt + History)。
6.  **Controller** 發出 `sig_generate` 信號給 **Worker**。
    *   *關鍵點：跨越執行緒邊界 (Thread Boundary)。*
7.  **Worker** (在背景執行緒) 收到信號，呼叫 LLM Engine 進行推論。
8.  **Worker** 推論結束，發出 `finished` 信號，將生成文字傳回 **Controller**。

#### **階段三：執行與回應 (Controller -> UI)**
9.  **Controller** 解析回應文字 (`CommandParser`)：
    *   **情況 A (純對話)**:
        *   LLM 回應普通文字 (如 "你好")。
        *   Controller 發出 `response_ready` 信號 -> UI 顯示文字。
    *   **情況 B (工具呼叫 - ReAct Loop)**:
        *   LLM 回應 JSON 指令 (如 `{"command": "load_data"}`)。
        1.  Controller 發出 `status_update` 信號 -> UI 顯示「正在執行工具...」。
        2.  Controller **執行工具函式** (操作 `Study` 物件)。
        3.  Controller 取得執行結果 (Result)。
        4.  **自動迴圈**: Controller 將 Result 作為新的「觀察」加入歷史，**重複步驟 5**，讓 LLM 根據結果產生最終回應。

### 3.3 UI 刷新機制 (UI Refresh Mechanism)

**核心原則**: Agent/Tool **不直接操作 UI**。
UI 刷新由 **Backend (Study)** 的狀態變更信號觸發。

```text
┌──────────────┐
│   Tool Call  │  執行: study.load_dataset(...)
└──────┬───────┘
       ↓
┌──────────────┐
│ Study Object │  修改內部狀態 (self.raw_data = ...)
│  (Backend)   │
└──────┬───────┘
       ↓
┌──────────────┐
│ Emit Signal  │  發出: study.data_changed.emit()
└──────┬───────┘
       ↓
┌──────────────┐
│ UI Listener  │  接收 Signal → 刷新數據列表/圖表
│ (MainWindow) │
└──────────────┘
```

### 3.2 實現方式

#### Qt Signal/Slot 機制

**Study 發出信號**:
```python
# XBrainLab/backend/study.py
from PyQt6.QtCore import QObject, pyqtSignal

class Study(QObject):
    # 定義信號
    data_loaded = pyqtSignal(str)      # 數據載入完成
    data_modified = pyqtSignal(str)    # 數據修改 (濾波、切分等)
    training_started = pyqtSignal()    # 訓練開始
    training_finished = pyqtSignal(dict) # 訓練完成，傳遞結果

    def load_dataset(self, path):
        # 執行載入邏輯
        self.raw_data = load_gdf(path)
        # 發出信號
        self.data_loaded.emit(f"Loaded {path}")
```

**UI 連接信號**:
```python
# XBrainLab/ui/main_window.py
class MainWindow(QMainWindow):
    def __init__(self, study):
        super().__init__()
        self.study = study

        # 連接 Backend 信號到 UI 槽函數
        self.study.data_loaded.connect(self.on_data_loaded)
        self.study.data_modified.connect(self.on_data_modified)
        self.study.training_finished.connect(self.on_training_finished)

    def on_data_loaded(self, message):
        # 刷新數據列表
        self.update_dataset_list()
        # 更新狀態欄
        self.statusBar().showMessage(message)

    def on_data_modified(self, message):
        # 刷新圖表
        self.plot_widget.refresh()
```

**Tool 只負責調用**:
```python
# XBrainLab/llm/tools/dataset_tools.py
class LoadDatasetTool(BaseTool):
    def execute(self, study, path):
        # 只調用 Backend 方法，不管 UI
        study.load_dataset(path)
        return f"Dataset loaded from {path}"
```

### 3.4 Controller 訊號同步機制 (Controller Signal Synchronization)
為了支援 Agent 操作後導致的 UI 更新，`DatasetController` 繼承自 `QObject` 並發出以下信號：
*   `dataChanged`: 當數據集內容變更時（如載入、預處理）。
*   `datasetLocked(bool)`: 當數據集被鎖定/解鎖時。
*   `importFinished(int, list)`: 檔案匯入完成後。

這確保了 Agent 不論是在後台載入數據還是執行預處理，UI 都能即時響應並刷新顯示。

## 4. 專案結構快照 (Project Structure Snapshot - LLM Module Only)

以下展示 `XBrainLab/llm/` 模組的內部結構。**注意：RAG 模組將擁有自己專屬的文件資料夾 (`knowledge_base/`)，以確保檢索範圍的精確性。**

```
XBrainLab/llm/                <-- Agent 核心模組
├── agent/                    <-- 控制層
│   ├── controller.py         <-- 協調者 (Main Thread)
│   ├── worker.py             <-- 執行者 (Worker Thread)
│   ├── parser.py             <-- 輸出解析
│   ├── prompt_manager.py     <-- Prompt 建構與管理 (System+History+Tools)
│
├── core/                     <-- LLM 引擎層
│   ├── config.py             <-- 模型設定
│   └── engine.py             <-- 推論引擎 (支援 HuggingFace Local Models)
│
├── tools/                    <-- 工具介面層 (Factory Pattern)
│   ├── definitions/          <-- Base Classes (Interface)
│   │   ├── dataset_def.py
│   │   ├── preprocess_def.py
│   │   └── ...
│   ├── mock/                 <-- Mock Implementation
│   │   ├── dataset_mock.py
│   │   └── ...
│   ├── real/                 <-- Real Implementation (Planned)
│   ├── base.py               <-- Tool Base Class
│   └── __init__.py           <-- Tool Factory
│
└── rag/                      <-- [規劃中] RAG 檢索模組
    ├── engine.py             <-- 檢索邏輯
    └── knowledge_base/       <-- **RAG 專屬知識庫** (存放供 Agent 檢索的文件)
        ├── tool_definitions.md  <-- 工具規格 (從 documentation 同步或遷移)
        ├── api_reference.md     <-- 後端 API 說明
        └── few_shot_examples.md <-- 操作範例
```
