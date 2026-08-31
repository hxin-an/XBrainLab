# XBrainLab Now

最後更新：`2026-09-01`

## Current baseline and release decision

`54ca582aa63f96f9fdd395c6e761c96ff038e297` 是本次 plan 的 product parent baseline。PR #94 已關閉
Basedpyright 假綠，PR #96 已建立 Desktop source release profile，PR #97 已將 MNE Raw／Epochs
17 項型別 diagnostics 清零並把全案真實基準由 67 降為 50。舊 release candidate PR #91 的
source、artifact 與 manual acceptance 仍為失效歷史，不得重用。
Repo-root `settings.json` 的本機修改由使用者擁有，不得 stage、commit、revert、覆寫或隱藏。

使用者於 `2026-08-31` 決定下一個版本為 **v0.9.0 Desktop Core Stable source release**：同一 candidate
必須完成人工 Windows Python native 與 WSLg 驗收；沒有 signed installer。Local Assistant 隨產品提供但
維持 **bounded preview**，不宣稱 Assistant Stable promotion。中文輸入不屬於本次 release blocker。

## Active program — v0.9.0 stable source convergence

### Evidence and blockers

1. 完整 Poetry 3.12 環境如實分析 416 個 production files；PR #97 後仍有 `50 diagnostics`。
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
- 正確環境中剩餘的 50 diagnostics 經分群修正或精確、可審查的第三方 stub boundary 收斂到 zero observed
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

### Current slice A — evaluation metrics type narrowing

- **Problem and evidence**：`backend/training/record/eval.py` 有 7 項 sklearn typing diagnostics；目前 production
  同時由 `precision_recall_fscore_support` 與既有 confusion matrix 推導同一組 metrics，但現有測試只覆蓋兩組
  一般輸入，沒有缺 class 的真實邊界。
- **Outcome**：復用現有 `calculate_confusion` 導出 per-class precision／recall／F1／support 與 macro，保留
  fixed class labels 和 `zero_division=0` 的輸出語意；單檔 7→0，全案從 50 獨立降為 43。
- **Scope／non-goals**：只改 `eval.py` 與直接 metrics test；不改 training workflow、UI、public schema、
  metric key／shape／value contract，也不混入 artifact persistence bug。不使用 broad cast、`Any`或 ignore。
- **Ownership／deletion**：owner before／after皆是既有 evaluation record，delta `0`；刪除重複 sklearn metric
  derivation，不新增 abstraction。預期 production net LOC 非正或接近零。
- **Repair and validation**：先保留現有 metrics passing baseline，新增 3-class 但只出現 class 0 的
  observable test，再復用 confusion matrix；跑 focused tests、相關 training record tests、完整外部
  Basedpyright、Ruff與diff check。
- **Stop／UI status**：若任一現有 metric 值／shape／missing-class 語意變更或需要新 owner 即停止。
  這是 non-UI type-only slice，無可見行為與 screenshot。

### Current slice B — third-party boundary cleanup

- **Problem and evidence**：`evaluation_render.py`、`visualization_controller.py`、`saliency_3d_engine.py`與
  `llm/core/downloader.py` 合計 5 項 diagnostics，分別來自 torchinfo、無法到達的 dict reconstruction、
  PyVista return type 與 Hugging Face private re-export import。現有 focused baseline 共 114 tests passed。
- **Outcome**：用最小 precise cast／public import／return annotation／刪除 impossible branch 表達現有 runtime
  contract；四檔 5→0，全案從 50 獨立降為 45，與 slice A 合併後預期 38。
- **Scope／non-goals**：只改上述 4 個 production files與直接必要 characterization；不改 evaluation／
  visualization／saliency／download 行為、UI、文案或 public API，不建立 compatibility path。
- **Ownership／deletion**：四個既有 owner 不變，delta `0`；刪除 `EvalRecord.output` 不可達的 dict
  重建邏輯，其餘僅為第三方 boundary 精確化。預期 production net LOC 介於 -2 至 +5。
- **Repair and validation**：以真實 `EvalRecord` 新增 independent-copy characterization，保留同一 114-test
  baseline，並跑完整外部 Basedpyright、四檔 Ruff與diff check。只有已驗證 public runtime API 才能使用。
- **Stop／UI status**：若需要 broad ignore／cast、第二套 output policy、行為或 owner 變更即停止。這是
  non-UI type-only slice，無可見行為與 screenshot。

### Deferred behavior bug — artifact key `allow_pickle`

`backend/training/record/artifact_store.py` 的 1 項 diagnostic 對應真實 persistence defect：NumPy 將
`allow_pickle` 視為 `np.savez_compressed` 的 control argument，而不是 array key。這不能在 type-only slice
裡用 suppression 消掉；待 A／B 完成後另開 bug-fix plan，提前拒絕該 reserved name，並要求續寫等
真實 side-effect test 與使用者手測批准。

## Progression and focused validation

1. **Current plan checkpoint**：合併本 canonical plan，再從同一 fixed main 建立 A／B 兩條互不重疊
   worktree；兩個 worker 各自實作，同一 independent reviewer 只在 frozen commit 後審查。
2. **A／B exact validation**：每片各自保留 passing baseline，只新增能使真實 defect 可觀察的 test；各自
   跑 focused tests、external full Basedpyright、Ruff、diff、review 與 PR CI。兩片合併後重跑全案，
   observed count 必須由 50 精確降為 38，不可有新 diagnostic。
3. **Remaining type debt**：依 8-file 上限繼續分為 model loop、training setup、UI／plot；最後單獨處理
   artifact behavior bug。第三方 stub mismatch 只允許已有 runtime evidence 的精確行級 suppression，最終
   external observed count 必須為 0。
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
