# XBrainLab Now

最後更新：`2026-07-21`

這頁只放下一輪施工焦點。

## 目前焦點

**Close the focused GUI repair candidate, then run Windows acceptance from that single branch.**

先前稽核列出的 product、scientific correctness、Qt lifecycle 與 agent host-safety blocker 已完成
實作、完整回歸、獨立 reviewer、commit / push 與 exact-commit dashboard 都已關閉。現在不再
擴張功能；`ux/gui-review-preprocess-polish` 已完成自動化與可見 artifact gate，收斂 commit / push
後的下一步是 Windows 真人 click-through，接受後才進 stabilization / main merge gate。

## 本輪 To-do

| 狀態 | 工作 | 完成判準 |
| --- | --- | --- |
| Done | Current docs rebaseline | `docs/current.md`、`docs/planning/now.md`、`docs/planning/roadmap.md`、`docs/architecture/README.md`、`docs/validation/README.md` 對目前方向不矛盾。 |
| Done | MCP 從 active plan 移除 | Roadmap、current truth、target / architecture docs 不再把 MCP 當 MVP、release、thesis 或 handoff gate。 |
| Done | Roadmap 心智模型定型 | Roadmap 改成 Rebaseline -> Desktop MVP -> Product Polish / Release Candidate -> Assistant MVP -> Thesis Evidence；UI/UX blocker 放進 Desktop MVP，視覺一致性放進 Product Polish。 |
| Done | Branch / worktree inventory | 目前正式 git worktree 只有本 repo；下一輪工程基底定為 `stabilize/desktop-mvp`，從 rebaseline checkpoint 建立。 |
| Done | Known blocker reset | 最近手測提到的 UI / runtime blocker 已重新列在本頁與 `docs/records/product_feedback.md`。 |
| Done | Handoff gate reset | 「可以手測」前必跑 happy path、edge case、多資料集、screenshot artifact 和 claim boundary；細節以 `docs/validation/README.md` 和 `.agents/workflows/handoff-candidate.md` 為準。 |
| Done | Delivery flow unified | Branch 規則與 handoff 規則已統一為 Desktop MVP Delivery Flow：short task branch -> stabilization line -> handoff candidate -> user acceptance -> main。 |
| Done | Desktop MVP audit | Architecture、UI、test/EEG reviewer 已盤點 command concurrency、Qt lifecycle、assistant policy、validation truth、窄螢幕 layout 與 artifact determinism。 |
| Done | Desktop MVP blocker repair | ApplicationService serialization、assistant refresh/lifecycle、Data Import review truth、real GDF event/evaluation evidence、validation matrix truth、narrow UI artifacts 已修復。 |
| Invalidated | Previous handoff candidate | 舊 dashboard、walkthrough 與 reviewer 結論未完整綁定目前 HEAD，已撤銷 handoff-ready claim；只保留為歷史 checkpoint。 |
| Done | Validation truth reset | Windows launcher 已改指向唯一 active repo；walkthrough 要求 reload/reapply、training completion、evaluation、visualization 真成功，scripted assistant transcript 只算 layout evidence。 |
| Done | Scientific training correctness | validation-only checkpoint、final test evaluation、split provenance、undefined AUC、BIDS bounds/run mapping、overlapping-window leakage 與 saliency atomicity都有 regression。 |
| Done | Non-blocking application view / shutdown | 原子 publication、non-blocking query、recovery path、background snapshot generation、owner-bound Qt receiver 與 native teardown regression 已通過。 |
| Done | Agent verified host loop | strict envelope、repair context、turn guard、request admission、confirmation / UI handoff 與真 Phi-4 ChatPanel workflow 已完成；raw model accuracy 仍明確列為 research gap。 |
| Done | Agent Panel product UI | loading / empty / ready / working / error、responsive composer、mode selector、suggestion prompts、inline typed confirmation 與 retry 已統一；12 列長 action card 可捲動且操作可達，無空白長值會安全斷行且 Copy 不污染原值；hidden dock refresh 不會讓 empty state 與 transcript 並存；focused `455/455`、完整 UI unit suite `2089/2089`、product walkthrough `7/7` 連續 3 輪、human-like walkthrough與 100% / 125% / 150% Qt subprocess gate 已通過。 |
| Done | Candidate closure | 完整 unit `9006`、integration `388`、靜態 / architecture / docs、多資料集、UI walkthrough、兩個獨立 reviewer 與 exact-commit dashboard 全數 PASS；branch 已 push。 |
| Done | Review / preprocess / visualization repair | Step 5 recipe 與 Epoch 解耦且 optional；Smart Parser、preprocess dialogs、三態 preview、固定 History、Explanation Plots 與共用色階 spectrogram 已完成 focused `567`、product `7`、human-like `42/42` 與多資料集 gate。 |
| Next | Windows user acceptance | 從已發佈候選 branch 做真人 click-through；通過前不直接合併 `main`。 |

## 2026-07-04 Rebaseline 結論

### Branch / worktree

