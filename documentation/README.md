# XBrainLab

XBrainLab 是一個專為腦波 (EEG) 研究設計的智慧分析平台。本專案的核心目標是**評估腦波數據的分析價值**，透過結合深度學習模型與顯著圖 (Saliency Map) 技術，協助研究人員判斷數據品質並理解模型決策依據。

## 核心功能 (Key Features)

*   **數據價值評估 (Data Valuation)**：利用深度學習模型自動分析腦波數據，判斷其是否具備後續分析或訓練的價值。
*   **可解釋性視覺化 (Saliency Map)**：生成顯著圖 (Saliency Map) 以視覺化模型關注的腦波特徵區域，提供直觀的解釋性分析。
*   **深度學習整合**：內建 PyTorch 模型訓練介面，支援模型訓練、評估與即時監控。
*   **AI 智能助手**：整合 LLM Agent，支援自然語言指令操作與 RAG 知識問答，降低操作門檻。
*   **基礎訊號處理**：提供濾波 (Filtering)、重參考 (Re-referencing) 等必要的預處理工具。

## 系統需求 (System Requirements)

*   **OS**: Linux (推薦), Windows, macOS
*   **Python**: 3.10+
*   **RAM**: 建議 16GB 以上 (處理大型 EEG 資料)
*   **GPU**: NVIDIA GPU (建議，用於加速模型訓練)

## 快速開始 (Quick Start)

### 1. 環境安裝
本專案使用 [Poetry](https://python-poetry.org/) 進行相依性管理。

```bash
# 安裝 Poetry (如果尚未安裝)
curl -sSL https://install.python-poetry.org | python3 -

# 安裝專案相依套件
poetry install
```

### 2. 啟動程式
```bash
# 啟動 XBrainLab
poetry run python run.py
```

## 測試 (Testing)

本專案提供多種 Poetry 指令來執行不同層級的測試。

### 執行測試
```bash
# 執行後端單元測試 (推薦優先執行)
poetry run test-backend

# 執行 UI 單元測試
poetry run test-ui

# 執行 LLM Agent 相關測試
poetry run test-llm

# 執行遠端/Headless 環境安全測試 (跳過需螢幕顯示的 UI 測試)
poetry run test-remote
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
    *   [Architecture](ui/architecture.md): 介面架構與 Signal 機制。
    *   [Flows](ui/flows.md): 使用者操作流程圖。
*   **Backend (後端核心)** - `documentation/backend/`
    *   [Architecture](backend/architecture.md): 資料處理管線設計。
    *   [API Reference](backend/api_reference.md): 核心類別與函式定義。
    *   [Flows](backend/flows.md): 資料流向圖。
*   **Agent (AI 代理)** - `documentation/agent/`
    *   [Architecture](agent/architecture.md): RAG 與 Agent 架構。
    *   [Tools API](agent/tools_api.md): 工具呼叫介面定義。
*   **Test (測試)** - `documentation/test/`
    *   [Guide](test/guide.md): 測試執行入門。
    *   [Strategy](test/strategy.md): 測試策略與 Mocking 技巧。
    *   **Cases**:
        *   [Backend Cases](test/cases/backend.md)
        *   [UI Cases](test/cases/ui.md)
        *   [Agent Cases](test/cases/agent.md)
