# XBrainLab Now

最後更新：`2026-08-27`

## Active slice：Electrode Layout BIDS readiness presentation

**Identity.** Worktree `/tmp/xbrainlab-electrode-layout-v1`，branch
`feature/electrode-layout-dataset-v1`，base `origin/main` =
`2c51d7b1e6ff83475f285f0db331becd3f87f5c1`，start SHA =
`c8e6d475bef713ba64cc780f05bfc43b012b98fb`，Draft PR #58 to `main`。Current candidate
identity comes only from Git's exact `HEAD` plus its source-bound artifact manifest, not this
planning narrative.
Root 保持 sole plan / scope / integration / CI / merge coordinator；Electrode builder 只修改這條
branch 的 Electrode/BIDS 路徑；UI product reviewer、data-interpretation reviewer 與 root 都是唯讀
reviewer。`settings.json` 是使用者本機設定，永不碰觸。

### 問題與 evidence

- BIDS summary artifact 顯示為平鋪 debug text（Layout／Source／Coverage／Coordinate frame）與三個
  同優先按鈕，沒有產品階層；picker 同時競爭 Auto Match、Clear Mapping、Back／Cancel／Replace。
- Earlier Dataset polish put a second visible status line below `Electrode Layout`; the user rejected that
  duplicate surface. BIDS/manual provenance, coverage and retained-BIDS restore still need to be clear in
  the dialog without turning the Dataset action area into a status card.
- 非 BIDS channel mapping 已可工作，但未將「保守預填、人工確認、不跨 dataset 誤用」明確收斂成
  deterministic product behavior。
- Review found that the existing Visualization convenience entrance was deleted instead of delegating to
  the Dataset route, and a manually reviewed duplicate electrode selection could still be persisted. Both
  are direct workflow/data-integrity defects within this slice.
- 既有可逆 BIDS lifecycle、command boundary、generation fence 及兩入口已存在；本 slice 是視覺與
  reviewed mapping polish，不能重建第二套 montage owner 或 mutation path。
- 已確認兩個 BIDS presentation defect：ready automatic BIDS montage 的 canonical `name=None` 被
  snapshot projection 的 `str(...)` 轉成字串 `"None"`；而使用者在 async preparation 仍為 `pending`
  時開啟 dialog，dialog 只持有當下 immutable snapshot，完成 publication 雖更新 Dataset surface，已開
  dialog 卻不會更新，並把 pending BIDS 誤畫成 `Manual override`／`not configured`。

### Outcome 與 scope

- Dataset `Electrode Layout` remains one button directly below `Channels`, with no visible secondary status
  label. Published layout truth is translated into natural product language only in that button's tooltip and
  `accessibleDescription` (for example, `BIDS layout ready · 4 of 4 EEG channels positioned`).
- Dataset／Visualization 兩入口都開同一 dialog，維持同一 `ApplyMontageCommand` /
  `ApplicationService` mutation path。
- BIDS summary renders directly on the dialog surface, not as a nested card or repeated dialog title:
  `BIDS coordinates`／`Manual override` eyebrow → visibly larger semibold current layout name → muted
  coverage plus coordinate facts. Its right-aligned actions are `Close`, optional secondary `Restore BIDS
  layout`, and the consistent rightmost primary `Change layout…`. Training lock remains viewable but prevents
  mutation with its existing reason.
- Picker hierarchy is layout selector row → secondary `Clear mapping` action → mapping table → footer. There
  is no `Re-run matching`: abandoning edits with Cancel already restores the saved mapping. BIDS footer is
  Back at left and Cancel／Replace at right; non-BIDS is Cancel／Apply at right; every page has one blue primary
  action and retains full labels at 150% DPI.
- Non-BIDS prefill 以 deterministic normalized channel names 排名 builtin montage；唯一最佳 layout 才
  preselect，且只填一對一可信 mapping。collision、alias ambiguity、EOG／EMG、純數字與 unknown 保持
  blank。tie／no-match 時 layout selector 明確保持 `Select layout`，不從 QSettings 的
  `last_montage` 跨 dataset 靜默預選；Apply disabled，亦不得儲存 mapping。caller 明確 default
  與唯一最佳仍可選 layout；`last_montage` 僅在 successful accept 後保留。永不 auto-apply；Cancel
  零 mutation。
