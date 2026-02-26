# XBrainLab

[![CI](https://github.com/hxin-an/XBrainLab/actions/workflows/ci.yml/badge.svg)](https://github.com/hxin-an/XBrainLab/actions/workflows/ci.yml)

XBrainLab 是一個專為腦波 (EEG) 研究設計的智慧分析平台。本專案的核心目標是**評估腦波數據的分析價值**，透過結合深度學習模型與顯著圖 (Saliency Map) 技術，協助研究人員判斷數據品質並理解模型決策依據。

## 核心功能 (Key Features)

*   **數據價值評估 (Data Valuation)**：利用深度學習模型自動分析腦波數據，判斷其是否具備後續分析或訓練的價值。
*   **可解釋性視覺化 (Saliency Map)**：生成顯著圖 (Saliency Map) 以視覺化模型關注的腦波特徵區域，提供直觀的解釋性分析。
*   **深度學習整合**：內建 PyTorch 模型訓練介面，支援模型訓練、評估與即時監控。
*   **AI 智能助手**：整合 LLM Agent，支援自然語言指令操作與 RAG 知識問答，降低操作門檻。
*   **基礎訊號處理**：提供濾波 (Filtering)、重參考 (Re-referencing) 等必要的預處理工具。
*   **模組化架構 (Modular Architecture)**：UI 與後端邏輯嚴格分離，提供更高的系統穩定性與可測試性。

## 系統需求 (System Requirements)

*   **OS**: Linux (推薦), Windows, macOS
*   **Python**: 3.10+
*   **RAM**: 建議 16GB 以上 (處理大型 EEG 資料)
*   **GPU**: NVIDIA GPU (建議，用於加速模型訓練)

## 下載專案 (Download)
1.  **Clone Repository**:
    ```bash
    git clone https://github.com/hxin-an/XBrainLab.git
    cd XBrainLab
    ```

## 快速開始 (Quick Start)

### 1. 環境安裝
本專案使用 [Poetry](https://python-poetry.org/) 進行相依性管理。

```bash
# 安裝 Poetry (如果尚未安裝)
curl -sSL https://install.python-poetry.org | python3 -

# [選項 1] 完整安裝 (包含 LLM 工具與開發依賴)
poetry install --with llm,dev,test

# [選項 2] 標準安裝 (GUI + 核心後端)
poetry install

# [選項 3] 加上 LLM 功能
poetry install --with llm
```

### 2. 啟動程式
```bash
# 啟動 XBrainLab (需 GUI 環境)
poetry run python run.py
```
### 3. LLM 設定 (可選)
XBrainLab 支援 **Local GPU** (HuggingFace), **OpenAI API**, 與 **Google Gemini API**。
系統會自動讀取 `.env` 檔案中的設定。

**步驟 1: 建立設定檔**
複製範例檔案並重新命名為 `.env`：
```bash
cp .env.example .env
```

**步驟 2: 填寫 API Key**
編輯 `.env` 檔案，填入您的 API Key：
```ini
# Google Gemini
GEMINI_API_KEY=AIza...

# OpenAI / DeepSeek
OPENAI_API_KEY=sk-...
```

**步驟 3: 切換模式**
您可以在 `.env` 中設定預設模式，或是修改 `XBrainLab/llm/core/config.py`：
```python
inference_mode = "gemini"  # 或 "api", "local"
```

**步驟 4: 驗證連線**
```bash
# 驗證 Gemini 連線
poe verify-gemini

# [工具] 列出可用模型 (包含 Preview 版)
poe list-models
```

## 測試 (Testing)

本專案提供多種 Poetry 指令來執行不同層級的測試。

### 執行測試
本專案已整合 **Poe the Poet**，強烈建議使用簡化指令：

```bash
# 執行所有測試 (單元測試 + 整合測試)
poe test

# 僅執行單元測試
poe test-unit

# 執行架構合規性檢查 (驗證 Dialog 層解耦)
poe check-architecture

# [驗證] 執行 Real Tools End-to-End 驗證流程 (Load -> Preprocess -> Train)
poe verify

# [測試] 執行 Real Tools 單元測試
poe test-real

poe test-unit

# [測試] 執行完整專案測試 (包含 Backend, UI, LLM)
poe test-all

# [清理] 清除輸出目錄
poe clean
```

### Agent Tool 測試 (Real Tool Testing Platform)
開發 Agent 工具時，可使用以下指令進行驗證：

```bash
# [Interactive Debug Mode] 使用 JSON 腳本執行 Tool 流程 (無需 LLM)
poetry run python run.py --tool-debug scripts/agent/debug/all_tools.json

# [Headless E2E] 執行無頭測試驗證所有 Real Tools
poetry run pytest scripts/dev/verify_all_tools_headless.py -v
```

或是使用原始 Poetry 指令：
```bash
# 執行後端單元測試
poetry run test-backend

# 執行 UI 單元測試
poetry run test-ui

# 執行 LLM Agent 相關測試
poetry run test-llm

# 執行遠端/Headless 環境安全測試
poetry run test-remote

# 執行 LLM Agent 認知能力基準測試
poetry run benchmark-llm
```

## 文件導航 (Documentation)

### 專案文件
*   **[ROADMAP.md](ROADMAP.md)**: 未來開發計畫與路線圖。
*   **[CONTRIBUTING.md](CONTRIBUTING.md)**: 開發者貢獻指南 (環境設定、Git 規範)。
*   **[CHANGELOG.md](CHANGELOG.md)**: 版本變更紀錄。
*   **[KNOWN_ISSUES.md](KNOWN_ISSUES.md)**: 已知問題與限制。
*   **[GLOSSARY.md](GLOSSARY.md)**: 領域術語表。

### 模組詳細文件
*   **UI (前端介面)** - `documentation/ui/`
    *   [Architecture 2.0](ui/ARCHITECTURE_2_0.md): 介面架構與 Observer Bridge 機制。
*   **Backend (後端核心)** - `documentation/backend/`
    *   [Architecture](backend/architecture.md): 後端架構、Facade、Controller 與資料處理管線設計。
*   **Agent (AI 代理)** - `documentation/agent/`
    *   [Agent Architecture](agent/agent_architecture.md): ReAct 迴圈、Agent 系統全貌。
    *   [Tool Definitions](agent/tool_definitions.md): 工具呼叫介面定義（19 個工具）。
    *   [Benchmark](agent/benchmark.md): 認知能力評測方法論。
    *   [Context Assembler](agent/context_assembler.md): Context Assembler 架構設計。
*   **Test (測試)** - `documentation/test/`
    *   [Testing Guide](test/README.md): 測試策略、執行方式與目錄結構。
    *   [LLM Test Cases](test/llm/llm_test_cases.md): LLM 模組單元測試案例。
    *   [UI Testing Strategy](test/ui/ui_testing_strategy.md): UI 測試策略與 Mock 技巧。
