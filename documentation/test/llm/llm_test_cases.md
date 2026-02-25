# LLM Module Unit Test Cases

**最後更新**: 2026-02-25

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

## 2. Context Assembler (`test_assembler.py`)

測試 `XBrainLab.llm.agent.assembler.ContextAssembler` 的 Prompt 組裝邏輯。

### Case 2.1: Prompt Structure
*   **Input**: A list of Mock Tools + RAG context.
*   **Expected Output**: String containing:
    *   "You are XBrainLab Assistant"
    *   "Available Tools:"
    *   JSON schema of the provided tools.
    *   RAG 檢索結果（若有）。

### Case 2.2: Tool Schema Formatting
*   **Input**: Single tool `LoadDataTool`.
*   **Expected Output**: String must contain `"name": "load_data"` and correct parameter definitions.

### Case 2.3: RAG Context Injection
*   **Input**: RAG retrieval results (few-shot examples).
*   **Expected Output**: Prompt 中包含 "Similar Example:" 區塊。

### Case 2.4: Empty RAG Context
*   **Input**: No RAG results available.
*   **Expected Output**: Prompt 正常生成，無 RAG 區塊。

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

---

## 5. Verification Layer (`test_verifier.py`)

測試 `XBrainLab.llm.agent.verifier.VerificationLayer` 的安全檢查邏輯。

### Case 5.1: Valid Tool Call
*   **Input**: `{"command": "load_data", "parameters": {"file_paths": ["/data/A.gdf"]}}`
*   **Expected**: Verification passes, tool call 允許執行。

### Case 5.2: Unknown Command
*   **Input**: `{"command": "unknown_tool", "parameters": {}}`
*   **Expected**: Verification fails, 回傳錯誤訊息。

### Case 5.3: Invalid Parameters
*   **Input**: `{"command": "bandpass_filter", "parameters": {"low_freq": -1}}`
*   **Expected**: Verification fails（無效參數範圍），觸發 Self-Correction。

---

## 6. RAG Retriever (`test_rag.py`)

測試 `XBrainLab.llm.rag.retriever` 的語義檢索功能。

### Case 6.1: Similar Example Retrieval
*   **Input**: Query "load two files from /home/data/"
*   **Expected**: 回傳 top-K 個相似案例，包含 `load_data` 相關範例。

### Case 6.2: Metadata Filtering
*   **Input**: Query with category filter `dataset`.
*   **Expected**: 回傳結果僅包含 Dataset 類別工具。

### Case 6.3: Empty Index
*   **Input**: Query against empty Qdrant index.
*   **Expected**: 回傳空列表，不拋出例外。

---

## 7. LLM Engine Backends (`test_engine.py`)

測試 `XBrainLab.llm.core.engine.LLMEngine` 與各 Backend 的初始化邏輯。

### Case 7.1: Backend Selection
*   **Input**: `LLMConfig(inference_mode="gemini")`
*   **Expected**: Engine 建立 `GeminiBackend` 實例。

### Case 7.2: Local Backend Fallback
*   **Input**: `LLMConfig(inference_mode="local")` 且無 GPU。
*   **Expected**: 嘗試載入模型時拋出明確錯誤（非靜默失敗）。

### Case 7.3: Stream Generation
*   **Input**: Mock backend, call `generate_stream(messages)`.
*   **Expected**: 回傳 generator/iterator，逐步 yield tokens。
