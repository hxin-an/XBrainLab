# XBrainLab 目前狀態

最後更新：`2026-07-23`

這頁只回答一件事：**現在能相信什麼，還不能宣稱什麼，下一步該做什麼。**
完整階段安排看 [Roadmap](planning/roadmap.md)，下一輪施工看 [Now](planning/now.md)。

## 一句話

目前 Desktop MVP integration line 已完成先前 blocker 的實作與自動化重建：non-blocking
application view、Qt shutdown lifecycle、strict agent envelope / recovery、BIDS event bounds 與
run mapping、overlapping-window split protection、post-training saliency atomicity都已有 regression
與跨資料集 evidence。完整 unit、integration、UI、多資料集及 human-like walkthrough 已通過。
最新 `ux/gui-review-preprocess-polish` repair candidate 另完成 Data Import Step 5、Smart Parser、
preprocess dialogs / preview / history、Training History 與 attribution spectrogram 的局部修復；
focused regression、product walkthrough、42-phase human-like walkthrough 與 required multi-dataset
gate 已通過。Agent Panel presentation 也已完成 Header、狀態畫面、suggestions、mode selector、
composer 與 Settings 的一致化，並通過窄版、DPI、狀態切換與完整 product walkthrough。
Windows 真人 click-through 尚未完成，因此仍不能稱 product complete 或合併 `main`。

MCP 已從 active product / thesis roadmap 拔掉。既有 MCP 程式碼、測試與 artifacts 只代表
歷史探索或相容性證據，不再是 MVP、release candidate 或 thesis evidence 的必要路線。

目前不能宣稱 product complete。

## 現況總覽

| 區域 | 目前狀態 | 邊界 |
| --- | --- | --- |
| Backend | `ApplicationService / Command API` 是主要 command spine；mutation lock 由 Study 擁有。`ApplicationViewPublication` 原子綁定 state、capability 與 generation：lock 空閒時刷新背景 truth，長 mutation 時立即回最後一份已驗證狀態。Training model selection 已移除 test-based checkpoint path。 | object-bearing `data_lists` / history query 仍刻意序列化；panels 仍有 injected controller observer / compatibility adapter，不能宣稱 zero-controller UI。 |
| UI | command 執行期間會抑制 observer duplicate refresh，完成後依 `changed_state` 走 shared refresh coordinator。Async command result/error 綁到 owner-child QObject，owner 被刪除時由 Qt 自動斷線；獨立 cleanup receiver 保留到 terminal `finished` 才解除 busy、suppression 與 worker ownership。Data Import 最後一步使用 compact import review；preprocess preview 明確分成 no-data / loaded / epoched-locked，兩種 History 使用固定外部高度與內部 scrollbar。 | automated walkthrough 不等於 human Windows desktop acceptance；仍需真人 Windows click-through，尤其是真訓練中關閉與 Windows/WSLg native teardown。 |
| Data Interpretation | `scan -> preview -> validate -> apply -> recipe` baseline 已存在；Data Import wizard 已補強 Tier 1/Tier 2 label-source、strict BIDS folder events、internal event evidence、external label placement、structured review coverage，並把 reviewed label placement 寫成獨立 epoch handoff 建議。Import Recipe 只保存重新載入 EEG、metadata、label source 與 label mapping 所需的選擇；Epoch window / baseline 不在 recipe 內，Epoch 尚未完成也不會阻止 import。`task`、`run` 缺失只顯示 optional note；這類來源仍可匯入，但不宣稱為 BIDS-complete。Label carrier pairing 現由 backend domain policy 統一供 candidate、apply 與 UI 使用；只配到部分 selected EEG 時會在載入前 blocked。 | BIDS 支援目前是 EEG task import MVP，不是 full BIDS validator；每個 selected run 必須有實際可解析的 events carrier，目前不宣稱 BIDS events inheritance。一般 folder 掃到 `events.tsv` 仍走普通 label-file flow。P300/SSVEP/clinical/XDF/LSL/MOABB/proprietary converters 不能誇大。 |
| Assistant / Agent | in-app assistant 提供 `Single action` 與 `Guided workflow`。Panel 已統一 Header、loading / empty / ready / working / waiting / error 狀態、可點選 suggestions、兩行 composer、inline typed confirmation card 與窄版 responsive layout；Settings 使用可捲動內容與固定 footer，在受限高度仍保留 Save / Cancel。重要 action 仍由既有 confirmation contract 處理；card 保留原始 request identity，完成 command 後只依 `changed_state` refresh GUI。Microsoft Phi-4 mini 的真實 GPU ChatPanel workflow 已完成 state query 與一般問答；視窗關閉後 runtime / dispatcher 都進入 `closed`、controller 釋放且 generation thread 歸零。 | raw-model candidate eval 目前只有 `6/12`；host-assisted product policy 是 `12/12`，兩者不可混稱。Linux/Qt 100% / 125% / 150% scale gate 不等於 Windows native DPI、多螢幕、長時間 local-model session 或 assistant acceptance。 |
| MCP | 從 active plan 移除。 | 不再追求 MCP hardening、MCP client certification、MCP external-agent product path 或 MCP thesis evidence。 |
| Packaging | Windows launcher / startup smoke 有 evidence。 | 還不是 signed installer，也不是 release approval。 |

