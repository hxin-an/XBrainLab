# XBrainLab 目前狀態

最後更新：`2026-07-10`

這頁只回答一件事：**現在能相信什麼，還不能宣稱什麼，下一步該做什麼。**
完整階段安排看 [Roadmap](planning/roadmap.md)，下一輪施工看 [Now](planning/now.md)。

## 一句話

XBrainLab 已完成本輪 Desktop MVP audit、blocker repair 與 handoff-candidate gate。
Application command serialization、assistant 執行政策與 Qt worker lifecycle、Data Import
pairing/review truth、真實 GDF event/evaluation 路徑、UI repaint artifact 和多資料集 validation
都有 current evidence；完整 dashboard 與 architecture/UI/test-EEG reviewer gates 已通過。
目前下一步是從本輪驗證並 push 的 `stabilize/desktop-mvp` 進行 Windows 真人 acceptance，
通過後才決定是否合併 `main`。

MCP 已從 active product / thesis roadmap 拔掉。既有 MCP 程式碼、測試與 artifacts 只代表
歷史探索或相容性證據，不再是 MVP、release candidate 或 thesis evidence 的必要路線。

目前不能宣稱 product complete。

## 現況總覽

| 區域 | 目前狀態 | 邊界 |
| --- | --- | --- |
| Backend | `ApplicationService / Command API` 是主要 command spine；lock 由 Study 擁有，因此 cached 或直接建立的 service 都會序列化同一份 state，首次 cached service 建立也有競態保護。Desktop close 會先安裝 command-admission fence，新 mutation 會在 admission 與 command lock 後各檢查一次。`CommandResult.diagnostics` 保持 JSON-safe，runtime object 只放在 `runtime`。 | 仍要持續防止 controller compatibility 與 duplicate state truth 回流。 |
| UI | PyQt 主流程、Data Interpretation wizard、training / evaluation / visualization surface 都有 baseline；command 執行期間會抑制 observer duplicate refresh，完成後依 `changed_state` 走 shared refresh coordinator。Data Interpretation review/apply/recipe 已改為 QThreadPool continuation，不使用自訂 nested event loop；Data Splitting preview 與 MainWindow close 有明確 worker ownership、failed/cancelled/slow-stop 狀態。 | automated walkthrough 不等於 human Windows desktop acceptance；仍需真人 Windows click-through，尤其是真訓練中關閉與 Windows/WSLg native teardown。 |
| Data Interpretation | `scan -> preview -> validate -> apply -> recipe` baseline 已存在；Data Import wizard 已補強 Tier 1/Tier 2 label-source、strict BIDS folder events、internal event evidence、external label placement、structured review coverage，並把 reviewed label placement 寫成 epoch 建議。Label carrier pairing 現由 backend domain policy 統一供 candidate、apply 與 UI 使用；只配到部分 selected EEG 時會在載入前 blocked。 | BIDS 支援目前是 EEG task import MVP，不是 full BIDS validator；每個 selected run 必須有實際可解析的 events carrier，目前不宣稱 BIDS events inheritance。一般 folder 掃到 `events.tsv` 仍走普通 label-file flow。P300/SSVEP/clinical/XDF/LSL/MOABB/proprietary converters 不能誇大。 |
| Assistant / Agent | in-app assistant 提供 `One Step` 與 `Workflow`：前者只做一個可執行步驟，後者可持續到真正的 confirmation / decision / UI dialog / terminal-command 邊界。工具曝光只由 backend capability policy 決定；單次 tool execution 已抽到 coordinator，UI 只讀 worker runtime snapshot。 | approved local model cache 目前仍缺；不能宣稱長時間本地模型 session、thesis-grade tool-call accuracy 或 Windows assistant acceptance。 |
| MCP | 從 active plan 移除。 | 不再追求 MCP hardening、MCP client certification、MCP external-agent product path 或 MCP thesis evidence。 |
| Packaging | Windows launcher / startup smoke 有 evidence。 | 還不是 signed installer，也不是 release approval。 |

## 下一個真正 blocker

**Windows 真人 acceptance：啟動、Data Import、preprocess/epoch、split/train、evaluation、
visualization/saliency 與 assistant click-through。**

Rebaseline 後的工程入口：

- 目前正式 git worktree 只有 `/mnt/d/workspace_v2/projects/lab/xbrainlab`。
- rebaseline checkpoint 是 `docs/rebaseline-drop-mcp` 的 latest pushed checkpoint。
- 下一輪工程基底是 `stabilize/desktop-mvp`，已從 rebaseline checkpoint 建立並 push。
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
- Data Interpretation 屬於 Desktop MVP；assistant / tool-call baseline 要等桌面主流程穩定後再推進。
- 現有 artifacts 能作為工程 evidence，但每個 evidence 都有明確邊界。
- required multi-dataset gate 目前覆蓋 3 個可訓練 public source family，以及 1 個 epoch-only CNT source；
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
| fast quality dashboard | Product baseline `2168f0a0` 為 clean `PASS`：Ruff、Basedpyright `0 errors`、architecture、startup、7 UI baselines、dialog、product walkthrough、real IO；final handoff commit 以 generated `artifacts/quality/latest.md` 為準。 | lint、type、architecture、startup、UI baseline、UI product walkthrough、UI unit、real-data IO。 |
| UI unit suite in latest lifecycle checkpoint | `1375 passed`；worker/shutdown focused + architecture batch `746 passed`。 | 支撐目前 UI regression、queued command fence、deleted-widget cleanup、Data Splitting Esc/X 與 async interpretation baseline，不取代人工 Windows UX approval。 |
| Data Interpretation format matrix | expected capabilities observed / match | 支撐代表性 scan / preview / validation format boundary。 |
| Required multi-dataset gate | strict dataset / format matrix OK；expanded IO + public BIDS + cross-source + checked-in real GDF pipeline `46 passed`；strict cross-source smoke `4 passed`（3 training + 1 CNT epoch-only） | 支撐 checked-in GDF/MAT、compact multiformat、public event-rich fixtures、public BIDS EEG fixture，並避免把 epoch-only CNT 誤稱可訓練。 |
| Human-like desktop walkthrough | `27/27` phases PASS；Data Import 實際擷取 Step 1/3/4/5，且 glyph、main navigation、visible right-panel paint guards clean。 | 支撐 Xvfb 自動化產品證據；不等於 Windows DPI、多螢幕或長時間真人 acceptance。 |
| Assistant focused regression | command policy、controller/worker lifecycle、refresh、UI wiring focused suites 已通過；核心合併批次最高 `283 passed`，後續 thread/UI targeted tests 亦通過 | 支撐 One Step / Workflow policy、owner-thread teardown、changed-state refresh；不代表本地模型長時間 session。 |
| Saliency / visualization focused tests | ApplicationService / training / UI saliency regression passed on `stabilize/bids-epoch-saliency-baseline`. | 支撐 background baseline、advanced settings recompute boundary、BIDS epoch handoff 和 resource preflight；不取代人工 UX review。 |
| Windows launcher walkthrough | PASS | 自動化 launcher command / bounded startup evidence，不是 signed installer 或真人 click-through。 |

## 先看哪裡

| 你想知道 | 讀這裡 |
| --- | --- |
| 下一步施工 | [planning/now.md](planning/now.md) |
| 產品階段 | [planning/roadmap.md](planning/roadmap.md) |
| 目前架構 | [architecture/README.md](architecture/README.md) |
| 目標架構 | [target/architecture.md](target/architecture.md) |
| 證據怎麼解讀 | [validation/README.md](validation/README.md) |
