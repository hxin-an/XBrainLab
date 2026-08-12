# XBrainLab Roadmap

最後更新：`2026-08-12`

這份 roadmap 是產品主線，不是施工日誌。它用來決定：**現在先做什麼、做到什麼程度才可交給使用者測、哪些 claim 不能先講。**

## 產品北極星

XBrainLab 要先成為一個能在 Windows 本地穩定操作的 EEG / BCI 桌面工具：

```text
啟動桌面 app
-> 解讀 EEG data / label / event
-> 使用者確認模糊語意
-> preprocess / epoch / dataset / train
-> evaluate / visualize
-> UI、assistant、scripts 看到同一份 workflow truth
```

MCP 已從 active product / thesis roadmap 移除。既有 MCP code、tests、artifacts 只保留為
歷史探索或相容性證據，不再是 MVP、release candidate、thesis evidence 或 handoff gate 的必要項目。

## 定型 Roadmap

| Phase | 目標 | 完成判準 | 不能宣稱 |
| --- | --- | --- | --- |
| 1 Rebaseline | 重新盤點目前真實狀態。 | 最新整合基底、branch/worktree、known blockers、可信測試、artifact freshness 和 canonical docs 都清楚。 | product usable。 |
| 2 Desktop MVP | 人能穩定跑完整 EEG workflow。 | import -> label/event -> metadata/epoch -> preprocess -> dataset -> train -> evaluate -> visualize 可在 Windows 桌面完成；阻礙使用或理解的 UI/UX 都清掉。 | polished release、assistant reliable、thesis claim。 |
| 3 Product Polish / Release Candidate | 主流程可用後，把產品質感與交付狀態整理到可測試版。 | UI visual language、empty/loading/error state、主要 dialogs、docs site、known limitations 和 troubleshooting 足夠一致。 | signed installer、正式 release approval。 |
| 4 Assistant MVP | in-app assistant 可可靠操作穩定桌面工具。 | assistant 使用同一套 backend command/state/verification；能處理 readiness、blocked reason、confirmation boundary 和 structured result。 | thesis-grade tool-call accuracy。 |
| 5 Thesis Evidence | 做正式 agent benchmark 和碩論 evidence package。 | case suite、dataset protocol、model/repeat count、scorer version、failure taxonomy、statistical report 和 artifact package 都可重跑。 | agent score 代表 UI 已完成。 |

## UI / UX 放在哪裡

UI / UX 不全部等到最後。

| 類型 | 所屬階段 | 判斷方式 |
| --- | --- | --- |
| 阻礙使用的 UI/UX | Desktop MVP | 使用者無法理解狀態、找不到下一步、畫面跑版、按鈕被擠掉、表格白字白底、流程容易誤操作，都算 blocker。 |
| 一致性與美感 polish | Product Polish / Release Candidate | 主流程已跑通後，再統一 spacing、字級、按鈕、表格、empty/loading/error state、文件站與 artifact gallery。 |
| Assistant 互動 UX | Assistant MVP | assistant 的提問、確認、tool feedback、blocked reason 和 error response，要在桌面流程穩定後設計。 |

## Desktop MVP 主流程

Desktop MVP 的核心不是「功能都存在」，而是使用者能完成一條可信的 EEG workflow：

```text
Choose EEG data
-> Load / confirm labels and events
-> Review metadata and epoch hints
-> Preprocess
-> Create epochs
-> Configure data split
-> Configure and run training
-> Review evaluation
-> Open visualization / saliency
```

這個階段要處理的 UI/UX blocker 包含：

- Data Import 的 duplicate label、remove/re-add、strict BIDS review、Match Labels / Review and Import 清楚度。
- Epoch / preprocess / dataset split dialogs 的 layout、button state、confirmation pattern。
- Training completion 不跳出煩躁的 blocking dialogs；長任務不卡 UI。
- Evaluation / Visualization table、fold switch、model summary、saliency readiness、3D blocked/available state 不跑版、不白字白底、不崩潰。
- 手測前必須有 automated happy path、edge/regression、多資料集 gate、screenshot artifact 和 claim boundary。

