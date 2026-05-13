# Data Import Tier 1 / Tier 2 Product Goal

Last updated: 2026-05-13

## Objective

Deliver the Data Import label workflow to a product-usable MVP for the agreed
Tier 1 / Tier 2 dataset classes only. The work is not complete until the
backend contract, wizard UI, recipe trace, epoch handoff, tests, screenshots,
and docs all agree on what is supported and what is intentionally unsupported.

This is an implementation goal, not a design note. Do not stop at inventory,
mock screenshots, or a visually acceptable panel that cannot actually apply the
selected label rules.

## Supported Dataset Classes

Complete support means scan, preview, user confirmation, apply/import, recipe
save/reload, UI review, and focused tests for these classes.

### Tier 1

1. GDF / BNCI / BCI Competition style datasets
   - EEG files may contain internal events.
   - Training files may have usable internal class events.
   - Evaluation/test files may need external label carriers such as `.mat` or
     text sequence labels.
   - Trial start, cue/class event, artifact, boundary, and ignored events must
     be distinguishable in the UI and backend evidence.

2. BIDS-like EEG folders
   - Support BIDS-like folder scan and `events.tsv` / `events.json` label/event
     interpretation.
   - Show subject/session/task/run metadata review.
   - Support `trial_type`, `value`, onset, duration, and sidecar levels where
     present.
   - Missing sidecar or incomplete BIDS metadata must be explicit warnings or
     action items.
   - Do not claim full BIDS validator-level support.

### Tier 2

3. Generic EEG files with internal events or annotations
   - Cover common internal event/annotation surfaces used by EDF+/PhysioNet,
     BrainVision markers, EEGLAB events, and MNE/FIF annotations where the
     current IO stack can read them.
   - Suggested label events must be generated from backend evidence, not fake UI
     examples.
   - Response, artifact, boundary, system, comment, and run markers must not be
     silently treated as class labels.
   - Run-dependent event semantics such as PhysioNet `T1` / `T2` must require a
     confirmable run/task mapping before supervised training can be trusted.

4. External label carriers
   - Support `.mat`, `.csv`, `.tsv`, and `.txt` carriers.
   - Labels may live outside the selected EEG folder.
   - Single-file import must not silently pull sibling EEG files into selected
     scope, but may auto-detect same-stem / nearby label carriers.
   - Supported placement modes:
     - EEG event order
     - label time
     - label interval
     - label event code
   - Placement choices, selected columns/variables, selected EEG events,
     class names, excluded events, confirmations, and warnings must be preserved
     in the import recipe.

## Explicit Non-Goals

Do not implement or claim support for these in this goal:

- full BIDS compliance or BIDS validator parity;
- P300 / ERP target hierarchy, row/column speller semantics, or target /
  non-target repetition logic;
- SSVEP / c-VEP frequency, phase, symbol, or stimulus metadata semantics;
- clinical long-recording workflows such as seizure intervals, sleep staging,
  clinical notes, or long-duration memory optimization;
- XDF / LSL multi-stream synchronization;
- OpenBCI / BrainFlow device-export semantics;
- MOABB dataset adapters;
- arbitrary proprietary logs, nested unknown MAT schemas, pickle files, or
  executable custom Python converters.

Fallback guidance is allowed when a carrier cannot be interpreted, but it must
be a clear blocked state with an example of the required table shape. Do not run
user-provided Python as part of this goal.

## Required Product Behavior

### Load Labels

- Rename the user-facing step to `Load Labels`.
- Auto-detected and user-added label carriers must be shown together with clear
  source language.
- Both auto-detected and user-added carriers must be removable.
- Duplicate carriers must not be added twice.
- `Load label file` and `Load label folder` must support labels outside the EEG
  folder.
- Do not show confusing filler rows such as `Will scan file` when the user
  already sees the loaded carrier.

### Match Labels: Labels Inside EEG Files

- The source selector must clearly distinguish `Labels inside EEG files` from
  `Loaded label files`.
- If this source is selected, class candidates must come from internal EEG
  events/annotations, not from loaded label files.
- The UI must show:
  - suggested training labels;
  - other EEG events not currently used as labels;
  - event code/name when reliable;
  - suggested use;
  - suggestion evidence;
  - count and file coverage.
- Users must be able to move events both ways: use as label and not a label.
- Class names should be editable directly in the table when class names are
  known or required.
- Sort displayed class names and event rows deterministically.
- Candidate logic must be testable backend behavior, not screenshot-only
  assumptions.

### Match Labels: Loaded Label Files

