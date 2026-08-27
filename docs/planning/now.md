# XBrainLab Now

最後更新：`2026-08-27`

## Active slice：Electrode Layout BIDS polish

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

### 明確 non-goals

- 不改 shared Information／Warning／Error modal style、其他 dialog framework 或全站樣式。
- 不改 Assistant prompt/controller/eval、`set_montage` publication policy、tool schema 或 GUI handoff
  contract；它們屬 Accuracy 支線。
- 不在 app 內加入 `Suggested` 標籤、教學卡、help text 或新 tooltip；review-before-apply 的說明留給
  後續外部使用者文件。
- 不改 Epoch channel axis、BIDS import/label semantics、trainer policy、資料掃描效能或 generic
  persistence architecture。

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

## Review, stop condition and UI approval

The user has explicitly approved this visible UI scope: BIDS Electrode Layout, Dataset status, mapping
hierarchy and non-BIDS safe prefill; both current entrances remain. Builder supplies exact HEAD, diff/LOC,
focused tests and artifacts. Independent UI reviewer checks hierarchy, contrast, wrapping, clipping,
keyboard/focus, dialog geometry, one-primary-action, default/narrow/DPI/loading/error/blocked/cancel states.
Data reviewer verifies selected-run provenance, partial/limited semantics, schema reuse and zero-mutation
failure paths. Root independently audits the exact SHA and accepts only in-scope blocking findings.

### Current implementation checkpoint

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
