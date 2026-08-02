# XBrainLab 目前狀態

最後更新：`2026-08-02`

這頁只回答三件事：目前在哪一條整合線、現在能相信什麼、離 handoff 還缺什麼。
短期施工看 [Now](planning/now.md)，驗證規則看
[Validation](validation/README.md)。

## 一句話

XBrainLab 正在 `stabilize/product-quality-closure` 做 product-quality closure。
這條整合線仍有 audit findings 和 exact-commit evidence 要完成，目前不是
handoff-ready，也不能排 Windows acceptance 或宣稱 product complete。

## Current Integration Context

| 項目 | Current truth |
| --- | --- |
| Active worktree | `/mnt/d/workspace_v2/projects/lab/xbrainlab/build/worktrees/assistant-product-v1` |
| Active branch | `stabilize/product-quality-closure` |
| Baseline | `ux/assistant-product-v1@3869aaef73acf3fb30ce95d15868c2abcf17c6f5`，只作 baseline / provenance，不是目前 candidate。 |
| Active goal | `docs/agent_goals/product_quality_closure_goal.md` |
| Finding ledger | [Product Quality Audit - 2026-07-30](records/product_quality_audit_2026-07-30.md) |
| Delivery state | Closure in progress；not handoff-ready；not product complete。 |

其他 registered worktree 不代表 active candidate。需要 inventory 時必須執行
`git worktree list --porcelain`，不要把數量或 branch 清單手動複製成長期 current truth。

## 目前實作真相

| 區域 | 已存在的 current implementation | 尚未完成的邊界 |
| --- | --- | --- |
| Backend | `ApplicationService / Command API` 是 UI、assistant、headless scripts 共用的 product command spine。`BackendFacade` 與 product live-object payload 已物理移除；五個 product panels 由 narrow ports 建立。Shutdown fencing、immutable Assistant publication、external-label import state 與 recipe reload 已有 focused owners，並由 source guards 防止 private state alias / host round-trip 回流。 | Standalone/test compatibility constructors 仍是 P2 cleanup；exact-commit evidence 尚未關閉。不能把 working checkpoint 宣稱為 target architecture fully aligned 或 repo-wide zero-controller。 |
| UI | Product state-changing render 以 revisioned application publication 為單一真相；command result 只處理 acknowledgement / error / in-flight feedback，Training progress 只走 transient event。五個 workflow panels 保留舊版固定右側 `Data Summary` 表格，不另設常駐 Readiness 區塊。Assistant header 不顯示額外狀態 badge；狀態保留在 tooltip / accessibility metadata，composer 使用固定 action geometry，訊息 bubble 依 viewport 與內容重排。Source guard 會追蹤 async callback call chain，阻止 command result 重改 Start/Stop、readiness 或 terminal state。 | Dirty integration work 和 focused tests 只是 checkpoint；offscreen 100/125/150% DPI 與窄寬度 artifact 已通過 working-checkpoint review，但在 clean exact-source screenshots、happy path、edge gate 及 reviewer re-gate 完成前，不是 Windows handoff candidate。Standalone compatibility observer path仍是 P2 cleanup。 |
| Data Interpretation | `scan -> preview -> validate -> apply -> recipe` baseline 存在。Selected EEG scope、label-carrier pairing、reviewed placement 和 BIDS task-import boundary 已有實作；working checkpoint 已新增 Graz external labels、PhysioNet internal events 與 public BIDS 的連續 Data Interpretation-to-training gate。 | 這不是 full BIDS validator，也不支撐任意 P300、SSVEP、clinical、XDF、LSL、MOABB 或 proprietary format claim。新的 strict gate 仍須從 final clean exact commit 重跑，才可成為 handoff evidence。 |
| Assistant | Product runtime 是 local-only；產品決策是 exact IBM Granite 3.3 2B，不做 silent model fallback。`AssistantTurnOrchestrator`、`AssistantToolAttemptSession`、RAG process lifecycle、Qt command/runtime/publication coordinators 已分開擁有 turn state、tool-attempt state、process 與 UI delivery；舊 controller writable aliases 已由 AST guard 禁止。Agent tool admission、capability、confirmation、verification 和 structured result 仍由 backend contract 保護。 | Granite/RAG success、confirmation、error、retry、cancel、long-session 與 Windows native teardown 必須在同一 final commit 重建 evidence；host-assisted workflow 不是 raw-model 或 thesis accuracy。 |
| Privacy / diagnostics | Centralized public diagnostics 會從 default logs、public command/result projection、assistant feedback 和 UI interaction outcome 移除完整私人路徑、常見 subject identifiers 與不安全 control characters；local file sink 有 bounded retention 與 owner-only policy。 | Native Windows/NTFS ACL、junction/reparse replacement、packaged launcher 與 second-account denial仍是平台 acceptance boundary；exact-commit validation 前不能宣稱完整產品 closure。 |
| Native UI lifecycle | Preprocess close/cancel work 已建立 quiesce / restore checkpoint；`tests/integration/ui/test_preprocess_native_lifecycle.py` 和 `tests/integration/ui/test_native_render_lifecycle.py` 分別保護 Preprocess 與 Visualization native ownership。 | 兩個 gate 不互相替代，也不取代 Windows/WSLg、DPI、interactive 3D、real training close 和長時間操作 acceptance。 |
| Packaging | Windows launcher / startup automation 存在。 | 不是 signed installer、release approval 或真人 click-through。 |
| MCP | 既有 code、tests、docs 或 artifacts 只算歷史探索 / compatibility evidence。 | MCP 已退出 active product / thesis roadmap。除非使用者明確要求，不做 MCP hardening、adapter certification 或 handoff gate。 |

