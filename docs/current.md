# XBrainLab 目前狀態

最後更新：`2026-07-30`

這頁只回答一件事：**現在能相信什麼，還不能宣稱什麼，下一步該做什麼。**
完整階段安排看 [Roadmap](planning/roadmap.md)，下一輪施工看 [Now](planning/now.md)。

## 一句話

目前 Desktop MVP integration line 已完成先前 blocker 的實作與自動化重建：non-blocking
application view、Qt shutdown lifecycle、strict agent envelope / recovery、BIDS event bounds 與
run mapping、overlapping-window split protection、post-training saliency atomicity都已有 regression
與跨資料集 evidence。完整 unit、integration、UI、多資料集及 human-like walkthrough 已通過。
先前 `ux/gui-review-preprocess-polish` repair candidate 另完成 Data Import Step 5、Smart Parser、
preprocess dialogs / preview / history、Training History 與 attribution spectrogram 的局部修復；
focused regression、product walkthrough、42-phase human-like walkthrough 與 required multi-dataset
gate 已通過。老師試用前的擴充資料 gate 另驗證 277 MB、10 組 hash-pinned fixtures：
OpenNeuro ds003061 三個 BIDS P300 runs 完成 reviewed class-label import，CHB-MIT 與
Sleep-EDF 完成 raw import 並正確保留 seizure / hypnogram sidecar 邊界。最新老師試用候選把
Agent Panel 的可見 mode selector 移除，改由每一回合的自然語言
產生 immutable execution scope；產品預設模型改為 exact-only
`ibm-granite/granite-3.3-2b-instruct`，不會因模型不可用而靜默換成另一個模型。真實 Granite GPU
流程已走到 Data Import 的 typed review boundary。最新 `ux/assistant-product-v1` 候選再收斂
Agent presentation、自然語言 turn scope、執行控制與 Application view publication delivery：
GUI queue 尚未確認 publication revision 時，terminal training event 會保留而不是遺失；確認
同一 revision 後只投遞一次。資料面重新通過 14 種格式、7 個公開 cases / 5 個來源 family 與
跨來源 training / epoch smoke。Windows 真人 click-through 尚未完成，因此仍不能稱 product
complete 或合併 `main`。

MCP 已從 active product / thesis roadmap 拔掉。既有 MCP 程式碼、測試與 artifacts 只代表
歷史探索或相容性證據，不再是 MVP、release candidate 或 thesis evidence 的必要路線。

目前不能宣稱 product complete。

## 現況總覽

| 區域 | 目前狀態 | 邊界 |
| --- | --- | --- |
| Backend | `ApplicationService / Command API` 是主要 command spine；mutation lock 由 Study 擁有。`ApplicationViewPublication` 原子綁定 state、capability、generation 與 revision。Qt bridge 以 revision acknowledgement 回報可見 state 已投遞；被 GUI queue 延後的 terminal training event 會保留，直到同一 revision 可見後再 exactly-once 投遞。Training model selection 已移除 test-based checkpoint path。 | object-bearing `data_lists` / history query 仍刻意序列化；panels 仍有 injected controller observer / compatibility adapter，不能宣稱 zero-controller UI。 |
| UI | command 執行期間會抑制 observer duplicate refresh，完成後依 `changed_state` 走 shared refresh coordinator。Async command result/error 綁到 owner-child QObject，owner 被刪除時由 Qt 自動斷線；獨立 cleanup receiver 保留到 terminal `finished` 才解除 busy、suppression 與 worker ownership。Data Import 最後一步使用 compact import review；preprocess preview 明確分成 no-data / loaded / epoched-locked，兩種 History 使用固定外部高度與內部 scrollbar。 | automated walkthrough 不等於 human Windows desktop acceptance；仍需真人 Windows click-through，尤其是真訓練中關閉與 Windows/WSLg native teardown。 |
| Data Interpretation | `scan -> preview -> validate -> apply -> recipe` baseline 已存在；Data Import wizard 已補強 Tier 1/Tier 2 label-source、strict BIDS folder events、internal event evidence、external label placement、structured review coverage，並把 reviewed label placement 寫成獨立 epoch handoff 建議。`Import file` 保留精確 selected scope，只自動偵測所選 EEG 附近且能配對的 label carriers，不會把共同父資料夾或子目錄擴大成 EEG scan scope。Import Recipe 只保存重新載入 EEG、metadata、label source 與 label mapping 所需的選擇；Epoch window / baseline 不在 recipe 內，Epoch 尚未完成也不會阻止 import。`task`、`run` 缺失只顯示 optional note；這類來源仍可匯入，但不宣稱為 BIDS-complete。Label carrier pairing 現由 backend domain policy 統一供 candidate、apply 與 UI 使用；只配到部分 selected EEG 時會在載入前 blocked。 | BIDS 支援目前是 EEG task import MVP，不是 full BIDS validator；每個 selected run 必須有實際可解析的 events carrier，目前不宣稱 BIDS events inheritance。一般 folder 掃到 `events.tsv` 仍走普通 label-file flow。P300/SSVEP/clinical/XDF/LSL/MOABB/proprietary converters 不能誇大。 |
| Assistant / Agent | Panel 已統一 Header、loading / empty / ready / working / waiting / error、suggestions、兩行 composer、typed confirmation card、responsive layout 與 Settings。使用者不再先選 `Single action` / `Guided workflow`；host 依本回合請求建立 immutable scope：說明不動工具、單一操作只做一步、明確要求「繼續到需要我決定」才允許受 policy 保護的安全續行。UI 可直接執行的 commands 與僅供 agent 建議的 commands 已分開；Stop Training 是明確 terminal endpoint，不會由 generic continuation 猜測執行。產品預設是 exact-only IBM Granite 3.3 2B；Phi 系列只保留為使用者明確選取的 legacy compatibility choice。host continuation 只允許 parameter-free `preview_interpretation` / `validate_interpretation`，仍需通過 schema、registry、capability 與 confirmation policy。 | 真 Granite boundary walkthrough 是 host-assisted 產品流程證據，不是 raw-model benchmark。它允許一次 strict-envelope 格式修復，且明確區分 model-owned scan 與 host-owned deterministic continuation；仍不等於 thesis accuracy、Windows native DPI、多螢幕或長時間 session acceptance。 |
| MCP | 從 active plan 移除。 | 不再追求 MCP hardening、MCP client certification、MCP external-agent product path 或 MCP thesis evidence。 |
| Packaging | Windows launcher / startup smoke 有 evidence。 | 還不是 signed installer，也不是 release approval。 |