| 項目 | 結論 |
| --- | --- |
| Active repo | `/mnt/d/workspace_v2/projects/lab/xbrainlab` |
| Registered git worktrees | 只有目前這個 worktree。之前的混亂主要是歷史 branches，不是多個仍掛載的 worktree。 |
| Current rebaseline checkpoint | `docs/rebaseline-drop-mcp` 的 latest pushed checkpoint。 |
| Current repair candidate | `ux/gui-review-preprocess-polish`；完成後 fast-forward `stabilize/desktop-mvp`，只保留一個手測入口。 |
| Main branch | `main` / `origin/main` 都落後目前 integration line；不要在 Desktop MVP gate 前直接把現在狀態推回 main。 |

目前只有三個 local branches 沒有併入 rebaseline checkpoint：

| Branch | 判斷 | 下一步 |
| --- | --- | --- |
| `docs/multi-gate-loop` | 舊 multi-gate 文件 / skill 線，和目前已整理的 `.agents` 文件有重疊，也帶有產品碼差異。 | 不整支 merge；若需要，只 cherry-pick 可用的 gate wording。 |
| `docs/development-process-rules` | 舊 governance 線，差異很大，會倒退目前 docs / tests 的 current truth。 | 不整支 merge。 |
| `wip/data-import-controller-dirty-checkpoint` | 舊大型 WIP，混合 Data Import、UI、backend、artifacts、tests，不能作為乾淨整合來源。 | 保留作歷史參考；不要整支 merge。 |

### Desktop MVP residual-risk board

原 blocker 已由 regression、multi-dataset 與 walkthrough 重建；這裡只保留仍需真人或後續研究
才能關閉的風險，不把已修問題繼續寫成 open blocker。

| Area | Remaining risk | Boundary / next gate |
| --- | --- | --- |
| Windows desktop UX | Xvfb screenshots不能證明實際 Windows DPI、遠端桌面、雙螢幕和長時間互動。 | 使用者在單一 stabilization branch 做真人 click-through。 |
| Interactive 3D | headless gate只能驗證 unavailable / framing boundary，不能操作 OpenGL 視圖。 | Windows GPU 桌面手測。 |
| Local agent accuracy | raw Phi-4 candidate目前 `6/12`；backend policy雖使產品安全分數達 `12/12`，但不是模型準確率。 | 後續獨立 research protocol，至少 50/100 cases 與 3 repeats。 |
| Architecture debt | Data Import dialog、LLM controller 等 orchestrator 仍偏大；目前有 focused helpers 和 source guards，但未宣稱 target architecture fully complete。 | 下一輪按責任切片，不在 handoff 前做純行數型重構。 |

### Handoff gate reset

以後任何回報「可以手測」都必須先達到 handoff candidate，不是只跑單一測試。

最低門檻：

1. focused regression：使用者指出的 bug 可重現或有可觀察 artifact。
2. same-class sweep：同類 panel / dialog / command / data flow 已搜尋並處理。
3. happy path：跑像使用者一樣的 workflow 或 UI walkthrough。
4. edge / regression：資料、import、label、epoch、training、evaluation、visualization 相關要跑 required multi-dataset gate。
5. artifact review：UI 可見改動要有 screenshot / walkthrough，主 agent 自己看過。
6. branch hygiene：worktree clean；validated checkpoint commit 並 push。
7. claim boundary：明確說仍不能宣稱什麼。

## 為什麼文件更新會停掉

文件不是沒價值，而是流程上沒有被強制放進每個 checkpoint gate。近期很多工作以 bugfix branch、
artifact refresh、聊天中狀態回報為主，`worklog` 和 screenshots 有更新，但 `current / now /
roadmap / architecture` 沒有每次同步，所以 canonical truth 慢慢落後。

新規則：

- 每個 handoff candidate 都要更新 canonical docs 或明確說「不需要更新，原因是什麼」。
- artifact 更新不能取代 `docs/current.md`。
- branch push / tests green 不能取代 `docs/planning/now.md`。
- roadmap 決策變更要寫入 `docs/planning/roadmap.md` 和 `docs/decisions/README.md`。

## 本輪不做

- 不把本輪 Step 5 局部修復擴張成 Match Labels / Data Import 全流程重做。
- 不做 MCP hardening、MCP client certification 或 MCP thesis evidence。
- 不開始 thesis-grade agent benchmark 實驗；那需要獨立 research branch / goal。
- 不把 automated dashboard PASS 當作 human Windows acceptance。
- 不把舊 artifact 當成 current truth。

## 本輪收尾條件

本輪可以收尾的條件是：

1. `ruff`、`basedpyright`、architecture guard、focused regression 和 full quality dashboard 通過。
2. required multi-dataset / format matrix / cross-source training gate 通過。
3. Data Import、assistant、Data Splitting、Saliency 等可見 artifact 由主 agent 實際看過。
4. architecture / clean code、UI product、test / EEG 三個獨立 reviewer 在修復後全數通過；第一輪
   reviewer 已退回具體問題，不能沿用修復前結論。
5. canonical docs 與 current code / validation truth 一致，`mkdocs build --strict` 通過。
6. branch clean commit 並 push；回報仍需 Windows 真人 acceptance，不誇大為 product complete。