## Assistant 與 Thesis 的位置

Assistant 是產品主線，但不應早於 Desktop MVP。

- Desktop workflow 不穩時，assistant 只會把不穩定流程自動化，反而放大 bug。
- Assistant MVP 先追求 reliable workflow operation，不追求 thesis score。
- Thesis Evidence 最後才做 formal benchmark、AutoResearch-style case generation、repeat runs 和 statistical report。

## Deferred Training Setup 與 Timed Search {#deferred-training-timed-search}

> 狀態：`target design recorded; not implemented`（`2026-08-12`）。目前 Training 仍只有
> deterministic recommended defaults；本節不表示 Optuna、trial orchestration、多模型搜尋或
> 新 UI 已存在。等目前產品工作完成並合併後，才從當時最新 `main` 建立獨立短 branch 實作。

Data Splitting 完成後，Training 目標 UI 提供兩條同等的一級路徑。Timed Search 是完整的自動
訓練路徑，不是把參數套回 manual setup 的輔助工具：

```text
Dataset Splitting
├─ Manual Training
│  └─ Training Setup -> Start Training
└─ Timed Search
   └─ Search Setup -> search trials -> winner final training -> test once
```

### Manual Training

- Sidebar 將 `Model Selection` 和 `Training Setting` 收斂成一個 `Training Setup` action，
  `Dataset Splitting` 與既有 `Start Training` 行為不變。
- Setup 在同一個 draft 中選 model、model parameters、pretrained weight、epochs、batch size、
  learning rate、optimizer、device 和 evaluation strategy；只有最後 `Save setup` 才原子提交。
- 重新開啟必須還原 current model、model parameters 和 weight state。Cancel、stale generation、
  recommendation 或 resource-preview failure 不得保存半套設定。
- Backend deterministic recommendations 仍只稱為 suggested starting values；使用者改過的欄位
  保留 manual provenance，`Start Training` resource preflight 仍是最後 authority。

### Timed Search 使用者 contract

- Sidebar 另有 `Timed Search` action。Search Setup 確認後立即開始，不需再按
  `Start Training`，也不覆寫 Manual Training Setup。
- 使用者可勾選一個或多個通過資料形狀與 resource admission 的模型；預設只勾 backend 建議
  模型。選擇多模型時必須警告時間會被分散，可能只能完成初步比較。
- 所有被選模型先公平取得相同 qualification phase，再讓較好的 candidates 進級；每個模型
  使用自己的 conditional search space。未完成相同資格階段時只能顯示
  `Incomplete comparison`，不可產生假 winner。
- Backend 依 reviewed task / class evidence 建議 validation objective，UI 明確顯示且允許改成
  compatible validation metric；同一次 search 的所有模型使用同一 objective。Test 不可用於
  sampling、pruning、early stopping、promotion 或 ranking。
- `Time budget` 是 search 加 winner final training 的總時間目標，不是硬秒數 SLA。系統依同一
  context 已完成 trials 的觀察時間保守預留 finalization；沒有足夠 evidence 時不得捏造可完成的
  trial 數。
- 預設搜尋 learning rate、batch size，及每個模型一個 catalog 明確宣告的代表性安全參數
  （通常是 dropout）。使用者可修改 suggested range，但不可超過 backend 的 type、shape 與
  resource hard bounds。
- optimizer、weight decay 和其他 model-specific fields 放在 Advanced；`epochs` 是各 trial 的
  上限與 pruning protocol，不是一般隨機搜尋維度。`n_channels`、`n_times`、`n_classes`、device、
  seed、data split 與 test metric 永遠不是搜尋欄位。

### 執行、History 與 final model

- ApplicationService 擁有 search lifecycle、capability、deadline、publication 與 shutdown；
  search coordinator 使用單一 GPU 串行 trials。Optuna 是預定的 sampler / pruner / study
  persistence implementation，不擁有 UI 或產品 lifecycle，也不啟動 daemon / Web UI。
- Optuna 預定固定 exact dependency 並使用 ask/tell、`n_jobs=1` 和 local SQLite study storage。
  XBrainLab 另保存 split、dataset、model、search-space、metric、protocol、seed、version 與
  artifact digest；Optuna storage 本身不是產品 evidence authority。
