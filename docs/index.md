# XBrainLab

[![CI](https://github.com/hxin-an/XBrainLab/actions/workflows/ci.yml/badge.svg)](https://github.com/hxin-an/XBrainLab/actions/workflows/ci.yml)

**EEG Analysis Platform with AI Agent**

XBrainLab 是一個專為腦波 (EEG) 研究設計的智慧分析平台。核心目標是**評估腦波數據的分析價值**，透過結合深度學習模型與顯著圖 (Saliency Map) 技術，協助研究人員判斷數據品質並理解模型決策依據。

## 核心功能

- **數據價值評估** — 利用深度學習模型自動分析腦波數據，判斷其是否具備後續分析或訓練的價值
- **可解釋性視覺化** — 生成 Saliency Map 以視覺化模型關注的腦波特徵區域
- **深度學習整合** — 內建 PyTorch 模型訓練介面，支援 EEGNet、SCCNet 等模型
- **AI 智能助手** — 整合 LLM Agent，支援自然語言指令操作與 RAG 知識問答
- **基礎訊號處理** — 提供濾波、重參考等必要的預處理工具
- **模組化架構** — UI 與後端邏輯嚴格分離，提供高可測試性

## 系統需求

| 項目 | 需求 |
|------|------|
| OS | Linux (推薦), Windows, macOS |
| Python | 3.10+ |
| RAM | 16GB 以上 (建議) |
| GPU | NVIDIA GPU (建議，用於加速模型訓練) |

## Quick Links

- [Installation](getting-started/installation.md)
- [Quick Start](getting-started/quickstart.md)
- [Architecture Overview](architecture/overview.md)
- [API Reference](api/backend/study.md)
- [Known Issues](development/known-issues.md)
- [Contributing](contributing.md)
- [Changelog](changelog.md)

## LLM 設定 (可選)

XBrainLab 支援 **Local GPU** (HuggingFace)、**OpenAI API** 與 **Google Gemini API**。
系統會自動讀取 `.env` 檔案中的設定：

```bash
cp .env.example .env
# 編輯 .env 填入 API Key (GEMINI_API_KEY 或 OPENAI_API_KEY)
```

詳細設定請參考 [Installation Guide](getting-started/installation.md)。
