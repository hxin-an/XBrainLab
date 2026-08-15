# XBrainLab 目前狀態

最後更新：`2026-08-15`

這頁只回答三件事：目前在哪一條整合線、現在能相信什麼、離 handoff 還缺什麼。
短期施工看 [Now](planning/now.md)，驗證規則看
[Validation](validation/README.md)。

## 一句話

XBrainLab 的可運作 desktop product foundation 與 dataset-storage consolidation 已合回 `main`。
目前從最新 `main` 建立短 branch，修復真人手測後續確認的 Subject／Channel primary action、
Data Split 第二步首次顯示跳動，並從 desktop 與 Assistant 退役會卡住的 Reset Session 入口。
Backend internal ResetSession command 保留；這條 branch 不改科學計算、split 演算法、channel
selection 語意或 dataset storage。

## Current Integration Context

| 項目 | Current truth |
| --- | --- |
| Active worktree | Manual UI regression candidate；實際 branch / SHA 由 Git 取得。repo-root `settings.json` 是不得納入版本控制的使用者本機設定。 |
| Product baseline | `main` |
| Current candidate | 從最新 `main` 建立的 manual UI follow-up / Reset Session surface-retirement branch；不是 release。 |
| Baseline | 以 candidate merge-base 的最新 `main` 為準，不在文件寫死 historical SHA。 |
| Active goal | 關閉三個真人手測 follow-up：primary/footer truth、Data Split 首幀穩定、desktop／Assistant Reset Session surface 退役。 |
| Historical ledger | [Product Quality Audit - 2026-07-30](records/product_quality_audit_2026-07-30.md)；只作 provenance，不是 active queue。 |
| Delivery state | Product foundation 與 dataset storage 已進入 `main`。本輪 follow-up 仍是 short-branch checkpoint；只有 focused evidence、可見 artifact、PR exact-head CI 成功並 merge 後才進入 baseline。舊 dataset source cleanup 仍未授權。 |

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
| Epoch / split / training contract | Epoch context 只接受 reviewed import handoff 與每段 recording 的 matching timing hints；缺少、格式錯誤、讀取失敗、source / placement 不一致，或 selected recordings 的 sampling frequency 不一致時 fail closed，且不改變既有資料；將所有 recordings resample 到同一 sampling frequency 後會重新取得 `Create Epoch` readiness。Duration / event-locked mode 由這份 reviewed handoff 綁定的 event placement 與 duration evidence 產生，不由 dialog 猜測。Split preview 會暫時建立 candidate datasets / masks 以產生摘要，完成後恢復原狀；Confirm 只保存 typed split specification、epoch revision、fingerprint 與 bounded preview summary，`Start Training` 才做 authoritative rematerialization、audit 與 publication。Training Setting 提供 deterministic starting recommendations，並逐欄位保存 trusted user edit 的 manual provenance。 | 這些 contract 已隨 product foundation 合回 `main`，但仍沒有 Windows 真人 acceptance。Split Confirm 不代表 training tensors 或 masks 已發布；recommendations 不是最佳參數、AutoML 或 timed hyperparameter search。 |
| EEG workflow foundation | `main` 包含 formal BIDS inventory / subject projection、reviewed import、owned long-running work、detached preprocess / epoch preparation、Training preview、Evaluation publication 與 explicit Saliency operation。使用者已回報 PhysionetMI 手動流程可完成；這是重要人工 checkpoint。 | Foundation 已合併不等於完整產品 handoff；該手測不是 exact-head automated receipt，也不能外推為所有 BIDS、所有模型、P300 Saliency 或 Windows native acceptance。 |
| Assistant | Local-only Assistant、IBM Granite 3.3 2B 選項、tool admission、capability、typed confirmation、decision owner、verification 和 structured result 的工程骨架存在；ApplicationService 仍控制最後 command admission。Desktop Assistant 不再發布 Reset Session tool；明確 reset session 請求會固定回覆 unavailable 且不讀狀態、不送 confirmation、不執行 mutation。 | Assistant 目前尚未準備好給老師使用。同一 request 仍可能向 Granite 2B 暴露多個競爭 tool schemas；現有 deterministic walkthrough 不是 real Granite tool-call accuracy、長時間使用或 Windows acceptance。Internal backend ResetSession command 與 opt-in MCP compatibility 不屬於本次 surface-retirement claim。 |
| Privacy / diagnostics | Centralized public diagnostics 會從 default logs、public command/result projection、assistant feedback 和 UI interaction outcome 移除完整私人路徑、常見 subject identifiers 與不安全 control characters；local file sink 有 bounded retention 與 owner-only policy。 | Native Windows/NTFS ACL、junction/reparse replacement、packaged launcher 與 second-account denial仍是平台 acceptance boundary；exact-commit validation 前不能宣稱完整產品 closure。 |
| Native UI lifecycle | Preprocess close/cancel work 已建立 quiesce / restore checkpoint；`tests/integration/ui/test_preprocess_native_lifecycle.py` 和 `tests/integration/ui/test_native_render_lifecycle.py` 分別保護 Preprocess 與 Visualization native ownership。 | 兩個 gate 不互相替代，也不取代 Windows/WSLg、DPI、interactive 3D、real training close 和長時間操作 acceptance。 |
| Packaging | Windows launcher / startup automation 存在。 | 不是 signed installer；release sign-off 與真人 click-through 尚未完成。 |
| MCP | 既有 code、tests、docs 或 artifacts 只算歷史探索 / compatibility evidence。 | MCP 已退出 active product / thesis roadmap。除非使用者明確要求，不做 MCP hardening、adapter certification 或 handoff gate。 |

## Dataset Consolidation Boundary

Canonical local hierarchy 是 `XBRAINLAB_DATA_DIR/datasets/`，下面分成 `source/`、`bids/`、
`public-fixtures/`、`manifests/` 與 `quarantine/`。沒有設定環境變數時，installed product 使用既有
跨平台 application-data default；CI 的 public fixture downloader 仍回退 repo-local cache，保持
乾淨 clone 可重建。Import dialog 只把 canonical root 當作起始位置，使用者仍可選任意外部路徑。

目前 migration contract 只允許 dry-run 與 verified copy。15 個 frozen BIDS corpus 依 dataset-relative
SHA-256 manifest 搬移；public fixtures 只搬 pinned manifest 內的檔案，因此 unverified orphan 不會
混入 canonical root。舊來源、quarantine、download seeds 與 worktree copies 都保留到 automated
validation 加 Windows MI/P300 手測通過；cleanup 必須是另一個明確授權的 checkpoint。

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
- `main` 是產品工作的唯一整合基線；working desktop product foundation 已經合回 `main`。
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
