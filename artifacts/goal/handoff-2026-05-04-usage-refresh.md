# XBrainLab Usage Refresh Handoff

Date: `2026-05-04 18:41 UTC+08`

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
- Keep local model cache within the existing limits unless the user explicitly approves otherwise.
- Commit each verified slice locally.

## Worktree Snapshot

Latest local commits at handoff:

```text
15002a1 ui: show label import target context
7d0f92c ui: show matched eeg for label carriers
4c2ad99 backend: map reviewed sequence labels by file stem
c9c79e2 backend: map reviewed timestamp labels by file stem
a26942a backend: propagate import review state
514587a docs: refresh product completion handoff
0da24db backend: apply reviewed sequence labels during import
626b606 backend: apply reviewed timestamp labels during import
15c242d backend: surface import format boundaries
f49af63 ui: add label carrier review to import wizard
3341d53 ui: guard headless 3d visualization
a41770f ui: capture visualization render walkthrough
```

Expected dirty files before this handoff docs commit:

```text
 M .vscode/settings.json
 M settings.json
```

These two files are protected user / workspace settings. Ignore them unless the
user explicitly asks otherwise. Do not stage them in any product or handoff
commit.

## Latest Verified Product Slice

The latest committed product slice is:

```text
15002a1 ui: show label import target context
```

It improved the legacy compatibility label path without making it the new
product mental model:

- `ImportLabelDialog` is now titled `Add Labels to Loaded Data`.
- The dialog shows which loaded EEG files the labels will be applied to.
- The dialog states that successful label import updates the current import
  recipe trace when Data Interpretation is active.
- `DatasetActionHandler.import_label()` passes loaded target file context into
  the dialog.
- This remains a service-backed compatibility path, not the mature embedded
  Data Interpretation label editor.

Immediately preceding completed slices:

- `7d0f92c` added `Matched EEG` to the Data Interpretation label carrier table.
  Single-file direct matches and multi-file unique stem matches show the target
  EEG filename; unresolved matches show `Needs review`.
- `4c2ad99` mapped reviewed MAT / TXT trial-order sequence labels by normalized
  file stem and skipped generic ambiguous sequence carriers.
- `c9c79e2` mapped reviewed CSV / TSV / BIDS events timestamp labels by
  normalized file stem and skipped generic ambiguous events carriers.
- `a26942a` propagated reviewed import truth into
  `ApplicationStateSnapshot.interpretation`, `query_state`, automation / MCP
  envelopes, and agent tool state.
- `0da24db` and `626b606` applied the single-file reviewed sequence and
  timestamp label paths during `apply_interpretation`.
- `15c242d` surfaced format capability boundaries for GDF, EDF / BDF, EEGLAB,
  BrainVision, MNE FIF, MAT labels, CSV / TSV / BIDS events, TXT, and blocked
  XDF / LSL stream-selection cases.
- `f49af63` added editable label carrier review rows to the import wizard and
  persisted `label_carrier_plan` through preview / apply / recipe.

Latest validation recorded before this handoff:

- focused import label target context tests: `2 passed`
- import label / dialog / DatasetActionHandler UI regression: `83 passed`
- production touched-file `basedpyright`: `0 errors`
- targeted `ruff` and format check: pass
- `poetry run mkdocs build --strict`: pass with the existing MkDocs Material warning
- `poetry run python tests/architecture_compliance.py`: Architecture compliant
- `git diff --check`: pass

Earlier validation in this continuation:

- shared import state propagation focused tests and app / automation / agent regression passed.
- timestamp multi-file label mapping tests passed, including ambiguous generic carrier skip.
- sequence multi-file label mapping tests passed, including ambiguous generic carrier skip.
- Data Interpretation UI replay passed and refreshed
  `artifacts/ui/data-interpretation-preview.png` plus
  `artifacts/ui/data-interpretation-replay.json`.

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
- The replay JSON includes review notes, label carrier rows, reviewed choices,
  matched EEG target text, timestamp label apply diagnostics, and recipe trace evidence.
- Local tool-call thesis-candidate benchmark evidence exists for `100` cases,
  primary / fallback x3, with cached non-China local models and no download.
  This supports the benchmark slice, but it does not replace UI, launcher, MCP,
  import wizard, or external experiment validation.

