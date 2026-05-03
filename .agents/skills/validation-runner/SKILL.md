---
name: validation-runner
description: Use when choosing and interpreting XBrainLab validation commands, quality dashboard checks, pytest gates, mkdocs builds, real-data IO smoke tests, and claim boundaries.
---

# validation-runner

## 用途

用於選擇 XBrainLab 驗證指令，並判斷結果能支撐什麼 claim。

## 先讀

1. `docs/validation/README.md`
2. `docs/architecture/validation.md`
3. `docs/current.md`
4. `.agents/runbooks/setup.md`

## 常用驗證

文件站：

```bash
poetry run mkdocs build --strict
```

fast dashboard：

```bash
poetry run python scripts/dev/update_quality_dashboard.py
```

real-data IO：

```bash
poetry run pytest --capture=sys tests/integration/io/test_io_integration.py -q
```

tiny pipeline smoke：

```bash
poetry run pytest --capture=sys \
  tests/integration/pipeline/test_full_pipeline.py::TestFullPipeline::test_train_and_evaluate_metrics \
  tests/integration/pipeline/test_study_training_e2e.py::TestStudyTrainCycle::test_full_cycle_eegnet \
  -q
```

## 判斷規則

- dashboard PASS 是 engineering health，不是 thesis claim。
- mock-heavy unit tests 是 regression floor，不是 real workflow evidence。
- public local-only fixture evidence 不能當作 clean clone always-on CI。
- optional `llm` group 未驗證前，不能宣稱 local LLM runtime ready。
- tool-call scoring system 尚未建立前，不能宣稱 agent tool-call accuracy。

## 輸出

每次驗證要寫：

- command
- result
- claim supported
- claim not supported
- follow-up
