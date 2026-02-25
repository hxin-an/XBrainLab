# Scripts 目錄結構

**最後更新**: 2026-02-25

本文件定義 `scripts/` 目錄的架構與使用規範。

---

## 目錄結構

```
scripts/
├── agent/                           # Agent 相關腳本
│   ├── benchmarks/                  # 評測腳本與資料
│   │   ├── simple_bench.py          # Benchmark 主腳本 (自動評分)
│   │   ├── audit_dataset.py         # 測試集品質審計
│   │   ├── patch_dataset.py         # 測試集修補工具
│   │   └── data/
│   │       └── external_validation_set.json  # OOD 測試集 (175 題)
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
# 執行 Benchmark（需指定 LLM 模式）
python scripts/agent/benchmarks/simple_bench.py

# 審計測試集品質
python scripts/agent/benchmarks/audit_dataset.py

# 修補測試集
python scripts/agent/benchmarks/patch_dataset.py
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
```

---

## 命名規範

| 類型 | 格式 | 範例 |
|------|------|------|
| Debug 腳本 | `debug_<功能>.json` | `debug_filter.json` |
| Benchmark 資料 | `<名稱>.json` | `external_validation_set.json` |
| Benchmark 腳本 | `<功能>.py` | `simple_bench.py` |
| 驗證腳本 | `verify_<功能>.py` | `verify_rag.py` |

---

## 相關文件

- [ADR-007: 測試策略](../decisions/ADR-007-tool-call-testing-strategy.md)
- [ADR-008: 評測框架](../decisions/ADR-008-tool-call-evaluation-framework.md)
