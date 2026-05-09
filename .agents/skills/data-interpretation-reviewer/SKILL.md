---
name: data-interpretation-reviewer
description: Use when reviewing XBrainLab EEG/BCI data import, label/event interpretation, BIDS handling, metadata resolution, recipe trace, dataset capability boundaries, and fallback/custom import design.
---

# data-interpretation-reviewer

## 用途

用於檢查 XBrainLab Data Interpretation 是否真的能支撐 EEG/BCI 現實資料，而不是只把檔案讀進來。

## 設計來源

已消化參考：

- BIDS：folder-level dataset、events.tsv onset/duration/trial_type、channels / participants、
  inheritance principle；入口不能只看單一副檔名。
- MNE-BIDS：讀 BIDS 時會連動 events.tsv / channels.tsv，且多 datatype / 多檔會需要明確 path
  與 mismatch handling。
- BCI/EEG 案例：GDF internal events + external labels、MAT / CSV / TSV / TXT labels、EDF+
  annotations、BrainVision markers、EEGLAB events、PhysioNet run-dependent semantics、P300
  target hierarchy、clinical interval annotations、XDF/LSL streams。

## 先讀

1. `docs/research/bci_eeg_import_label_design_source.md`
2. `docs/target/data_interpretation_system.md`
3. `docs/architecture/data_pipeline.md`
4. `docs/architecture/backend.md`
5. Data Interpretation source/tests/artifacts touched by the change

## Review Gate

檢查：

- 入口是否是 `source_path` / folder / BIDS root / recipe，而不是只選單一 EEG file。
- scan / preview / validate / confirm / apply / recipe 是否都留下可審查 output。
- label carrier 是否保存 field、anchor、time model、granularity、role、target file。
- event code 是否被誤當 class；trial start、cue、response、artifact、boundary 是否區分。
- label time base 是否清楚：sample index、seconds、Unix timestamp、trial order、interval。
- subject / session / task / run 是否保存 source、decision、override、reason。
- BIDS inheritance / events.json levels / channels mismatch 是否有清楚 boundary。
- `safe` / `needs_confirmation` / `blocked` 是否由資料語意決定，不是 LLM confidence。
- recipe reload 是否重新 scan / preview / validate，不直接 apply。
- downstream training / saliency 是否只作 acceptance，不混進 import module 本體。

## 打回條件

- 只說 imported，沒有 label/event/metadata preview。
- 特殊 dataset 被靜默猜測並 apply。
- GDF / MAT / BIDS events label mapping 沒有人可確認的 class map / anchor。
- legacy label import 仍是新 UI / agent 的主心智模型。
- recipe trace 無法重跑或無法解釋當初選擇。

## 輸出格式

```md
## Data Interpretation Verdict

- verdict: trustworthy / limited but explicit / not trustworthy

## Coverage

- supported:
- needs confirmation:
- blocked:

## Semantic Risks

## Required Eval Cases
```
