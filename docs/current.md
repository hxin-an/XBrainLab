# XBrainLab 目前狀態

最後更新：`2026-08-13`

這頁只回答三件事：目前在哪一條整合線、現在能相信什麼、離 handoff 還缺什麼。
短期施工看 [Now](planning/now.md)，驗證規則看
[Validation](validation/README.md)。

## 一句話

XBrainLab 的 product baseline 是 `main`。目前最高優先工作是收斂 15 個固定 MOABB
datasets 的 BIDS / MainWindow reliability candidate：產品碼已有 backend-owned BIDS index、
bounded parsed-content cache、operation ID / cooperative cancellation、重工作的 detached
prepare / short commit 邊界，以及必須由使用者點擊的 `Compute Saliency`。這些仍是
dirty implementation checkpoint；資料尚未完整 materialize，也還沒有 30 個 green journey
receipts、clean exact-commit evidence、exact-head CI 或 Windows 人工驗收。

本輪數量邊界是固定的 15 個 datasets：5 個 anchor datasets 各 5 subjects，其餘 10 個各
2 subjects；每個 dataset 必須用 fresh process 各跑 cold 與 replay，合計 30 條使用者式
GUI journeys。這是本次交付的 fixed denominator，不等於長期約 80 個 MOABB cases，也不與
另一個 20-scenario product gate 混為已通過的 evidence。

## Current Integration Context

| 項目 | Current truth |
| --- | --- |
| Active worktree | 以 `git rev-parse --show-toplevel`、`git branch --show-current` 與 `git status --short --branch` 為準；repo-root `settings.json` 是不得納入版本控制的使用者本機設定。 |
| Product baseline | `main` |
| Current candidate | 依 [Now](planning/now.md) 從最新 `main` 形成的下一個 clean、pushed exact-head commit；實際 branch / SHA 一律從 Git 取得，不寫死在本頁。 |
| Baseline | 以當次 Git 的 `main` / merge-base 為準，不重用舊 SHA。 |
| Active goal | 將固定 15-dataset BIDS bytes、checksums、設定與 30 條 GUI journeys 綁在同一 clean exact commit / Poetry / CUDA identity，全綠後才進入 exact-head CI 與 Windows 人工邊界。 |
| Historical ledger | [Product Quality Audit - 2026-07-30](records/product_quality_audit_2026-07-30.md)；只作 provenance，不是 active queue。 |
| Delivery state | Dirty implementation checkpoint；15/15 仍 awaiting materialization，尚無 30 條 green receipts、pushed exact-head CI / Windows acceptance，不是 handoff-ready 或 release-ready。 |

其他 registered worktree 不代表 active candidate。需要 inventory 時必須執行
`git worktree list --porcelain`，不要把數量或 branch 清單手動複製成長期 current truth。
目前這輪 import / training / montage polish 沒有 exact-SHA handoff dossier；tracked screenshots 與 ignored walkthrough 都只算
checkpoint evidence。

## 目前實作真相

