# XBrainLab 目前狀態

最後更新：`2026-08-14`

這頁只回答三件事：目前在哪一條整合線、現在能相信什麼、離 handoff 還缺什麼。
短期施工看 [Now](planning/now.md)，驗證規則看
[Validation](validation/README.md)。

## 一句話

XBrainLab 的 product baseline 是 `main`；目前候選從最新 `main` 擷取已由使用者實際操作的
desktop product foundation，保留完整 `XBrainLab/**` runtime 與 product regression，同時排除
MOABB campaign、materializer、GUI driver 與其 delivery gate。候選仍須完成 focused validation、
push、PR exact-head CI 與合併，才會成為新的 `main`；在此之前只能稱 validated checkpoint。

## Current Integration Context

| 項目 | Current truth |
| --- | --- |
| Active worktree | Product-foundation extraction candidate；實際 branch / SHA 由 Git 取得。repo-root `settings.json` 是不得納入版本控制的使用者本機設定。 |
| Product baseline | `main` |
| Current candidate | 從最新 `main` 建立的 product-foundation PR；不是 release。 |
| Baseline | 以 candidate merge-base 的最新 `main` 為準，不在文件寫死 historical SHA。 |
| Active goal | 先把 working desktop foundation 以 product-only PR 合回 `main`；接受後再集中 datasets，最後另開 P300 Saliency fix。 |
| Historical ledger | [Product Quality Audit - 2026-07-30](records/product_quality_audit_2026-07-30.md)；只作 provenance，不是 active queue。 |
| Delivery state | Product-only extraction 已 push 並建立 draft PR `#16`。最新 exact-head CI 已驗證 BIDS montage publication-race 修正，並通過已完成的 platform、unit、integration 與 required public multi-dataset gates；Windows core test 另揭露 cache-cleanup fault injection 全域攔截 `Path.resolve`，已收斂為只使目標 cache root 失敗且本機通過。仍須 push 新 exact head、等待所有 non-skipped checks completed/success 並經 PR merge，才可成為 `main`。 |

其他 registered worktree 不代表 active candidate。需要 inventory 時必須執行
`git worktree list --porcelain`，不要把數量或 branch 清單手動複製成長期 current truth。
目前這輪 import / training / montage polish 沒有 exact-SHA handoff dossier；tracked screenshots 與 ignored walkthrough 都只算
checkpoint evidence。

## 目前實作真相

