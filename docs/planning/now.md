# XBrainLab Now

最後更新：`2026-09-01`

## Current baseline and release decision

`a426ad90e0fb153b5b847042301b7e8d78a65823` 是本次 plan 的 product parent baseline。PR #107 在
`79708a0eea1bc7b640c6cbd5b3fc10db8f75530b` 已通過 automated CI，但仍等待使用者批准；Windows native
手測在該 source 發現兩個與 PR #107 diff 無關的可見 blocker，因此這份 candidate 不能作為穩定版驗收來源。
舊 release candidate PR #91 的 source、artifact 與 manual acceptance 仍為失效歷史，不得重用。
Repo-root `settings.json` 的本機修改由使用者擁有，不得 stage、commit、revert、覆寫或隱藏。

使用者於 `2026-08-31` 決定下一個版本為 **v0.9.0 Desktop Core Stable source release**：同一 candidate
必須完成人工 Windows Python native 與 WSLg 驗收；沒有 signed installer。Local Assistant 隨產品提供但
維持 **bounded preview**，不宣稱 Assistant Stable promotion。中文輸入不屬於本次 release blocker。

## Active program — v0.9.0 stable source convergence

### Evidence and blockers

1. PR #107 已將最後一項真實 Basedpyright defect 收斂到 observed zero diagnostics；該 PR 仍須獨立批准與
   merge，且不吸收本次 UI 修正。
2. PR #96 的 canonical `desktop-source` profile 已進入 main：Desktop 核心 gate 保持完整，bounded
   Assistant 固定 Granite 4.0 Micro 與 81-case inventory，並明示
   `assistant_stable_promotion=false`。目前結果仍只支持 bounded preview，不可宣稱
   Assistant Stable promotion。
3. PR #91 的 0.9.0 version／release truth 變更尚未進入 main。必須先將真實 diagnostics 清零、將
   deterministic runner 接入 CI，再從新的 fixed main 建立全新 candidate。
4. Windows native Training Settings 的 `Set` 右框與垂直 scrollbar 視覺間距不足；同 source 的 WSLg
   未呈現相同問題。使用者已明確批准略為加寬對話框與增加平台中性的右側 gutter。
5. 3D XYZ 首次 render 正常，但使用者在 Windows native 觀察到 VRAM error／warning 後指示器移到中央遮住頭部。
   現有 `add_camera_orientation_widget()` 沒有 explicit viewport，因此錯誤提示後的 layout／repaint 或 renderer
   recovery 都沒有固定位置 contract；尚無證據把根因限定為其中一條 lifecycle。使用者已批准改為固定右上角、
   不可點擊的方向指示器。

### Outcomes

- Basedpyright runner 在 dependency type information 不可解析時 fail closed；完整依賴環境及 CI 結果一致。
- PR #107 維持獨立的 artifact safety change；本次 UI PR 不重寫其 scope 或 evidence。
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
- 使用者已明確批准本 slice 的兩項可見 UI 變更：Training Settings 寬度／右側間距，以及 3D XYZ 固定右上角
  且不可點擊。除此以外的 layout、文案、互動、狀態或流程不在授權內。

### Current slice G — Windows Training Settings and recovered 3D parity

- **Outcome**：Training Settings 至少 664 logical px，內容右側 gutter 30 px，scrollbar 仍貼齊 window edge，
  `Set` 到 scrollbar 至少 30 px；3D 使用 `add_axes(interactive=False)` 與 explicit normalized viewport
  `(0.81, 0.80, 0.97, 0.96)`，初始 render、VRAM 提示後及可重現的 renderer retry 後都固定右上角。
- **Scope／non-goals**：只改既有 Training dialog 與 3D head renderer owner及直接測試／capture；不改 VRAM
  warning policy、interactor teardown、camera center、mesh、scalar bar、training behavior、PyVista／VTK版本或 public API。
- **Ownership／complexity**：兩個既有 UI owner不變；不新增 module、owner、state、receipt、platform branch或
  resize lifecycle。兩個互不重疊 worker各產生一個 focused commit，root整合到單一 PR，frozen後由獨立 reviewer審查。
- **Repair and validation**：兩條線皆先建立最小 failing observable guard。Training跑100／125／150%與wide
  scrollbar geometry；3D automated test精確驗證 repeated render皆建立單一固定 viewport marker，Windows native
  walkthrough另依實際順序驗證首次正常→觸發VRAM提示／錯誤→關閉或恢復後仍在右上角。Ruff、focused Qt suites與
  exact-source screenshots通過後，Windows native與WSLg同SHA手測；automated mock不取代native錯誤路徑證據。
- **Stop／manual status**：若需要修改 VRAM admission、建立第二個 renderer owner、升級VTK，或 native recovery後
  marker仍不固定即停止。這是可見產品行為，使用者對 frozen SHA 明確手測通過並同意 merge 前不得合併。

## Progression and focused validation

1. **Current slice**：Training與3D worker在獨立worktree完成RED→GREEN；root只整合兩個focused commits，
   檢查production files／LOC／owner delta並凍結exact SHA。
2. **Slice G validation**：跑focused Qt suites、Ruff、UI capture與Windows native recovery walkthrough；independent
   reviewer審行為、測試品質、scope與claim boundary，PR CI及使用者批准後才 merge。
3. **PR #107 closure**：artifact fix維持獨立PR與批准，不以本次UI手測替代其source evidence。
4. **CI closure**：PR #107 合併後，將 deterministic Basedpyright runner 接入現有 full-dependency job；不建立
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
