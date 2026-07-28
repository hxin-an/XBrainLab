# XBrainLab Now

最後更新：`2026-07-29`

這頁只放下一輪施工焦點。

## 目前焦點

**Close one Granite 2B, multi-format teacher candidate, then run Windows acceptance.**

老師下週要用不同格式資料操作 GUI。本輪只收斂一個可手測候選：保留現有 EEG workflow，
把 assistant 簡化為自然語言決定本回合 scope，產品預設切到 exact Granite 3.3 2B，並用真實
多格式 / 多來源資料、真人式 wizard、跨來源 epoch / training 與可見 Agent artifacts 驗證。
候選可動且 Windows acceptance 完成後，才 freeze benchmark；現在不先做 accuracy 主張。

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
| Done | Natural-language turn scope | 移除可見 `Single action` / `Guided workflow` selector；host 依單一 request 建立 immutable no-tool / single-step / continue-until-decision / terminal-endpoint scope。解釋型 prompt 不取得 mutation admission。 |
| Done | Granite 3.3 2B exact runtime | IBM Granite 3.3 2B 是 product primary；runtime 不自動 fallback。catalog trust、dtype、context truncation、prompt / structured smoke 與真 GPU workflow 有 regression。Phi 只保留明確 legacy choice。 |
| Done | Host continuation safety | 只有 parameter-free preview / validate 可由 host deterministic continuation；allowlist、schema、registry、capability、auto-execution 與 confirmation policy 全由 coordinator fail closed。非空參數會在讀 context / verifier / registry 前被拒絕。 |
| Done | Teacher data-format gate | lifecycle `20/20`、required formats `14/14`、7 public cases / 5 source families、real five-step wizard `17 passed`、IO/BIDS/cross-source integration `36 passed`、strict cross-source `4/4`。 |
| Done | Review / preprocess / visualization repair | Step 5 recipe 與 Epoch 解耦且 optional；Smart Parser、preprocess dialogs、三態 preview、固定 History、Explanation Plots 與共用色階 spectrogram 已完成 focused `567`、product `7`、human-like `42/42` 與多資料集 gate。 |
| Done | Candidate closure | Relevant regression `2700 passed`、Qt assistant integration `17 passed`、Ruff / full Basedpyright / architecture / MkDocs PASS；human-like、Granite 2B workflow、adaptive boundary artifacts 由主 agent 檢視，UI 與 architecture reviewer re-gate PASS。候選提交與 push 後只保留受保護的本機設定差異。 |
| Next | Windows user acceptance | 從同一個已 push 候選做真人 click-through；通過前不合併 `main`。 |
| Later | XBrainLab benchmark | working candidate 通過後，另外 freeze case suite、scorer、prompt condition、source fingerprint 與 repeats。產品 host-assisted score和 raw-model score分開。 |

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
| Local agent accuracy | Granite 真實 boundary workflow 已通過，但尚未跑 frozen benchmark。 | working candidate 通過後才建立至少 50/100 cases、30% negative/recovery 與 3 repeats 的獨立 research protocol。 |
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
