# XBrainLab Usage Refresh Handoff

Date: `2026-05-04 18:06 UTC+08`

This handoff exists because the current runner is stopping for usage refresh.
Resume in the active repo:

```text
/mnt/d/workspace_v2/projects/lab/XBrainLab
```

## Hard Boundaries

- Do not push.
- Do not touch or revert `.vscode/settings.json`.
- Do not touch or revert root `settings.json`.
- Do not run destructive git commands.
- Do not mark the product goal complete while known blockers remain.
- Keep API / Gemini / remote LLM out of the product execution path.
- Do not use or download China-source models.
- Do disk / VRAM / cache preflight before any model download.
- Keep local model cache within the existing limits unless the user explicitly
  approves otherwise.
- Commit each verified slice locally.

## Worktree Snapshot

Latest local commits at handoff:

```text
0da24db backend: apply reviewed sequence labels during import
626b606 backend: apply reviewed timestamp labels during import
15c242d backend: surface import format boundaries
f49af63 ui: add label carrier review to import wizard
3341d53 ui: guard headless 3d visualization
a41770f ui: capture visualization render walkthrough
c9ea93a docs: refresh usage handoff
f9f0956 assistant: capture training completion walkthrough
7936328 agent: preserve training output dir
```

Expected dirty files after the latest committed product slice:

```text
 M .vscode/settings.json
 M settings.json
```

These two files are protected user / workspace settings. Ignore them unless the
user explicitly asks otherwise. Do not stage them in the handoff commit.

## Latest Verified Product Slice

The latest committed product slice is:

```text
0da24db backend: apply reviewed sequence labels during import
```

It extended Data Interpretation apply so reviewed external labels are no longer
recipe-only in the narrow safe cases:

- timestamp CSV / TSV / BIDS events carriers can be applied during
  `apply_interpretation` when there is one loaded EEG file, one reviewed
  carrier, selected label field and anchor, confirmed interpretation, and
  `seconds` or `relative_time` time model;
- reviewed MAT / TXT trial-order sequence carriers can be applied when there is
  one loaded EEG file, one carrier, selected label field, confirmed class map,
  `trial_order` time model, and trial granularity;
- timestamp mode uses existing `dataset.apply_labels_batch()`;
- sequence mode uses existing `dataset.apply_labels_legacy()`;
- both paths update `AppliedInterpretation.label_imports`, `label_apply`
  diagnostics, and recipe trace entries such as `label_import:timestamp:1` or
  `label_import:legacy:1`;
- unsafe cases still skip with a reason instead of guessing.

Immediately preceding Data Interpretation slices:

- `f49af63` added editable label carrier review rows to the import wizard and
  persisted `label_carrier_plan` through preview / apply / recipe.
- `15c242d` surfaced format capability boundaries for GDF, EDF / BDF, EEGLAB,
  BrainVision, MNE FIF, MAT labels, CSV / TSV / BIDS events, TXT, and blocked
  XDF / LSL stream-selection cases.
- `626b606` applied reviewed timestamp labels during import and refreshed the
  UI replay artifact with `label_apply.status=applied`.

Latest validation already recorded:

```bash
poetry run pytest --capture=sys tests/unit/backend/application/test_application_service.py::test_apply_interpretation_applies_reviewed_mat_sequence_label_carrier tests/unit/backend/application/test_application_service.py::test_apply_interpretation_applies_reviewed_timestamp_label_carrier -q
poetry run ruff check XBrainLab/backend/application/service.py tests/unit/backend/application/test_application_service.py
poetry run basedpyright XBrainLab/backend/application/service.py tests/unit/backend/application/test_application_service.py
poetry run ruff format --check XBrainLab/backend/application/service.py tests/unit/backend/application/test_application_service.py
poetry run mkdocs build --strict
git diff --check
```

Expected results:

- focused MAT / timestamp label apply tests: `2 passed`
- targeted `ruff`: pass
- targeted `basedpyright`: `0 errors, 0 warnings, 0 notes`
- targeted format check: pass
- mkdocs strict build: pass with the existing MkDocs Material warning
- diff check: pass

## Current Evidence Highlights

- True local ChatPanel controlled tiny training completion evidence exists under
  `artifacts/ui/chatpanel-local-training-completion/`.
- Visualization render evidence exists under
  `artifacts/ui/visualization-render/`; Saliency Map, Spectrogram, and
  Topographic Map render in a true MainWindow walkthrough after a tiny CPU
  training run.