- Reviewed mapping 只在 exact ordered channel schema 相同時重用；不得跨 dataset silently reuse legacy
  mapping，亦不得破壞性清除舊設定。
- BIDS readiness remains owned by the existing application publication. The snapshot preserves an automatic
  BIDS `name=None` as null rather than the visible literal `"None"`; the dialog presents compact truthful
  pending/ready/unavailable states and observes only its active pending summary through the existing Dataset
  publication route. A publication must never pull a user who entered mapping back to the summary.

### 明確 non-goals

- 不改 shared Information／Warning／Error modal style、其他 dialog framework 或全站樣式。
- 不改 Assistant prompt/controller/eval、`set_montage` publication policy、tool schema 或 GUI handoff
  contract；它們屬 Accuracy 支線。
- 不在 app 內加入 `Suggested` 標籤、教學卡、help text 或新 tooltip；review-before-apply 的說明留給
  後續外部使用者文件。
- 不改 Epoch channel axis、BIDS import/label semantics、trainer policy、資料掃描效能或 generic
  persistence architecture。
- 不改 BIDS preparation lifecycle、輪詢／timer、direct `LOAD_DATA` provenance inference、second state
  owner、Retry／Re-run action 或任何第二 mutation path；本次不是文案重寫，只修正狀態的真實呈現。

## Complexity review

Current worktree relative to `origin/main` touches **16 production files**, `+972/-424/net +548` LOC，
同時超過 12 production files 與 net +300，必須在此後的所有 polish 修改前保持 complexity review。

- **Owners before/after:** `ApplicationService` remains the only authoritative montage mutation/
  publication owner; `BidsMontagePreparationCoordinator` remains bounded async preparation owner;
  `DatasetSidebar` / `MontagePickerDialog` remain presentation and human confirmation only. This PR does
  add `ElectrodeLayoutStateSnapshot`: a frozen, detached public state DTO / revisioned application-state
  projection within `ApplicationStateSnapshot`, not an owner. It carries detached copied lists but is only
  shallow-frozen; it makes no deep-immutability claim. It exists for the necessary UI/Assistant-safe state seam:
  `StateSnapshotService.build()` projects coordinator truth into the application snapshot, which crosses
  `ApplicationViewPublication` and serialized `QueryStateCommand(state)` without exposing mutable coordinator
  state. Its actual production consumers are (1) `DatasetSidebar.update_sidebar()` through
  `publication.state.electrode_layout`, (2) `DatasetSidebar.open_electrode_layout()` through the state-query
  `electrode_layout` dictionary passed to the reviewed dialog, and (3)
  `ApplicationService._only_montage_preparation_status_changed()` when preserving advisory progress in a
  concurrent-state comparison. It adds no mutation, persistence or confirmation authority; owner count,
  command spine, state machine and compatibility-path count are unchanged.
- **Reuse/deletion first:** retain both visible Dataset and Visualization Electrode Layout entrances. The
  Visualization button is a thin delegate to `DatasetSidebar.open_electrode_layout`; both therefore reuse
  the same dialog/open route, current state query, projection, retained BIDS snapshot and
  `ApplyMontageCommand`. Remove/reduce only generic BIDS information-modal branching and duplicated
  internal presentation/action policy.
- **Why one PR remains coherent:** all touched files serve one workflow—read current layout, human-review a
  mapping, then confirmed apply/restore through the existing command spine. A separate shared-modal or
  Assistant change is explicitly excluded. If new work requires a new owner, crosses 1,500 production LOC,
  or cannot be tied to this workflow, split it to a new branch rather than extend PR #58.

## Data and interaction invariants

- BIDS geometry is observed selected-run evidence, not a claim of full BIDS validation. BIDS metadata may
  be limited/partial; partial coverage remains visible and must not reorder/slice the data channel axis.
- A manual override is a reviewed user choice. The ready compatible BIDS snapshot may be restored during
  the same import; new import/reset, trainer guard, and stale generation fail closed.