## 下一個真正 blocker

**從已完成自動化 gate 的同一候選分支做 Windows 真人 acceptance。**

目前優先順序：

1. 從已 push 的 `ux/assistant-product-v1` 候選啟動 Windows GUI，依手測清單走
   Data Import、preprocess / epoch、
   split / train、evaluation / visualization 與 assistant。
2. 老師可用版確認後才 freeze XBrainLab benchmark 的 source、cases 與 scorer；不在產品候選仍變動
   時先做論文準確率主張。

Rebaseline 後的工程入口：

- 目前正式 git worktree 只有 `/mnt/d/workspace_v2/projects/lab/xbrainlab`。
- 目前 teacher handoff candidate 在 `ux/assistant-product-v1`；驗證與真人 acceptance 通過後再
  fast-forward stabilization line，不新增另一個手測 worktree。
- `docs/multi-gate-loop`、`docs/development-process-rules`、`wip/data-import-controller-dirty-checkpoint`
  不整支 merge；只在需要時 cherry-pick 可用片段。
- 使用者回報的 bug 已作為 audit trigger，並完成 architecture、UI、test/EEG 三路盤點與主要
  blocker repair；最後 reviewer gate 必須重新讀 current code / artifact，不接受 worker 自我宣稱。
- 後續每個 handoff candidate 都必須更新 canonical docs 或明確說明不需要更新的理由。

Desktop MVP 前仍要先把 backend / UI 穩定化繼續收乾淨：

- product runtime 不應偷偷 fallback 到 legacy controller mutation。
- UI refresh 不應每個頁面自己猜狀態。
- 測試不應把舊 fallback 當作成功條件。
- `BackendFacade` module 已物理移除；product runtime 要直接使用
  `ApplicationService / Command API` 或薄 command adapter，不能重新加入 facade
  wrapper。

## 可以宣稱

- Roadmap 主線已定型為：Rebaseline -> Desktop MVP -> Product Polish / Release Candidate ->
  Assistant MVP -> Thesis Evidence。
- 正式 git worktree 已收斂到一個；下一輪產品修復從 `stabilize/desktop-mvp` 走。
- `ApplicationService / Command API` 是目前要收斂的 product spine。
- Data Interpretation 與 desktop workflow 已進入候選驗證；assistant 目前只支撐受 backend policy
  保護的 MVP，不支撐 thesis-grade raw-model accuracy claim。
- 現有 artifacts 能作為工程 evidence，但每個 evidence 都有明確邊界。
- required multi-dataset gate 目前覆蓋 2 個有公開 protocol class semantics 的 training source
  family，以及 SCCN EEGLAB、MNE CNT 兩個 IO/epoch-only source；SCCN `rt` / `square`
  不作 supervised class claim；
  同時保留 checked-in GDF/MAT、public BIDS 與 Data Interpretation format matrix。

## 不能宣稱

- product complete。
- backend target architecture fully aligned。
- Data Interpretation final。
- automated UI walkthrough 等於 human Windows desktop acceptance。
- tool-call eval 等於 UI / product completion。
- MCP baseline 屬於 active roadmap。
- launcher smoke 等於 release approval 或 signed installer。
- `stabilize/desktop-mvp` 已完成 Windows 真人手測或已合併 `main`。

## 最近驗證

