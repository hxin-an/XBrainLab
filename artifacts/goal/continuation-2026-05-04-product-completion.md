# XBrainLab Product Completion Continuation

Date: `2026-05-04`

Use this after usage refresh. Continue from active repo:

```text
/mnt/d/workspace_v2/projects/lab/XBrainLab
```

Latest usage-refresh handoff:

```text
artifacts/goal/handoff-2026-05-04-usage-refresh.md
```

## Hard Boundaries

- Do not push.
- Do not touch / revert `.vscode/settings.json`.
- Do not touch / revert root `settings.json`.
- Do not use destructive git commands.
- Do not mark the goal complete while known product blockers remain.
- Keep API / Gemini / remote LLM out of the product execution path.
- Do not use or download China-source models.
- Do local LLM disk / VRAM / cache preflight before any model download.
- Commit each verified slice locally.

## Latest Completed Product Slice

Latest product commit:

```text
15002a1 ui: show label import target context
```

This slice makes the legacy compatibility label flow safer and clearer:

- `Add Labels to Loaded Data` now shows the loaded EEG target files.
- The dialog explains that successful label import updates the active Data
  Interpretation recipe trace.
- Dataset actions pass loaded target context into the dialog.
- It remains compatibility UI, not the complete embedded label editor.

Important product slices already completed:

- `a26942a backend: propagate import review state`
- `c9c79e2 backend: map reviewed timestamp labels by file stem`
- `4c2ad99 backend: map reviewed sequence labels by file stem`
- `7d0f92c ui: show matched eeg for label carriers`
- `0da24db backend: apply reviewed sequence labels during import`
- `626b606 backend: apply reviewed timestamp labels during import`
- `15c242d backend: surface import format boundaries`
- `f49af63 ui: add label carrier review to import wizard`
- `3341d53 ui: guard headless 3d visualization`
- `a41770f ui: capture visualization render walkthrough`
- `f9f0956 assistant: capture training completion walkthrough`

Validation is recorded in `docs/records/worklog.md`,
`docs/records/implementation_log.md`, `docs/validation/README.md`, and the
handoff file.

## Do Not Redo Without Reason

- ChatPanel Data Interpretation short-chain evidence is already done.
- ChatPanel import-to-dataset pipeline-chain evidence is already done.
- Agent exposure for `evaluate`, `visualize`, and `saliency` is already done.
- ChatPanel training-readiness boundary evidence is already done.
- Controlled tiny ChatPanel training-completion evidence is already done.
- MainWindow VisualizationPanel Matplotlib render evidence is already done.
- Headless/offscreen 3D blocked UX is already guarded and captured.
- Label carrier review, format capability boundaries, timestamp label apply,
  MAT / TXT sequence label apply, shared state propagation, and safe multi-file
  label mapping are already implemented.

Redo one only if the underlying parser, verifier, command surface, UI feedback,
backend result contract, visualization render path, Data Interpretation recipe
contract, or shared state schema changed.

## Immediate Resume Steps

1. Check worktree:

```bash
git status --short
```

Only `.vscode/settings.json` and root `settings.json` should be unrelated
protected dirty files. If this continuation / handoff docs update is not yet
committed, commit only the docs / artifacts touched by the handoff.

2. Read current truth and latest records:

```bash
sed -n '1,180p' docs/current.md
sed -n '200,320p' docs/planning/now.md
tail -n 140 docs/records/worklog.md
tail -n 180 docs/records/implementation_log.md
```

3. Next highest-value product slice:

```text
MCP Inspector / release config hardening
```

Suggested inspection:

```bash
rg -n "MCP|mcp|Inspector|stdio|run_mcp|mcp_server|mcp_tool" XBrainLab scripts tests docs artifacts -S
```

Candidate implementation shape:

```text
checked-in MCP external-client config or launch manifest
  -> invokes prepared XBrainLab runtime
  -> does not require client-side EEG / PyQt / PyTorch dependencies
  -> shares tool schema with ApplicationService automation
  -> proves tools/list and tools/call through focused test or stdio walkthrough
  -> records artifact / docs
  -> local commit
```

4. After MCP config, continue with remaining product gaps:

- mature embedded label import wizard;
- generic folder-level label carrier disambiguation UI;
- raw-event-anchor-specific GDF / MAT alignment;
- all-format manual compatibility matrix and XDF / LSL boundary / parser work;
- Windows Desktop launcher human click-through / WSLg multi-monitor verification;
- interactive desktop 3D / PyVista verification if a real OpenGL session exists;
- external thesis experiment runner / statistical report;
- final validation sweep and docs closure.

## Remaining Product Blockers

- Full embedded post-load label import wizard is incomplete.
- Generic folder-level `events.tsv` / `labels.mat` disambiguation remains
  skipped, with no interactive resolution surface yet.
- Raw-event-anchor-specific GDF / MAT alignment remains incomplete.
- Full all-format manual compatibility matrix and XDF / LSL stream parser remain incomplete.
- Windows Desktop launcher human click-through / WSLg multi-monitor behavior is not manually verified.
- Interactive desktop 3D / PyVista render is not verified.
- MCP Inspector GUI / release config is not complete.
- External thesis experiment runner / statistical report is not done.
- Full product thesis-ready claim still depends on product validation beyond the
  tool-call benchmark.
- Goal must remain incomplete until these are fixed or explicitly documented as not done.

## Handoff Rule

If another resource / context / GPU / WSL limit appears:

- Do not mark complete.
- Commit verified slices only.
- Update `docs/records/worklog.md`.
- Update `docs/records/implementation_log.md`.
- Add or refresh a continuation prompt in `artifacts/goal/`.