## Do Not Redo Without Reason

- Do not redo true ChatPanel training-completion walkthrough unless local model
  agent execution, training command surface, evaluation, saliency, or visible
  ChatPanel feedback changed.
- Do not redo visualization render walkthrough unless visualization panel,
  training state, saliency, or render contract changed.
- Do not redo label carrier wizard review / format boundary / label apply work
  unless `data_interpretation.py`, wizard result mapping, scan format detection,
  recipe serialization, or state snapshot propagation changed.
- Do not redo full local LLM x3 eval for documentation-only edits. Rerun
  targeted eval if prompt / schema / parser / verifier behavior changes, then
  rerun full primary / fallback x3 before thesis-candidate claims.
- Do not redo shared state snapshot propagation or multi-file safe label mapping
  unless a relevant backend contract changes.

## Current Known Blockers

Do not claim product completion yet.

- Full embedded post-load label import wizard is still incomplete. The current
  post-load dialog is compatibility UI with better target context.
- Generic folder-level `events.tsv` / `labels.mat` disambiguation remains
  intentionally skipped; the product does not yet provide an interactive
  resolution surface for these cases.
- Raw-event-anchor-specific GDF / MAT alignment is not modeled.
- Full all-format manual compatibility matrix and XDF / LSL stream parser remain incomplete.
- Windows Desktop launcher human click-through / WSLg multi-monitor behavior has not been manually verified.
- Interactive desktop 3D / PyVista render has not been verified; only headless blocked UX is proven.
- MCP Inspector GUI / release config is not completed.
- External thesis experiment runner / statistical report is not done.
- Thesis-candidate local LLM evidence exists, but the full product claim still
  depends on UI, launcher, MCP, import, and experiment validation.

## Immediate Resume Plan

1. Re-check worktree:

   ```bash
   git status --short
   ```

   Only `.vscode/settings.json` and root `settings.json` should be unrelated
   protected dirty files after this handoff commit.

2. Inspect MCP server / client / docs:

   ```bash
   rg -n "MCP|mcp|Inspector|stdio|run_mcp|mcp_server|mcp_tool" XBrainLab scripts tests docs artifacts -S
   ```

   Likely files:

   ```text
   XBrainLab/mcp/server.py
   scripts/dev/run_mcp_server.py
   scripts/dev/capture_mcp_stdio_walkthrough.py
   tests/unit/mcp/
   tests/unit/backend/application/test_automation.py
   docs/current.md
   docs/validation/README.md
   artifacts/mcp/
   ```

3. Recommended next product slice:

   ```text
   MCP Inspector / release config hardening
     -> checked-in external-client config or launch manifest
     -> command invokes prepared XBrainLab runtime, not client-side EEG deps
     -> tools/list and tools/call still use ApplicationService automation schema
     -> focused tests or stdio walkthrough evidence
     -> docs / records update
     -> local commit
   ```

4. After MCP config, continue with remaining product blockers:

   - embedded label import wizard hardening;
   - generic label carrier disambiguation UI for folder-level carriers;
   - Windows Desktop launcher human click-through / WSLg multi-monitor verification;
   - interactive desktop 3D render verification if a real OpenGL desktop session is available;
   - external thesis experiment runner / statistical report;
   - final validation sweep and docs closure.

## Claim Boundary

Current evidence supports:

- ApplicationService-backed Data Interpretation scan -> preview -> validate ->
  confirm/apply -> recipe baseline;
- import wizard metadata / class-map / label carrier review;
- format-specific supported / needs-review / blocked boundaries;
- single-file and safe multi-file reviewed timestamp / trial-order label apply;
- shared import truth propagation to UI / agent / headless / MCP state;
- true local ChatPanel single-command-per-turn workflow through controlled tiny training completion;
- true MainWindow post-training Matplotlib visualization render evidence;
- headless 3D blocked UX.

Current evidence does not support:

- completed desktop product;
- completed mature embedded import wizard label editor;
- completed raw-event-anchor label alignment;
- completed Windows Desktop human click-through;
- completed interactive desktop 3D render;
- completed MCP Inspector / release configuration;
- completed external thesis experiment package;
- full product thesis-ready claim.

Goal status must remain incomplete.