- BIDS and non-BIDS mapping both require human confirmation before command submission. UI readiness/error
  text projects backend truth and never creates a second capability policy.
- A non-BIDS tie/no-match is not a default. Its selector stays explicitly unselected; manual selection is
  required before any confirmation can persist a mapping. Duplicate electrode targets are rejected before
  QSettings writes or command submission.
- Loading, failed preparation, no-layout, partial coverage, locked training, Cancel, Back, and stale
  results must be recoverable and must not partially mutate authoritative state.

## Implementation and test-first sequence

1. 2026-08-27 UI feedback supersedes the earlier status-card direction: remove the visible `QLabel` below
   Dataset > `Electrode Layout`; publish the same truthful layout state only through the existing button
   tooltip and accessibility metadata.  The button itself remains the only Dataset-surface control.
2. Establish the smallest red observable UI tests: no visible status `QLabel` below the button; truthful
   tooltip/accessibility; summary label/value text hierarchy; right-aligned summary action cluster with one
   primary action; no `Re-run matching` control or production callback; and Cancel leaves persisted mapping
   and data untouched.  Keep the existing non-BIDS conservative prefill, saved mapping, Restore BIDS and
   ApplicationService command-path contracts.
3. Implement deletion-first in `DatasetSidebar` and `PickMontageDialog` only.  In the summary, align the
   actions at the right so `Change layout…` is not isolated at the left; remove `Re-run matching` because
   Cancel already discards unsaved edits.  Do not add tutorial copy, backend policy, or Assistant work.
   The direct summary surface must also use scoped presentation (not global theme changes): a muted small
   eyebrow (`BIDS coordinates` or `Manual override`), visibly larger semibold current layout name, and muted
   compact coverage/coordinate facts.  A structural role alone is insufficient when the rendered font/color
   hierarchy remains visually flat.
4. Capture and inspect the current BIDS summary, picker and Dataset surface at default scale plus focused
   DPI/narrow state if available.  Run focused UI tests, ruff and `git diff --check`.  Offscreen evidence is
   not Windows/WSLg acceptance; stop at an initial UI revision for the user to approve before any further
   Assistant multi-turn work.
5. This explicitly user-approved visible repair first adds red tests for real-null automatic BIDS names;
   ready fallback without literal `None`; pending BIDS without manual/not-configured semantics; publication
   refresh from pending to ready/unavailable; and the guard that mapping is never yanked back by an async
   publication. Then make the smallest fix in the snapshot projection, Dataset sidebar and existing dialog;
   preserve Cancel, Restore BIDS and training guards. Capture pending, ready automatic BIDS, unavailable,
   manual override, mapping and Dataset surfaces at default and 150% DPI.

## Review, stop condition and UI approval

The user has explicitly approved this visible UI scope: BIDS Electrode Layout, Dataset status, mapping
hierarchy and non-BIDS safe prefill; both current entrances remain. Builder supplies exact HEAD, diff/LOC,
focused tests and artifacts. Independent UI reviewer checks hierarchy, contrast, wrapping, clipping,
keyboard/focus, dialog geometry, one-primary-action, default/narrow/DPI/loading/error/blocked/cancel states.
Data reviewer verifies selected-run provenance, partial/limited semantics, schema reuse and zero-mutation
failure paths. Root independently audits the exact SHA and accepts only in-scope blocking findings.

### Current implementation checkpoint

