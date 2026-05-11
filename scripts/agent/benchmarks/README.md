# Agent Benchmark Scripts

實驗腳本集，用於驗證 XBrainLab Agent 的工具選擇與架構正確性。

**目前狀態：** 這些是歷史 benchmark scripts，不是 product-delivery 主線。
新的 tool-call eval 要等 backend / UI / agent / local LLM / launcher 穩定後，
再依 `docs/validation/README.md` 重新建立。

**目前文件請參考：**
- [Agent 架構](../../../docs/architecture/agent.md)
- [驗證策略](../../../docs/validation/README.md)

## Quick Start

```bash
# 1. 驗證資料完整性
poetry run python scripts/agent/benchmarks/validate_gold_set.py

# 2. RAG 檢索品質 (CPU only, 無需 API Key)
poetry run python scripts/agent/benchmarks/rag_experiment.py

# 3. Legacy tool-call smoke; product eval 尚未啟用
poetry run python scripts/agent/benchmarks/simple_bench.py --model phi --delay 1

# 4. 架構正確性驗證 (無需 API Key)
poetry run python scripts/agent/benchmarks/validate_architecture.py
```

## Scripts

| 腳本 | 用途 | 需 API |
|------|------|--------|
| `simple_bench.py` | Legacy stage-aware tool-call smoke | No; local catalog models only |
| `rag_experiment.py` | RAG 檢索品質 (Recall, MRR) | No |
| `validate_gold_set.py` | 資料集 schema + 分割完整性 | No |
| `validate_architecture.py` | Pipeline 架構靜態驗證 | No |
| `split_dataset.py` | gold_set → train/test/val 分割 | No |
