# XBrainLab Now

最後更新：`2026-09-03`

## Current baseline

`77d125ef3b94648337c8cfb6df0e3bf614b6a435` 是目前 `main`／`origin/main` 的產品基線，已合併
PR #109 的 Windows source bootstrap；其歷史、exact evidence 與使用者 Windows 手測／merge 批准由 Git
與 PR 記錄保存，不再作為 active plan。Repo-root `settings.json` 的本機修改由使用者擁有，絕不可
stage、commit、revert、覆寫或隱藏。

## Active slice — SSVEP import review re-preview routing

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

### Outcome and user-visible contract

- Re-preview 後只信任 fresh backend `ValidationDecision`：`blocked` 時以 typed actionable target reopen；本
  slice 的 class/event blocker 必須 reopen `Match Labels`，並保留該 decision/action cards。`safe` 和
  `needs_confirmation` reopen `Review and Import`，讓使用者對新 candidate 作 final confirmation。
- `ApplyInterpretationCommand` 不得對 blocked candidate 執行；既有 fresh-final-review confirmation boundary
  必須保留。
- status bar 顯示 concise backend-truth-aligned recovery outcome（例如 review updated and current task），不以
  前端另造 validation policy。loading、cancel、failed 與 repeat lifecycle 保持現有 owner。

### Scope, non-goals, assumptions, ownership

- Scope 僅限 coordinator 的 fresh-decision-to-reopen-step routing、直接 focused regression tests、此 plan，和
  必要的 offscreen walkthrough artifact。production files 預計只有
  `XBrainLab/ui/panels/dataset/data_interpretation_action_coordinator.py`；tests 預計只有
  `tests/unit/ui/dataset/test_interpretation_async_flow.py`。
- 不改五階段、dialog layout、copy hierarchy、backend Data Interpretation policy／payload schema、Apply semantics、
  raw loader、recipe schema、MOABB dependency、dataset download、filter、Assistant fallback 或 data split。
- 此 slice 不宣稱 MAMEM1／Wang2016 raw MATLAB import、Guttmann raw BDF/sidecar import、target-to-frequency/
  phase/code recipe semantics或「SSVEP 可用」。這些需要獨立 decision、adapter 與 source-diverse real-data gate。
- Owner before/after 不變：`DataInterpretationCommandService` owns scan/preview/validate/apply state and decision;
  `DataInterpretationActionCoordinator` only owns async UI command orchestration; preview dialog renders typed
  result. 不新增 owner、state machine、module或 compatibility path。
- Deletion/reuse first：reuse existing `_repreview_interpretation_async` and typed `action_items`; do not add a
  parallel wizard/router or frontend inference. 預估 production net `+20–45 LOC`（或更少），1 production file。
- UI approval 已存在：使用者說「目前 review and import 這五個階段我很滿意不要大改」，並在討論 status bar
  後回覆「我覺得可以」。本 slice 只在該批准下修正 recovery routing/status，仍需 focused screenshot/walkthrough
  與後續 Windows native human acceptance。

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

### Stop condition

- Stop rather than expand scope if fresh backend output lacks typed action items/target, targets a stage outside the
  existing five, requires backend policy/schema changes, makes Apply reachable for blocked input, changes more than
  the stated one production file, or cannot be observed by the focused test.
- Do not proceed into raw SSVEP adapters, target-frequency/phase semantics, data download, classifier work, filter,
  Assistant fallback or splitting cleanup. After this slice, claim only that the existing import wizard routes a
  fresh blocked review to its backend-provided recovery stage; do not claim SSVEP import/training readiness.