- **2026-08-27 approved merge blocker — reviewed mapping generation fence.** Evidence from
  PR review: `DatasetSidebar.open_electrode_layout()` reads state and later submits either
  manual or Restore-BIDS `ApplyMontageCommand` without binding the reviewed dialog to the
  publication generation. If a different dataset publishes while the dialog is open, the old
  reviewed mapping can be applied to the new dataset. Outcome: capture the one publication
  generation whose state is queried to open the dialog; bind that same generation to the state
  query and both existing ApplyMontageCommand submissions so the ApplicationService rejects a
  changed publication through the existing blocked/review-again presentation. Scope: the
  sidebar's reviewed-dialog route and one smallest observable regression test. Non-goals: BIDS
  async summary refresh, dialog geometry/copy, command owner, cancellation, persistence policy,
  and all other Electrode behavior. Assumption: ApplicationService already enforces
  `expected_publication_generation`; the UI must only preserve and pass its captured token.
  Test-first: add a red test that changes the publication generation between review and both
  manual/Restore-BIDS confirmation paths, asserting the query and command receive the original
  generation and that stale failure uses existing review-again semantics; then make the minimal
  binding change and rerun the red test plus sidebar/picker adjacent tests. UI scope was
  explicitly approved by the user on **2026-08-27**. Stop after focused green evidence, scoped
  Ruff/format, and `git diff --check`; do not commit, push, merge, or touch other worktrees.
  Red evidence: the new parameterized Replace/Restore test failed **2 times** because neither
  the state query nor `ApplyMontageCommand` received `expected_publication_generation`. Green
  evidence: the same two paths now pass the captured token and stale rejection presents `Review
  Electrode Layout Again`; **64 passed** across the directly related DatasetSidebar and picker
  suites. Scoped Ruff check/format and `git diff --check` pass. The production repair is
  `+28/-3` (net `+25`) in the existing sidebar only; it adds no owner, command path or async
  behavior. No commit, push or merge was performed.

- **2026-08-27 approved final compact-Summary spacing follow-up.** The user clarified that the
  target is not Dataset sidebar spacing and not the expanded mapping footer. It is the compact
  `Manual override` Summary: `Change layout…` currently ends about **35 logical px** above the
  dialog bottom, while the expanded footer's 14–16px edge rhythm is the desired reference. The
  extra blank area comes from the Summary-only 170px minimum height, not from button margins.
  Outcome: let the compact Summary fit at **150px minimum height**, so its action row retains the
  approved 16px content separation and 8px inter-button gap while its bottom edge settles at the
  existing 14px dialog margin. Non-goals: no Dataset sidebar, expanded mapping, outer dialog
  margins, copy, command/state, Restore/Clear placement or other-dialog change. First add a shown
  geometry assertion for the Summary action-to-dialog-bottom gap and demonstrate the current
  ~35px failure; then change only the Summary minimum-height and existing page-geometry policy.
  Re-run picker/sidebar focused tests, Ruff and `git diff --check`; inspect compact Summary at
  default and 150%, including manual, pending and unavailable copy. The user explicitly approved
  this visible scope. Stop before push or merge and repeat WSLg acceptance for the changed exact
  commit.
  Red evidence was **2 failed** focused assertions: the old compact Summary retained its 170px
  minimum-height contract and the shown `Change layout…` action ended **35 logical px** above the
  dialog bottom rather than the target 14–16px. Red also established that merely changing the
  minimum to 150px was insufficient: Qt retained the unconstrained Summary `sizeHint` at 164px,
  leaving a 29px visible gap. The minimal coherent production repair keeps the same dialog/layout
  owner and, only while the Summary is shown, bounds its page to its existing width-aware content
  height before `fit_to_content`; mapping resets that bound. Thus ready, pending and manual Summary
  content settles at 540×150 logical px with a 14–16px footer edge, while a wrapped unavailable
  reason safely grows to 540×164. A second real shown-refresh red test caught the initially missed
  stale bound: pending → long unavailable stayed at 540×150, then manual stayed at 540×164. The
  same-owner repair clears that prior maximum and invalidates/activates the existing Summary layout
  before calculating the current width-aware limit. Green evidence is **62 passed** across picker
  and DatasetSidebar tests, including Summary → mapping → Back, manual, pending, long unavailable
  and the shown pending → unavailable → manual refresh geometry; exact
  changed-file Ruff check/format and `git diff --check` pass. Dirty-source offscreen artifacts
  inspected at default and 150% are
  `build/dev-artifacts/electrode-summary-bottom-v1-default/` and
  `build/dev-artifacts/electrode-summary-bottom-v1-150/`; they include compact manual/ready/pending/
  unavailable and unchanged mapping surfaces. The regenerated ready captures include both `Close`
  and `Change layout…`: default SHA-256
  `01e77ea187af5348cba394b5afe68d83d9ec0ec829b79ee9c979c79d9be3ed19`; 150% SHA-256
  `819c3b9a9c7a35b8ce8b29ab8301765253e77d931b4dafd2be42519e49183779`. No DatasetSidebar
  or expanded mapping source changed. Before WSLg handoff, regenerate the canonical manual Summary
  and mapping surfaces from one clean exact commit at default and 150% in
  `build/dev-artifacts/electrode-summary-bottom-handoff-v1/` and its `-150/` peer; both manifests
  must record that same commit with `dirty: false` and passed surface contracts.

