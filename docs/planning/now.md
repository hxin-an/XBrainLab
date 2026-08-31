# XBrainLab Now

最後更新：`2026-09-01`

## Current baseline and release decision

`76ca41a81ba62cff965cf75991d2e6c53cc13644` 是本次 plan 的 product parent baseline。PR #94 已關閉
Basedpyright 假綠，PR #96 已建立 Desktop source release profile；PR #97、#99、#100、#102 與 #103
累計清除 46 項型別 diagnostics，把全案真實基準由 67 降為 21。舊 release candidate PR #91 的
source、artifact 與 manual acceptance 仍為失效歷史，不得重用。
Repo-root `settings.json` 的本機修改由使用者擁有，不得 stage、commit、revert、覆寫或隱藏。

使用者於 `2026-08-31` 決定下一個版本為 **v0.9.0 Desktop Core Stable source release**：同一 candidate
必須完成人工 Windows Python native 與 WSLg 驗收；沒有 signed installer。Local Assistant 隨產品提供但
維持 **bounded preview**，不宣稱 Assistant Stable promotion。中文輸入不屬於本次 release blocker。

## Active program — v0.9.0 stable source convergence

### Evidence and blockers

1. 完整 Poetry 3.12 環境如實分析 416 個 production files；PR #103 後仍有 `21 diagnostics`。
   Fake-green 已關閉，但真實 type debt 尚未清零，Basedpyright 也還未接入現有 full-dependency
   CI job，所以 release gate 仍不可宣稱通過。
2. PR #96 的 canonical `desktop-source` profile 已進入 main：Desktop 核心 gate 保持完整，bounded
   Assistant 固定 Granite 4.0 Micro 與 81-case inventory，並明示
   `assistant_stable_promotion=false`。目前結果仍只支持 bounded preview，不可宣稱
   Assistant Stable promotion。
3. PR #91 的 0.9.0 version／release truth 變更尚未進入 main。必須先將真實 diagnostics 清零、將
   deterministic runner 接入 CI，再從新的 fixed main 建立全新 candidate。

### Outcomes

- Basedpyright runner 在 dependency type information 不可解析時 fail closed；完整依賴環境及 CI 結果一致。
- 正確環境中剩餘的 21 diagnostics 經分群修正或精確、可審查的第三方 stub boundary 收斂到 zero observed
  diagnostics；不得擴大 exclude 或把整批 debt 寫入 baseline。
- 既有 canonical handoff runner 新增唯一命名的 `desktop-source` release profile；無參數 strict 行為維持
  不變，不建立第二套 manifest 或任意 skip list。
- Desktop profile 跑全部核心產品 gate，並以 case-level no-regression 的 bounded Assistant gate取代
  strict promotion gate；artifact 必須明示 `assistant_stable_promotion=false`。
- 所有 prerequisite 進 main 後，才建立新 `release/v0.9.0-source-baseline-v2`、同步 0.9.0 identity、跑
  exact-source automated dossier，再交同一 SHA 的 Windows native／WSLg 真人驗收。

### Scope, ownership, and complexity

- **Root coordinator** 是唯一 plan、branch／worktree、scope、merge order、exact SHA、artifact、manual
  acceptance 與 release owner。
- **Validation worker** 只負責 Basedpyright resolver probe、runner/tests 與按 subsystem 分片的 diagnostics。
- **Release-contract worker** 只負責 handoff profile、bounded evaluator result contract、tests 與 canonical
  claim docs；不得修改 product Assistant tool、prompt、Host admission 或 runtime behavior。
- **Independent reviewer** 在每個 frozen slice 後審 diff、test quality、claim boundary 與 complexity；不在
  受審 branch 補功能。最多兩個互不重疊 worker，不派重複 reviewer。
- Basedpyright debt 跨過 8 個 production files，必須拆成每 PR 不超過 8 個 production files的 data／
  preprocess、training／model、UI／plot 等 slices。每個 slice owner delta `0`，優先 narrowing、runtime
  guard、正確 import 或 deletion；不得新增 owner、state machine、receipt 或 compatibility path。
- Validation／release-profile production delta 預計限於既有 `scripts/dev` commands，product runtime
  delta `0`。若任一 pure refactor 淨增超過 100 production LOC 或 owner 增加，停止並做 complexity review。
- 使用者已明確批准計畫中 **type-only、無可見行為變更** 的 `XBrainLab/ui/` 修正；若需要改 layout、文案、
  互動、狀態或流程，立即停止並另取 UI 確認。

### Current slice E — UI and plot type boundaries

- **Problem and evidence**：剩餘 21 項中有 20 項集中於
  `modal_presentation.py`、`single_plot_window.py`、`data_splitting_preview_dialog.py`、
  `training_setting_dialog.py`、`preprocess/preview_widget.py` 與 `base_saliency_view.py`。分布為
  optional Qt access 3 項、Matplotlib private re-export 1 項、training numeric narrowing 1 項、
  PyQtGraph public／private boundary 14 項與 Figure metadata 1 項；直接 UI baseline 為 192 passed。
