# Agent Code Structure (Agent 程式碼結構說明)

本文檔詳細說明 `XBrainLab/llm/` 目錄下各個 Python 檔案的內部結構、類別職責與函式邏輯。

## 1. `agent/` (Agent 控制層)

此目錄包含 Agent 的大腦與神經系統，負責決策、記憶與執行緒管理。

### `controller.py`
*   **類別 `LLMController(QObject)`**
    *   **職責**: Agent 的中樞神經，協調 UI、Worker 與 Tools。
    *   **屬性**:
        *   `history`: List[Dict]，儲存對話歷史 (User, Assistant, System)。
        *   `worker`: `AgentWorker` 實例。
        *   `worker_thread`: `QThread` 實例。
    *   **方法**:
        *   `handle_user_input(text)`: 接收 UI 輸入，更新歷史，觸發生成。
        *   `_generate_response()`: 組合 Prompt，發送信號給 Worker。
        *   `_on_generation_finished()`: 接收 Worker 回應，呼叫 Parser。
        *   `_execute_tool(name, params)`: 執行工具，並將結果餵回給 Agent (ReAct Loop)。

### `worker.py`
*   **類別 `GenerationThread(QThread)`**
    *   **職責**: 執行實際的 LLM 推論迴圈，避免阻塞 Worker Thread 的事件迴圈。
    *   **方法 `run()`**: 呼叫 `engine.generate_stream` 並透過信號發送 Chunk。
*   **類別 `AgentWorker(QObject)`**
    *   **職責**: 駐留在背景執行緒的執行者，管理 LLM Engine。
    *   **方法**:
        *   `initialize_agent()`: 載入模型 (Lazy Loading)。
        *   `generate_from_messages(messages)`: 啟動 `GenerationThread` 進行推論。

### `parser.py`
*   **類別 `CommandParser`**
    *   **職責**: 解析 LLM 的文字輸出，提取 JSON 工具指令。
    *   **方法 `parse(text)`**:
        *   使用 Regex 尋找 \`\`\`json ... \`\`\` 區塊。
        *   驗證 JSON 格式。
        *   回傳 `(command_name, parameters)` Tuple 或 `None`。

### `prompts.py`
*   **職責**: 管理 System Prompt 模板。
*   **函式 `get_system_prompt(tools)`**:
    *   將 `AVAILABLE_TOOLS` 的定義轉換為 JSON Schema 格式。
    *   注入到 System Prompt 中，教導 Agent 如何使用工具。

---

## 2. `core/` (LLM 核心層)

此目錄負責與底層 LLM 模型 (如 HuggingFace Transformers, llama.cpp) 介接。

### `engine.py`
*   **類別 `LLMEngine`**
    *   **職責**: 封裝模型載入與推論細節。
    *   **方法**:
        *   `load_model()`: 根據 Config 載入 Tokenizer 和 Model。
        *   `generate_stream(messages)`: 接收對話列表，執行串流生成 (Yield str)。
    *   **實作細節**: 目前支援本地模型 (如 Phi-3, Qwen)，未來可擴充 API 支援。

### `config.py`
*   **類別 `LLMConfig`**
    *   **職責**: 定義模型參數。
    *   **屬性**:
        *   `model_path`: 模型權重路徑。
        *   `max_new_tokens`: 最大生成長度。
        *   `temperature`: 隨機性參數。
        *   `device`: 執行裝置 (cuda/cpu)。

---

## 3. `tools/` (工具模組)
此目錄採用分層架構，以支援 Mock 與 Real 工具的無縫切換。

### 目錄結構
*   `definitions/`: 定義所有工具的 Base Class (Interface)。包含 `name`, `description`, `parameters` 定義，但 `execute` 方法未實作。
    *   `dataset_def.py`, `preprocess_def.py`, `training_def.py`, `ui_control_def.py`
*   `mock/`: 繼承 Base Class 並實作 Mock 邏輯。用於測試與評估。
    *   `dataset_mock.py`, `preprocess_mock.py`, ...
*   `real/`: (待實作) 繼承 Base Class 並實作真實 Backend 呼叫。
*   `__init__.py`: 實作工廠模式 `get_all_tools(mode='mock')`，負責實例化並回傳工具列表。

### 主要工具類別 (Base Classes)

#### `dataset_def.py`
*   `BaseListFilesTool`: 列出檔案。
*   `BaseLoadDataTool`: 載入數據 (支援檔案與目錄)。
*   `BaseAttachLabelsTool`: 綁定標籤。
*   `BaseClearDatasetTool`: 清除數據。
*   `BaseGetDatasetInfoTool`: 獲取數據資訊。
*   `BaseGenerateDatasetTool`: 生成訓練集。

#### `preprocess_def.py`
*   `BaseStandardPreprocessTool`: 標準預處理流程。
*   `BaseBandPassFilterTool`: 帶通濾波。
*   `BaseNotchFilterTool`: 陷波濾波。
*   `BaseResampleTool`: 重採樣。
*   `BaseNormalizeTool`: 正規化。
*   `BaseRereferenceTool`: 重參考。
*   `BaseChannelSelectionTool`: 通道選擇。
*   `BaseSetMontageTool`: 設定 Montage。
*   `BaseEpochDataTool`: 切段數據。

#### `training_def.py`
*   `BaseSetModelTool`: 設定模型。
*   `BaseConfigureTrainingTool`: 設定訓練參數。
*   `BaseStartTrainingTool`: 開始訓練。

#### `ui_control_def.py`
*   `BaseSwitchPanelTool`: 切換 UI 面板與視圖。
    *   支援 `view_mode` 參數，可精確導航至特定 Tab (如 `saliency_map`, `metrics`)。