## 下一個真正 blocker

**從已發佈的單一候選分支完成 Windows 真人 acceptance。**

目前優先順序：

1. 從 `ux/gui-review-preprocess-polish` 啟動 Windows GUI，依手測清單走 Data Import、
   preprocess / epoch、split / train、evaluation / visualization 與 assistant。
2. 若發現問題，以目前候選 commit 為基底建立 focused repair，不把未驗證修復直接合併 `main`。
3. Windows acceptance 通過後，才 fast-forward stabilization line 並準備 main merge gate。

Rebaseline 後的工程入口：

- 目前正式 git worktree 只有 `/mnt/d/workspace_v2/projects/lab/xbrainlab`。
- 目前 repair candidate 在 `ux/gui-review-preprocess-polish`；驗證與真人 acceptance 通過後再
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
| fast quality dashboard | `artifacts/quality/latest.md` overall PASS；workspace traceability 只列出 protected local config `settings.json`。 | 支撐 automated handoff candidate；不等於 Windows 真人 acceptance。 |
| Full unit / integration | `9006 passed, 1 skipped`；integration `388 passed`。 | 支撐目前 Python / Qt / backend / agent regression；不等於真人 UX acceptance。 |
| Architecture / static quality | architecture compliance PASS；本輪 Ruff PASS；本輪 touched product files 的 BasedPyright 為 `0 errors / 0 warnings / 0 notes`。 | full-repo BasedPyright 仍有 `122` 個既有 errors，不能把本輪 scoped clean 說成全 repo type-clean；靜態檢查也不能證明所有 runtime 行為。 |
| Required multi-dataset gate | Data Interpretation real lifecycle `20/20`、14 種 format paths、7 個 public cases / 5 source families、7 個 pinned fixture fact contracts、7 個 external placement contracts、4 個 internal profiles、固定 11 個 reviewed label/event cases；strict cross-source `4/4`（2 training + 2 IO/epoch-only）。 | 支撐列出的真實資料與格式邊界；SCCN `rt` / `square` 與 CNT marker 不是 protocol-grounded supervised classes，也不是 training evidence；不是 full BIDS validator 或任意 proprietary format claim。 |
| UI integration / walkthrough | 本輪 focused regression `567 passed`、product walkthrough `7 passed`；human-like walkthrough `42/42` phases、44 required screenshots、resource smoke PASS，table geometry findings / clipped rows 均為 0。 | 支撐 Xvfb 可觀察流程；不等於 Windows DPI、雙螢幕或真人 acceptance。 |
| Agent Panel product UI | 最新 focused presentation / regression suite `511 passed`；compact evidence 在 `artifacts/ui/assistant-presentation-current/`，涵蓋 loading、empty、conversation、confirmation、error、320 / 420 / 760 responsive、Settings collapsed / expanded / constrained-height 與 150% scale。focused 與 DPI source fingerprint 穩定；human-like walkthrough `42/42` phases、44 required screenshots、resource smoke PASS。 | 支撐目前 Qt layout、typed confirmation、scroll-follow、owner-bound deferred reflow、signal path與 Linux offscreen scale contract；不證明 Windows native DPI、真實模型長 session、實際下載中的 Settings 畫面或 raw-model accuracy。 |
| Local assistant | Phi-4 mini GPU ChatPanel workflow PASS；post-close runtime / dispatcher `closed`、controller released、generation threads `0`；raw tool-call `6/12`，host-assisted product policy `12/12`。 | 支撐狹義 local runtime、terminal ownership 與產品安全邊界；不支撐 thesis-grade accuracy 或長時間 session。 |
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