- **Outcome**：用 Qt local narrowing、Matplotlib public import、現有 `TrainingOption` 所需的 `float` boundary、
  PyQtGraph public `PlotItem`／`ViewBox` API 與實際 `QEvent.Leave` event filter，取代 private field 與
  `leaveEvent` monkey-patch；Figure metadata 僅把 dotted assignment 改成同一 Figure 上的 `setattr`。
  六檔 20→0，全案 observed count 由 21 降為 1。
- **Scope／non-goals**：只改上述 6 個 production files與兩個直接 leave-event tests；不改 layout、文案、
  icon、crosshair outcome、plot bounds、dataset split flow、class-weight validation結果、saliency margin計算、
  public API 或 backend state。不新增 screenshot、source guard、compatibility path或泛用 UI abstraction。
- **Ownership／deletion**：六個既有 dialog／view owners 不變，delta `0`；刪除兩組 monkey-patch closures／
  stored handlers，復用 QObject event filter與既有 plot owners。不建立 `WeakKeyDictionary`、global cache或第二套
  metadata policy。預期 production net LOC 介於 -10 至 +20。
- **Repair and validation**：先保留 192-test baseline；把兩個直接呼叫 monkey-patched handler 的弱測試改為
  發送真實 `QEvent.Leave`，分別確認 time／frequency 的水平線、垂直線與 tooltip label 都隱藏且 event 不被
  消耗。再跑同一 focused suite、六檔 Ruff、
  完整外部 Basedpyright 21→1、frozen-SHA review、PR CI與既有 Windows／macOS／Linux UI lifecycle gates。
- **Stop／UI status**：若 icon／geometry／copy、crosshair ordering或 native `leaveEvent`、invalid class-weight
  feedback、plot item ownership／teardown、saliency resize recovery有任何可見或互動差異，立即停止並另取 UI
  確認。使用者已批准本計畫中的 type-only、無可見行為 UI 修改；本 slice 不授權產品 redesign。

### Deferred behavior bug — artifact key `allow_pickle`

`backend/training/record/artifact_store.py` 的 1 項 diagnostic 對應真實 persistence defect：NumPy 將
`allow_pickle` 視為 `np.savez_compressed` 的 control argument，而不是 array key；目前 GUI 的固定 key vocabulary
不會產生此名稱，但 direct internal caller 會得到「寫入成功、讀回 integrity failure」的自相矛盾 artifact。
這不能用 suppression 消掉；待 slice E 完成後另開 bug-fix plan，只復用現有 key validation 提前拒絕
`allow_pickle`，不建立 reserved-name registry，並要求原子 side-effect test 與使用者批准。

## Progression and focused validation

1. **Current plan checkpoint**：合併本 canonical plan，再從 fixed main 建立單一 slice E worktree；一個 worker
   實作，root 重跑 focused／external gates，同一 independent reviewer 只在 frozen commit 後審查。
2. **Slice E exact validation**：保留 192-test baseline並強化兩個真實 Leave events；跑 external full
   Basedpyright、Ruff、diff、frozen-SHA review與 PR CI。observed count 必須由 21 精確降為 1，不可有 UI delta。
3. **Final behavior debt**：另開 plan與短 PR，只修 artifact `allow_pickle` 的已證明 silent inconsistency；
   以 atomic failure test與使用者批准收斂最後 1 項，external observed count 必須為 0。
4. **CI closure**：diagnostics 清零後，將 deterministic Basedpyright runner 接入現有 full-dependency job；不建立
   第二套 CI truth。
5. **Fresh candidate**：重建 0.9.0 identity／docs，clean、push、freeze exact SHA，以 D-mounted model／RAG
   caches及offline Granite跑 `desktop-source` canonical manifest；所有 non-skipped CI completed/success。
6. **Manual acceptance**：Windows native完成 startup、PhysioNet核心 workflow、BIDS／GDF import spot checks、
   recipe reload、四種 Saliency view、Spectrogram 四條重現與 3D time；WSLg完成 launcher、model settings、
   bounded Assistant及 Spectrogram＋Assistant interaction。兩邊完整 SHA 必須相同。

## Stop conditions

- 任一 prerequisite source變更未經 focused test／review／PR，不建立 release candidate。
- Basedpyright fake green、external diagnostics非零、bounded Assistant出現任何新的 case failure、required gate
  missing／pending／stale／failed，或 exact-source dossier不完整，皆為 checkpoint。
- 真人發現 crash、資料損失、重複 execution、錯誤 workflow mutation、import/review不一致、recipe reload
  失敗、visual overlap、modal trap或無限 checking，立即關閉 candidate；另開短修復 PR 回 main 後重建。
- 只有同一 frozen candidate 的 desktop-source dossier、Windows native、WSLg、PR CI 與使用者明確手測通過／
  merge同意全部閉合，才 merge。Merge tree必須等於已測 candidate tree，之後才建立 immutable annotated
  `v0.9.0` tag與 GitHub source release；缺陷以 revert／`v0.9.1` 處理，不移動 tag。
