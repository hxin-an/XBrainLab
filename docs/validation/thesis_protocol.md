# Thesis Tool-Call Evaluation Protocol

最後更新：`2026-05-03`

這份文件定義 XBrainLab 要支撐碩士論文主張時使用的驗證 protocol。論文主 evidence 是
assistant 的 tool-call accuracy：它是否選對工具、給對參數、遵守當前 workflow state、正確處理
blocked / invalid command，並在錯誤後自我修正。

EEG training / evaluation accuracy 不是本論文要仔細驗證的主指標。它只用來證明 XBrainLab
作為目標科學軟體的資料流程可以被穩定操作，不能取代 agent tool-call scoring。

本文件不是日常 smoke 測試清單；日常工程健康仍看 `docs/validation/README.md`。任何 thesis
claim 都必須對到固定 benchmark cases、可重跑 scorer、machine-readable artifact 和
human-readable report。

## Thesis Claim Boundary

本論文的主要評估問題：

- assistant 是否能從使用者 intent 選出正確 tool / command。
- assistant 是否能在不同 app state 下只呼叫 currently allowed command。
- assistant 是否能產生正確參數，而不是只選對工具名。
- assistant 是否能正確解讀 backend `CommandResult` / verification failure。
- assistant 是否能把 tool error 轉成使用者可理解的回覆，而不是暴露 raw schema / traceback。
- assistant 是否能在低信心、缺參數或 blocked state 下請求補充資訊或自我修正。

EEG classification metrics、train/validation/test split、模型 baseline 和 statistical reporting
屬於 product pipeline reliability / domain task sanity。除非論文另立 EEG classification
研究問題，否則不得把它們寫成主要 thesis result。

## Evidence 分層

| 層級 | 資料來源 | 可支撐 | 不可支撐 |
| --- | --- | --- | --- |
| deterministic tool-call cases | repo 內固定 cases / expected calls / expected state | scorer schema、scripted baseline、regression floor | local LLM 真實 tool-call accuracy |
| local LLM tool-call runs | 同一 cases 接 local primary / fallback runtime | tool selection / parameter / state-transition / recovery accuracy | EEG model quality |
| UI-assisted workflow cases | 真 UI / agent 操作代表性 EEG workflow | end-to-end workflow success、user-facing error handling | EEG classification thesis result |
| checked-in EEG fixtures | `tests/data/` compact GDF/MAT/multiformat fixtures | IO、shape、tiny train/evaluate smoke | agent tool-call accuracy 或 EEG 泛化能力 |
| public / external EEG datasets | documented source、license、checksum | domain workflow robustness、optional EEG model sanity | tool-call accuracy 或本論文主結論 |

資料下載不可靜默發生。public 或 external dataset 需先記錄來源、授權、大小、cache/path、
checksum 與清理方式。但資料級驗證只是讓 tool-call cases 有可信工作環境，不是主要論文評分。

## Tool-Call Metrics

正式 thesis report 至少要包含：

- intent accuracy
- tool selection accuracy
- parameter accuracy
- state-transition accuracy
- blocked-command handling accuracy
- user-visible response quality for tool errors
- self-correction / clarification success rate
- invalid / unsafe call rate
- parser failure rate
- verifier rejection rate

每個 case 至少保存：

- user command
- initial app state snapshot
- available command summary
- expected tool call / expected no-call behavior
- expected parameters
- expected verification result
- expected backend state delta
- actual model output
- parsed tool call
- verification result
- backend `CommandResult`
- final user-visible response
- score breakdown

## Tool-Call Benchmark Cases

cases 應覆蓋：

- happy-path workflow：load data、label/event、preprocess、epoch、dataset、configure training、train。
- state-gated workflow：資料未載入前不可 train；dataset / epoch 後不可隨意開新 dataset。
- query workflow：evaluation / visualization / saliency / state summary。
- destructive workflow：reset / clear 類 command 需要確認邊界。
- missing parameter：例如 list files 缺 directory 時，要要求補資訊，不暴露 raw error。
- invalid command：backend policy blocked 時，回覆 blocked reason 的使用者語言版本。
- multi-step recovery：第一次 tool call 被 verifier 擋下後，能否修正。

case 數量不能只停在 demo 級：

- 第一版 engineering baseline 至少 `50` 個 tool-call cases。
- 正式 thesis candidate baseline 至少 `100` 個 tool-call cases。
- 每個主要 workflow stage 至少 `10` 個 cases：data import、label/event、preprocess、epoch、
  dataset、training、evaluation / visualization / saliency、reset / lifecycle。
