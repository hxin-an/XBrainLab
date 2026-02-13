# Scripts 目錄結構

本文件定義 `scripts/` 目錄的架構與使用規範。

---

## 目錄結構

```
scripts/
├── agent/                    # Agent 相關
│   ├── debug/                # Interactive Debug 腳本
│   │   ├── filter.json
│   │   ├── epoch.json
│   │   └── full_flow.json
│   │
│   ├── benchmarks/           # 評測測試集
│   │   ├── tool_call.json
│   │   ├── rag_ablation.json
│   │   └── memory_ablation.json
│   │
│   ├── run_debug.py          # 執行 Debug Mode
│   ├── run_eval.py           # 執行評測
│   └── run_ablation.py       # 執行消融實驗
│
├── dev/                      # 開發輔助
│   └── run_checks.py
│
└── ci/                       # CI/CD
    └── run_tests.sh
```

---

## 使用方式

### Interactive Debug

```bash
python scripts/agent/run_debug.py scripts/agent/debug/filter.json
```

### 執行評測

```bash
python scripts/agent/run_eval.py --model gpt-4
```

### 執行消融實驗

```bash
python scripts/agent/run_ablation.py --type rag
```

---

## 命名規範

| 類型 | 格式 | 範例 |
|------|------|------|
| Debug 腳本 | `<功能>.json` | `filter.json` |
| Benchmark | `<名稱>.json` | `tool_call.json` |
| 消融測試 | `<組件>_ablation.json` | `rag_ablation.json` |
| Python 腳本 | `run_<功能>.py` | `run_eval.py` |

---

## 相關文件

- [ADR-007: 測試策略](../decisions/ADR-007-tool-call-testing-strategy.md)
- [ADR-008: 評測框架](../decisions/ADR-008-tool-call-evaluation-framework.md)
