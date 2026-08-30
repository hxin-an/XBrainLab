# Training target contract

最後更新：`2026-08-30`

本文件定義 class loss weighting 與 validation early stopping 的已核准目標態。它不代表目前
`main` 已實作這些能力。

## Shared boundary

- 兩項設定都屬於現有 Training Settings、`ConfigureTrainingCommand`、training option／plan／run
  artifact 與 TrainingManager lifecycle；不新增 training owner 或第二條 execution path。
- 只能使用 training／validation data 做設定與 checkpoint 決策；test data 只能做 final evaluation。
- UI、Assistant 與 scripts 使用同一份 resolved training option／snapshot。
- Assistant 的 model-facing `configure_training` 維持零參數 GUI handoff；weighting、patience 與
  `min_delta` 不可加入 local model tool schema。
- 只有 persisted requested settings、resolved per-fold values、monitor history 與 terminal reason 足以重現時，
  run 才能作為 evaluation／visualization／saliency 來源。

## Class loss weighting

Training Settings 提供三種 mutually exclusive mode：

| Mode | Contract |
| --- | --- |
| `Off` | 預設。Training criterion 不接收 class weights，與現有 behavior 等價。 |
| `Balanced` | 每個 fold／repeat 只以該 training split 的 count 計算 `w_c = N / (K * n_c)`，其中 `N` 是 training samples 總數、`K` 是 target class 數、`n_c` 是 class `c` 的 training count。 |
| `Custom` | UI 以 class name 顯示每類 positive finite multiplier，預設 `1.0`；不接受 unknown class、缺少 class、零、負數、NaN 或 infinity。 |

共通規則：

- Weight 只套用 training criterion；validation／test criterion 與 metrics 保持 unweighted。
- 不使用 weighted sampler／oversampling／undersampling，不改 batch 的樣本分佈。
- 任一 target class 在當次 training split 的 count 為零時，Start Training 在建立 trainer 或 mutation
  前 blocked；不以 epsilon、infinite weight 或刪 class 隱藏。
- Requested mode／custom multipliers、per-fold class counts／class order／resolved weights 必須進入
  training option snapshot、run history 與 artifact manifest。
- 改變 weighting 是新 training configuration；不改寫已完成 run 的記錄或 evaluation。
- Custom class names／order 只來自當前 reviewed dataset class map；configure 與 Start Training
  都要重驗 mapping generation。Mapping 改變後舊 multipliers fail closed，不以舊 index 靜默對到新 class。
- Weighted criterion 是 record／fold-local runtime value；不改寫會被多個 fold／repeat 共用的
  `TrainingOption.criterion`。

## Validation early stopping

Training Settings 提供 `enabled`、positive integer `patience` 與 non-negative finite absolute
`min_delta`；預設 disabled，預設值為 `patience = 5`、`min_delta = 0.0`。

- Monitor 自動跟隨當次 validation checkpoint-selection metric：validation loss 越低越好，
  validation accuracy／AUC 越高越好。使用者不在另一個 control 選第二套 monitor。
- Improvement 必須比目前 best 好且超過 absolute `min_delta`；其餘 valid validation checkpoints
  將 no-improvement count 加一。當 count 達到 `patience` 時停止當次 repeat。
- `Last Epoch` checkpoint selection 或無 validation split／loader 時，early stopping 不可啟用；
  submit 必須顯示 recoverable validation blocker。
- AUC 在單一 class／其他原因下 undefined 時，該 checkpoint 不取代 best、不增加
  no-improvement count。若全程無有效 AUC，該 repeat 跑到 epoch limit 並保存無法判定的
  monitor evidence，不 silent fallback 到 test 或另一 metric。
- 每個 fold／repeat 有獨立 best／count／terminal reason，不跨 repeat 累計。
- Early stop 是 successful training terminal，terminal reason 為 early stopping；不發布 cancelled／
  failed，不觸發 cancel rollback。User stop 仍是獨立 cancelled／stopped lifecycle。
- Best validation checkpoint 依現有 selection contract 用於 final evaluation、history 與 saliency source。
  Final epoch 仍可作 monitor history 保留，但不取代 best checkpoint。
- Requested settings、metric／direction、best epoch／value、checkpoint observations、stop epoch／reason 都要
  儲存在 run history／artifact，不只留在 UI log。

## Acceptance boundary

- Deterministic tests 必須證明 train-only weighting、unweighted validation／test、per-fold resolution、
  三種 monitor direction／threshold、patience boundary、undefined AUC、best reload、disabled equivalence
  與 persistence。
- Training 是 data-sensitive workflow；交付前必須通過 canonical source-diverse dataset gate。
- UI artifact／offscreen test 不取代同一 exact SHA 的 Windows Training Settings、progress、history
  與 final evaluation 手測。