- Pairing board must read left-to-right as `EEG file -> Label file -> Status`.
- Users choose the label file for each EEG file. Status belongs next to the
  label side, not as the primary thing being chosen.
- Same-base-name pairing can be the default, but manual correction must be
  possible.
- If pairing or label interpretation fails, hide downstream placement tables and
  show a concise blocked fallback card with a `View examples` dialog.
- The fallback card must explain:
  - XBrainLab loaded the file but cannot identify label rows yet;
  - each row must describe one label, trial, event, or interval;
  - there must be one label column;
  - there must be one placement column such as `event_code`, `onset_seconds`,
    `sample`, or interval columns.

### Placement Modes

For loaded label files, each placement mode needs a mode-specific UI and backend
apply path.

- EEG event order:
  - user selects which EEG event rows receive labels;
  - allow multiple target event codes when valid;
  - show selected event count, label row count, excluded events, and unmatched
    count;
  - support artifact/excluded trials without silently shifting labels.
- Label time:
  - user selects label value field and time field;
  - time basis must be explicit enough for apply and recipe;
  - preview must show where sample/time labels will land.
- Label interval:
  - user selects label value field plus onset and duration/end/stop/offset
    fields;
  - apply must honor the selected duration/end field, not only a hard-coded
    `duration` column.
- Label event code:
  - user selects label value field and event-code field;
  - apply must map label rows onto matching EEG event codes, not just preview
    the rule.

Avoid first-layer terms such as `Anchor`, `Granularity`, `Role`, or `Label unit`.
Use task language: `Read labels from`, `Use as`, `Place labels by`,
`Target EEG events`, `Suggestion evidence`, and `Check`.

### BIDS-Like Events

- Detect `events.tsv` as a label/event carrier.
- Read available event columns and `events.json` levels when present.
- Missing `events.json`, missing onset, or ambiguous duration must become
  structured warnings/action items.
- The UI should have a BIDS-like review state that is explicit about being
  BIDS-like, not full BIDS support.

### Review Metadata

- Review subject/session/task/run compactly.
- Smart Parse and manual edits must write choices into the import recipe.
- Metadata warnings should be clear without making optional task/run fields feel
  mandatory unless downstream split/training requires them.

### Review And Import

- Show grouped actionable items, not a flat warning list.
- Each item must include issue, impact, next action, and target step.
- Primary import/apply action must remain visible.
- Normal, needs-review, and blocked states must each have screenshot evidence.
- The final review must summarize the chosen label source, pairing, placement
  mode, selected target events/fields, class mapping, and remaining limitations.

### Epoch Handoff

- The applied interpretation must expose enough structured state for epoch setup
  to prefill or constrain target events / labels / interval timing.
- Do not redesign the full epoch workflow in this goal, but prevent Data Import
  from applying label semantics that epoch cannot later understand.
- Add at least one focused test or smoke artifact proving the selected label
  interpretation is visible to epoch-related state or command readiness.

## Backend Requirements

- Keep UI, in-app agent, headless scripts, and MCP aligned with
  `ApplicationService / Command API`.
- Extend the Data Interpretation contract only through structured scan,
  candidate, preview, validation, apply, and recipe fields.
- Merge auto-discovered and user-added label carriers in preview.
- Preserve:
  - label source;
  - metadata parser choices and manual overrides;
  - file pairing;
  - selected label field / variable;
  - placement mode;
  - selected time/event/interval fields;
  - selected target EEG events;
  - class map and class names;
  - run-dependent mappings;
  - confirmations and structured action items.
- Recipe reload must reconstruct preview and validation; it must not bypass
  review by blindly applying stale choices.
- Unsupported classes must produce explicit blocked/limited states, not silent
  guesses.

## UI Quality Bar

- The wizard must be task-oriented panels, one step at a time.
- No nested scrolling inside table sections at normal desktop size.
- Footer actions must stay visible. `Cancel` stays on the left; `Back` and the
  primary next/import action stay on the right.
- Dense data is allowed, but every panel must have clear hierarchy, aligned
  labels, and readable spacing.
- Do not show fake backend-rendered data in screenshots. If evidence is shown,
  it must come from code that can run.
- Generate full screenshots at normal desktop size for:
  - Choose EEG Data;
  - Load Labels empty;
  - Load Labels auto-detected;
  - Load Labels user-added;
  - Load Labels duplicate/removal state;
  - Load Labels many carriers;
  - Review Metadata with Smart Parse;
  - Match Labels internal EEG labels;
  - Match Labels loaded labels: event order;
  - Match Labels loaded labels: label time;
  - Match Labels loaded labels: label interval;
  - Match Labels loaded labels: label event code;
  - Match Labels BIDS-like events;
  - conversion fallback card and example dialog;
  - Review and Import normal;
  - Review and Import needs-review;
  - Review and Import blocked;
  - one epoch handoff / prefill evidence artifact.

