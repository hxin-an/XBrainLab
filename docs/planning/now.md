# XBrainLab Now

最後更新：`2026-09-04`

## Current baseline

`2315c8ac08c1cc2683e6526eec9b368add809bff` 是目前 `origin/main` 的產品基線。Repo-root
`settings.json` 的本機修改由使用者擁有，絕不可 stage、commit、revert、覆寫或隱藏。

PR #111（Evaluation render expected-stale reporting）仍獨立維持在其原 branch，尚未取得該 exact
head 的 Windows 手測／merge 批准；本 slice 從 `origin/main` 另開 branch，絕不混入 #111。

## Active slice — Data Splitting contract, materialization parity, and truthful preview

### Problem and evidence

- 現有可選的 `Disable`/`*_IND` 與 Train admission 不一致：Test Disable 和 Individual 的 Subject/
  Independent 組合能在 preview 出現，卻不能產生有效 train/evaluation partition；Validation Disable
  也會留下 truthy holder，導致 Train 與 preview 的含義不同。
- 現有 ratio 在 test 後再對剩餘資料切 validation，且對 epoch rows 而非原子 group 計算；KFold 可接受
  `K=1` 或對不足群組產生少於 K folds。preview 只顯示計數、save 與 Train 又各自 materialize，沒有可驗證
  的 allocation identity。
- Session 現況以 subject-session pair 而非跨 subject 的同名 session label 分組；manual empty、字串 bool
  及明確 `{}` split config 亦可能被靜默接受或回退 legacy。這些皆會使使用者的 split 選擇無法可靠解釋。
- SSVEP 的 frequency class 是既有 supervised label，不需要 frequency adapter；MAMEM1 已證明 import/
  epoch/training 路徑可用，但 split contract 必須使 frequency classes 和任何 BIDS/MOABB supervised
  classes 同樣可重現地進入訓練與評估。
- Exact-head audit 所列的 admission、audit parity、cancellation、Validation Disable Ratio nearest-feasible、
  mixed Manual residual 與實際 materialization evidence gaps 均已在既有 owner 關閉；回歸測試覆蓋 strict
  structured payload、pair-scoped provenance、preview/Train 同 audit、cancel linearization、Manual scope/
  duplicate/atomic constraints，以及 CV Validation Number 的 exact cardinality。這仍是 bounded contract，
  不是任意資料集的科學品質或 complete-solver 證明。
- Exact-head supplemental complete regression 發現的兩個 stale UI root-contract tests 已以 observable
  `DataSplittingDialog` kwargs 更新，現在傳遞已批准的 saved split rehydration
  `initial_specification`；production/UI 均未改動。
- Exact-head CI 三平台失敗收斂的兩個 stale integration tests 已完成：(1) product walkthrough 的 12 original
  trial groups、Test/Validation 各 `0.25`，依批准的 original-scope contract 使用 `6/3/3`；(2) training
  recommendation synthetic `Epochs` fixture 已提供真實 shape 的 verified non-overlap epoch-window provenance。
  production audit 未放寬。
- Exact-head CI `linux-integration-rest` 的六個失敗同樣都是 stale sequential-ratio expectations，audit 均
  通過：`application_service_workflow` 的 `7/2/3` 改為 `6/3/3`；checked-in GDF `A01`（total 273）由
  `176/43/54` 改為 `165/54/54`，`A02/A03`（各 total 270）由 `173/43/54` 改為 `162/54/54`，涵蓋三個
  training-smoke cases 與一個 CUDA OOM case；`real_data_command_spine` 的 `A01` 亦為
  `176/43/54` 改為 `165/54/54`。scope 限 tests/docs，不改 production。
- `application_service_workflow` 同一 integration test 另有 direct stale assertion：顯式空
  `split_config` 舊期望成功；批准契約只有 `None` 可走 legacy default，顯式空 rules 必須 fail closed 並保留
  state。scope 限 tests/docs，不得放寬 production。
- 上述七個 stale expectations/assertions（六個 count 與 explicit-empty assertion）均已修。Aggregate old-head
  job 未提供額外測試；它因缺 provenance sidecar 而正確 fail closed，不是 Data Split regression。
- Canonical manifest 在 `origin/main` 已有 direct-script `ModuleNotFoundError`，無法完成；supplemental full
  regression 的 `llm-rag` 缺 `langchain_huggingface` 亦為環境問題。兩者不得混為本 Data Split defect 或
  handoff evidence。

