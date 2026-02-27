# Agent Architecture

## Overview

XBrainLab Agent 採用 **ReAct (Reasoning + Acting)** 模式，透過 LLM 驅動的工具呼叫操作後端。

## 核心元件

### LLMController (`controller.py`)
Agent 中樞，協調 User、LLM、RAG 與 Tools：

- `handle_user_input(text)` — 接收輸入 → RAG 檢索 → 觸發生成
- `_generate_response()` — 透過 ContextAssembler 組合 Prompt
- `_process_tool_calls()` — 執行工具呼叫、結果回饋 LLM

### ContextAssembler (`assembler.py`)
動態組裝 System Prompt + Tool Definitions + RAG Context + History。

### VerificationLayer (`verifier.py`)
Pluggable Validator 策略模式，執行前驗證工具參數：

| Validator | 適用 Tools | 驗證內容 |
|---|---|---|
| `FrequencyRangeValidator` | bandpass, standard_preprocess | `low < high`, 皆正數 |
| `TrainingParamValidator` | configure_training | epoch/batch_size 正整數 |
| `PathExistsValidator` | load_data, attach_labels | 路徑存在性 |

### AgentMetricsTracker (`metrics.py`)
結構化日誌與指標追蹤：

- **TurnMetrics**: 每輪 Token 計數、Latency、LLM 呼叫次數
- **ToolExecution**: 工具名稱、參數、執行時間、成功/失敗
- Controller 7 處 metrics 整合點

### RAG Engine (`rag/`)
語義相似度檢索（Qdrant），支援 Few-Shot 範例注入。

## 資料流

```
User Input → ChatPanel → LLMController
    ↓
RAG Retriever → Few-Shot Examples
    ↓
ContextAssembler → Full Prompt
    ↓
AgentWorker (QThread) → LLM Inference
    ↓
CommandParser → Tool Call
    ↓
VerificationLayer → Validate Params
    ↓
Tool Registry → BackendFacade → Study
    ↓
Observable → QtObserverBridge → UI Refresh
```

詳見 [完整 Agent 文檔](../../documentation/agent/agent_architecture.md)。