| 區域 | 已存在的 current implementation | 尚未完成的邊界 |
| --- | --- | --- |
| Backend | `ApplicationService / Command API` 是 UI、assistant、headless scripts 共用的 product command spine。`BackendFacade` 與 product live-object payload 已物理移除；五個 product panels 由 narrow ports 建立。Shutdown fencing、immutable Assistant publication、external-label import state 與 recipe reload 已有 focused owners，並由 source guards 防止 private state alias / host round-trip 回流。 | Standalone/test compatibility constructors 仍是 P2 cleanup；exact-commit evidence 尚未關閉。不能把 working checkpoint 宣稱為 target architecture fully aligned 或 repo-wide zero-controller。 |
| UI | Product state-changing render 以 revisioned application publication 為單一真相；command result 只處理 acknowledgement / error / in-flight feedback，Training progress 只走 transient event。五個 workflow panels 保留舊版固定右側 `Data Summary` 表格，不另設常駐 Readiness 區塊。Assistant header 不顯示額外狀態 badge；狀態保留在 tooltip / accessibility metadata，composer 使用固定 action geometry，訊息 bubble 依 viewport 與內容重排。Source guard 會追蹤 async callback call chain，阻止 command result 重改 Start/Stop、readiness 或 terminal state。 | Dirty integration work 和 focused tests 只是 checkpoint；offscreen 100/125/150% DPI 與窄寬度 artifact 已通過 working-checkpoint review，但在 clean exact-source screenshots、happy path、edge gate 及 reviewer re-gate 完成前，不是 Windows handoff candidate。Standalone compatibility observer path仍是 P2 cleanup。 |
| Data Interpretation | `scan -> preview -> validate -> apply -> recipe` baseline 存在。Selected EEG scope、label-carrier pairing、reviewed placement 和 BIDS task-import boundary 已有實作。BIDS label-field recommendation 以 selected runs 的 bounded row/sidecar evidence、run coverage 與跨 run consistency 為依據；只要任一 selected events table 超過 row 或 byte inspection bound，就停止自動推薦並要求 review。明確使用者選擇仍優先。外部 event values 的第一層 `Use as` 已收斂成 `Training class` / `Do not use`；等待 scan 或重新 matching 時先顯示完整 wizard loading surface。Local-only `p300-multisubject` profile 保存 ds003061 的 `sub-001` 到 `sub-003`、共 9 runs，並保護 exact selected-subject scope；真人手測仍只確認 Graz 2a GDF（A01T/A02T/A03T）與 OpenNeuro ds003061 P300 BIDS。 | Recommendation 是可審查建議，不是 BIDS schema 猜測或自動確認。`Do not use` 只排除 supervised class，不刪除 EEG event。多 subject fixture 與自動化 review 不是三位 subject 的 Windows 真人 acceptance；一個 GDF dataset family 和一個 BIDS dataset 也不能外推為所有 GDF/BIDS、full BIDS validator、任意 P300/SSVEP/clinical/XDF/LSL/MOABB 或 proprietary format 支援。 |
| Epoch / split / training contract candidate | Epoch context 只接受 reviewed import handoff 與每段 recording 的 matching timing hints；缺少、格式錯誤、讀取失敗、source / placement 不一致，或 selected recordings 的 sampling frequency 不一致時 fail closed，且不改變既有資料；將所有 recordings resample 到同一 sampling frequency 後會重新取得 `Create Epoch` readiness。Duration / event-locked mode 由這份 reviewed handoff 綁定的 event placement 與 duration evidence 產生，不由 dialog 猜測。Split preview 會暫時建立 candidate datasets / masks 以產生摘要，完成後恢復原狀；Confirm 只保存 typed split specification、epoch revision、fingerprint 與 bounded preview summary，`Start Training` 才做 authoritative rematerialization、audit 與 publication。Training Setting 提供 deterministic starting recommendations，並逐欄位保存 trusted user edit 的 manual provenance。 | 這些是 dirty working candidate 正在收斂的 contract，尚未有 clean exact-head CI / Windows acceptance。Split Confirm 不代表 training tensors 或 masks 已發布；recommendations 不是最佳參數、AutoML 或 timed hyperparameter search。 |
| EEG workflow foundation candidate | 候選包含 formal BIDS inventory / subject projection、reviewed import、owned long-running work、detached preprocess / epoch preparation、Training preview、Evaluation publication 與 explicit Saliency operation。使用者已回報 PhysionetMI 手動流程可完成；這是重要人工 checkpoint。 | 候選尚未合併；該手測不是 exact-head automated receipt，也不能外推為所有 BIDS、所有模型、P300 Saliency 或 Windows native acceptance。 |
| Assistant | Local-only Assistant、IBM Granite 3.3 2B 選項、tool admission、capability、typed confirmation、decision owner、verification 和 structured result 的工程骨架存在；ApplicationService 仍控制最後 command admission。Standalone debug host 已和 product runtime 對齊 high-impact setting confirmation，walkthrough 也會區分 confirmation card 與 GUI handoff。 | Assistant 目前尚未準備好給老師使用。同一 request 仍可能向 Granite 2B 暴露多個競爭 tool schemas；現有 deterministic walkthrough 不是 real Granite tool-call accuracy、長時間使用或 Windows acceptance。 |
| Privacy / diagnostics | Centralized public diagnostics 會從 default logs、public command/result projection、assistant feedback 和 UI interaction outcome 移除完整私人路徑、常見 subject identifiers 與不安全 control characters；local file sink 有 bounded retention 與 owner-only policy。 | Native Windows/NTFS ACL、junction/reparse replacement、packaged launcher 與 second-account denial仍是平台 acceptance boundary；exact-commit validation 前不能宣稱完整產品 closure。 |
| Native UI lifecycle | Preprocess close/cancel work 已建立 quiesce / restore checkpoint；`tests/integration/ui/test_preprocess_native_lifecycle.py` 和 `tests/integration/ui/test_native_render_lifecycle.py` 分別保護 Preprocess 與 Visualization native ownership。 | 兩個 gate 不互相替代，也不取代 Windows/WSLg、DPI、interactive 3D、real training close 和長時間操作 acceptance。 |
| Packaging | Windows launcher / startup automation 存在。 | 不是 signed installer；release sign-off 與真人 click-through 尚未完成。 |
| MCP | 既有 code、tests、docs 或 artifacts 只算歷史探索 / compatibility evidence。 | MCP 已退出 active product / thesis roadmap。除非使用者明確要求，不做 MCP hardening、adapter certification 或 handoff gate。 |

## Main Checkpoint Boundary

這次候選的目的，是把使用者已能操作的程式基礎從舊 reliability checkpoint 擷取成可審查的
product-only PR，再合回 `main`。它不是 release acceptance，也不攜帶 MOABB campaign tooling、
materialized datasets、driver receipts 或大 build artifacts。

後續至少要：

1. 完成 product-foundation PR 的 exact-head CI 與合併，保留舊 checkpoint 作 rollback provenance。
2. 在接受後把 EEG datasets 集中到 `tests/fixtures/data/`，先驗 checksum 再刪重複 source/cache。
3. 從新 `main` 另開 P300 Saliency fix，以真人失敗的 typed backend status 定責。
4. 把 Assistant 收斂成依自然語言理解意圖的簡化 prototype，再校準 prompt、tools、state truth
   與 confirmation UX。
5. 重寫舊 Agent gate，使它驗證目前產品心智模型，而不是讓過時 gate 的 PASS 代表品質。

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
- `main` 是產品工作的唯一整合基線；目前 product foundation 仍是 draft PR 候選。
- Graz 2a GDF、OpenNeuro ds003061 P300 BIDS 與使用者回報的 PhysionetMI 流程有人工 checkpoint；三者 evidence identity 不同，不能合併成 cross-dataset gate PASS。
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
- signed installer、release sign-off、scientific model-quality 或 thesis-grade agent accuracy。

## 先看哪裡

| 你想知道 | 讀這裡 |
| --- | --- |
| 下一步施工 | [planning/now.md](planning/now.md) |
| Historical audit | [records/product_quality_audit_2026-07-30.md](records/product_quality_audit_2026-07-30.md)；active work 只讀 Now。 |
| 下一個 candidate contract | [planning/now.md](planning/now.md) 與 [validation/README.md](validation/README.md) |
| 目前架構 | [architecture/README.md](architecture/README.md) |
| 目標架構 | [target/architecture.md](target/architecture.md) |
| Evidence 與 handoff gate | [validation/README.md](validation/README.md) |