### Outcome and exact contract

- 保留 Data Splitting `Step 1 → Step 2 → Save → Train` workflow 與 Data Import 五個階段。Full 支援 Test
  `Trial|Session|Subject`；Individual 支援 `Trial|Session`。Validation 為 `Disable` 或該 training mode
  可用的任一 unit，且可與 Test 混用；所有
  Independent variants 及 Test Disable 移除，Individual Subject 一律拒絕。
- 非 CV 的 Test/Validation units 支援 `Ratio|Number|Manual`；CV Test 僅 exact `KFold`，CV Validation
  僅 `Disable|Ratio|Number`。Test 一個 rule、Validation 零或一 active rule；舊 invalid payload 必須要求
  reconfigure，不能靜默 rewrite。`None` 才可走 legacy default，明確 `split_config={}` 不是 legacy；JSON
  boolean 必須是實際 bool。
- Trial 為 temporal-overlap atomic group；Session 為所有 subject 共用同名 session label；Subject 為整個
  subject。Test 從 Train+Validation 隔離，Validation 從 Train 隔離；混用策略遵守各自的隔離單位。
- Ratio 以原始 scope 的 atomic group count 算，Number 是精確正 group 數，Manual 必須非空、無重複且在 scope。
  Test/Validation capacities jointly computed，最小化 requested test/validation target 的總絕對偏差；同分時
  優先更多 train、較小 test deviation、stable group key。每個 required split 必須非空，否則 preview 阻擋。
- K 必須 `2 ≤ K ≤ groups` 且每個 scope 有 exact K folds；test groups 不重複且聯集等於 scope。確定性、
  bounded 的 allocation 在固定 capacities 下優先完整 evaluation coverage，再 class×partition coverage/
  imbalance 與 stable ID。train 全 classes 是 hard constraint；不切 atomic group。
- Preview 與 Train 使用同一 canonical materialization/audit；receipt 保存 allocation materialization digest，
  Train 重新算 rows/coverage/digest，任一不符 fail closed。Preview row 顯示原始 group、selected group、row
  counts、missing class display names 與 `saliency_source=test|validation|unavailable`。若 test class 不全但
  validation 完整，沿用 validation saliency fallback；兩者皆不完整時允許訓練/evaluation，但該 fold 不產生
  saliency，其他 eligible fold 仍繼續。
- `preview_receipt=None` 保留既有 unreviewed deterministic command path：Train 仍以同一
  `DatasetGenerator.generate()` 與 audit materialize，但不宣稱或比較 reviewed-preview parity。提供 receipt
  時必須有 canonical SHA-256 digest（`unbound`/手工 placeholder 一律拒絕），Train 必重算並 fail closed。

### Scope, non-goals, ownership, and complexity

- Scope：既有 split domain/application owner 內的 enum/config admission、atomic allocation、audit、preview
  publication、receipt/materialization comparison、training saliency admission，及直接 backend tests。UI worker
  只消費 backend truth，另行處理已批准的 dynamic grid、Step 2 copy、manual chooser、rehydration 與 lifecycle。
- 本次直接相關的舊測試也在 scope：盤點並刪除已退役的 Test Disable／Independent expectation，將 mock-heavy、
  繞過 production command entrypoint 或只複製 helper implementation 的 split tests，以最小且較強的
  domain/command/materialization replacement 取代；不進行全 repo test cleanup，也絕不以刪測使 suite 變綠。
- Non-goals：不加 SSVEP/frequency adapter、CCA/FBCCA、dataset-specific split rule、solver、second allocation
  engine、new owner/state machine/compatibility path；不改 filter、Assistant restart、import wizard 五階段或
  `settings.json`。不宣稱所有 MOABB；本機 15 corpus 僅用於 catalog/availability 檢查，不把它誤稱為
  15/15 materialization 證據。
- Owners before/after 不變：`DatasetGenerationService` owns command admission/save/materialization；
  `DatasetGenerator`/`Epochs` own mask allocation；`SplitAudit` owns partition evidence；`TrainingPlan` owns
  saliency split choice；preview publisher only publishes immutable DTO. Reuse/delete invalid enum dispatch,
  silent clamps, fixed fake split facts, and duplicate admission rather than adding a parallel policy.