- negative / blocked / missing-parameter / recovery cases 合計不得少於總 cases 的 `30%`。
- multi-turn workflow cases 不得少於 `15` 個，且必須包含至少一條完整
  load -> preprocess -> epoch -> dataset -> configure training -> train -> query result sequence。
- local LLM primary / fallback runner 至少重跑 `3` 次，保存 run-level artifact；若因資源限制
  降低次數，report 必須明確標成 exploratory，不能當 thesis candidate。

deterministic tool-call eval 可以證明 scoring framework 和 scripted policy 正確，但不能宣稱
local LLM 真實 tool-call 能力。local LLM tool-call eval 需要在產品主線穩定後，以同一批 cases
重跑 primary / fallback model，並記錄 parser failure、verification failure、retry 和 recovery。

## Tool Refactor And Verification Architecture

正式 tool-call eval 前，tool surface 需要先完成重構：

- agent tools 不直接包 controller；能走 `ApplicationService` command 的 mutating workflow 必須走
  service command。
- tool availability、blocked reason、confirmation requirement 必須由 backend capability policy 產生。
- Context Assembler 只能暴露目前 state 下合理的 tool / command 摘要，不讓 LLM 自行判斷所有
  backend capability。
- Tool call 前必須再經 Verification Layer guard；不能只相信 prompt 內的 available tool list。
- Verification Layer 至少檢查：schema、required parameters、state precondition、resource
  existence、confirmation boundary、unsafe / destructive action、confidence threshold。
- scorer 必須同時記錄 proposed tool call、verification result、backend `CommandResult`、
  state_before / state_after 和 visible response。
- raw backend schema、traceback、tool exception 不可直接出現在使用者 transcript；必須轉成人能理解的回覆，
  structured diagnostics 另存。

這個 verification architecture 是 thesis evidence 的一部分。若 tool surface 尚未重構完成，
只能做 engineering baseline，不能宣稱 thesis-grade tool-call accuracy。

## EEG Pipeline Support Protocol

以下 split / metrics / baseline protocol 只服務於產品 workflow 和 domain task sanity。它讓
agent tool-call benchmark 有可重跑的 EEG 工作環境，但不是 thesis 的主要準確率評估。

資料級支撐也需要足夠數量與來源分層：

- checked-in compact fixtures 要覆蓋至少 GDF、MAT、metadata / label 入口和 event-rich case。
- public fixture slice 至少要能支持一條 event-rich import -> preprocess -> epoch -> dataset smoke。
- 若使用 external EEG dataset，只作 pipeline support；需要記錄 source、license、checksum、
  subject/session count 和清理方式。
- 任一資料來源不足時，tool-call report 必須標註哪些 workflow stage 的 evidence 只能算 synthetic
  或 fixture-level，不可泛化。

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

## EEG Pipeline Metrics

若需要報告 EEG pipeline sanity，classification 報告至少包含：

- accuracy
- balanced accuracy
- macro F1
- AUC
- confusion matrix

若資料是 binary classification，AUC 使用 ROC-AUC；若是 multiclass，需明確標註 macro /
one-vs-rest 設定。所有 metrics 要同時保存 machine-readable JSON 和 human-readable summary。

## EEG Pipeline Baselines

若 thesis appendix 或 product validation 需要 EEG model sanity，才需要至少包含：

- chance / majority-class baseline。
- classical baseline：例如 CSP + LDA 或 CSP + SVM。
- neural baseline：目前 XBrainLab 可跑 EEGNet、ShallowConvNet、SCCNet。
- ablation：沒有 agent assistance 的 manual workflow vs agent-assisted workflow，僅用於工具使用效率
  或 workflow completion，不得混入 EEG classification metrics。

baseline 必須使用同一份 split artifact，不可各自重新抽 split。

## EEG Split Artifact Schema

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

EEG pipeline experiment artifact directory 應長成：

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

如果 split artifact audit 失敗，該 EEG pipeline run 不能被引用為 domain workflow evidence。

## Current Gap

目前已建立 deterministic tool-call eval baseline 和 EEG split audit helper / artifact schema /
validator script。尚未完成的是正式 local LLM primary / fallback tool-call accuracy runner、
case-level report、failure taxonomy、confidence interval / repeat-run policy，以及可重跑的
thesis evidence matrix。

external EEG dataset runner、repeat runs、baseline comparison 和 statistical reporting 是可選的
pipeline support，不是目前 thesis 主線。這些不能取代 local LLM 真實 tool-call accuracy run。
