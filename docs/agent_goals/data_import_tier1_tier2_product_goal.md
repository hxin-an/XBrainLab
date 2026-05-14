# Data Import Tier 1/Tier 2 Product Delivery Goal

Goal: Deliver the XBrainLab Data Import label workflow to MVP product quality for
the four supported mainstream EEG/BCI data categories, with polished Load Labels,
Match Labels, Review and Import, BIDS-like handling, and epoch handoff.

This is not a UI polish-only task. This is not an audit-only task. The goal is
complete only when the product flow is usable, reviewable, tested, screenshot
validated, and accepted by both required gate reviewers.

## Required Skills / Docs

Read and follow:

- `AGENTS.md`
- `.agents/skills/pr-branch-governance/SKILL.md`
- `.agents/skills/ui-product-reviewer/SKILL.md`
- `.agents/skills/data-interpretation-reviewer/SKILL.md`
- `.agents/skills/tdd-guard/SKILL.md`
- `.agents/skills/validation-runner/SKILL.md`
- `docs/current.md`
- `docs/target/data_interpretation_system.md`
- `docs/architecture/data_pipeline.md`
- `docs/architecture/backend.md`
- `docs/architecture/ui.md`
- `docs/research/bci_eeg_import_label_design_source.md`
- current Data Import screenshots under `artifacts/ui/data-import-wizard-steps/`

## Branch / Scope Rules

- Do not work directly on `main`.
- Use a UX/product integration branch, not a backend hygiene branch.
- Keep unrelated dirty worktree changes untouched.
- Commit and push each validated checkpoint.
- Do not rewrite unrelated preprocessing, training, visualization, or agent UI.
- Do not create another large planning document. Update canonical docs only when
  implementation truth changes.

## Supported Data Categories For This Goal

Support these four categories as product paths. "Support" means scan, preview,
semantic confirmation, label matching, recipe preservation, Review and Import,
and epoch handoff. It does not mean silent auto-guessing.

### 1. GDF / BNCI / BCI Competition

Examples: BCI Competition IV 2a, Graz motor imagery, BNCI MI family.

Required behavior:

- Detect and preview GDF/internal event tables where available.
- Separate trial start, cue, class label, response, artifact, boundary, run
  marker, ignored event roles.
- Support internal class events for training data.
- Support external label sequence for evaluation/testing data.
- Let the user choose target trial/cue anchors for external sequence matching.
- Show anchor count, label count, artifact trial count, class distribution, and
  mismatch impact.
- Preserve selected trigger, ignored trigger, event role mapping, class map,
  artifact/exclusion choices, and confirmations in the import recipe.
- Epoch handoff must know which event/anchor and class map to propose.

### 2. BIDS-Like Dataset

This goal supports BIDS-like EEG event/metadata workflows. Do not claim full BIDS
validator-level support.

Required behavior:

- Import entry supports scanning a BIDS folder/root, not only single EEG files.
- Show selected scope separately from scan location.
- Show subject, session, task, run, datatype/modality when discoverable.
- Read and preview `events.tsv` columns including `onset`, `duration`,
  `trial_type`, `value`, `response_time`, `HED`, and `channel` when present.
- Read `events.json` levels/descriptions for class display names when present.
- Surface missing sidecars, missing duration, unknown onset/time unit, coverage
  mismatch, and parser warnings as needs-review or blocked action items.
- Preserve BIDS entities and chosen event/label interpretation in recipe.
- Epoch handoff must use BIDS event timing and class map choices.

### 3. Generic EEG Files With Internal Events / Annotations

Examples: EDF+/PhysioNet EEGMMI, EEGLAB `.set`, BrainVision
`.vhdr/.vmrk/.eeg`, MNE FIF annotations/events.

Required behavior:

- Preview internal annotations/markers/events with counts and suggested roles.
- Do not treat boundary, artifact, response, sync, or new-segment markers as
  class labels by default.
- For PhysioNet EEGMMI/EDF+, handle run-dependent semantics such as `T1`/`T2`
  by surfacing run/task mapping for confirmation; never silently assume one
  global class meaning.
- For EEGLAB, surface boundary counts and epoched-vs-continuous status when
  available.
- For BrainVision, separate stimulus, response, sync, new segment, comment, and
  unknown marker roles when available.
- Preserve event role mapping, class names, ignored markers, run-level mapping,
  and confirmation choices in recipe.
- Epoch handoff must use confirmed event roles and run-level mapping.

### 4. External Label Carriers

Examples: `.mat`, `.csv`, `.tsv`, `.txt`, competition labels, labels stored
outside the selected EEG folder.

Required behavior:

- Auto-detect nearby label/event carriers.
- Allow loading label files/folders from separate locations.
- Allow removing auto-detected and user-added label sources.
- Prevent duplicate label sources.
- Handle many label files without nested scrolling or layout collapse.
- For `.mat`, expose candidate variables; do not silently pick the first
  label-like variable when ambiguous.
- For `.txt`, support label sequence review.
- For `.csv/.tsv`, support label column, event order, time/sample placement,
  interval placement, and event-code matching.
- Pair EEG file first, label file second, matching user habit.
- Show mismatch impact and next action when counts, events, or fields do not
  align.
- Provide fallback converted label table guidance when the label file can be
  loaded but cannot be safely matched.
- Preserve label source, target EEG file, label field, placement method, time
  model, duration/end field, event-code mapping, confirmations, and class map in
  recipe.

## Explicit Non-Supported Categories For This Goal