- Complexity checkpoint (2026-09-04): the current combined production diff against `origin/main` is 14 files,
  `+1806/-512` (net `+1294`). This exceeds the ordinary 8-file/+300-net trigger but remains below the
  approved 1,500-net one-PR stop. Owners remain unchanged: `Epochs`/`DatasetGenerator` allocate masks,
  `SplitAudit` owns evidence/digest, `DatasetGenerationService` owns save/materialize admission,
  `DatasetSplitPreviewPublisher` publishes detached truth, and the UI projects it. No module, public class,
  authoritative owner, state machine, solver or compatibility path has been introduced. Deletions include retired
  Test Disable/Independent dispatch, sequential split methods, UI-local duplicate admission policy, mock-only
  retired tests and weak count/digest echoes; their replacements exercise real allocation or command materialization.
  The bounded deterministic allocation is deliberately not a complete solver and fails closed when no admissible
  partition is found. Replan if production net reaches 1,500 or a new owner/state machine/solver/compatibility path
  becomes necessary.
- UI approval is explicit: the user approved preserving the five-stage import flow and the existing 5×5-like split
  presentation logic, with real dynamic counts and the stated colors/copy. UI still requires screenshot/walkthrough
  and later native Windows acceptance on exact PR head.
- Audit repair actual: four existing production files, `+348/-138` (net `+210`). It reused `SplitAudit`, preview
  publisher, `DatasetGenerationService`, `DatasetGenerator` and
  config admission code; no module, owner, state machine, solver, receipt, or compatibility path was added.

### TDD repair and validation sequence

1. Add the smallest red public/domain reproductions before production edits: invalid strategy/mode matrix,
   Validation Disable/empty semantics, strict boolean and `{}` admission, global Session grouping, ratio/Number
   group capacity, K bounds/exact folds, and preview receipt mismatch. 同時盤點直接被新 contract 淘汰的
   Disable/Independent tests；每個刪除必須有涵蓋真實 observable contract 的 stronger replacement。
2. Implement one canonical allocation/audit path in existing owners; parameterize real `Epochs`/
   `DatasetGenerator` tests for 1/2/3/5/7 groups, unequal group sizes/classes, mixed protocols and determinism.
   Assert allocation atomicity, coverage, cardinality and Train/preview identity rather than helper internals.
3. Add lower-mock preview → receipt → save → materialize → Train admission → evaluation/saliency tests; stub only
   expensive final trainer. Verify complete-test, validation-fallback, and unavailable saliency outcomes without
   turning an expected unavailable fold into a generic worker failure.
4. UI tests cover 1/3/5/15 subject layouts, unavailable choices/reasons, narrow/keyboard/manual cancel, 50+ rows,
   class notices and saved-spec rehydration. Root visually inspects screenshots; offscreen does not replace Windows
   native acceptance.
5. Run focused backend/UI selectors under explicit timeout and `prlimit --core=0` where MNE/Qt/PyTorch is involved,
   then changed-file Ruff and `git diff --check`. Before handoff, run canonical public source-diverse data gates and
   exact-head Windows manual materialization for MAMEM1 EEGLAB Trial/KFold with five frequency classes,
   BNCI2014_009 BrainVision Subject/Session, and PhysionetMI EDF Subject/Trial. The local pinned 15 MOABB corpus is
   catalog evidence only, not a 15/15 materialization requirement or arbitrary-MOABB claim.
6. **Audit-repair TDD (complete):** red/green public-command and real materialization cases closed mixed provenance
   fail-closed behavior, preview-time audit parity, cooperative cancellation with no successful receipt after a
   successful cancel, strict structured payload fields while preserving only `split_config=None` legacy behavior,
   nearest-feasible no-validation Ratio, mixed Manual residual semantics, Manual duplicate/out-of-scope/atomic
   constraints, and CV Validation Number exact cardinality. The repairs stayed in the existing owners; no parallel
   allocator or policy path was introduced.

### Stop condition

- Stop rather than expand if valid contract behavior requires a new owner, second state machine/allocation engine,
  generic solver, compatibility rewrite, dataset-specific frequency semantics, or changes outside split/
  materialization/saliency and the explicitly approved UI surface.

### Implementation progress and evidence checkpoint

- Contract/admission, canonical allocation/audit, receipt parity, saliency fallback, saved-spec UI projection and
  obsolete/mock-heavy split-test cleanup are implemented in the existing owners. The five-stage import workflow is
  unchanged.