- **2026-08-27 approved follow-up — Replace recovery and picker spacing.** WSLg manual testing of
  `ea494b97` found that choosing a montage then pressing `Replace Layout` opened the generic error
  presentation. `app.log` and the call site identify `DatasetSidebar.open_electrode_layout()` using
  `not positions` on the dialog's NumPy position array; Python raises ambiguous-truth-value before
  `ApplyMontageCommand` can run. The user has explicitly approved the visible repair: Summary keeps
  only `Close` and rightmost `Change layout…`, with a true 16 logical-px content-to-footer gap;
  `Restore BIDS layout` remains available only after `Change layout…` in the expanded mapping footer,
  immediately after `Back`; `Clear mapping` moves into the selector row on the right, rather than
  occupying its own line. Scope is only this ndarray guard and the existing dialog's layout. Do not
  alter copy beyond moving existing controls, BIDS preparation/publication, restore semantics,
  command ownership/spine, training guard, Cancel behavior, Assistant, or generic styles. Add the
  smallest red observable DatasetSidebar test with a real `PickMontageDialog`-shaped ndarray result
  and verify it fails at the prior truthiness guard before command submission; then use an explicit
  `positions is None or len(positions) == 0` check. Add relative layout tests for the 16px group
  separation, summary action set/order, mapping footer restore placement, and selector-row Clear
  action. Green evidence is the same test plus directly related picker/sidebar suites, Ruff and
  `git diff --check`; inspect default and 150% dialog captures. Prepare one local candidate commit,
  then stop before push, merge, or handoff claim; WSLg acceptance must be repeated for the exact
  changed SHA.
  The red reproduction was **1 failed** real-picker → DatasetSidebar test, at the old
  `not positions` guard, with the documented NumPy ambiguous-truth-value exception before an
  `ApplyMontageCommand`; the three new layout contracts were also red (**3 failed**: 11px effective
  summary grouping gap, Restore still in Summary, and Clear in a separate toolbar). Green focused
  evidence is **129 passed / 1 optional public-fixture skip** for picker, Dataset sidebar, state
  projection and BIDS preparation integration tests; changed-file Ruff check/format and
  `git diff --check` pass. A root-run real tiny MNE-BIDS path also completed
  Scan → Preview → Validate → Apply → real DatasetSidebar / Picker → `standard_1020` Replace, with
  the authoritative result `manual / standard_1020 / 64 of 69 channels`; this is one bounded fixture,
  not a broad BIDS-support claim. Follow-up production delta is **+30/-21, net +9 LOC** across the
  existing dialog and sidebar, with no new owner, command, state machine or compatibility path.
  Root's exact-source visual audit then found the Summary `Close` and `Change layout…` buttons
  touching: the outer summary's zero spacing left the action layout without an explicit horizontal
  policy. The refinement added a shown-geometry red assertion for a minimum **8 logical-px**
  Close→Change gap; it failed at **0px**. The smallest green change sets the existing
  `summary_actions` layout spacing to 8. Picker/sidebar focused evidence is **61 passed**; Ruff
  check/format and `git diff --check` pass. Final clean-source capture targets are
  `build/dev-artifacts/electrode-layout-recovery-handoff-v1/` and
  `build/dev-artifacts/electrode-layout-recovery-handoff-v1-150/`; their manifests must record the
  same exact commit, `dirty: false`, stable source identity and passed surface contracts. Root must
  inspect both Summary and expanded picker at each scale. These remain offscreen development
  evidence, not WSLg acceptance.

