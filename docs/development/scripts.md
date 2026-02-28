# Scripts 目錄結構

**最後更新**: 2026-02-25

本文件定義 `scripts/` 目錄的架構與使用規範。

---

## 目錄結構

```
scripts/
├── agent/                           # Agent 相關腳本
│   ├── benchmarks/                  # 評測腳本與資料
│   │   ├── simple_bench.py          # Stage-Aware Benchmark 主腳本 (自動評分)
│   │   ├── rag_experiment.py        # RAG 檢索品質評測 (CPU only)
│   │   ├── validate_gold_set.py     # 資料集 Schema + 分割完整性驗證
│   │   ├── validate_architecture.py # Pipeline 架構靜態驗證
│   │   ├── split_dataset.py         # gold_set → train/test/val 分割
│   │   └── data/
│   │       ├── train.json           # 60% (126 examples) — RAG 索引用
│   │       ├── test.json            # 20% (42 examples) — 評估用
│   │       └── val.json             # 20% (42 examples) — 調參用
│   │
│   └── debug/                       # Interactive Debug 腳本
│       ├── all_tools.json           # 全工具流程 Debug
│       ├── debug_filter.json        # 濾波功能 Debug
│       └── debug_ui_switch.json     # UI 切換 Debug
│
└── dev/                             # 開發與驗證輔助
    ├── run_tests.py                 # 執行測試套件
    ├── list_gemini_models.py        # 列出可用 Gemini 模型
    ├── verify_all_tools_headless.py # Headless 全工具驗證
    ├── verify_gemini_llm.py         # Gemini API 連線驗證
    ├── verify_headless.py           # Headless 模式基礎驗證
    ├── verify_lazy_import.py        # Lazy Import 正確性檢查
    ├── verify_preprocess_imports.py # 預處理 Import 驗證
    ├── verify_rag.py                # RAG 索引 / 檢索驗證
    └── verify_real_tools.py         # Real Tool ↔ Backend 整合驗證
```

---

## 使用方式

### Benchmark 評測

```bash
# Stage-Aware Tool-Call 準確率 (需要 GEMINI_API_KEY)
poetry run python scripts/agent/benchmarks/simple_bench.py --model gemini --delay 1

# RAG 檢索品質 (CPU only, 無需 API Key)
poetry run python scripts/agent/benchmarks/rag_experiment.py

# 資料集 Schema + 分割完整性驗證
poetry run python scripts/agent/benchmarks/validate_gold_set.py

# Pipeline 架構靜態驗證
poetry run python scripts/agent/benchmarks/validate_architecture.py

# 重新分割 gold_set → train/test/val
poetry run python scripts/agent/benchmarks/split_dataset.py
```

### Interactive Debug

在 UI 内使用 `--tool-debug` 啟動模式，載入 JSON 腳本進行互動除錯：

```bash
python run.py --tool-debug scripts/agent/debug/all_tools.json
```

### 開發驗證

```bash
# 驗證 Real Tool 與 Backend 整合
python scripts/dev/verify_real_tools.py

# 驗證 RAG 索引與檢索
python scripts/dev/verify_rag.py

# 驗證 Headless 模式下所有工具
python scripts/dev/verify_all_tools_headless.py

# 執行完整測試套件
python scripts/dev/run_tests.py

# Logger f-string 自動轉換
python scripts/dev/fix_logger_fstrings.py

# 覆蓋率報告生成
python scripts/dev/cov_report.py
```

---

## 命名規範

| 類型 | 格式 | 範例 |
|------|------|------|
| Debug 腳本 | `debug_<功能>.json` | `debug_filter.json` |
| Benchmark 資料 | `<split>.json` | `train.json`, `test.json`, `val.json` |
| Benchmark 腳本 | `<功能>.py` | `simple_bench.py` |
| 驗證腳本 | `verify_<功能>.py` | `verify_rag.py` |

---

## 相關文件

- [ADR-007: 測試策略](../decisions/ADR-007-tool-call-testing-strategy.md)
- [ADR-008: 評測框架](../decisions/ADR-008-tool-call-evaluation-framework.md)
