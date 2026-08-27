# XBrainLab Now

最後更新：`2026-08-27`

## Active slice：Electrode Layout BIDS polish

**Identity.** Worktree `/tmp/xbrainlab-electrode-layout-v1`，branch
`feature/electrode-layout-dataset-v1`，base `origin/main` =
`2c51d7b1e6ff83475f285f0db331becd3f87f5c1`，current head =
`c8e6d475bef713ba64cc780f05bfc43b012b98fb`，Draft PR #58 to `main`。
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
  blank。永不 auto-apply；Cancel 零 mutation。
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
- **Reuse/deletion first:** retain both visible Dataset and Visualization Electrode Layout entrances while
  reusing their same dialog/open route, current state query, projection, retained BIDS snapshot and
  `ApplyMontageCommand`; remove/reduce only generic BIDS information-modal branching and duplicated
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
- Current repair keeps both entrances on the existing dialog and command path; it adds truthful Dataset status,
  summary card/action hierarchy, conservative non-BIDS prefill and schema-bound reviewed mapping reuse. Current
  total production diff is the complexity-review value above; this repair itself changes only the existing
  `DatasetSidebar` and `PickMontageDialog` presentation owners.
- Green evidence: focused UI/application/data run is **78 passed / 345 deselected**; architecture montage
  ownership sweep is **6 passed / 246 deselected**; ruff check/format and `git diff --check` pass. The public
  BIDS fixture plus montage-preparation suite is included in the 78 tests; its 9 MNE warnings are pre-existing
  loader/type warnings, not test failures.
- Offscreen artifacts inspected under `/tmp/xbrainlab-electrode-artifacts/`: BIDS current, manual restore,
  BIDS picker, non-BIDS conservative prefill, sidebar loading and sidebar error. They demonstrate hierarchy
  and no clipping in the captured widths; they are not WSLg/native manual acceptance.
- Remaining handoff work: canonical source-diverse dataset gate, pushed exact-head CI, independent UI/data
  review and WSLg manual acceptance. Therefore this branch remains a **checkpoint**, not handoff-ready.

Stop at a pushed exact commit plus focused evidence, source-diverse dataset evidence, reviewer/root
checkpoint and Draft PR update. Do not merge, call it handoff-ready, or claim manual acceptance until the
user has WSLg-tested the same exact SHA and explicitly approves merge. A later source change invalidates
that acceptance.
