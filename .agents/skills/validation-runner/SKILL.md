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

required multi-dataset handoff gate：

```bash
poetry run python scripts/dev/fetch_public_eeg_fixtures.py
poetry run python scripts/dev/report_dataset_validation_matrix.py --strict --format json
poetry run python scripts/dev/report_data_interpretation_format_matrix.py --format json
QT_QPA_PLATFORM=offscreen poetry run pytest --capture=sys \
  tests/integration/io/test_io_integration.py \
  tests/integration/io/test_public_bids_fixture.py \
  tests/integration/pipeline/test_public_cross_source_training_smoke.py -q
poetry run python scripts/dev/run_public_cross_source_training_smoke.py \
  --format json --strict
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
- architecture / refresh / state-truth 類修復，必須有 same-class sweep 和 source guard clean
  evidence；只跑新增測試只能支撐 checkpoint，不能支撐 complete。
- 給使用者手測或宣稱 handoff-ready 前，必須完成 `.agents/workflows/handoff-candidate.md`：
  focused regression、same-class sweep、happy path、edge/regression、artifact review、branch
  hygiene 和 claim boundary。
- data/import/label/epoch/training/evaluation/visualization handoff 前，必須跑 required
  multi-dataset gate；跳過時只能稱為 checkpoint。
- 不同副檔名不等於不同資料集；同一 source family 的轉檔只能算 format coverage，不能算 dataset source diversity。
- public local-only fixture evidence 不能當作 clean clone always-on CI。
- optional `llm` group 未驗證前，不能宣稱 local LLM runtime ready。
- tool-call scoring system 尚未建立前，不能宣稱 agent tool-call accuracy。

## 輸出

每次驗證要寫：

- command
- result
- claim supported
- claim not supported
- completion label：`complete` / `checkpoint` / `blocked`
- follow-up