- The readiness revision preserves automatic BIDS `name=None` through `StateSnapshotService`; it does not
  expose literal `"None"`. `DatasetSidebar` adapts only the already-published visualization preparation
  state/reason for its bounded active dialog reference, clears that reference after `exec`, and does not add
  polling, a second owner or a mutation route. `PickMontageDialog` updates its retained summary data on
  publication while mapping stays visible; Back then shows the new state. The summary is clamped to 540–560
  logical px while visible and mapping expands to 700 px; the transition test asserts shown summary → mapping
  → Back geometry. Production delta for this readiness revision is **+157/-42,
  net +115 LOC** across `StateSnapshotService`, `DatasetSidebar` and `PickMontageDialog`.
- Red evidence: **5 failed** focused tests reproduced literal `"None"`, ready fallback, pending semantic
  misrender, absent publication refresh and sidebar publication delivery. Root pre-commit focused evidence is
  **128 passed / 1 optional public-fixture skip** for state, picker, Dataset-sidebar and real tiny-BIDS
  preparation integration coverage; scoped Ruff check/format and `git diff --check` pass. The tests also retain
  Cancel persistence, Restore BIDS and training guard coverage. New dirty-source default/150% captures are in
  `build/dev-artifacts/electrode-layout-readiness-v5/` and
  `build/dev-artifacts/electrode-layout-readiness-v5-150/`; these temporary diagnostic captures cover ready
  automatic BIDS, pending, unavailable, manual override and mapping at default and 150%. They show summary
  540×170 / mapping 700×320 logical geometry (and the corresponding 150% pixels) without clipping or an
  oversized blank pending footer. The old/new PNG pixel regions are identical and include their action buttons;
  the apparent omission was a multi-image viewer presentation artifact, not a Qt paint or layout correction.
  They remain dirty-source offscreen evidence, not WSLg acceptance.
- The v3 scoped repair is deletion-first and keeps both entrances on the same reviewed dialog and
  `ApplyMontageCommand` / `ApplicationService` path. It removes the Dataset status `QLabel`, nested
  summary-card/form, `Re-run matching` control/callback and its ignored-saved-mapping path; it adds no owner,
  backend policy, Assistant behavior or second mutation path. For this revision the two production files are
  **+57/-102, net -45 LOC** (`PickMontageDialog` +40/-79; `DatasetSidebar` +17/-23).
- Red evidence for this revision: **5 failed / 50 passed** caught the visible status label, missing natural
  accessible metadata, old summary-action order and Re-run control; a follow-up style contract was red at
  **2 failed / 29 passed** because the screenshot's source/name/facts were visually flat. Green focused UI
  evidence is **54 passed**, including a valid persisted `mapping_v2` schema reopened after a real row edit
  followed by Cancel. Changed-file ruff check, ruff format check and `git diff --check` pass.
- Dirty-source offscreen artifacts were inspected at default scale:
  `build/dev-artifacts/electrode-hierarchy-v3/electrode-layout-bids-summary.png`; and at 150%:
  `build/dev-artifacts/electrode-hierarchy-v3-150/electrode-layout-bids-summary.png`. They show the eyebrow,
  primary layout name, muted facts and one rightmost primary action without clipping. Earlier v2 captures
  also cover the picker and Dataset button surface; the Dataset narrow walkthrough matrix in
  `build/dev-artifacts/electrode-hierarchy-v2-dataset/` passed **36 scenarios**. These are offscreen/dirty
  development evidence only, not native Windows acceptance.
- Remaining handoff work is exact-clean-commit artifact capture, root/UI/data review, canonical
  source-diverse dataset gate, pushed exact-head CI and same-SHA WSLg manual acceptance plus explicit merge
  consent. This branch is a **checkpoint**, never handoff-ready; a source change invalidates acceptance.

Stop at a clean local exact commit plus focused evidence, source-bound artifacts and reviewer/root checkpoint.
Do not push, merge, call it handoff-ready, or claim manual acceptance until root coordinates the remaining
gates and the user WSLg-tests the same exact SHA. A later source change invalidates that acceptance.
