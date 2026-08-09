# XBrainLab 目前狀態

最後更新：`2026-08-09`

這頁只回答三件事：目前在哪一條整合線、現在能相信什麼、離 handoff 還缺什麼。
短期施工看 [Now](planning/now.md)，驗證規則看
[Validation](validation/README.md)。

## 一句話

XBrainLab 的 Desktop GUI 基線仍是 `main`。尚未合併的
`integration/eeg-workflow-improvements-v1` 把五個 EEG workflow 改進整合成同一個驗證候選：
curated Braindecode model catalog、BIDS subject preselection、training test curve、validated
cross-fold Evaluation summary，以及 cross-fold Saliency summary / display normalization。候選另有
一個 local-only OpenNeuro P300 多 subject profile（3 subjects、9 runs）與 selected-scope regression，
並完成一輪 BIDS review latency 與 CI runtime checkpoint。真人手測
目前仍只支撐 Graz 2a GDF 與 OpenNeuro ds003061 P300 BIDS 各一個資料集；新候選尚未取得
Windows acceptance 或 exact-head CI success，因此不能宣稱已進入 `main`、product complete、
Assistant ready 或廣泛資料格式相容。

## Current Integration Context

| 項目 | Current truth |
| --- | --- |
| Active worktree | 以 `git rev-parse --show-toplevel` 為準；不要把舊 registered worktree 當成 current product checkout。 |
| Product baseline | `main` |
| Current candidate | `integration/eeg-workflow-improvements-v1`；尚未合併，不是 release。 |
| Baseline | `main@a0e16b400236b687bd2b4c9f58ef4a20929e377b`。 |
| Active goal | 先關閉五項 EEG workflow integration candidate，再依 [Now](planning/now.md) 推進效能與 Assistant。 |
| Finding ledger | [Product Quality Audit - 2026-07-30](records/product_quality_audit_2026-07-30.md) |
| Delivery state | Pushed unmerged integration checkpoint；尚未通過 exact-head CI / Windows acceptance，不是 handoff-ready。 |

其他 registered worktree 不代表 active candidate。需要 inventory 時必須執行
`git worktree list --porcelain`，不要把數量或 branch 清單手動複製成長期 current truth。
目前五項改進沒有 exact-SHA handoff dossier；tracked screenshots 與 ignored walkthrough 都只算
checkpoint evidence。

## 目前實作真相

| 區域 | 已存在的 current implementation | 尚未完成的邊界 |
| --- | --- | --- |
| Backend | `ApplicationService / Command API` 是 UI、assistant、headless scripts 共用的 product command spine。`BackendFacade` 與 product live-object payload 已物理移除；五個 product panels 由 narrow ports 建立。Shutdown fencing、immutable Assistant publication、external-label import state 與 recipe reload 已有 focused owners，並由 source guards 防止 private state alias / host round-trip 回流。 | Standalone/test compatibility constructors 仍是 P2 cleanup；exact-commit evidence 尚未關閉。不能把 working checkpoint 宣稱為 target architecture fully aligned 或 repo-wide zero-controller。 |
| UI | Product state-changing render 以 revisioned application publication 為單一真相；command result 只處理 acknowledgement / error / in-flight feedback，Training progress 只走 transient event。五個 workflow panels 保留舊版固定右側 `Data Summary` 表格，不另設常駐 Readiness 區塊。Assistant header 不顯示額外狀態 badge；狀態保留在 tooltip / accessibility metadata，composer 使用固定 action geometry，訊息 bubble 依 viewport 與內容重排。Source guard 會追蹤 async callback call chain，阻止 command result 重改 Start/Stop、readiness 或 terminal state。 | Dirty integration work 和 focused tests 只是 checkpoint；offscreen 100/125/150% DPI 與窄寬度 artifact 已通過 working-checkpoint review，但在 clean exact-source screenshots、happy path、edge gate 及 reviewer re-gate 完成前，不是 Windows handoff candidate。Standalone compatibility observer path仍是 P2 cleanup。 |
| Data Interpretation | `scan -> preview -> validate -> apply -> recipe` baseline 存在。Selected EEG scope、label-carrier pairing、reviewed placement 和 BIDS task-import boundary 已有實作。Local-only `p300-multisubject` profile 保存 ds003061 的 `sub-001` 到 `sub-003`、共 9 runs，並保護 exact selected-subject scope；真人手測仍只確認 Graz 2a GDF（A01T/A02T/A03T）與 OpenNeuro ds003061 P300 BIDS。 | 多 subject fixture 與自動化 review 不是三位 subject 的 Windows 真人 acceptance；一個 GDF dataset family 和一個 BIDS dataset 也不能外推為所有 GDF/BIDS、full BIDS validator、任意 P300/SSVEP/clinical/XDF/LSL/MOABB 或 proprietary format 支援。 |
| EEG workflow candidate | BIDS import 可在正式 scan 前列出 subjects、sessions、tasks、runs，且只掃 selected subjects；Training 提供 curated Braindecode model catalog 並發布 test accuracy curve；Evaluation / Visualization 使用一基索引的 Fold / Run 語言，只有 backend 證明 test masks 與 cohort 相容時才提供 `All Folds` summary；Saliency Normalize 只改 detached render data。 | Candidate 尚未合併；Braindecode catalog 不是「支援 Braindecode 全模型」，cross-fold summary 不是 scientific model comparison，Normalize 不改原始 attribution。 |
| Assistant | Local-only Assistant、IBM Granite 3.3 2B 選項、tool admission、capability、confirmation、verification 和 structured result 的工程骨架存在；ApplicationService 仍控制最後 command admission，未發現 model-output 直接繞過的 P0。 | Assistant 目前尚未準備好給老師使用。High-impact training settings 尚未統一走 typed confirmation；GUI handoff 與真正 confirmation 仍共用 `WAITING_FOR_DECISION`；同一 request 仍可能向 Granite 2B 暴露多個競爭 tool schemas。現有 RAG/Granite/UI evidence 也不是 current exact-source acceptance。 |
| Privacy / diagnostics | Centralized public diagnostics 會從 default logs、public command/result projection、assistant feedback 和 UI interaction outcome 移除完整私人路徑、常見 subject identifiers 與不安全 control characters；local file sink 有 bounded retention 與 owner-only policy。 | Native Windows/NTFS ACL、junction/reparse replacement、packaged launcher 與 second-account denial仍是平台 acceptance boundary；exact-commit validation 前不能宣稱完整產品 closure。 |
| Native UI lifecycle | Preprocess close/cancel work 已建立 quiesce / restore checkpoint；`tests/integration/ui/test_preprocess_native_lifecycle.py` 和 `tests/integration/ui/test_native_render_lifecycle.py` 分別保護 Preprocess 與 Visualization native ownership。 | 兩個 gate 不互相替代，也不取代 Windows/WSLg、DPI、interactive 3D、real training close 和長時間操作 acceptance。 |
| Packaging | Windows launcher / startup automation 存在。 | 不是 signed installer、release approval 或真人 click-through。 |
| MCP | 既有 code、tests、docs 或 artifacts 只算歷史探索 / compatibility evidence。 | MCP 已退出 active product / thesis roadmap。除非使用者明確要求，不做 MCP hardening、adapter certification 或 handoff gate。 |

