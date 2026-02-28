# Benchmark Data Management

## Directory Structure

```
XBrainLab/llm/rag/data/
  gold_set.json          ← MASTER dataset (210 examples, 19 tools × 10 + 20 complex)

scripts/agent/benchmarks/
  data/
    train.json           ← 60% stratified split (126 examples)
    test.json            ← 20% held-out test set (42 examples)
    val.json             ← 20% validation set (42 examples)
    manifest.json        ← Checksums + metadata for integrity verification
  split_dataset.py       ← Generates train/test/val from gold_set
  validate_gold_set.py   ← Schema validation + split integrity + manifest check
  simple_bench.py        ← Tool-call accuracy benchmark (LLM required)
  rag_experiment.py      ← RAG retrieval quality benchmark (CPU only)
```

## Gold Set Design Principles

### Intent-Only Parameters

The gold set tests **intent extraction** — it only specifies parameters
the user **explicitly mentions** in their query. For example:

- "Set learning rate to 0.0005" → `{"learning_rate": 0.0005}` (no epoch/batch_size)
- "Repeat training 5 times" → `{"repeat": 5}` (no epoch/batch_size/learning_rate)

This is **by design**: we measure whether the model correctly identifies
*what the user asked for*, not whether it fills default values.

The validation script flags these as `[INTENT]` warnings (not errors).

### Tool Coverage

All 19 tools have at least 10 dedicated single-tool examples.
The `complex` category adds 20 multi-step workflow examples.

| Category   | Count | Tools |
|-----------|------:|-------|
| dataset   |    60 | list_files, load_data, attach_labels, clear_dataset, get_dataset_info, generate_dataset |
| preprocess |   90 | apply_standard_preprocess, apply_bandpass_filter, apply_notch_filter, resample_data, normalize_data, set_reference, select_channels, set_montage, epoch_data |
| training  |    30 | set_model, configure_training, start_training |
| ui        |    10 | switch_panel |
| complex   |    20 | Multi-tool workflows |

## Data Pipeline

### 1. Edit gold_set.json

The master dataset lives at `XBrainLab/llm/rag/data/gold_set.json`.
All edits happen here.

### 2. Re-split

```bash
python scripts/agent/benchmarks/split_dataset.py
```

This regenerates `train.json`, `test.json`, `val.json`, and `manifest.json`.
The manifest captures the gold_set's MD5 checksum for staleness detection.

### 3. Validate

```bash
python scripts/agent/benchmarks/validate_gold_set.py
```

Checks:
- Schema validation (parameter names, types vs actual tool definitions)
- No duplicate IDs
- All 19 tools covered
- Split integrity (no overlap, no missing, content equality)
- Manifest freshness (gold_set hasn't changed since last split)

### 4. Run experiments

```bash
# RAG-only (CPU, no API key needed)
python scripts/agent/benchmarks/rag_experiment.py

# Tool-call accuracy (requires GEMINI_API_KEY in .env)
poetry run benchmark-llm --model gemini
```

## RAG Configuration

| Setting | Benchmark | Production |
|---------|-----------|------------|
| Indexed data | train.json only (126) | Full gold_set.json (210) |
| Data leakage | None (test/val never indexed) | N/A (all examples available) |
| Storage | Temp dir (auto-cleaned) | `XBrainLab/llm/rag/storage/` |
| Embedding | all-MiniLM-L6-v2 (384-dim) | Same |

The benchmark intentionally uses fewer indexed examples than production
to avoid data leakage. This makes benchmark results **conservative** —
production RAG has access to all 210 examples.

## Staleness Detection

If you edit `gold_set.json` without re-running `split_dataset.py`:

```
[MANIFEST] gold_set.json has changed since last split!
    Expected MD5=abc123, got def456. Re-run split_dataset.py.
```

## Adding New Examples

1. Add entries to `gold_set.json` with unique IDs (format: `{tool_short}_{NN}`)
2. Run `split_dataset.py` to regenerate splits + manifest
3. Run `validate_gold_set.py` to verify integrity
4. Run experiments to measure impact
