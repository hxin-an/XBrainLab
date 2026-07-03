# XBrainLab 目前狀態

最後更新：`2026-07-04`

這頁只回答一件事：**現在能相信什麼，還不能宣稱什麼，下一步該做什麼。**
完整階段安排看 [Roadmap](planning/roadmap.md)，下一輪施工看 [Now](planning/now.md)。

## 一句話

XBrainLab 正在重新盤點成 Windows 本地 EEG / BCI 桌面工具。Roadmap、MCP 下線、
branch/worktree inventory、known blocker board 和 handoff gate 已重新對齊；下一步進入
Desktop MVP blocker repair。

MCP 已從 active product / thesis roadmap 拔掉。既有 MCP 程式碼、測試與 artifacts 只代表
歷史探索或相容性證據，不再是 MVP、release candidate 或 thesis evidence 的必要路線。

目前不能宣稱 product complete。

## 現況總覽

| 區域 | 目前狀態 | 邊界 |
| --- | --- | --- |
| Backend | `ApplicationService / Command API` 已是主要 command spine；UI、assistant 和 scripts 不應把 `BackendFacade` 當入口，service lazy wrappers 已改成明確 command handler。 | Desktop MVP 和 Product Polish 階段都要持續防止新的 legacy / duplicate refresh truth。 |
| UI | PyQt 主流程、Data Interpretation wizard、training / evaluation / visualization surface 都有 baseline；`stabilize/bids-epoch-saliency-baseline` 已把 2026-06-17 定稿的 saliency background baseline flow 落到 command/UI path。 | automated walkthrough 不等於 human Windows desktop acceptance；仍需真人 Windows click-through 才能宣稱產品驗收完成。 |
| Data Interpretation | `scan -> preview -> validate -> apply -> recipe` baseline 已存在；Data Import wizard 已補強 Tier 1/Tier 2 label-source、BIDS-like events、internal event evidence、external label placement、structured review coverage，並把 reviewed label placement 寫成 epoch 建議。 | 還不是 full BIDS / arbitrary import system；P300/SSVEP/clinical/XDF/LSL/MOABB/proprietary converters 不能誇大。Epoch 目前消費 import 建議，不代表 epoch/preprocess 全流程已做完整 UX 重作。 |
| Assistant / Agent | in-app assistant 仍是產品與論文方向，但要等桌面主流程、command surface、verification layer 和 benchmark protocol 重新整理乾淨後再推。 | 目前不能宣稱 thesis-grade tool-call accuracy，也不能用 agent score 代表 UI 已可用。 |
| MCP | 從 active plan 移除。 | 不再追求 MCP hardening、MCP client certification、MCP external-agent product path 或 MCP thesis evidence。 |
| Packaging | Windows launcher / startup smoke 有 evidence。 | 還不是 signed installer，也不是 release approval。 |

## 下一個真正 blocker

**Desktop MVP blocker repair：在唯一工程基底上修主流程 blocker。**

Rebaseline 後的工程入口：

- 目前正式 git worktree 只有 `/mnt/d/workspace_v2/projects/lab/xbrainlab`。
- rebaseline checkpoint 是 `docs/rebaseline-drop-mcp` at `9f91994f`。
- 下一輪工程基底是 `stabilize/desktop-mvp`，從 rebaseline checkpoint 建立。
- `docs/multi-gate-loop`、`docs/development-process-rules`、`wip/data-import-controller-dirty-checkpoint`
  不整支 merge；只在需要時 cherry-pick 可用片段。
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

## 不能宣稱

- product complete。
- backend target architecture fully aligned。
- Data Interpretation final。
- automated UI walkthrough 等於 human Windows desktop acceptance。
- tool-call eval 等於 UI / product completion。
- MCP baseline 屬於 active roadmap。
- launcher smoke 等於 release approval 或 signed installer。
- `stabilize/desktop-mvp` 已經 handoff-ready；它只是下一輪修復基底。

## 最近驗證

| Gate | 最近結果 | 用途 |
| --- | --- | --- |
| `mkdocs build --strict` | PASS | 文件站可建。 |
| fast quality dashboard | Clean evidence lives in generated `artifacts/quality/latest.md` for the current branch/commit. | lint、type、architecture、startup、UI baseline、UI product walkthrough、UI unit、real-data IO。 |
| UI unit suite in dashboard | `1265 passed` | 支撐目前 UI regression baseline，不取代人工 UX approval。 |
| Data Interpretation format matrix | expected capabilities observed / match | 支撐代表性 scan / preview / validation format boundary。 |
| Required multi-dataset gate | strict dataset matrix OK; IO + public BIDS + cross-source integration `36 passed`; public cross-source strict smoke `4 passed, 0 missing, 0 failed` | 支撐 checked-in GDF/MAT、compact multiformat、public event-rich fixtures、public BIDS EEG fixture。 |
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
