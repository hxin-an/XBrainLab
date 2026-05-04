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
f9f0956 assistant: capture training completion walkthrough
```

This slice proves true local ChatPanel controlled tiny training completion:

- real `MainWindow` / `ChatPanel` / local primary model
  `microsoft/Phi-4-mini-instruct`;
- no model download, runtime `gpu-ready`, cache about `15.34 GB`;
- ApplicationService dataset preparation through Data Interpretation -> recipe
  apply -> preprocess -> epoch -> dataset;
- visible one-command-per-turn flow:
  `set_model` -> `configure_training` -> observed / approved `start_training`
  confirmation -> training completion -> `evaluate` -> `saliency` configure ->
  `visualize` -> saliency readiness query;
- final state has finished runs `1`, evaluation metrics available, saliency
  configured / available, ChatPanel idle;
- artifacts under `artifacts/ui/chatpanel-local-training-completion/`.

Supporting fixes:

- saliency flat `method` / `params` normalization;
- `visualization` / `visualisation` intent recognition;
- stale saliency config cleanup on readiness query;
- metrics bar chart layout failure fallback;
- missing optional `torchinfo` model-summary fallback.

Validation already recorded in `docs/records/worklog.md`,
`docs/records/implementation_log.md`, and `docs/validation/README.md`.

## Do Not Redo Without Reason

- ChatPanel Data Interpretation short-chain evidence is already done.
- ChatPanel import-to-dataset pipeline-chain evidence is already done.
- Agent exposure for `evaluate`, `visualize`, and `saliency` is already done.
- ChatPanel training-readiness boundary evidence is already done.
- Controlled tiny ChatPanel training-completion evidence is already done.

Redo one only if the underlying parser, verifier, command surface, UI feedback,
or backend result contract changed.

## Immediate Resume Steps

1. Check worktree:

```bash
git status --short
```

Only `.vscode/settings.json` and root `settings.json` should be unrelated
protected dirty files.

2. Read current truth and records:

```bash
sed -n '1,240p' docs/current.md
sed -n '1,240p' docs/planning/now.md
tail -n 180 docs/records/worklog.md
tail -n 220 docs/records/implementation_log.md
sed -n '780,900p' docs/validation/README.md
```

3. Next highest-value product slice:

```text
full visualization / saliency canvas render UI evidence
```

The latest ChatPanel training-completion artifact proves readiness summaries,
not real render/canvas output. Build or verify a user-observable render path and
capture screenshots/artifacts that show the actual UI update.

4. If render path is blocked, take the smallest architecture-aligned slice:

```text
ApplicationService typed render/readiness result
  -> UI panel consumes the same result/capability policy
  -> agent command remains one verified command per turn
  -> focused tests
  -> UI-observable screenshot or clear blocked reason
```

5. After render evidence, continue with the remaining product gaps:

- mature import wizard embedded label / anchor / MAT variable editor;
- Windows Desktop launcher human click-through / WSLg multi-monitor verification;
- MCP Inspector GUI / release config;
- external thesis experiment runner / statistical report;
- primary / fallback local LLM x3 thesis-candidate eval report.

## Remaining Product Blockers

- Full saliency / visualization canvas render UI walkthrough is missing.
- Windows Desktop launcher human click-through / WSLg multi-monitor behavior is
  not manually verified.
- MCP Inspector GUI / release config is not complete.
- Label import is recipe-trace compatible but not yet a mature import wizard
  embedded label / anchor / MAT variable editor.
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
