# Thesis Tool-Call Evaluation Protocol

最後更新：`2026-05-06`

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
| deterministic tool-call cases | repo 內固定 cases / expected calls / expected state | scorer schema、policy / verifier baseline、regression floor | local LLM 真實 tool-call accuracy 或 UI 行為 |
| scripted backend replay | 固定 tool calls / commands 直接跑 backend | CommandResult、state transition、capability / autonomy policy | UI 是否真的更新、使用者是否看得懂 |
| UI-observable scripted replay | 固定 replay 經過 UI adapter / ChatPanel / import wizard，保存 transcript、state、screenshots 或 UI artifacts | 人眼可審查的 UI 行為、button enablement、visible response、wizard flow | local LLM 真實 tool-call accuracy |
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
- autonomy-boundary handling accuracy
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
- expected autonomy decision / decision boundary
- expected backend state delta
- actual model output
- parsed tool call
- verification result
- backend `CommandResult`
- final user-visible response
- UI-observable artifact，若此 case 屬於 UI replay 或 UI-assisted workflow
- score breakdown

## Tool-Call Benchmark Cases

cases 應覆蓋：

- happy-path workflow：scan source、preview interpretation、validate、confirm / apply、preprocess、
  epoch、dataset、configure training、train。
- Data Interpretation workflow：BIDS folder scan、GDF + external label、MAT 多 label-like variable、
  event role disambiguation、recipe reload。
- metadata resolution workflow：subject / session / task / run 推論、preview、confirmation、
  user override、subject-wise split 前置條件。
- autonomy-boundary workflow：command technically allowed 但 agent 必須停下來確認，例如
  apply interpretation、select split strategy、start training、reset / new session。
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
- data import / label-event cases 必須覆蓋 Data Interpretation 的 `safe`、`needs_confirmation`、
  `blocked`、BIDS `warning / limited / blocked` 和 recipe reload。
- negative / blocked / missing-parameter / recovery cases 合計不得少於總 cases 的 `30%`。
- multi-turn workflow cases 不得少於 `15` 個，且必須包含至少一條完整
  scan -> preview -> validate -> apply -> preprocess -> epoch -> dataset -> configure training ->
  train -> query result sequence。
- local LLM primary / fallback runner 至少重跑 `3` 次，保存 run-level artifact；若因資源限制
  降低次數，report 必須明確標成 exploratory，不能當 thesis candidate。

deterministic tool-call eval 可以證明 scoring framework 和 scripted policy 正確，但不能宣稱
local LLM 真實 tool-call 能力。local LLM tool-call eval 需要在產品主線穩定後，以同一批 cases
重跑 primary / fallback model，並記錄 parser failure、verification failure、retry 和 recovery。

## Local Eval Gate 分層

Local tool-call eval 不是每個小修都跑 full primary / fallback x3。正式 thesis claim 需要
完整重跑；日常 verifier、normalizer、prompt、case wording、UI refresh 或 backend cleanup
只應使用較小 gate：

| Gate | 使用時機 | 模型 / 重跑策略 |
| --- | --- | --- |
| Fast dev gate | 日常小切片、回歸修正、changed / failed cases。 | deterministic eval；repeat `1`；不跑 fallback model。 |
| Candidate gate | 需要真 local model 驗證受影響 case family。 | primary model；affected families；repeat `1` 或 `2`。 |
| Release / thesis gate | 更新正式 benchmark claim 或 thesis evidence artifact。 | deterministic full suite；primary full suite x3；fallback full suite x3；刷新 dashboard。 |

Release / thesis local gate 前必須先記錄 disk / cache / `nvidia-smi` VRAM preflight。RTX
5070 Ti 16GB 已在 fallback x3 觀察到高壓 VRAM boundary；若 VRAM 幾乎滿載，不應啟動 full
fallback x3，而要保存 `resource_preflight.*` 並延後 formal local rerun，或改跑 fast dev /
candidate gate。`scripts/agent/evals/run_local_tool_call_eval.py` 的 full-suite repeat `3`
local run 必須顯式帶 `--eval-gate release` 或 `--eval-gate thesis`；預設 candidate gate 會先寫
`resource_preflight.*` 並拒絕啟動模型。這種 blocked preflight 不能被寫成 thesis-ready rerun。
deterministic CLI 也同樣分層：`scripts/agent/evals/run_tool_call_eval.py` 的預設 `fast` gate
只允許 `--case-id` / `--case-family` / `--case-limit` subset 和 repeat `1`；正式 full-suite
dashboard refresh 必須顯式帶 `--eval-gate release` 或 `--eval-gate thesis`。

## Scripted Replay

scripted replay 不能只停在文字報告。它應分成兩層：

| 模式 | 用途 | 人要看什麼 |
| --- | --- | --- |
| backend replay | 用固定 tool call / command 檢查 backend state、CommandResult、capability / autonomy policy | JSON / markdown report、state_before / state_after、decision boundary |
| UI-observable replay | 用固定 replay 經過 UI adapter、ChatPanel 或 import wizard，確認使用者看見的行為正確 | screenshots、transcript、visible status、button enablement、wizard step、error wording |

UI-observable replay 的目標不是替代 local LLM eval，而是避免「backend report PASS，但 UI
使用者看起來仍然錯」。

UI replay artifact 至少應保存：

- replay case id。
- initial state。
- scripted command sequence。
- UI entrypoint：ChatPanel、import wizard、button-driven workflow 或 MCP external-agent path。
- visible transcript / status text。
- relevant screenshots 或 approved UI artifacts。
- expected / actual button enabled state。
- expected / actual wizard step。
- final state snapshot。
- pass / fail reason。

若 UI replay 只產出 backend JSON，不能用來宣稱 UI 行為已驗證。

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
- Verification Layer 必須把 Data Interpretation validation result 納入 tool-call guard：
  `blocked` 不可執行，`needs_confirmation` 必須轉成使用者確認，`safe` 也仍要通過
  ApplicationService capability policy。
- scorer 必須同時記錄 proposed tool call、verification result、backend `CommandResult`、
  autonomy decision、decision boundary、state_before / state_after 和 visible response。
- tool taxonomy 必須重新設計為 workflow intent / side effect / decision boundary 導向，不能只沿用
  舊 `load_data` / `attach_labels` 或 `dataset / preprocess / training` 粗分類。
- MCP server 若加入 validation，必須只作 external agent adapter；MCP calls 仍需經
  ApplicationService、capability policy、autonomy policy 和 visible-response formatter。
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

目前已建立 deterministic tool-call eval baseline、local primary / fallback runner、case-level
scorer、dashboard、failure taxonomy、repeat-run artifact 和 resource preflight guard。最新
benchmark slice 使用同一 `121` cases，deterministic / primary / fallback artifacts 均已刷新；這可
作為該 benchmark 的 thesis-candidate tool-call evidence。

尚未完成的是把這些 artifact 整理成正式 thesis report/evidence matrix、補 confidence interval
或統計呈現、並在每次更新正式 claim 前依 release / thesis gate 重跑與保存 resource/latency
條件。tool-call benchmark 也不能取代 UI、launcher、MCP 或 import wizard 的產品驗收 evidence。

external EEG dataset runner、repeat runs、baseline comparison 和 statistical reporting 是可選的
pipeline support，不是目前 thesis 主線。這些不能取代 local LLM 真實 tool-call accuracy run。
