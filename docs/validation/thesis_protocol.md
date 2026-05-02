# Thesis Validation Protocol

最後更新：`2026-05-02`

這份文件定義 XBrainLab 要支撐碩士論文主張時使用的驗證 protocol。它不是日常 smoke
測試清單；日常工程健康仍看 `docs/validation/README.md`。任何論文 claim 都必須對到
固定資料來源、固定 split、固定 seed、可審計 artifact 和可重跑命令。

## Evidence 分層

| 層級 | 資料來源 | 可支撐 | 不可支撐 |
| --- | --- | --- | --- |
| checked-in fixtures | `tests/data/` 內的 compact GDF/MAT/multiformat fixtures | IO、shape、tiny train/evaluate smoke | 泛化能力、跨來源結論 |
| public fixtures | `tests/data/public/`，由 documented script 下載或手動放入 | public source import、event-rich fixture pipeline smoke | full thesis conclusion |
| external thesis datasets | 論文指定完整資料集，保留原始來源、版本、checksum | EEG classification thesis claim | agent tool-call accuracy |

資料下載不可靜默發生。public 或 external dataset 需先記錄來源、授權、大小、cache/path、
checksum 與清理方式。

## Split Protocol

三種 split 必須分開標註：

- `trial-wise`：同一 subject/session 可以出現在 train/validation/test，不允許同一 trial
  index 跨 split。只適合工程 smoke 或 intra-session baseline。
- `session-wise`：同一 `(subject, session)` group 不可跨 split。適合檢查 session transfer，
  尤其是同一 subject 不同 session 的穩定性。
- `subject-wise`：同一 subject 不可跨 split。這是跨 subject 泛化 claim 的最低要求。

避免 data leakage 的規則：

- test split 先建立並鎖定；validation split 必須從 test 之外的 remaining data 產生。
- preprocessing 若會學到資料統計量，fit 只能使用 train split，再套用到 validation/test。
- model selection、early stopping、hyperparameter tuning 只能看 validation，不可看 test。
- final test metrics 只能在 protocol 鎖定後計算。

目前 `DatasetGenerator.split_test()` 先分 test，`DatasetGenerator.split_validate()` 從
`dataset.get_remaining_mask()` 產生 validation，這符合 validation 不從 test 抽樣的基本要求。
新增 `XBrainLab/backend/dataset/split_audit.py` 會檢查 train/validation/test index overlap，
並依 `trial-wise`、`session-wise`、`subject-wise` 檢查 group leakage。

## Reproducibility

每個正式 run 必須保存：

- fixed `seed`。
- `repeat` 次數與 run index。
- deterministic setting，例如 PyTorch deterministic flags 是否啟用。
- train/validation/test split indices。
- 完整 config：dataset、preprocess、epoch、model、optimizer、training option、device。
- environment info：Python、platform、XBrainLab commit、torch/cuda/mne 版本。

目前 seed helper 在 `XBrainLab/backend/utils/seed.py`，training record 會保存 seed 與 random
state。正式 thesis runner 仍需要把 commit hash、dependency versions 和 split artifact 一起
寫入同一個 artifact directory。

## Metrics

EEG classification 報告至少包含：

- accuracy
- balanced accuracy
- macro F1
- AUC
- confusion matrix

若資料是 binary classification，AUC 使用 ROC-AUC；若是 multiclass，需明確標註 macro /
one-vs-rest 設定。所有 metrics 要同時保存 machine-readable JSON 和 human-readable summary。

## Baselines

正式 thesis evidence 需要至少包含：

- chance / majority-class baseline。
- classical baseline：例如 CSP + LDA 或 CSP + SVM。
- neural baseline：目前 XBrainLab 可跑 EEGNet、ShallowConvNet、SCCNet。
- ablation：沒有 agent assistance 的 manual workflow vs agent-assisted workflow，僅用於工具使用效率，
  不得混入 EEG classification metrics。

baseline 必須使用同一份 split artifact，不可各自重新抽 split。

## Artifact Schema

split artifact schema 版本目前是 `1`，JSON schema 放在：

```text
docs/validation/split_artifact_schema.json
```

code entrypoint：

```text
XBrainLab/backend/dataset/split_audit.py
scripts/dev/validate_split_artifact.py
```

最小 artifact 欄位：

- `schema_version`
- `protocol`
- `seed`
- `repeat`
- `audit`
- `environment`
- `config`
- `datasets[].indices.train`
- `datasets[].indices.validation`
- `datasets[].indices.test`
- `datasets[].counts`
- `datasets[].groups`

審計命令：

```bash
poetry run python scripts/dev/validate_split_artifact.py artifacts/thesis/splits.json
```

目前相關 tests：

```bash
poetry run pytest --capture=sys \
  tests/unit/backend/dataset/test_split_audit.py \
  tests/unit/scripts/test_validate_split_artifact.py -q
```

## Rerun 與 Audit

正式 experiment artifact directory 應長成：

```text
artifacts/thesis/<run_id>/
  split_artifact.json
  config.json
  metrics.json
  metrics.md
  confusion_matrix.csv
  train.log
  model_summary.txt
  environment.json
```

重跑流程：

1. 讀 `split_artifact.json`，驗證 schema 和 audit。
2. 讀 `config.json`，固定 seed、dataset path、preprocess、model、optimizer。
3. 重建同一 train/validation/test indices。
4. 重跑 train/evaluate。
5. 比對 metrics schema、run log、model summary 和 environment。

如果 split artifact audit 失敗，該 run 不能列入 thesis evidence。

## Agent Tool-Call Eval Boundary

agent tool-call accuracy eval 必須獨立於 EEG classification metrics。

- EEG metrics 回答模型是否能分類資料。
- agent tool-call metrics 回答 assistant 是否選對工具、參數、狀態轉移與錯誤恢復。

deterministic tool-call eval 可以證明 scoring framework 和 scripted policy 正確，但不能宣稱
local LLM 真實 tool-call 能力。local LLM tool-call eval 需要在產品主線穩定後，以同一批 cases
重跑 primary / fallback model，並記錄 parser failure、verification failure、retry 和 recovery。

## Current Gap

本輪已建立 split audit helper、artifact schema、validator script 和 unit tests。尚未完成的是
正式 external thesis dataset runner、full experiment registry、statistical significance report
和 local LLM 真實 tool-call accuracy run。這些不能被 dashboard PASS 或 tiny pipeline smoke 取代。