- Focused pre-commit candidate-tree evidence: full Application+Dataset `2388 passed`; selected Training `628 passed`;
  UI `178 passed`; selected architecture `285 passed`; whole-repo Ruff check and format check passed; Basedpyright
  regression reported `0` new diagnostics; architecture compliance script passed. These results close the listed
  audit/admission/cancellation/no-validation-ratio/mixed-Manual/evidence-gap checkpoint; they do not certify an
  arbitrary dataset, scientific split quality, or a complete solver.
- Supplemental UI root-contract evidence: `test_sidebars_and_components.py` `102 passed`; the
  `tests/unit/ui/test_*.py` selector `944 passed`, and its root rerun of the single file also `102 passed`.
- Integration-UI green evidence: with the correct `PYTHONPATH`, full `tests/integration/ui` reports `119 passed,
  21 skipped`. The first attempt without that path produced three direct-script `ModuleNotFoundError`s; that is an
  existing runner-entrypoint/environment issue, not a Data Split defect.
- Stale-test green evidence: ApplicationService integration file `21 passed`; checked-in GDF `15/15` passed;
  command spine `1/1` passed. The authoritative `linux-integration-rest` result collected `346`, with `311 passed`,
  `35` optional-public-fixture skipped, and `0 failed`; pipeline reports `121 passed, 6 skipped`. Aggregated evidence
  is `10438 passed, 21 skipped, 0 failed`.
- Remaining work: final tests/docs review and commit/push, exact-head CI, and the specified Windows native manual
  acceptance. The canonical manifest retains its existing runner-entrypoint blocker. Until those gates close, this
  remains a checkpoint, not handoff-ready.
- Stop if deterministic allocation cannot satisfy hard train-class/required-split constraints for a given input:
  publish a recoverable infeasible preview with the cause, never silently clamp, split an atomic group, or mutate
  saved truth. Do not expand into arbitrary MOABB support, UI redesign, or a second allocator.

## Historical record — SSVEP import review routing and EEGLAB preflight sampling rate

### Problem and evidence

- Data Import 的既有五個使用者階段是：`Choose EEG Data`、`Load Labels`、`Review Metadata`、`Match Labels`、
  `Review and Import`。使用者明確滿意這五段，要求不要大改。
- 真實 command lifecycle 是 `scan -> preview -> validate -> confirm -> apply -> recipe`；只有
  `AppliedInterpretation` 才能成為下游 truth。
- 在 `DataInterpretationActionCoordinator._repreview_interpretation_async()`，Match Labels 或 final review
  的 edit 會正確重跑 `PreviewInterpretationCommand` 與 `ValidateInterpretationCommand`，但 validated callback
  無條件以舊 `initial_step` reopen dialog。它沒有使用 fresh `ValidationDecision.action_items` 的
  `target_step`。因此新的 `blocked` class/event mapping candidate 可能回到 `Review and Import`，而不是回到
  backend 指定的 `Match Labels`；使用者看不到清楚的 recovery path。
- 這是 coordinator routing defect，不是 dataset 名稱、raw SSVEP parser、backend validator 或 Apply defect。
  已有 focused tests coverage re-preview、fresh final review 與 no-apply boundary，但尚未刻畫 fresh blocked
  decision 的 target-step routing。
- 使用者的 MAMEM1 BIDS 手測揭露另一個直接阻擋：`sub-1` 的 uncompressed embedded MAT v5 `.set` 把
  `EEG.data` 放在 `EEG.srate` 之前。bounded preflight 一讀到 signal shape 就當作完整 header 回傳，因而
  得到樣本數卻漏掉真實 header 的 `srate=250 Hz`。BIDS event review 無法由 `n_times / sfreq` 建立 recording
  bounds，安全地退回 `Match Labels`。這不是頻率 class、SSVEP adapter 或使用者 choices 的問題；同型 embedded
  EEGLAB `.set` 都可能受影響。

### Outcome and user-visible contract

- Re-preview 後只信任 fresh backend `ValidationDecision`：`blocked` 時以 typed actionable target reopen；本
  slice 的 class/event blocker 必須 reopen `Match Labels`，並保留該 decision/action cards。`safe` 和
  `needs_confirmation` reopen `Review and Import`，讓使用者對新 candidate 作 final confirmation。
- `ApplyInterpretationCommand` 不得對 blocked candidate 執行；既有 fresh-final-review confirmation boundary
  必須保留。
- status bar 顯示 concise backend-truth-aligned recovery outcome（例如 review updated and current task），不以
  前端另造 validation policy。loading、cancel、failed 與 repeat lifecycle 保持現有 owner。