- 每個 search trial 可在 Training History 顯示為一列，但共享同一個 `Timed Search #N` group。
  group 和 row 必須有 typed search / trial identity；不可用一般 training row 的 magic fields
  冒充。completed、pruned、failed、incomplete 與 OOM recovery 都保留清楚狀態。
- 現有 `Accuracy`、`Loss`、`Log` 區域新增第四個 `Hyperparameters` tab。選取任一 manual run、
  search trial 或 final row 時，顯示該列完整 parameters；search rows 另顯示 objective、phase、
  rank、range、elapsed 與停止原因，不新增 HPO dashboard 或壓縮主畫面固定高度。
- Search trials 完全不能取得 test loader / metric / artifact，也不觸發一般 post-training saliency。
  只有完成相同最高 qualification phase 的 eligible candidates 可以競逐 winner。
- Winner 產生後，系統在總時間目標內自動進行一次正式 final training；validation 選 checkpoint，
  test 最後只評估一次。History 的 `Final` row 是唯一正式 trained result，也是唯一可進入
  Evaluation / Saliency 的 search output。
- 若時間不足以公平比較或完成 final training，保存為 resumable `Incomplete`，不讀 test、
  不發布正式模型。Resume 只接受相同 dataset / epoch / split / models / search space / metric /
  protocol / seeds / versions identity；context 改變後只能檢視舊結果或開始新 search。
- 時間到或使用者按 Stop 後不再建立 trial，current trial 在最近安全 epoch / batch boundary
  合作式停止。完成 trials 仍保留，未完成 trial 不參與排名；UI 在 terminal publication 前顯示
  `Stopping safely…`，不得提早宣稱已停止。
- OOM 不可 silent fallback CPU 或偷改 manual settings。若在使用者核准的範圍內降低 batch size，
  必須建立帶 lineage 的新 recovery trial；否則該 trial 明確失敗。

### 實作切片與驗證底線

1. 先收斂 `Training Setup` 並補 current model / parameters / weight hydration；不在此 slice 引入 HPO。
2. 建立 typed model/search catalog、objective、range、hard bounds、Search Setup 與 resource preview。
3. 建立 ApplicationService-owned coordinator、Optuna ask/tell、deadline、pruning、stop/resume、
   SQLite persistence 與 immutable publication。
4. 建立 test-zero-access trial runner、公平多模型 phase/promotion、winner final training 與唯一
   test evaluation。
5. 擴充 typed History identity、group presentation、`Hyperparameters` tab 與 final-result capability。

驗收至少包含：Manual Setup atomic save / cancel / stale；search range 與 model conditional validity；
balanced-accuracy / compatible objective scorer；split 與 preprocessing fold leakage；test zero-access；
公平 qualification；fake-clock time / trial caps；stop / shutdown / resume；OOM lineage；final test exactly
once；History / Hyperparameters selection；100% / 125% / 150% DPI；以及 RTX 5070 Ti 上 wall time、RAM、
VRAM cleanup、UI responsiveness 和安全停止延遲。取得實測前不得宣稱可在某時間內完成多少 trials。

## MCP 決策

MCP 不再是 active roadmap。

- 不再規劃 MCP hardening phase。
- 不再把 MCP client certification 當 release 或 thesis 前置。
- 不再要求 backend / UI / assistant handoff 跑 MCP gate。
- 既有 MCP 相關 records 保留在 git history / records，作為過去探索，不作為下一步工作。

如果未來重新啟用 MCP，必須另開 decision，重新定義 scope、security、session ownership、
client matrix 和 validation cost；不能從舊 roadmap 自動復活。

## Not Now

- MCP hardening / MCP client certification。
- signed installer / notarization。
- formal thesis benchmark refresh。
- full local model x3 release gate。
- Expert Workflow Mode。
- Workflow Recipe DSL。
- Training Model Registry / Model Node Visualization。
- Training timed hyperparameter search（當前只交付 deterministic recommended defaults）。
