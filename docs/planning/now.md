# XBrainLab Now

最後更新：`2026-09-01`

## Current baseline and release decision

`e9e28d19784231bd73cc18cbc15b9d3b060fb738` 是本次 plan 的 product parent baseline。PR #94 已關閉
Basedpyright 假綠，PR #96 已建立 Desktop source release profile；PR #97、#99、#100、#102、#103 與 #105
累計清除 66 項型別 diagnostics，把全案真實基準由 67 降為 1。舊 release candidate PR #91 的
source、artifact 與 manual acceptance 仍為失效歷史，不得重用。
Repo-root `settings.json` 的本機修改由使用者擁有，不得 stage、commit、revert、覆寫或隱藏。

使用者於 `2026-08-31` 決定下一個版本為 **v0.9.0 Desktop Core Stable source release**：同一 candidate
必須完成人工 Windows Python native 與 WSLg 驗收；沒有 signed installer。Local Assistant 隨產品提供但
維持 **bounded preview**，不宣稱 Assistant Stable promotion。中文輸入不屬於本次 release blocker。

## Active program — v0.9.0 stable source convergence

### Evidence and blockers

1. 完整 Poetry 3.12 環境如實分析 416 個 production files；PR #105 後仍有 `1 diagnostic`。
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
- 正確環境中剩餘的 1 diagnostic 經可觀察的 behavior fix 收斂到 zero observed
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

### Current slice F — reject the NumPy `allow_pickle` control key

- **Problem and evidence**：`backend/training/record/artifact_store.py` 的最後 1 項 `reportArgumentType` 對應真實
  persistence defect。鎖定的 NumPy `2.5.2` 將 `allow_pickle` 視為 `np.savez_compressed` control argument；
  `write_json_npz_artifact(arrays={"allow_pickle": ...})` 目前回報寫入成功，但 NPZ 丟失該 array、manifest仍記錄
  該 key，第一次讀回即以 `ArtifactIntegrityError` 失敗。現有 GUI／TrainRecord／EvalRecord 使用固定 key
  vocabulary，不會產生此名稱；缺陷只在 direct internal writer caller 可達。
- **Outcome**：復用 writer 現有 per-key validation，在任何 directory／temporary／manifest／NPZ mutation 前，
  以既有 `ArtifactStoreError` 拒絕精確名稱 `allow_pickle`。NumPy `2.5.2` 的 public stub 無法表達
  「dynamic `**kwargs` 已排除此 control key」，因此只在已受該 validation 保護的
  `np.savez_compressed` call 抑制精確 `reportArgumentType`。單檔 1→0，全案 observed count 由 1 降為 0。
- **Scope／non-goals**：implementation 只改 `artifact_store.py` 與 `test_safe_artifact_store.py`，另同步本 active
  plan 的實測 blocker；不改 schema、reader、hash、
  atomic replace、directory identity、production writer key vocabulary、UI 或 public artifact shape。不建立
  reserved-name registry，不順手處理會立即 TypeError且不發布 artifact的 `file` key，也不新增 compatibility path。
  不准 `Any`、callable cast、wrapper、private NumPy API、file-level ignore 或其他 diagnostic suppression。
- **Ownership／deletion**：既有 artifact store仍是唯一 persistence owner，delta `0`；在既有 invalid-name條件
  增加一個 proven collision，並在同一 external stub boundary 保留一個 rule-specific line ignore；沒有新
  helper／class／state。預期 production net LOC 介於 0 至 +8（主要是既有條件的可讀性換行）。
- **Repair and validation**：先新增一個 side-effect test，證明舊版不拒絕且發布自相矛盾檔案；修正後要求
  `ArtifactStoreError` 且 manifest／NPZ皆不存在。跑完整 safe-artifact focused suite、相關 record exports、Ruff、
  完整外部 Basedpyright 1→0、frozen-SHA review與 PR CI。紅測已證明舊版沒有 raise；runtime condition 後
  45 項 artifact／record tests通過，但 analyzer仍保守假設 dynamic dict可能含 control key，因而校準上述邊界；
  加入 exact-rule boundary 後，root 獨立重跑同 45 項皆通過，完整 416 files 為 0 diagnostics。
- **Stop／manual status**：若修正需要新 policy owner、泛用 key framework、schema／normal product writer變更，
  或超出單一既有 validation condition與一個 exact-rule call-site ignore即停止。這是 non-UI internal behavior fix，
  沒有有意義的 click-through；frozen SHA 必須以 automated side-effect evidence交使用者明確批准，批准前不 merge。

## Progression and focused validation

1. **Current plan checkpoint**：合併本 canonical plan，再從 fixed main 建立單一 slice F worktree；一個 worker
   實作，root 重跑 focused／external gates，同一 independent reviewer 只在 frozen commit 後審查。
2. **Slice F exact validation**：執行 failing characterization → 單一 validation condition → rule-specific NumPy
   stub boundary → passing artifact／record suites；跑 external full Basedpyright、Ruff、diff、frozen-SHA review與
   PR CI，使用者批准後才 merge。observed count 必須由 1 精確降為 0，不可擴張 key policy。
3. **Zero-debt checkpoint**：slice F 合併後從 clean main重跑 deterministic external analyzer與 dependency probe；
   zero observed diagnostics只代表 type gate閉合，不自動宣稱產品 release-ready。
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