- EEGLAB bounded preflight 必須在不 materialize signal samples 的前提下，繼續讀完同一 bounded MAT struct 所需
  scalar metadata；對 data-before-srate 的 embedded MAT v5 source 保留 `sampling_rate_hz=250.0`。這讓 BIDS
  duration validation 使用真實 recording bounds，而不是為 SSVEP 或 frequency class 增加特殊路徑。

### Scope, non-goals, assumptions, ownership

- Scope 包含 coordinator 的 fresh-decision-to-reopen-step routing、EEGLAB embedded MAT v5 bounded-header completion、
  直接 focused regressions、此 plan，和必要的 offscreen walkthrough artifact。production files 預計只有
  `XBrainLab/ui/panels/dataset/data_interpretation_action_coordinator.py` 與
  `XBrainLab/backend/application/eeglab_set_preflight.py`；tests 預計只有
  `tests/unit/ui/dataset/test_interpretation_async_flow.py` 與
  `tests/unit/backend/application/test_eeglab_preflight_gate.py`。
- 不改五階段、dialog layout、copy hierarchy、backend Data Interpretation policy／payload schema、Apply semantics、
  raw loader、recipe schema、MOABB dependency、dataset download、filter、Assistant fallback 或 data split。
- 不新增 frequency adapter、target-to-frequency/phase/code inference、CCA/FBCCA 或 BIDS special case；不宣稱所有
  MOABB、任意 BIDS/event schema、科學 SSVEP accuracy 或 benchmark quality。MAMEM1 的 accepted contract 僅是使用者可將
  `trial_type` frequency values 明確選成 supervised classes，且 import 後可進入既有 epoch/split/train workflow。
- Owner before/after 不變：`DataInterpretationCommandService` owns scan/preview/validate/apply state and decision;
  `DataInterpretationActionCoordinator` only owns async UI command orchestration; preview dialog renders typed
  result; `eeglab_set_preflight` remains the sole bounded `.set` metadata owner. 不新增 owner、state machine、module或
  compatibility path。
- Deletion/reuse first：reuse existing `_repreview_interpretation_async` and typed `action_items`; do not add a
  parallel wizard/router, frontend inference, or second EEG reader. Routing repair 預估 production net `+20–45 LOC`；
  preflight repair actual `+23/-4 LOC`，兩個既有 production owners，owner delta `0`。
- UI approval 已存在：使用者說「目前 review and import 這五個階段我很滿意不要大改」，並在討論 status bar
  後回覆「我覺得可以」。本 slice 只在該批准下修正 recovery routing/status，仍需 focused screenshot/walkthrough
  與後續 Windows native human acceptance；preflight repair 本身不改可見 UI。

### TDD repair sequence and validation

1. 在 `tests/unit/ui/dataset/test_interpretation_async_flow.py` 先新增最小 red reproduction：從 changed
   Match Labels/final draft re-preview，fresh validation returns `blocked` plus typed `target_step="Match Labels"`;
   assert reopened dialog uses `Match Labels`, preserves fresh review state/action items, shows recovery status, and
   never calls Apply. 它必須在 current code 因 reopen uses stale `initial_step` 而失敗。
2. 加 direct adjacent cases: fresh `safe` and `needs_confirmation` reopen `Review and Import` and preserve the
   required fresh confirmation boundary; cancellation/error remains owned by existing lifecycle.
3. 只在 coordinator 加最小 resolver using fresh typed decision/action items; unsupported/missing target fails
   closed to the conservative review path, never guessed from SSVEP names or UI labels. 不改 backend or dialog policy.
4. Run the red selector, then the same selector green and directly coupled async-flow file under Qt-safe timeout /
   `prlimit --core=0`; run changed-file Ruff and `git diff --check`.
5. Produce the existing data-import offscreen capture plus a user-like blocked-to-Match-Labels walkthrough artifact;
   inspect the screenshot for five-step preservation, readable status, no clipping/overlap. Offscreen evidence does
   not replace Windows native acceptance.
