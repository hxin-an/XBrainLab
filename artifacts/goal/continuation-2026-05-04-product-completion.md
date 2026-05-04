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
0da24db backend: apply reviewed sequence labels during import
```

This slice closes the narrow safe path for reviewed external label application
inside Data Interpretation:

- timestamp CSV / TSV / BIDS events carriers apply through
  `dataset.apply_labels_batch()` when one EEG file and one confirmed reviewed
  timestamp carrier are present;
- MAT / TXT trial-order sequence carriers apply through
  `dataset.apply_labels_legacy()` when one EEG file, one reviewed carrier,
  trial granularity, `trial_order` time model, and a confirmed class map are
  present;
- applied interpretations now record `label_apply` diagnostics,
  `label_imports`, and recipe trace entries for the applied labels;
- unsupported / ambiguous cases remain skipped with reason instead of being
  guessed.

Immediately preceding product slices:

- `f49af63 ui: add label carrier review to import wizard`
- `15c242d backend: surface import format boundaries`
- `626b606 backend: apply reviewed timestamp labels during import`
- `a41770f ui: capture visualization render walkthrough`
- `3341d53 ui: guard headless 3d visualization`
- `f9f0956 assistant: capture training completion walkthrough`

Validation already recorded in `docs/records/worklog.md`,
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
- Label carrier review, format capability boundaries, timestamp label apply, and
  MAT / TXT sequence label apply are already implemented.

Redo one only if the underlying parser, verifier, command surface, UI feedback,
backend result contract, visualization render path, or Data Interpretation
recipe contract changed.

## Immediate Resume Steps

1. Check worktree:

```bash
git status --short
```

Only `.vscode/settings.json` and root `settings.json` should be unrelated
protected dirty files. If this continuation / handoff docs update is not yet
committed, commit only the docs / artifacts touched by that handoff.

2. Read current truth and latest records:

```bash
sed -n '1,180p' docs/current.md
sed -n '200,260p' docs/planning/now.md
sed -n '90,240p' docs/records/worklog.md
sed -n '140,260p' docs/records/implementation_log.md
```

3. Next highest-value product slice:

```text
Data Interpretation import truth in shared state snapshot
```

The import recipe / UI now knows `label_carrier_plan` and
`format_capabilities`, but `ApplicationStateSnapshot.interpretation`,
`query_state`, automation, agent, and MCP may still expose only older summary
fields. Fix this so UI / agent / headless / MCP share the same import truth.

Suggested TDD shape:

```text
apply reviewed timestamp or MAT sequence interpretation
  -> assert result.state.interpretation has label_carrier_plan
  -> assert result.state.interpretation has format_capabilities
  -> assert serialized automation/query_state payload contains the same fields
  -> implement only the missing state propagation
```

4. After state propagation, continue with the remaining product gaps:

- mature embedded label import wizard;
- multi-file label mapping;
- raw-event-anchor-specific GDF / MAT alignment;
- all-format manual compatibility matrix and XDF / LSL boundary / parser work;
- Windows Desktop launcher human click-through / WSLg multi-monitor
  verification;
- MCP Inspector GUI / release config;
- interactive desktop 3D / PyVista verification if a real OpenGL session exists;
- external thesis experiment runner / statistical report;
- primary / fallback local LLM x3 thesis-candidate evidence organization.

## Remaining Product Blockers

- Shared state snapshot may not yet include the newest Data Interpretation label
  carrier and format capability details.
- Full embedded post-load label import wizard is incomplete.
- Multi-file label mapping is not automatic.
- Raw-event-anchor-specific GDF / MAT alignment remains incomplete.
- Full all-format manual compatibility matrix and XDF / LSL stream parser remain
  incomplete.
- Windows Desktop launcher human click-through / WSLg multi-monitor behavior is
  not manually verified.
- Interactive desktop 3D / PyVista render is not verified.
- MCP Inspector GUI / release config is not complete.
- External thesis experiment runner / statistical report is not done.
- Thesis-candidate local LLM report still needs primary / fallback x3 evidence
  organization.
- Goal must remain incomplete until these are fixed or explicitly documented as
  not done.

## Handoff Rule

If another resource / context / GPU / WSL limit appears:

- Do not mark complete.
- Commit verified slices only.
- Update `docs/records/worklog.md`.
- Update `docs/records/implementation_log.md`.
- Add or refresh a continuation prompt in `artifacts/goal/`.
