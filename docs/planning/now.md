# XBrainLab Now

最後更新：`2026-07-04`

這頁只放下一輪施工焦點。

## 目前焦點

**Current truth rebaseline before more feature work.**

最近幾週產品、UI、saliency、Data Import、agent / thesis discussion 都有推進，但 canonical docs
沒有跟著每個 checkpoint 收乾淨，導致 roadmap、current state、artifact claim 和實際分支狀態重新變得難判斷。

現在先做文件與狀態重盤點，再繼續推進功能。這不是暫停工程，而是避免在錯誤前提上繼續疊工作。

## 本輪 To-do

| 狀態 | 工作 | 完成判準 |
| --- | --- | --- |
| Done | Current docs rebaseline | `docs/current.md`、`docs/planning/now.md`、`docs/planning/roadmap.md`、`docs/architecture/README.md`、`docs/validation/README.md` 對目前方向不矛盾。 |
| Done | MCP 從 active plan 移除 | Roadmap、current truth、target / architecture docs 不再把 MCP 當 MVP、release、thesis 或 handoff gate。 |
| Done | Roadmap 心智模型定型 | Roadmap 改成 Rebaseline -> Desktop MVP -> Product Polish / Release Candidate -> Assistant MVP -> Thesis Evidence；UI/UX blocker 放進 Desktop MVP，視覺一致性放進 Product Polish。 |
| Done | Branch / worktree inventory | 目前正式 git worktree 只有本 repo；下一輪工程基底定為 `stabilize/desktop-mvp`，從 rebaseline checkpoint 建立。 |
| Done | Known blocker reset | 最近手測提到的 UI / runtime blocker 已重新列在本頁與 `docs/records/product_feedback.md`。 |
| Done | Handoff gate reset | 「可以手測」前必跑 happy path、edge case、多資料集、screenshot artifact 和 claim boundary；細節以 `docs/validation/README.md` 和 `.agents/workflows/handoff-candidate.md` 為準。 |
| Next | Desktop MVP blocker repair | 從唯一工程基底修主流程 blocker；每個修復分支都要通過 handoff candidate gate 才能交給使用者手測。 |

## 2026-07-04 Rebaseline 結論

### Branch / worktree

| 項目 | 結論 |
| --- | --- |
| Active repo | `/mnt/d/workspace_v2/projects/lab/xbrainlab` |
| Registered git worktrees | 只有目前這個 worktree。之前的混亂主要是歷史 branches，不是多個仍掛載的 worktree。 |
| Current rebaseline checkpoint | `docs/rebaseline-drop-mcp` at `9f91994f`。 |
| Next engineering base | `stabilize/desktop-mvp`，從 rebaseline checkpoint 建立，用來修 Desktop MVP blockers。 |
| Main branch | `main` / `origin/main` 都落後目前 integration line；不要在 Desktop MVP gate 前直接把現在狀態推回 main。 |

目前只有三個 local branches 沒有併入 rebaseline checkpoint：

| Branch | 判斷 | 下一步 |
| --- | --- | --- |
| `docs/multi-gate-loop` | 舊 multi-gate 文件 / skill 線，和目前已整理的 `.agents` 文件有重疊，也帶有產品碼差異。 | 不整支 merge；若需要，只 cherry-pick 可用的 gate wording。 |
| `docs/development-process-rules` | 舊 governance 線，差異很大，會倒退目前 docs / tests 的 current truth。 | 不整支 merge。 |
| `wip/data-import-controller-dirty-checkpoint` | 舊大型 WIP，混合 Data Import、UI、backend、artifacts、tests，不能作為乾淨整合來源。 | 保留作歷史參考；不要整支 merge。 |

### Desktop MVP blocker board

這些是下一輪修復入口，不代表都一定仍存在；每項開始前要先在 `stabilize/desktop-mvp`
重現或以 artifact 確認。

| Area | Blocker / risk | Gate before handoff |
| --- | --- | --- |
| Data Import / labels | Remove label 後再 load 同一檔可能重複；auto-detected 與 user-added label source 移除語意容易混淆；Match Labels 可能沒同步 reload 後的 label state。 | focused label reload regression、Data Import wizard format matrix、多資料集 gate、wizard screenshot review。 |
| Review and Import | confirm / review item 可能太碎；相同問題跨檔案應 group；metadata missing subject/session/run 不應變成過度嚴厲或重複 action。 | structured action item tests、review screenshot artifact、user-task wording review。 |
| Epoch / preprocess | 先前出現過切頁或 PSD / time-series preview 造成 Qt native crash；epoch dialog 曾有背景色與 layout overflow。 | crash reproduction sweep、figure lifecycle / UI-thread guard、epoch/preprocess screenshots。 |
| Dataset split | Step layout、preview title overlap、table dark background、confirm pattern、disabled select column、combo arrow 視覺一致性需要重新驗證。 | dataset split UI tests、screenshot review、same-class dialog sweep。 |
| Model selection / training | model selection scroll、parameters layout、pretrained weights controls、training 完成後不要用 blocking dialog 打斷。 | model-selection dialog screenshot、training smoke、status-bar behavior check。 |
| Evaluation | metrics / per-class tables 曾出現白底白字、初始選取不合理、model summary 空或卡住。 | evaluation panel UI tests、table palette guard、tiny trained-record walkthrough。 |
| Visualization / saliency | saliency readiness、label mapping、fold switch、3D centering / availability、Matplotlib figure cleanup 需要 current branch verification。 | visualization render walkthrough、saliency focused tests、3D runtime probe、figure-count guard。 |

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

- 不重開 Match Labels / Review and Import 大型 UX 設計。
- 不做 MCP hardening、MCP client certification 或 MCP thesis evidence。
- 不開始 thesis-grade agent benchmark 實驗；那需要獨立 research branch / goal。
- 不把 automated dashboard PASS 當作 human Windows acceptance。
- 不把舊 artifact 當成 current truth。

## 收尾條件

本輪可以收尾的條件是：

1. MCP 已從 active docs 和 gate 語意移除。
2. Roadmap 五階段心智模型已寫進 canonical docs。
3. `mkdocs build --strict` 通過。
4. `git diff --check` 通過。
5. docs branch clean commit 並 push。
6. 下一輪工程入口清楚：哪個分支、哪些 blocker、哪些 gate、哪些文件要同步。