6. 先在 `tests/unit/backend/application/test_eeglab_preflight_gate.py` 新增最小 red reproductions：uncompressed
   embedded MAT v5 `EEG` struct 的 `data` 在 `srate` 前，以及 top-level `data` 後仍有 ignored metadata、再有
   `srate` 的 continuation；兩者 assert bounded inspection retains shape/dtype and `sampling_rate_hz == 250.0`
   while physical reads remain bounded and no signal materializes。另以既有最多 256 個 post-data outer metadata
   elements 的 cap，證明 255 個 ignored elements 後的 `srate` 仍可讀到、256 個後的 late `srate` 則 fail closed
   as an embedded bound with `sampling_rate_hz is None`，不得為找 rate 讀取 signal。
   current code 必須因 early return 令 sampling rate 為 `None` 而失敗；不先修改 production。修理後 rerun exact
   selectors and the coupled EEGLAB preflight file under `prlimit --core=0` and timeout.
7. Windows native acceptance on the exact PR head: select MAMEM1 `sub-1` runs 0–2, map `trial_type`
   `6.66/7.50/8.57/10.00/12.00` to five explicit `Hz` classes, continue to Review and Import without a missing
   sampling-rate blocker, Apply, epoch `0–3 s`, save `Individual/Trial` split, and complete one CPU EEGNet epoch.
   Record five imported classes and completed training; this is MAMEM1-specific acceptance, not a broad MOABB claim.

### Implementation progress and focused evidence

- Red reproduction completed: the new coordinator async seam dispatched `PreviewInterpretationCommand` then
  `ValidateInterpretationCommand`; a fresh `blocked` decision with typed `target_step="Match Labels"` actually
  reopened stale `Review and Import`, exactly proving the reported defect. No Apply was invoked.
- Minimal repair completed: coordinator reuses `adapt_serialized_validation_decision()` from the existing review
  presenter. A valid fresh blocked decision takes its first typed blocked action target; `safe`,
  `needs_confirmation`, invalid, or incomplete decisions reopen conservative `Review and Import`. The sole new
  status copy is `Import review updated · Continue in <task>`.
- Green focused evidence: red selector then passed; blocked/safe/needs-confirmation routing selectors were `3 passed`
  (2.32s); full `tests/unit/ui/dataset/test_interpretation_async_flow.py` was `85 passed` (12.42s); directly coupled
  review presenter/loading Qt tests were `23 passed` (1.25s). Changed-file Ruff and `git diff --check` passed.
- TCP-only Xvfb focused capture completed with exit `0`: the existing canonical generator wrote
  `build/dev-artifacts/ssvep-repreview-ui-evidence/04-match-labels-final-loaded-label-files.png` and its root
  manifest. PNG SHA-256 is `efc535fdd7aaa1479bc72047f8f800bbbd89ccca2141c82d98ffa50644ee7b04`; it is a readable
  1220×1320 xcb-native-window screenshot. Visual inspection confirms all five named stages remain visible, Match
  Labels is active, the class-event choices and footer are readable, and there is no observed clipping/overlap.
  This focused capture proves only the pre-existing five-stage Match Labels surface; it does not exercise the new
  asynchronous re-preview route or status bar, is dirty-source evidence, and is not Windows human acceptance. The
  exact-source Windows human walkthrough remains required before any merge claim.

### PR #110 direct product dependency — EEGLAB embedded sampling-rate preflight

- Exact red evidence: the new uncompressed embedded MAT v5 data-before-srate selector failed on the unmodified
  parser with `1 failed in 0.56s`; inspection had `bound_known=True`, embedded `(4, 100000)` float32 data and
  `sampling_rate_hz=None`. This isolates the early header completion defect without loading EEG samples.
- Minimal parser repair is complete in the existing `eeglab_set_preflight` owner: after embedded data is bounded,
  uncompressed top-level scalar metadata may continue through the existing cap; compressed, v7.3, payload and
  unsafe-reference boundaries retain their existing fail-closed behavior. Actual production delta is `+23/-4 LOC`,
  owner delta `0`; no loader, BIDS policy, frequency adapter, UI, or compatibility path was added.
- Green regression inventory: one nested data-before-srate regression, one ordinary top-level continuation regression,
  and two real top-level cap boundaries (255 ignored post-data elements then `srate=250`; 256 then late `srate=None`)
  are included in the full EEGLAB preflight suite. Independent review found no lifecycle, ownership, payload-read,
  cap, or class-carrier blocker after the 255/256 boundary correction.
- Actual MAMEM1 bounded probe on `sub-1/ses-0/eeg/sub-1_ses-0_task-ssvep_run-0_eeg.set` reports `bound_known=True`,
  `storage_mode=embedded`, `sampling_rate_hz=250.0`, `header_bytes_read=512`, shape `(256, 117917)`, and `float32`.
  This proves the exact cached run's header admission only; it is not an Apply/epoch/train or scientific claim.
