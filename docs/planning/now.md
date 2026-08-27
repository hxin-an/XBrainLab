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
- Dataset 的 Electrode Layout 只有按鈕／tooltip，缺少可掃讀的 current layout、coverage 與 loading
  state。BIDS 和 manual layout 的差異及可 restore 的 retained snapshot 不夠清楚。
- 非 BIDS channel mapping 已可工作，但未將「保守預填、人工確認、不跨 dataset 誤用」明確收斂成
  deterministic product behavior。
- Review found that the existing Visualization convenience entrance was deleted instead of delegating to
  the Dataset route, and a manually reviewed duplicate electrode selection could still be persisted. Both
  are direct workflow/data-integrity defects within this slice.
- 既有可逆 BIDS lifecycle、command boundary、generation fence 及兩入口已存在；本 slice 是視覺與
  reviewed mapping polish，不能重建第二套 montage owner 或 mutation path。

### Outcome 與 scope

- Dataset `Channels` 正下方顯示非互動狀態：`BIDS layout · N/N positioned`、
  `Manual layout · N/N positioned`、`Preparing BIDS layout…` 或 `No electrode layout`。
- Dataset／Visualization 兩入口都開同一 dialog，維持同一 `ApplyMontageCommand` /
  `ApplicationService` mutation path。
- Summary 成為正式 status card：`Electrode Layout`、BIDS context、layout status、coverage、coordinate
  frame；每個 state 一個 primary action。BIDS current 為 `Close` + `Change layout…`；manual override
  retained BIDS snapshot 為 `Choose another layout…`、`Close` + `Restore BIDS layout`；training lock 仍可
  查看、但不可變更並顯示原因。
- Picker 固定 hierarchy：layout selector → table toolbar (`Re-run matching`、`Clear mapping`) →
  mapping table → footer。BIDS footer 為 Back／Cancel／Replace，non-BIDS 為 Cancel／Apply；每一頁僅一個
  blue primary action。
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

Current worktree relative to `origin/main` touches **15 production files**, `+880/-411/net +469` LOC，
同時超過 12 production files 與 net +300，必須在此後的所有 polish 修改前保持 complexity review。

- **Owners before/after:** `ApplicationService` remains the only authoritative montage mutation/
  publication owner; `BidsMontagePreparationCoordinator` remains bounded async preparation owner;
  `DatasetSidebar` / `MontagePickerDialog` remain presentation and human confirmation only. No new owner,
  command, public class, state machine, compatibility path or persistence authority is permitted.
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

1. Establish/extend smallest red UI/behavior tests for Dataset status projection, summary action hierarchy,
   non-BIDS unique/tied/ambiguous prefill, exact-schema reuse, and Cancel zero mutation. Characterize any
   existing behavior-preserving move before structural edits; do not manufacture mock choreography.
2. Update presentation using existing dialog/sidebar owner boundaries only; retain command path and apply
   the minimal backend projection needed for truthful status/pre-fill.
3. Run focused backend/application tests for BIDS snapshot lifecycle, capability/trainer guard, generation
   fence and command confirmation; run focused UI dialog/sidebar tests for default, loading, error, partial,
   locked, cancel, repeat and narrow-width states.
4. Capture and inspect offscreen artifacts for BIDS current, manual override/restore, non-BIDS partial
   mapping, loading/error and narrow/DPI layout. Offscreen is evidence only; WSLg manual acceptance remains
   required before merge.
5. Run required source-diverse dataset gate because this is BIDS/import/visualization-adjacent. Record exact
   commands, artifact paths and their claim boundary; do not claim handoff-ready when any canonical gate is
   unavailable or fails.

## Review, stop condition and UI approval

The user has explicitly approved this visible UI scope: BIDS Electrode Layout, Dataset status, mapping
hierarchy and non-BIDS safe prefill; both current entrances remain. Builder supplies exact HEAD, diff/LOC,
focused tests and artifacts. Independent UI reviewer checks hierarchy, contrast, wrapping, clipping,
keyboard/focus, dialog geometry, one-primary-action, default/narrow/DPI/loading/error/blocked/cancel states.
Data reviewer verifies selected-run provenance, partial/limited semantics, schema reuse and zero-mutation
failure paths. Root independently audits the exact SHA and accepts only in-scope blocking findings.

### Current implementation checkpoint

- Red baseline: the two focused UI files reported **6 failed / 46 passed** before repair: no sidebar status
  projection, old BIDS primary-action hierarchy, and unsafe tie/duplicate/schema-reuse mapping behavior.
- Reviewer-focused red characterization then found the deleted Visualization entrance, duplicate persistence,
  and non-BIDS first-row/`last_montage` fallback. The extended focused red run was **4 failed / 42 passed**;
  its tests now require the shared Dataset route, duplicate rejection, `Select layout` for ties/no-match,
  disabled Apply, zero persistence, and recovery after an explicit selection.
- Current repair keeps both entrances on the existing dialog and command path. It adds truthful Dataset status,
  the card/action hierarchy, conservative non-BIDS prefill and schema-bound reviewed mapping reuse; it does
  not add an owner or a second mutation path. At final commit preparation, the production diff against
  `origin/main` is **16 files, +964/-419, net +545 LOC**, so the complexity review remains active.
- Green evidence at commit preparation: the focused UI slice is **163 passed**; application/state montage
  coverage is **19 passed / 319 deselected**; BIDS preparation plus public fixture coverage is
  **34 passed / 1 skipped** (one optional public fixture is not installed) with **9 MNE loader/type warnings**;
  montage architecture ownership is **6 passed / 246 deselected**. Changed-file ruff and `git diff --check`
  must be repeated after the final documentation update.
- The preliminary offscreen preview under `/tmp/xbrainlab-electrode-preview/` is tied to dirty source and is
  intentionally non-authoritative. After a clean local exact commit, regenerate a source-bound manifest with
  BIDS current/manual/picker, non-BIDS, Dataset loading/error, both entrances, narrow geometry and explicit
  150% offscreen captures. Inspect those images before asking root for review.
- Remaining handoff work: the exact-commit artifact capture, root/UI/data review, canonical source-diverse
  dataset gate, pushed exact-head CI, and WSLg manual acceptance. Therefore this branch remains a
  **checkpoint**, not handoff-ready.

Stop at a clean local exact commit plus focused evidence, source-bound artifacts and reviewer/root checkpoint.
Do not push, merge, call it handoff-ready, or claim manual acceptance until root coordinates the remaining
gates and the user WSLg-tests the same exact SHA. A later source change invalidates that acceptance.
