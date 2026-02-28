# Agent Benchmark Scripts

實驗腳本集，用於驗證 XBrainLab Agent 的工具選擇與架構正確性。

**完整文件請參考：**
- [實驗指南](../../../docs/agent/experiment-guide.md) — 完整流程、執行步驟與結果解讀
- [資料管理](../../../docs/agent/data-management.md) — 資料集格式、分割與驗證
- [Agent 架構](../../../docs/architecture/agent.md) — Pipeline 設計與工具系統

## Quick Start

```bash
# 1. 驗證資料完整性
poetry run python scripts/agent/benchmarks/validate_gold_set.py

# 2. RAG 檢索品質 (CPU only, 無需 API Key)
poetry run python scripts/agent/benchmarks/rag_experiment.py

# 3. Tool-Call 準確率 (需要 GEMINI_API_KEY)
poetry run python scripts/agent/benchmarks/simple_bench.py --model gemini --delay 1

# 4. 架構正確性驗證 (無需 API Key)
poetry run python scripts/agent/benchmarks/validate_architecture.py
```

## Scripts

| 腳本 | 用途 | 需 API |
|------|------|--------|
| `simple_bench.py` | Stage-aware tool-call 準確率 | Yes |
| `rag_experiment.py` | RAG 檢索品質 (Recall, MRR) | No |
| `validate_gold_set.py` | 資料集 schema + 分割完整性 | No |
| `validate_architecture.py` | Pipeline 架構靜態驗證 | No |
| `split_dataset.py` | gold_set → train/test/val 分割 | No |
