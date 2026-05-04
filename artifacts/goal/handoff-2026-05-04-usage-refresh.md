# XBrainLab Usage Refresh Handoff

Date: `2026-05-04 12:57 UTC+08`

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
a228a9d assistant: capture training readiness boundary
84d9c66 agent: expose analysis tools
9f26e4f docs: add usage refresh handoff
0cb480e assistant: capture import to dataset chain
9513dfa assistant: capture data interpretation tool chain
```

Expected dirty files after the latest committed slice:

```text
 M .vscode/settings.json
 M settings.json
```

These two files are protected user / workspace settings. Ignore them unless the
user explicitly asks otherwise.

## Latest Verified Product Slice

The latest committed slice is
`a228a9d assistant: capture training readiness boundary`.

It added true local ChatPanel evidence for the dataset-ready training boundary:

- `scripts/dev/capture_chatpanel_local_training_readiness_walkthrough.py`
- `tests/unit/scripts/test_capture_chatpanel_local_training_readiness_walkthrough.py`
- `artifacts/ui/chatpanel-local-training-readiness/chatpanel-local-training-readiness-walkthrough.json`
- `artifacts/ui/chatpanel-local-training-readiness/chatpanel-local-training-readiness-walkthrough.md`
- ready screenshot plus six turn screenshots under
  `artifacts/ui/chatpanel-local-training-readiness/`

What the artifact proves:

- A real `MainWindow` / `ChatPanel` / `AgentManager` / `LLMController` /
  `AgentWorker` / `LLMEngine` path ran with cached local primary model
  `microsoft/Phi-4-mini-instruct`.
- Runtime classification was `gpu-ready`; cache usage was about `15.34 GB`; no
  model download was needed.
- Synthetic dataset-ready state was prepared through `ApplicationService`.
- The visible ChatPanel workflow executed one verified tool per turn:
  - `set_model`
  - `configure_training`
  - `start_training`
  - `visualize`
  - `saliency`
  - `evaluate`
- The script observed the high-impact training confirmation dialog and rejected
  it deliberately. Training did not start.
- Final state had dataset available, model `EEGNet`, training option present,
  trainer not created, training not running, and evaluation unavailable.
- The `evaluate` turn surfaced the user-facing blocked reason:
  `Create a training plan before evaluating results.`
- Visible assistant text was checked for raw tool syntax, traceback, schema, and
  developer wording markers.

Recorded validation for the latest slice:

```bash
poetry run pytest --capture=sys tests/unit/scripts/test_capture_chatpanel_local_training_readiness_walkthrough.py -q
poetry run ruff check scripts/dev/capture_chatpanel_local_training_readiness_walkthrough.py tests/unit/scripts/test_capture_chatpanel_local_training_readiness_walkthrough.py
poetry run basedpyright scripts/dev/capture_chatpanel_local_training_readiness_walkthrough.py tests/unit/scripts/test_capture_chatpanel_local_training_readiness_walkthrough.py
timeout 900s env QT_QPA_PLATFORM=offscreen poetry run python scripts/dev/capture_chatpanel_local_training_readiness_walkthrough.py --output-dir artifacts/ui/chatpanel-local-training-readiness --timeout-seconds 840
poetry run mkdocs build --strict
git diff --check
```

Expected results:

- unit: `4 passed`
- targeted `ruff`: pass
- targeted `basedpyright`: `0 errors, 0 warnings, 0 notes`
- true local ChatPanel walkthrough: `status=passed`
- mkdocs strict build: pass with the existing MkDocs Material warning
- diff check: pass

## Prior Slice To Keep In Mind

`84d9c66 agent: expose analysis tools` closed the agent exposure gap for backend
analysis commands:

- `evaluate`, `visualize`, and `saliency` now have definitions / mock / real
  tools.
- `application_surface.py` maps them directly to `EvaluateCommand`,
  `VisualizeCommand`, and `SaliencyCommand`.
- Parser / intent / trained-stage prompt now recognize them as workflow tools.
- Targeted tests passed (`293 passed`), broader agent/tools regression passed
  (`516 passed`), deterministic eval was `100 / 100`, and affected-case local
  primary / fallback smokes were each `5 / 5`.

This means the next runner should not spend time re-adding analysis tools.

## Current Known Blockers

Do not claim product completion yet.

- No true controlled tiny ChatPanel training completion has been captured.
- No ChatPanel post-training `evaluate` metrics, visualization render, or
  saliency render artifact exists.
- Full UI button-click to real training / evaluation / visualization / saliency
  completion is not done.
- Windows Desktop launcher human click-through / WSLg multi-monitor behavior has
  not been manually verified. There is automated command-path evidence only.
- MCP stdio server and stdlib client walkthrough exist, but MCP Inspector GUI /
  release config is not completed.
- Label import is recipe-trace compatible but still not a mature import wizard
  embedded label / anchor / MAT variable editor.
- External thesis experiment runner / statistical report is not done.

## Immediate Resume Plan

Start with the smallest product slice that unlocks the next visible workflow.

1. Re-check worktree:

   ```bash
   git status --short
   ```

   Only `.vscode/settings.json` and root `settings.json` should be dirty.

2. Inspect the training command path before approving real training:

   ```text
   ConfigureTrainingCommand
   BaseConfigureTrainingTool
   XBrainLab/llm/tools/application_surface.py
   start_training / train command tests
   ```

   Current known issue: `ConfigureTrainingCommand` supports `output_dir`, but
   the agent-facing `configure_training` tool schema / application-surface
   mapping did not expose `output_dir` when last inspected. Add tests first if
   this is still true.

3. If still missing, add a focused slice:

   ```text
   configure_training tool accepts output_dir
     -> ApplicationService command receives it
     -> training option/state records it
   ```

   Run targeted unit tests, targeted `ruff`, targeted `basedpyright`,
   `mkdocs build --strict`, and `git diff --check`. Commit that slice.

4. Then capture the next UI-observable local-model artifact:

   ```text
   dataset ready
     -> set model
     -> configure tiny training with temp/artifact output_dir
     -> explicit training confirmation
     -> controlled training completion if safe
     -> evaluate metrics
     -> visualization / saliency render or clear blocked reason
   ```

   The assistant must still execute one verified command per turn. Do not let it
   auto-train without an observed confirmation boundary.

5. If training is too slow, unsafe, or flaky in WSL/GPU context, capture the
   blocker as evidence and do not mark the goal complete.

## Do Not Redo Without Reason

- Do not redo the short ChatPanel Data Interpretation chain unless scan /
  preview / validate parsing, verification, or tool schema changed.
- Do not redo the import-to-dataset chain unless apply / preprocess / epoch /
  dataset behavior changed.
- Do not redo analysis-tool exposure unless `evaluate` / `visualize` /
  `saliency` registry or command mapping changed.
- Do not rerun the full `100` case local LLM eval for documentation-only edits.
  Rerun targeted eval if prompt / schema / parser / verifier behavior changes,
  then rerun full primary / fallback x3 before making thesis-candidate claims.

## Claim Boundary

Current evidence supports:

- true local ChatPanel visible response;
- true local ChatPanel single-tool execution;
- true local ChatPanel two-turn continuity after compact tool history;
- true local ChatPanel Data Interpretation scan -> preview -> validate;
- true local ChatPanel Data Interpretation apply -> preprocess -> epoch ->
  dataset;
- ApplicationService-backed agent tools for evaluate / visualize / saliency;
- true local ChatPanel dataset-ready training confirmation boundary and
  analysis-readiness blocked-state handling.

Current evidence does not support:

- completed desktop product;
- completed training / evaluation / saliency ChatPanel workflow;
- completed Windows Desktop human click-through;
- completed mature import wizard label editor;
- completed MCP Inspector / release configuration;
- completed external thesis experiment package.

Goal status must remain incomplete.