| 區域 | 已存在的 current implementation | 尚未完成的邊界 |
| --- | --- | --- |
| Backend | `ApplicationService / Command API` 是 UI、assistant、headless scripts 共用的 product command spine。`BackendFacade` 與 product live-object payload 已物理移除；五個 product panels 由 narrow ports 建立。目前 candidate 又加入 lock-independent `OwnedWorkRegistry`，用 operation ID、typed kind / phase、stage 與 cooperative checkpoint 管理 import review / apply、preprocess、epoch、training、evaluation、saliency 與 render。 | 這是 source + focused-regression checkpoint，尚未由 30 條真實 GUI journeys 驗證所有 cancel / retry / close interleavings。Standalone/test compatibility constructors 仍是 P2 cleanup；不能宣稱 target architecture fully aligned。 |
| UI | Product state-changing render 以 revisioned application publication 為單一真相；command result 只處理 acknowledgement / error / in-flight feedback，Training progress 只走 transient event。五個 workflow panels 保留舊版固定右側 `Data Summary` 表格，不另設常駐 Readiness 區塊。Assistant header 不顯示額外狀態 badge；狀態保留在 tooltip / accessibility metadata，composer 使用固定 action geometry，訊息 bubble 依 viewport 與內容重排。Source guard 會追蹤 async callback call chain，阻止 command result 重改 Start/Stop、readiness 或 terminal state。 | Dirty integration work 和 focused tests 只是 checkpoint；offscreen 100/125/150% DPI 與窄寬度 artifact 已通過 working-checkpoint review，但在 clean exact-source screenshots、happy path、edge gate 及 reviewer re-gate 完成前，不是 Windows handoff candidate。Standalone compatibility observer path仍是 P2 cleanup。 |
| Data Interpretation | `scan -> preview -> validate -> apply -> recipe` baseline 存在。Strict BIDS 現在由 immutable、bounded `BidsDatasetIndex` 統一 nested-root resolution、subject catalog、recordings、events / channels / electrode / coordinate / JSON sidecars 與 completeness；selected-subject projection 供 scan / review / apply / montage 重用。JSON / delimited sidecar parsing 以完整 bytes SHA-256、parser ID 與 schema version 綁定 bounded immutable cache，Windows 不以 `ctime` 作內容捷徑。 | Index / cache 只是已實作的 discovery 與讀取邊界，不是 full BIDS inheritance / validator 或任意 dataset 語意支援。15 個 campaign datasets 仍未完成 materialization 與 GUI acceptance；目前真人資料主張仍只限 Graz 2a GDF 與 OpenNeuro ds003061 P300 BIDS。 |
| Epoch / split / training contract candidate | Epoch context 只接受 reviewed import handoff 與每段 recording 的 matching timing hints；缺少、格式錯誤、讀取失敗、source / placement 不一致，或 selected recordings 的 sampling frequency 不一致時 fail closed，且不改變既有資料；將所有 recordings resample 到同一 sampling frequency 後會重新取得 `Create Epoch` readiness。Duration / event-locked mode 由這份 reviewed handoff 綁定的 event placement 與 duration evidence 產生，不由 dialog 猜測。Split preview 會暫時建立 candidate datasets / masks 以產生摘要，完成後恢復原狀；Confirm 只保存 typed split specification、epoch revision、fingerprint 與 bounded preview summary，`Start Training` 才做 authoritative rematerialization、audit 與 publication。Training Setting 提供 deterministic starting recommendations，並逐欄位保存 trusted user edit 的 manual provenance。 | 這些是 dirty working candidate 正在收斂的 contract，尚未有 clean exact-head CI / Windows acceptance。Split Confirm 不代表 training tensors 或 masks 已發布；recommendations 不是最佳參數、AutoML 或 timed hyperparameter search。 |
| EEG workflow baseline / current polish | BIDS subject selection、curated Braindecode catalog、test curve、cross-fold summary 與 detached Saliency Normalize 已進入 `main`。目前 candidate 的 training completion 只發布 metrics；只有明確點擊 visible `Compute Saliency` 才排程 attribution。Evaluation / Saliency / Normalize / render 有 operation identity 與 stale-result guard。 | 這不代表所有 curated models 可用、scientific model quality 或 native 3D 驗收。Map 與 Spectrogram 目前只有 source / focused test checkpoint，還沒有 15-dataset exact-source screenshots。 |
| MOABB campaign tooling | Tracked plan 固定 15 個 datasets / subjects、EDF + BrainVision + EEGLAB（及一個 formal BDF mirror）、cold + replay、5/5/5 cancellation 分區、1 epoch / repeat / fold、Evaluation、explicit Saliency、Map、Spectrogram 與 clean close。Materializer 預設不下載；GUI driver 只在 `QFileDialog` 注入 path，其餘點擊 visible + enabled production controls。 | Tracked GUI plan 的 15 列目前全是 `awaiting_dataset_materialization`，`bids.root=null`。沒有 ready/freeze manifest 或 green receipts；runner contract / unit tests 不是真實資料成功。 |
| Assistant | Local-only Assistant、IBM Granite 3.3 2B 選項、tool admission、capability、typed confirmation、decision owner、verification 和 structured result 的工程骨架存在；ApplicationService 仍控制最後 command admission。Standalone debug host 已和 product runtime 對齊 high-impact setting confirmation，walkthrough 也會區分 confirmation card 與 GUI handoff。 | Assistant 目前尚未準備好給老師使用。同一 request 仍可能向 Granite 2B 暴露多個競爭 tool schemas；現有 deterministic walkthrough 不是 real Granite tool-call accuracy、長時間使用或 Windows acceptance。 |
| Privacy / diagnostics | Centralized public diagnostics 會從 default logs、public command/result projection、assistant feedback 和 UI interaction outcome 移除完整私人路徑、常見 subject identifiers 與不安全 control characters；local file sink 有 bounded retention 與 owner-only policy。 | Native Windows/NTFS ACL、junction/reparse replacement、packaged launcher 與 second-account denial仍是平台 acceptance boundary；exact-commit validation 前不能宣稱完整產品 closure。 |
| Native UI lifecycle | Preprocess close/cancel work 已建立 quiesce / restore checkpoint；`tests/integration/ui/test_preprocess_native_lifecycle.py` 和 `tests/integration/ui/test_native_render_lifecycle.py` 分別保護 Preprocess 與 Visualization native ownership。 | 兩個 gate 不互相替代，也不取代 Windows/WSLg、DPI、interactive 3D、real training close 和長時間操作 acceptance。 |
| Packaging | Windows launcher / startup automation 存在。 | 不是 signed installer；release sign-off 與真人 click-through 尚未完成。 |
| MCP | 既有 code、tests、docs 或 artifacts 只算歷史探索 / compatibility evidence。 | MCP 已退出 active product / thesis roadmap。除非使用者明確要求，不做 MCP hardening、adapter certification 或 handoff gate。 |

## Main Checkpoint Boundary

這次合併到 `main` 是使用者明確接受的開發基線收斂，不是 release acceptance。合併理由是
避免後續修復繼續分散在長期 stabilization branch；它不會把尚未完成的 Assistant、效能或
格式支援自動提升成完成。

後續至少要：

1. 收斂 backend BIDS / cache / owned-work / cancellation 與 GUI visible-control route，並關閉
   same-class regression。
2. 在 D 槽 materialize 固定 15-dataset bytes，完成 formal BIDS validator、source / BIDS
   checksums、license / provenance 與 ready plan。
3. 用同一 clean exact commit / Poetry / CUDA identity 串行跑完 30 條 fresh-process
   MainWindow journeys；任一失敗都不交付。
4. 主 agent 逐圖審查 artifacts，完成與 exact plan / receipt / screenshot SHA 綁定的獨立 visual-review attestation，再跑 canonical handoff gates、push 與 exact-head CI。
5. 只有上述全部關閉後才能形成 Windows 人工驗收候選；performance 與 simplified Assistant
   仍是後續工作。

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
- 15-dataset materializer / GUI campaign 的 fail-closed contract 與 runner source 已存在，但仍是
  pending execution checkpoint。

## 不能宣稱

- 目前是 release、product-complete 或 Assistant-ready candidate。
- 所有 GDF、所有 BIDS 或 full BIDS validator 已通過真人驗收。
- 任一舊 dashboard、walkthrough、reviewer verdict 或手動 test total 代表 current branch。
- 15 個 MOABB datasets 已 materialize、30 條 journeys 已通過，或目前已可供手測。
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