## Main Checkpoint Boundary

這次合併到 `main` 是使用者明確接受的開發基線收斂，不是 release acceptance。合併理由是
避免後續修復繼續分散在長期 stabilization branch；它不會把尚未完成的 Assistant、效能或
格式支援自動提升成完成。

後續至少要：

1. 以 `main` 為基線修正老師試用前發現的 GUI/data workflow blocker。
2. 針對載入、preprocess、training、publication refresh 與 plotting 做可觀察的效能量測和打磨。
3. 把 Assistant 收斂成依自然語言理解意圖的簡化 prototype，再校準 prompt、tools、state truth
   與 confirmation UX。
4. 重寫舊 Agent gate，使它驗證目前產品心智模型，而不是讓過時 gate 的 PASS 代表品質。
5. 擴大真人資料集 acceptance；在此之前只保留已實際手測的兩個 dataset claim。

## Evidence Truth

`artifacts/quality/latest.md` 是可覆寫的 local generated report，不是 canonical truth。
`ux/assistant-product-v1@3869aaef` 的 PASS report 只證明 baseline；不能代表目前
`main`。舊 `stabilize/product-quality-closure` evidence 只保留為此次整合的 provenance。

未來 release / Assistant candidate evidence 必須同時符合：

- profile 是 `handoff`；
- branch / commit 是當次明確指定的 candidate，且最終整合回 `main`；
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
- `main` 現在是後續產品工作的單一整合基線。
- Graz 2a GDF 與 OpenNeuro ds003061 P300 BIDS 各一個資料集已完成真人 GUI 手測。
- Local-only ds003061 P300 fixture 已有 3 subjects、9 runs，可重跑 selected-subject scope regression。

## 不能宣稱

- 目前是 release、product-complete 或 Assistant-ready candidate。
- 所有 GDF、所有 BIDS 或 full BIDS validator 已通過真人驗收。
- 任一舊 dashboard、walkthrough、reviewer verdict 或手動 test total 代表 current branch。
- backend target architecture、Data Interpretation 或 Assistant 已 final。
- 舊 Agent gate 已對齊目前 Assistant 心智模型，或可作為 Assistant 品質結論。
- 效能已完成打磨，或高階硬體上的流暢度可外推到其他電腦。
- automated UI / launcher evidence 等於 human Windows acceptance。
- 目前 BIDS latency 數字可跨機重現，或效能工作已完成。
- MCP 是 product、release 或 thesis prerequisite。
- signed installer、release approval、scientific model-quality 或 thesis-grade agent accuracy。

## 先看哪裡

| 你想知道 | 讀這裡 |
| --- | --- |
| 下一步施工 | [planning/now.md](planning/now.md) |
| Active findings | [records/product_quality_audit_2026-07-30.md](records/product_quality_audit_2026-07-30.md) |
| 下一個 candidate contract | [planning/now.md](planning/now.md) 與 [validation/README.md](validation/README.md) |
| 目前架構 | [architecture/README.md](architecture/README.md) |
| 目標架構 | [target/architecture.md](target/architecture.md) |
| Evidence 與 handoff gate | [validation/README.md](validation/README.md) |
