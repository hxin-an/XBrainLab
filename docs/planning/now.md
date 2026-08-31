# XBrainLab Now

最後更新：`2026-09-01`

## Current baseline and release decision

`f37e40e774f17e135416899da6bfb565312ed2e9` 是本次 plan 的 product parent baseline。PR #94 已關閉
Basedpyright 假綠，PR #96 已建立 Desktop source release profile；PR #97、#99 與 #100 累計清除
29 項型別 diagnostics，把全案真實基準由 67 降為 38。舊 release candidate PR #91 的
source、artifact 與 manual acceptance 仍為失效歷史，不得重用。
Repo-root `settings.json` 的本機修改由使用者擁有，不得 stage、commit、revert、覆寫或隱藏。

使用者於 `2026-08-31` 決定下一個版本為 **v0.9.0 Desktop Core Stable source release**：同一 candidate
必須完成人工 Windows Python native 與 WSLg 驗收；沒有 signed installer。Local Assistant 隨產品提供但
維持 **bounded preview**，不宣稱 Assistant Stable promotion。中文輸入不屬於本次 release blocker。

## Active program — v0.9.0 stable source convergence

### Evidence and blockers

1. 完整 Poetry 3.12 環境如實分析 416 個 production files；PR #100 後仍有 `38 diagnostics`。
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
- 正確環境中剩餘的 38 diagnostics 經分群修正或精確、可審查的第三方 stub boundary 收斂到 zero observed
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

### Current slice C — Torch model and loop boundaries

- **Problem and evidence**：`EEGNet.py`、`SCCNet.py`、`ShallowConvNet.py`、`epoch_runner.py` 與
  `evaluator.py` 合計 10 項 `reportPrivateImportUsage`。鎖定的 PyTorch `2.11.0+cu130` 中
  `ones`、`log`、`clamp` 與 `cat` 皆實際存在且列於 `torch.__all__`，因此這是 dynamic export／
  stub boundary，不是 runtime defect。直接 model、runner、evaluator 與 trainer integration 基準為 248 passed。
- **Outcome**：兩處 `torch.log(torch.clamp(x, min=1e-7))` 改用等價 `x.clamp(min=1e-7).log()`，
  消除 4 項；其餘兩處 `ones` 與四處 `cat` 只在原 public call 加診斷專用行級 suppression。
  五檔 10→0，全案從 38 獨立降為 28。
- **Scope／non-goals**：只改上述 5 個 production files；現有 characterization 已直接覆蓋行為，不為
  suppression 新增 source guard。不改 model architecture／shape、device／dtype、batch order、gradient、
  empty-loader semantics、public API、UI 或 persistence。
- **Ownership／deletion**：現有三個 model class 與 runner／evaluator owners 不變，delta `0`；方法鏈替換
  嵌套函式，不新增 wrapper／helper。預期 production net LOC 不超過 +6。
- **Repair and validation**：保留同一 248-test baseline，驗證四個 runtime public exports，並跑完整外部
  Basedpyright、五檔 Ruff／diff，frozen-SHA review 與 PR CI。
- **Stop／UI status**：若 suppression 不是單一 public call，或輸出、gradient、allocation、empty batch、owner
  有任何變更即停止。這是 non-UI type-only slice，無可見行為與 screenshot。

### Current slice D — Torch training setup boundaries

- **Problem and evidence**：`training/option.py`、`training/record/train.py`、`training/training_plan.py` 與
  `training/utils.py` 合計 7 項 `reportPrivateImportUsage`，分布在 6 個精確 call sites。鎖定 runtime 已實際
  驗證 `zeros`、`tensor`、`float32`、`from_numpy` 與 `Generator.manual_seed`；直接基準為 263 passed。
- **Outcome**：只在六個現有 public call 加行級 `reportPrivateImportUsage` suppression，不替換 API 或
  建立 wrapper。四檔 7→0，全案從 38 獨立降為 31；與 slice C 合併後預期 21。
- **Scope／non-goals**：只改上述 4 個 production files，不新增測試／source guard；不改 CUDA probe、
  class-weight dtype／device、SharedMemoryDataset copy／hot path、DataLoader seed／ordering、optimizer validation、
  public API、UI 或 persistence。
- **Ownership／deletion**：TrainingOption、TrainRecord、TrainingPlan 與 optimizer helper 的現有 owners 不變，
  delta `0`；沒有更正確且不改 runtime 的 deletion／public import。預期 production net LOC 約 +6。
- **Repair and validation**：保留同一 263-test baseline，跑完整外部 Basedpyright、四檔 Ruff／diff、
  frozen-SHA review 與 PR CI。`training_plan.py` 的 CRLF 不得因行級修改變成全檔 line-ending diff。
- **Stop／UI status**：若出現非該單一診斷的 ignore、行為／line-ending／owner 變更或 focused
  baseline 退步即停止。這是 non-UI type-only slice，無可見行為與 screenshot。

### Deferred behavior bug — artifact key `allow_pickle`

`backend/training/record/artifact_store.py` 的 1 項 diagnostic 對應真實 persistence defect：NumPy 將
`allow_pickle` 視為 `np.savez_compressed` 的 control argument，而不是 array key。這不能在 type-only slice
裡用 suppression 消掉；待 Torch 與 UI slices 完成後另開 bug-fix plan，提前拒絕該 reserved name，並要求續寫等
真實 side-effect test 與使用者手測批准。

## Progression and focused validation

1. **Current plan checkpoint**：合併本 canonical plan，再從同一 fixed main 建立 C／D 兩條互不重疊
   worktree；兩個 worker 各自實作，同一 independent reviewer 只在 frozen commit 後審查。
2. **C／D exact validation**：每片保留既有 passing characterization baseline，核對鎖定 PyTorch runtime 的
   public exports；各自跑 focused tests、external full Basedpyright、Ruff、diff、frozen-SHA review 與 PR CI。
   兩片依序進 main 後重跑 combined gate，observed count 必須由 38 精確降為 21，不可有新 diagnostic。
3. **Remaining type debt**：依 8-file 上限完成 UI／plot 的 20 項 type-only diagnostics；最後才獨立判定並
   修理 artifact 的 1 項 behavior bug。第三方 stub mismatch 只允許已有 runtime evidence 的精確行級
   suppression，最終 external observed count 必須為 0。
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