Do not implement full support for these in this goal:

- P300 / ERP hierarchy.
- SSVEP / c-VEP stimulus metadata.
- Clinical long-recording EEG workflows.
- XDF / LSL multi-stream synchronization.
- OpenBCI / BrainFlow device export semantics.
- MOABB dataset adapters or downloaders.
- Arbitrary proprietary logs, nested MAT structs, pickle/object labels, custom
  Python converters beyond clear fallback guidance.

For these categories, the product must be honest: detect when possible, explain
that the workflow is not supported in this MVP, and route to converted label
table / custom recipe guidance. Do not silently guess.

## Required UI Outcomes

Finish these wizard pages to product quality:

- Choose EEG Data.
- Load Labels.
- Review Metadata.
- Match Labels.
- Review and Import.

Hard UI requirements:

- Each step must be task-designed, not a table pasted into a panel.
- Primary action remains visible.
- Cancel/Back/Next placement follows desktop dialog convention.
- No nested scrolling inside table/list sections.
- Long lists must fit through page-level scroll only.
- No duplicate status/check blocks.
- No first-layer debug wording such as anchor/time/granularity/role when a
  task-oriented label is clearer.
- Load Labels must handle many labels, removal, duplicates, empty state, and
  external folders cleanly.
- Match Labels must have polished UIs for internal labels, event order,
  time/sample, interval, event code, fallback conversion, and BIDS-like labels.
- Review and Import must show grouped actionable items with issue, impact, next
  action, and target step.

## Epoch Handoff

Import completion must produce enough recipe/state for epoch setup to prefill or
suggest:

- selected EEG event/anchor,
- class label source,
- class map,
- ignored/artifact events,
- time model and time origin,
- interval onset/duration/end fields,
- BIDS subject/session/task/run context,
- run-dependent class mapping where applicable.

Do not leave import and epoch with separate hidden assumptions.

## Required Gate Subagents

You must use two reviewer subagents as hard gates. These reviewers are not
implementation workers.

### Gate 1: Data Interpretation Gate

Ask this reviewer to inspect code, tests, recipes, screenshots, and artifacts
against the four supported data categories. It must answer:

- Does the implementation support the four required categories without silent
  guessing?
- Are unsupported categories honestly blocked or routed to fallback?
- Are recipes sufficient for replay and epoch handoff?
- Are mainstream semantic risks covered by tests?

If this reviewer returns `not trustworthy` or lists product-blocking findings,
the goal is incomplete until the main agent fixes or explicitly removes the
claim.

### Gate 2: UI Product Gate

Ask this reviewer to inspect screenshots and UI code. It must answer:

- Does each page look like a polished task-oriented desktop wizard?
- Are layout, spacing, alignment, information hierarchy, and action placement
  product-ready?
- Are many-label, BIDS-like, blocked, fallback, and Review and Import states
  readable?
- Does any page still look like debug tables pasted into cards?

If this reviewer returns `not product-ready` or lists product-blocking findings,
the goal is incomplete until the main agent fixes them and regenerates evidence.

## Validation Requirements

Add or update focused tests for:

- labels stored outside the selected EEG folder,
- selected scope vs scan location,
- auto-detected and user-added label source merge/removal/deduplication,
- GDF/BNCI-style internal events and external labels,
- BIDS-like events.tsv/events.json metadata and levels,
- EDF+/PhysioNet run-dependent mapping behavior,
- EEGLAB boundary / BrainVision marker role exclusion where fixtures allow,
- event order, time/sample, interval, event-code placement,
- structured Review and Import action items,
- recipe preservation and epoch handoff,
- UI/dialog layout states including many labels and no nested-scroll sections.

Run and report:

- focused backend tests,
- focused UI/dialog tests with `QT_QPA_PLATFORM=offscreen`,
- screenshot capture scripts for all required states,
- product smoke: Import file/folder/BIDS-like folder -> Load label folder ->
  Review Metadata -> Match Labels -> Review and Import -> Epoch handoff,
- `git diff --check`,
- `ruff`/pre-commit or equivalent checks for changed Python files.

## Required Screenshot Evidence

Regenerate and inspect screenshots for:

- Choose EEG Data normal and many-file states.
- Load Labels empty, auto-detected, user-added, many labels, duplicate, removal.
- Review Metadata normal and Smart Parse states.
- Match Labels internal events.
- Match Labels external event order.
- Match Labels time/sample.
- Match Labels interval.
- Match Labels event code.
- Match Labels fallback converted table.
- BIDS-like folder review.
- Review and Import normal, needs-review, blocked.
- Epoch handoff/prefill state.

## Completion Rules

The goal is complete only if:

- all four supported data categories are implemented to the support definition,
- unsupported categories are not claimed and have clear fallback/blocked behavior,
- both gate subagents return pass/acceptable without product-blocking findings,
- focused tests and product smoke pass,
- screenshot evidence is regenerated and manually inspected,
- recipe and epoch handoff are verified,
- branch is committed and pushed,
- remaining risks are explicit with file references.

Do not say "done" if any gate fails. Say `incomplete` and continue fixing.

## Final Report Must Include

- Complete or incomplete.
- Branch and commit hashes.
- Supported data categories and evidence.
- Unsupported categories and fallback behavior.
- UI gate verdict and fixes made from its findings.
- Data gate verdict and fixes made from its findings.
- Tests added/changed.
- Validation commands and results.
- Screenshot artifact paths.
- Remaining risks or limitations.
- Files intentionally not touched.