| Gate | 最近結果 | 用途 |
| --- | --- | --- |
| `mkdocs build --strict` | PASS | 文件站可建。 |
| fast quality dashboard | Ruff、Basedpyright、architecture、startup、7 張 UI baseline、dialog、product walkthrough、BIDS visible matrix、UI unit `2128 passed`、real IO `31 passed` 全數 PASS。提交前 dashboard 只因 dirty-worktree traceability 為 WARN；exact-commit 結果以 `artifacts/quality/latest.md` 為準。 | 支撐 automated handoff candidate；不等於 Windows 真人 acceptance。 |
| Full unit / integration | 最新分層 gate：backend publication/application `231 passed`、UI/chat/product `571 passed`、agent/core/integration `2123 passed`、architecture/source guards `274 passed`。 | 支撐目前 Python / Qt / backend / agent regression；分層數字不能相加當成全 repo unique test count，也不等於真人 UX acceptance。 |
| Architecture / static quality | architecture compliance PASS；Ruff PASS；full-repo Basedpyright `0 errors / 0 warnings / 0 notes`。五層 turn-scope ownership guard 覆蓋 assembler、controller、dispatcher、runtime lifecycle 與 AgentManager；publication delivery 另有真 `ApplicationService -> QtObserverBridge -> AgentManager` exactly-once regression。 | 靜態檢查不能證明所有 runtime 行為。 |
| Required multi-dataset gate | Data Interpretation real lifecycle `20/20`、14 種 format paths、7 個 public cases / 5 source families、7 個 pinned fixture fact contracts、7 個 external placement contracts、4 個 internal profiles、固定 11 個 reviewed label/event cases；IO/BIDS/cross-source integration `36 passed, 3 skipped`，strict cross-source `4/4`（2 training + 2 IO/epoch-only）。三個 skip 是未下載的 OpenNeuro / Sleep-EDF / CHB-MIT teacher fixtures，並非 required-ci 失敗。 | 支撐列出的真實資料與格式邊界；SCCN `rt` / `square` 與 CNT marker 不是 protocol-grounded supervised classes，也不是 training evidence；不是 full BIDS validator 或任意 proprietary format claim。 |
| Teacher dataset preflight | local-only manifest `277,106,963 bytes`、10 groups 全部 hash/size verified；OpenNeuro P300、CHB-MIT、Sleep-EDF 三個較大型 ApplicationService cases `3/3` PASS。OpenNeuro 三 run 的 `747 / 750 / 748` 個來源 `(sample, class label)` 與匯入後逐筆一致，並成功建立合計 `2,245` epochs；真 GUI 另走完五步 wizard、label-field repreview、8 個 value controls 與三 run apply。 | OpenNeuro case支撐該資料集三 run 的 reviewed class-label import 與 bounded epoch handoff；CHB-MIT / Sleep-EDF 只支撐 raw import 與 sidecar 分類，不支撐 seizure / hypnogram 自動標籤或一般化臨床資料認證。完整三-run BIDS GUI gate約需 5 分鐘，是 Windows 真人試用仍需觀察的延遲風險。 |
| UI integration / walkthrough | focused assistant artifact PASS；human-like walkthrough `42/42` phases、`45` screenshots；真 Granite boundary artifact PASS。最終 artifacts 位於 `artifacts/ui/assistant-product-v1-*-final/`，由主 agent 檢查 full-window、narrow、settings、confirmation 與 terminal state。 | 支撐 offscreen / Xvfb 可觀察流程；不等於 Windows DPI、雙螢幕或真人 acceptance。 |
| Agent / policy regression | Agent/core/integration `2123 passed`；Stop Training 的英文/中文 multi-stage admission 與 publication-ack terminal delivery regression 均通過。Architecture 與 clean-code reviewer 在修復 deferred terminal delivery 後 re-gate PASS。 | 支撐 request admission、immutable turn scope、terminal endpoint、schema/capability/confirmation 與 host-continuation allowlist；不是 UX 或模型準確率證據。 |
| Local assistant | Granite 3.3 2B 為 exact primary，runtime inspection `gpu-ready`，cache `12.77 GB / 20 GB`。真 GPU workflow 與 adaptive boundary artifacts 都 PASS：model-owned scan、host-owned preview/validate、typed review handoff、Waiting 呈現及取消後 state 不變。 | 這是單一受控 product workflow，不是 raw Granite benchmark、長時間 session 或 Windows acceptance。 |
| Resource guard calibration | RTX 5070 Ti bounded probe 已量測 EEGNet、SCCNet、ShallowConvNet；三者保守估算皆覆蓋觀察到的單步 peak。 | 只涵蓋 batch 8、22 channels、301 samples 的校準範圍；不是所有模型、batch 或完整訓練 peak 的普遍證明。 |
| Windows launcher walkthrough | PASS | 自動化 launcher command / bounded startup evidence，不是 signed installer 或真人 click-through。 |

## 先看哪裡

| 你想知道 | 讀這裡 |
| --- | --- |
| 下一步施工 | [planning/now.md](planning/now.md) |
| 產品階段 | [planning/roadmap.md](planning/roadmap.md) |
| 目前架構 | [architecture/README.md](architecture/README.md) |
| 目標架構 | [target/architecture.md](target/architecture.md) |
| 證據怎麼解讀 | [validation/README.md](validation/README.md) |