## Product-Quality Closure

目前 closure 是否完成，只能由 audit ledger 和 active goal 的 hard gates 判定。局部 checkpoint、
單一 reviewer PASS、dashboard PASS 或一組 focused tests 都不能把整體狀態改成
handoff-ready。

本輪至少還要：

1. 關閉所有 code-controllable P0/P1 findings，保留 focused regression 和 same-class guard。
2. 重跑 real `ApplicationService` happy path、deterministic oracle、strict fixture manifest 和
   required multi-dataset gates。
3. 重建 exact Granite / secure offline RAG 的 success、recovery、cancel、long-session evidence，
   以及 full/narrow/DPI UI artifacts，並由主 agent 逐項檢查。
4. 從同一個 clean exact commit 跑 Ruff、完整 configured product-source Basedpyright、
   architecture、complete regression、strict MkDocs 和 handoff quality dashboard。
5. commit、push、確認 protected local settings 未被 stage，再產生 Windows handoff report。

完成這些自動化條件只會形成 Windows handoff candidate。Product completion 和 merge 到
`main` 仍需真人 Windows acceptance。

## Evidence Truth

`artifacts/quality/latest.md` 是可覆寫的 local generated report，不是 canonical truth。
`ux/assistant-product-v1@3869aaef` 的 PASS report 只證明 baseline；不能代表目前
`stabilize/product-quality-closure`。

Final evidence 必須同時符合：

- profile 是 `handoff`；
- branch 是 `stabilize/product-quality-closure`；
- report commit 唯一對應 `git rev-parse HEAD` 記錄的 pushed candidate exact SHA；
- worktree clean，或只保留規則明確允許且未 stage 的 protected local settings；
- 所有 required checks 從該 commit 重跑，沒有用 stale cache、hidden skip、xfail 或 deselection。

Canonical docs 不保存手動加總的 test totals。需要 total 時直接引用符合上述 identity 的
generated evidence；branch、commit 或 dirty state 不吻合時，只能稱為 historical evidence
或 checkpoint。

## 可以宣稱

- `ApplicationService / Command API` 是 active product command spine。
- `BackendFacade` 已物理移除，回流必須被 architecture guard 擋下。
- Product assistant runtime 是 local-only，MCP 不是 active roadmap。
- Baseline 和 current integration line 已明確分開。
- Product-quality closure 正在進行，audit ledger 是 finding/status authority。

## 不能宣稱

- `ux/assistant-product-v1@3869aaef` 是目前 handoff candidate。
- product-quality closure 已完成或目前已 handoff-ready。
- 任一舊 dashboard、walkthrough、reviewer verdict 或手動 test total 代表 current branch。
- backend target architecture、Data Interpretation 或 Assistant 已 final。
- automated UI / launcher evidence 等於 human Windows acceptance。
- MCP 是 product、release 或 thesis prerequisite。
- signed installer、release approval、scientific model-quality 或 thesis-grade agent accuracy。

## 先看哪裡

| 你想知道 | 讀這裡 |
| --- | --- |
| 下一步施工 | [planning/now.md](planning/now.md) |
| Active findings | [records/product_quality_audit_2026-07-30.md](records/product_quality_audit_2026-07-30.md) |
| Completion contract | `docs/agent_goals/product_quality_closure_goal.md` |
| 目前架構 | [architecture/README.md](architecture/README.md) |
| 目標架構 | [target/architecture.md](target/architecture.md) |
| Evidence 與 handoff gate | [validation/README.md](validation/README.md) |