- Focused Windows evidence on the current dirty source: EEGLAB preflight `19 passed` (0.72s), resource guard
  `48 passed` (2.37s), interpretation resource reader `14 passed` (1.80s), and async import routing `85 passed`
  (10.27s), each under `prlimit --core=0`, explicit timeout, `MNE_DONTWRITE_HOME=true`, and offscreen Qt where
  applicable. Changed production/test/UI Ruff and `git diff --check` passed.
- Next step: commit and push this exact source, wait for non-skipped CI on that exact PR head, then repeat the full
  native Windows MAMEM1 acceptance (three sub-1 runs, five `trial_type` frequency classes, Apply, `0–3 s` epoch,
  Individual/Trial split, CPU EEGNet one epoch) before any merge claim.

### PR #110 direct CI blocker — restore Dataset startup lazy import

- Exact `6b9f1fe09425ea2274333538975a5eeb59bfd330` has four direct Linux CI failures in the Dataset import-latency
  boundary. Their common root is this slice's new top-level coordinator import of
  `XBrainLab.ui.dialogs.dataset.review_import_presenter`: importing Dataset actions now imports the Dataset dialog
  package during first-open, violating its explicit lazy-import contract. This is an eager-import regression, not a
  routing, validation, raw-SSVEP, or behavior failure.
- Repair scope is only to restore the existing lazy seam: remove the coordinator top-level presenter import and
  import the existing adapter only at fresh decision resolution. Do not add a parser, module, owner, cache, schema,
  dialog/layout change, or fallback policy. The same typed adapter and routing outcome remain authoritative.
- TDD evidence is the existing four import-latency selectors, run directly in the external Linux environment: they
  must fail current source because the dialog package is eager. After the smallest lazy import repair, rerun those
  selectors, the routing triplet, full async-flow file, a relevant MainWindow startup probe if environment permits,
  changed-file Ruff and `git diff --check`.
- Stop if lazy resolution changes the typed decision contract, delays/loses routing behavior, causes a new startup
  import root, or needs a broader dialog/package redesign. This repair restores no user-visible behavior beyond
  startup import latency and does not change the five stages or SSVEP claim boundary.
- Red evidence completed in the external Linux environment: the direct import-latency probes found
  `XBrainLab.ui.dialogs.dataset.review_import_presenter` after Dataset panel/actions import. The selected CI boundary
  set was `2 failed, 2 passed`; both failures have the stated common eager-import root. The remaining two reported CI
  failures are the same package-startup boundary on their own CI paths, not an additional routing defect.
- Minimal repair completed: the adapter import now occurs inside `_repreview_step_for_decision()` only. It preserves
  the existing adapter, typed decision semantics and routing outcome; no new parser/module/owner/cache was added.
- Green evidence: the same four direct import-latency selectors plus default MainWindow startup probe and the routing
  triplet were `8 passed` (5.46s). Full async-flow was `85 passed` (12.26s); changed-file Ruff and `git diff --check`
  passed. These are dirty-source focused results only and do not replace PR CI or Windows acceptance.
- Independent review passed: the repair preserves the existing lazy dialog boundary and routes through the same
  adapter only after a fresh decision exists; it found no lifecycle, policy, owner, or visible-flow blocker. Combined
  focused evidence is `91 passed` across the import-latency/startup boundary and complete async-flow protection.
  Next step is commit/push this exact lazy-import repair, then wait for PR CI on that exact head; do not treat this
  local evidence as CI completion or Windows acceptance.

### Stop condition

- Stop rather than expand scope if fresh backend output lacks typed action items/target, targets a stage outside the
  existing five, requires backend policy/schema changes, makes Apply reachable for blocked input, changes more than
  the stated two production files, or cannot be observed by the focused test.
- Stop rather than broaden the preflight fix if a correct scalar requires reading numeric signal payload, compressed
  header decoding exceeds its existing budget, a MAT v7.3 file is involved, or the repair needs a loader/BIDS policy
  change. Do not proceed into raw SSVEP adapters, target-frequency/phase semantics, data download, classifier work,
  filter, Assistant fallback or splitting cleanup. After this slice, claim only typed review routing plus the exact
  embedded EEGLAB sampling-rate repair; MAMEM1 supervised training remains subject to the listed Windows acceptance.