- Headless/offscreen `3D Plot` is guarded and shows a human-readable blocked
  reason instead of creating a PyVista plotter and crashing.
- Data Interpretation replay artifacts exist:
  - `artifacts/ui/data-interpretation-preview.png`
  - `artifacts/ui/data-interpretation-applied.png`
  - `artifacts/ui/data-interpretation-replay.json`
- The replay JSON now includes review notes, label carrier rows, reviewed
  choices, timestamp label apply diagnostics, and recipe trace evidence.

## Do Not Redo Without Reason

- Do not redo the true ChatPanel training-completion walkthrough unless local
  model agent execution, training command surface, evaluation, saliency, or
  visible ChatPanel feedback changed.
- Do not redo the visualization render walkthrough unless visualization panel,
  training state, saliency, or render contract changed.
- Do not redo label carrier wizard review / format boundary work unless
  `data_interpretation.py`, wizard result mapping, scan format detection, or
  recipe serialization changed.
- Do not rerun full local LLM x3 eval for documentation-only edits. Rerun
  targeted eval if prompt / schema / parser / verifier behavior changes, then
  rerun full primary / fallback x3 before thesis-candidate claims.

## Current Known Blockers

Do not claim product completion yet.

- `ApplicationStateSnapshot.interpretation` may still omit the newest
  `label_carrier_plan` and `format_capabilities` truth; agent / MCP /
  `query_state` should expose the same import truth as UI / recipe.
- Full embedded post-load label import wizard is still incomplete.
- Multi-file label mapping is not automatic.
- Raw-event-anchor-specific GDF / MAT alignment is not modeled; only the narrow
  reviewed trial-order sequence path is applied.
- Full all-format manual compatibility matrix and XDF / LSL stream parser remain
  incomplete.
- Windows Desktop launcher human click-through / WSLg multi-monitor behavior has
  not been manually verified.
- Interactive desktop 3D / PyVista render has not been verified; only headless
  blocked UX is proven.
- MCP Inspector GUI / release config is not completed.
- External thesis experiment runner / statistical report is not done.
- Thesis-candidate local LLM report still needs primary / fallback x3 evidence
  organization before making thesis-ready claims.

## Immediate Resume Plan

1. Re-check worktree:

   ```bash
   git status --short
   ```

   Only `.vscode/settings.json` and root `settings.json` should be dirty unless
   the handoff docs have not yet been committed.

2. Inspect state snapshot propagation:

   ```text
   XBrainLab/backend/application/state.py
   XBrainLab/backend/application/service.py
   XBrainLab/backend/application/automation.py
   XBrainLab/llm/tools/application_surface.py
   tests/unit/backend/application/test_application_service.py
   ```

3. Recommended next product slice:

   ```text
   Data Interpretation import truth in shared state snapshot
     -> label_carrier_plan visible in ApplicationStateSnapshot.interpretation
     -> format_capabilities visible in ApplicationStateSnapshot.interpretation
     -> query_state / automation / agent / MCP see the same truth
     -> focused backend tests
     -> docs / records update
     -> local commit
   ```

4. After that, continue with product blockers in this order:

   - embedded label import wizard hardening;
   - Windows Desktop launcher human click-through / WSLg multi-monitor
     verification;
   - MCP Inspector GUI / release config;
   - interactive desktop 3D render verification if a real OpenGL desktop session
     is available;
   - external thesis experiment runner / statistical report;
   - primary / fallback local LLM x3 thesis-candidate eval report.

## Claim Boundary

Current evidence supports:

- ApplicationService-backed Data Interpretation scan -> preview -> validate ->
  confirm/apply -> recipe baseline;
- import wizard metadata / class-map / label carrier review;
- format-specific supported / needs-review / blocked boundaries;
- narrow reviewed timestamp and trial-order sequence label apply during import;
- true local ChatPanel single-command-per-turn workflow through controlled tiny
  training completion;
- true MainWindow post-training Matplotlib visualization render evidence;
- headless 3D blocked UX.

Current evidence does not support:

- completed desktop product;
- completed mature import wizard label editor;
- completed multi-file or raw-event-anchor label alignment;
- completed Windows Desktop human click-through;
- completed interactive desktop 3D render;
- completed MCP Inspector / release configuration;
- completed external thesis experiment package;
- thesis-ready local LLM evidence.

Goal status must remain incomplete.