## Required Tests And Validation

Add or update focused tests for:

- labels stored outside the selected EEG folder;
- selected EEG scope versus scan location;
- single-file import not importing sibling EEG files;
- auto-detected label carrier removal and duplicate prevention;
- internal EEG label source not reading loaded-label class values;
- suggested-label evidence classification;
- moving events between label and non-label groups;
- run-dependent `T1` / `T2` mapping confirmation and recipe persistence;
- BIDS-like `events.tsv` / `events.json` columns, warnings, and action items;
- external label placement by event order;
- external label placement by label time;
- external label placement by interval, including selected end/stop/offset fields;
- external label placement by event code apply path;
- structured Review and Import action items;
- UI/dialog footer visibility and no nested table scrolling;
- product smoke:
  `Import file/folder -> Load label folder -> Review metadata -> Match labels -> Review and Import`.

Recommended validation commands should include the focused backend tests, focused
UI tests with `QT_QPA_PLATFORM=offscreen`, screenshot scripts, lint for touched
Python files, `git diff --check`, and `poetry run mkdocs build --strict`.

## Gate Review

Before final completion, use two independent reviewers if subagents are
available:

1. Data Interpretation reviewer
   - Judge whether the four supported dataset classes are truly covered by
     backend behavior, recipe persistence, tests, and explicit unsupported
     boundaries.
2. UI Product reviewer
   - Judge whether the wizard is visually clean, task-oriented, readable at
     normal desktop size, and supported by real screenshots.

If either reviewer returns a blocking finding, fix it and ask for review again.
Do not summarize a blocked review as success.

## Branch / PR Rules

- Work on a Data Import branch, not directly on `main`.
- Preserve unrelated dirty worktree changes.
- Keep commits reviewable by slice.
- Push validated checkpoints.
- Do not mix this goal with backend-wide cleanup, docs-site redesign, local LLM,
  MCP hardening, or training UI redesign.

## Completion Criteria

This goal is complete only when:

- the four supported dataset classes have implemented backend/UI behavior;
- unsupported classes are explicit non-goals with blocked/limited user feedback;
- recipe trace preserves the choices needed to reproduce the import;
- epoch handoff has at least minimal structured evidence;
- required tests pass;
- screenshot artifacts exist and are readable;
- canonical docs are updated without overclaiming;
- both gate reviewers pass without blocking findings;
- branch is committed and pushed;
- final report includes exact validation commands, changed files, pushed commit,
  remaining risks, and unsupported classes.

## Goal Prompt

Use this prompt for a new goal or a new agent conversation:

```text
Goal: Deliver the XBrainLab Data Import Tier 1 / Tier 2 label workflow to product-usable MVP quality by following docs/agent_goals/data_import_tier1_tier2_product_goal.md.

Work in /mnt/d/workspace_v2/projects/lab/XBrainLab. First read AGENTS.md, docs/current.md, docs/target/data_interpretation_system.md, docs/research/bci_eeg_import_label_design_source.md, docs/architecture/data_pipeline.md, docs/validation/README.md, and the goal file.

Implement only the four supported dataset classes in the goal: GDF/BNCI-style internal+external labels, BIDS-like events.tsv/events.json, generic EEG internal events/annotations, and MAT/CSV/TSV/TXT external label carriers. Treat P300/ERP hierarchy, SSVEP/c-VEP semantics, clinical long recordings, XDF/LSL sync, OpenBCI/BrainFlow semantics, MOABB adapters, proprietary logs, nested unknown MAT schemas, pickle, and executable custom Python converters as explicit non-goals with clear blocked/limited UI states.

Do not stop at a plan, inventory, screenshots, or mock UI. Implement backend scan/preview/validate/apply/recipe behavior, Load Labels, Match Labels, Review Metadata, Review and Import, minimal epoch handoff, focused tests, screenshots, and canonical docs until the goal completion criteria are met.

Use ApplicationService / Command API as product truth. Preserve unrelated dirty worktree changes. Do not work directly on main. Commit and push validated checkpoints.

Before final completion, use two reviewers if subagents are available: one Data Interpretation reviewer for mainstream format coverage and one UI Product reviewer for layout/product quality. Blocking findings must be fixed and reviewed again. Final report must include exact validation commands/results, screenshots/artifacts, docs updated, commit hash, pushed branch, unsupported boundaries, and remaining risks.
```
