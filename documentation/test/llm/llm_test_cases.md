# LLM Module Unit Test Cases

本文檔記錄 XBrainLab LLM 模組的單元測試案例。

## 1. Command Parser (`test_parser.py`)

測試 `XBrainLab.llm.agent.parser.CommandParser` 的解析邏輯。

### Case 1.1: Valid JSON Command
*   **Input**: 
    ```text
    Sure, I can help with that.
    ```json
    {
        "command": "load_data",
        "parameters": {"file_paths": ["/data/A.gdf"]}
    }
    ```
    ```
*   **Expected Output**: `("load_data", {"file_paths": ["/data/A.gdf"]})`

### Case 1.2: No JSON Block
*   **Input**: "Just a normal conversation response."
*   **Expected Output**: `None`

### Case 1.3: Malformed JSON
*   **Input**: 
    ```text
    ```json
    { "command": "load_data", "parameters": { ... broken ...
    ```
    ```
*   **Expected Output**: `None` (Should log warning but not crash)

### Case 1.4: Multiple JSON Blocks
*   **Input**: Text with two JSON blocks.
*   **Expected Output**: Should parse the *first* valid block found.

---

## 2. System Prompts (`test_prompts.py`)

測試 `XBrainLab.llm.agent.prompts.get_system_prompt` 的生成邏輯。

### Case 2.1: Prompt Structure
*   **Input**: A list of Mock Tools.
*   **Expected Output**: String containing:
    *   "You are XBrainLab Assistant"
    *   "Available Tools:"
    *   JSON schema of the provided tools.

### Case 2.2: Tool Schema Formatting
*   **Input**: Single tool `LoadDataTool`.
*   **Expected Output**: String must contain `"name": "load_data"` and correct parameter definitions.

---

## 3. Mock Tools (`test_tools.py`)

測試 `XBrainLab.llm.tools` 下各個 Mock Tool 的執行回傳。

### Case 3.1: Dataset Tools
*   **Tool**: `ListFilesTool`
*   **Action**: Execute with directory path.
*   **Expected**: Return mock file list string (e.g., "['A01T.gdf']").

### Case 3.2: Preprocess Tools
*   **Tool**: `StandardPreprocessTool`
*   **Action**: Execute with parameters.
*   **Expected**: Return "Applied standard preprocessing pipeline."

### Case 3.3: Training Tools
*   **Tool**: `SetModelTool`
*   **Action**: Execute with `model_name="EEGNet"`.
*   **Expected**: Return "Model set to EEGNet."

---

## 4. Controller Logic (`test_controller.py`)

測試 `XBrainLab.llm.agent.controller.LLMController` 的狀態管理與流程控制。
*注意：此測試需 Mock `AgentWorker` 與 `Study` 以隔離依賴。*

### Case 4.1: User Input Handling
*   **Action**: Call `handle_user_input("Hello")`.
*   **Expected**: 
    *   "Hello" added to `history`.
    *   `sig_generate` signal emitted.

### Case 4.2: Tool Execution Flow (ReAct)
*   **Action**: Simulate Worker returning a JSON tool command.
*   **Expected**:
    *   `status_update` signal emitted ("Executing tool...").
    *   Tool executed.
    *   Tool output added to `history` (Role: User).
    *   `sig_generate` emitted again (Loop).

### Case 4.3: Sliding Window
*   **Action**: Add 20 messages to history, then trigger generation.
*   **Expected**: The messages passed to Worker should only contain the last N rounds (plus System Prompt).
