# XBrainLab Now

最後更新：`2026-08-31`

## Current baseline and release decision

`main` 與 `origin/main` 在本計畫開始時同為
`c339884a611b18c6ac3e4582760d7aa518ab51ba`。PR #92 的 Saliency Spectrogram 修復已由使用者手測通過並
合併；舊 release candidate PR #91 的 source、artifact 與 manual acceptance 仍為失效歷史，不得重用。
Repo-root `settings.json` 的本機修改由使用者擁有，不得 stage、commit、revert、覆寫或隱藏。

使用者於 `2026-08-31` 決定下一個版本為 **v0.9.0 Desktop Core Stable source release**：同一 candidate
必須完成人工 Windows Python native 與 WSLg 驗收；沒有 signed installer。Local Assistant 隨產品提供但
維持 **bounded preview**，不宣稱 Assistant Stable promotion。中文輸入不屬於本次 release blocker。

## Active program — v0.9.0 stable source convergence

### Evidence and blockers

1. PR #94 已在 `main` 的 `f456acb7` 讓 Basedpyright runner 於依賴型別不可解析時 fail closed；完整
   Poetry 3.12 環境仍如實分析 416 個 production files 並回報 `67 diagnostics`。假綠路徑已關閉，但真正
   type debt 尚未清零，所以 gate 仍不可宣稱通過。
2. Canonical handoff manifest 目前只表示包含 Assistant strict promotion 的單一 required set；Granite 3B
   已驗收基準仍是 36/36 positive、10/10 explicit parameter origin、5/5 missing guard、22/24 product
   no-action、6/7 clarification。這可支持 bounded preview，不可被改寫為 24/24、7/7 Stable promotion。
3. PR #91 的 0.9.0 version／release truth 變更尚未進入 main。必須先閉合上述 prerequisite，再從新的
   fixed main 建立全新 candidate。

### Outcomes

- Basedpyright runner 在 dependency type information 不可解析時 fail closed；完整依賴環境及 CI 結果一致。
- 正確環境中的 67 diagnostics 經分群修正或精確、可審查的第三方 stub boundary 收斂到 zero observed
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

### Current slice — MNE Raw／Epochs type narrowing

- **Problem and evidence**：`backend/load_data/raw.py` 有 9 項、`backend/preprocessor/resample.py` 有 8 項
  diagnostics；原因是 `is_raw()` 無法替 static analyzer 收窄 `BaseRaw | BaseEpochs`，以及 MNE resample
  stub 對回傳聯集與 `events=None` 的保守描述。完整依賴環境的 focused count 是 17；直接相關的 Raw、
  resample、preprocess及controller characterization 共 70 tests passed。
- **Outcome**：在不改 runtime observable behavior 的前提下，以 concrete `isinstance` branch 與 MNE public
  in-place resample API 將這兩檔收斂為 0 diagnostics；保留 raw event sample scaling、epoch event wipe、
  finite-data guard、publication與error semantics。
- **Scope／non-goals**：只改上述 2 個 production files與直接必要測試；不改 ApplicationService／controller、
  UI、文案、資料流程、public API、其他 type debt或 baseline。不得使用 `Any`、broad cast／ignore、private MNE
  API、compatibility path或新 abstraction。
- **Ownership／deletion**：owner before／after皆為既有 Raw data wrapper與Resample processor，delta `0`；刪除
  重複 resample comment與不必要的 `events=None`，復用既有 `set_mne`、`set_mne_and_wipe_events`及event setter。
  預估 production delta約等量替換，遠低於 pure-refactor complexity trigger。
- **Repair and validation**：先保留同一70-test passing baseline，再做 concrete narrowing；重跑完全相同測試、
  完整外部 Basedpyright（兩檔 17→0、全案 67→50）、兩檔 Ruff與diff check。MNE／Qt相關測試使用明確 timeout、
  `prlimit --core=0`、`MNE_DONTWRITE_HOME=true`與暫存config目錄。
- **Stop／UI status**：若需要型別掩蓋、private API、行為或owner變更即停止；只有17項全消失且70-test baseline
  不退步才 scope-complete。這是使用者已批准的 non-UI type-only slice，沒有可見 UI 變更；不需新增 screenshot。

## Progression and focused validation

1. **Plan checkpoint**：先合併本 canonical plan；之後才建立兩條 prerequisite worktree。
2. **Basedpyright determinism**：先建立 observable fake-green red test／dependency-resolution probe，再修 runner；
   在 fresh process、完整 Poetry 3.12 env 與 CI 各連跑兩次。Sandbox 無 dependency types 時必須明確失敗。
3. **Type debt slices**：保留或新增直接 runtime characterization；每片修後跑 focused tests、external full
   Basedpyright、Ruff、architecture及受影響 subsystem tests。第三方 stub mismatch 只允許精確行級
   suppression並附 runtime evidence；最終 external observed count 必須為 0。
4. **Release evidence contract**：test-first證明 default profile仍使用 strict 24/24、7/7；desktop profile
   不能任意漏 gate，bounded report必須 exact model/revision、81/81 complete，且 PR #71 所有 passed case
   不得退步。三個已知失敗可維持或改善，不能換成新失敗。
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
