# XBrainLab Roadmap

最後更新：`2026-07-03`

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
-> Generate dataset / split
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
