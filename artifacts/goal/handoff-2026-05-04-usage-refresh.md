# XBrainLab Usage Refresh Handoff

Date: `2026-05-04 13:52 UTC+08`

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
f9f0956 assistant: capture training completion walkthrough
7936328 agent: preserve training output dir
9984cc9 docs: refresh usage handoff
a228a9d assistant: capture training readiness boundary
84d9c66 agent: expose analysis tools
```

Expected dirty files after the latest committed product slice:

```text
 M .vscode/settings.json
 M settings.json
```

These two files are protected user / workspace settings. Ignore them unless the
user explicitly asks otherwise.

## Latest Verified Product Slice

The latest committed product slice is:

```text
f9f0956 assistant: capture training completion walkthrough
```

It added true local ChatPanel evidence for controlled tiny training completion:

- `scripts/dev/capture_chatpanel_local_training_completion_walkthrough.py`
- `tests/unit/scripts/test_capture_chatpanel_local_training_completion_walkthrough.py`
- `artifacts/ui/chatpanel-local-training-completion/chatpanel-local-training-completion-walkthrough.json`
- `artifacts/ui/chatpanel-local-training-completion/chatpanel-local-training-completion-walkthrough.md`
- ready / trained screenshots plus seven turn screenshots under
  `artifacts/ui/chatpanel-local-training-completion/`

What the artifact proves:

- A real `MainWindow` / `ChatPanel` / `AgentManager` / `LLMController` /
  `AgentWorker` / `LLMEngine` path ran with cached local primary model
  `microsoft/Phi-4-mini-instruct`.
- Runtime classification was `gpu-ready`; cache usage was about `15.34 GB`; no
  model download was needed.
- Dataset-ready state was prepared through `ApplicationService`:
  `scan_source` -> `preview_interpretation` -> `validate_interpretation` ->
  `apply_interpretation` -> `preprocess` -> `create_epoch` -> `generate_dataset`.
- The visible ChatPanel workflow executed one verified command per turn:
  - `set_model`
  - `configure_training` with controlled temp `output_dir`
  - observed / approved `start_training` confirmation
  - training completion wait
  - `evaluate`
  - `saliency` configure
  - `visualize`
  - saliency readiness query
- Final state had dataset available, model `EEGNet`, training option present,
  output dir `/tmp/xbrainlab-chatpanel-training-completion-output`, trainer
  present, training not running, finished runs `1`, evaluation metrics
  available, and saliency configured / available.
- ChatPanel returned idle and visible assistant text stayed product-facing.

Supporting fixes in the same slice:

- `SaliencyCommand` normalizes flat `method` / `params` to evaluator-required
  `SmoothGrad` / `SmoothGrad_Squared` / `VarGrad` params.
- Intent detection recognizes `visualization` / `visualisation`.
- Saliency readiness query drops stale saliency config params from previous
  turns.
- Metrics bar chart `tight_layout` singular-matrix failure is degraded to a
  warning.
- Missing optional `torchinfo` returns a user-facing unavailable message without
  logging a traceback.

Recorded validation for the latest slice:

```bash
poetry run pytest --capture=sys tests/unit/backend/application/test_application_service.py::test_saliency_command_can_configure_params tests/unit/backend/application/test_application_service.py::test_saliency_command_normalizes_flat_method_params tests/unit/llm/agent/test_intent.py tests/unit/llm/agent/test_tool_call_normalizer.py tests/unit/scripts/test_capture_chatpanel_local_training_completion_walkthrough.py tests/unit/backend/controller/test_evaluation_controller.py -q
scripts/dev/run_ui_pytest.sh tests/unit/ui/test_ui_components.py::TestMetricsBarChart -q
poetry run pytest --capture=sys tests/unit/llm/agent -q
poetry run python scripts/agent/evals/run_tool_call_eval.py --output-dir artifacts/agent_evals --repeat-count 2
timeout 1200s env QT_QPA_PLATFORM=offscreen poetry run python scripts/dev/capture_chatpanel_local_training_completion_walkthrough.py --output-dir artifacts/ui/chatpanel-local-training-completion --timeout-seconds 1080
poetry run ruff check XBrainLab/backend/application/service.py XBrainLab/backend/controller/evaluation_controller.py XBrainLab/llm/agent/intent.py XBrainLab/llm/agent/tool_call_normalizer.py XBrainLab/ui/panels/evaluation/metrics_bar_chart.py scripts/dev/capture_chatpanel_local_training_completion_walkthrough.py tests/unit/backend/application/test_application_service.py tests/unit/backend/controller/test_evaluation_controller.py tests/unit/llm/agent/test_intent.py tests/unit/llm/agent/test_tool_call_normalizer.py tests/unit/scripts/test_capture_chatpanel_local_training_completion_walkthrough.py tests/unit/ui/test_ui_components.py
poetry run basedpyright XBrainLab/backend/application/service.py XBrainLab/backend/controller/evaluation_controller.py XBrainLab/llm/agent/intent.py XBrainLab/llm/agent/tool_call_normalizer.py XBrainLab/ui/panels/evaluation/metrics_bar_chart.py scripts/dev/capture_chatpanel_local_training_completion_walkthrough.py tests/unit/backend/application/test_application_service.py tests/unit/backend/controller/test_evaluation_controller.py tests/unit/llm/agent/test_intent.py tests/unit/llm/agent/test_tool_call_normalizer.py tests/unit/scripts/test_capture_chatpanel_local_training_completion_walkthrough.py tests/unit/ui/test_ui_components.py
poetry run mkdocs build --strict
git diff --check
```

Expected results:

- focused regression: `48 passed`
- UI fallback regression: `3 passed`
- broader agent suite: `235 passed`
- deterministic tool-call eval refresh: `100 / 100`
- true local ChatPanel walkthrough: `status=passed`
- targeted `ruff`: pass
- targeted `basedpyright`: `0 errors, 0 warnings, 0 notes`
- mkdocs strict build: pass with the existing MkDocs Material warning
- diff check: pass

## Do Not Redo Without Reason

- Do not redo the short ChatPanel Data Interpretation chain unless scan /
  preview / validate parsing, verification, or tool schema changed.
- Do not redo the import-to-dataset chain unless apply / preprocess / epoch /
  dataset behavior changed.
- Do not redo analysis-tool exposure unless `evaluate` / `visualize` /
  `saliency` registry or command mapping changed.
- Do not redo the controlled tiny training-completion walkthrough unless the
  local-model agent, training command surface, evaluation command, saliency
  command, or visible ChatPanel feedback changed.
- Do not rerun the full `100` case local LLM eval for documentation-only edits.
  Rerun targeted eval if prompt / schema / parser / verifier behavior changes,
  then rerun full primary / fallback x3 before making thesis-candidate claims.

## Current Known Blockers

Do not claim product completion yet.

- Full saliency / visualization canvas render UI walkthrough is still missing.
  The latest artifact proves readiness / summary tools, not actual rendered
  saliency or visualization canvas evidence.
- Windows Desktop launcher human click-through / WSLg multi-monitor behavior has
  not been manually verified. There is automated command-path evidence only.
- MCP stdio server and stdlib client walkthrough exist, but MCP Inspector GUI /
  release config is not completed.
- Label import is recipe-trace compatible but still not a mature import wizard
  embedded label / anchor / MAT variable editor.
- Full user-facing import wizard polish remains incomplete.
- External thesis experiment runner / statistical report is not done.
- Primary / fallback local LLM x3 thesis-candidate eval report still needs
  organizing before making thesis-readiness claims.

## Immediate Resume Plan

Start with the next visible product gap. Recommended order:

1. Re-check worktree:

   ```bash
   git status --short
   ```

   Only `.vscode/settings.json` and root `settings.json` should be dirty.

2. Inspect the current visualization / saliency UI path:

   ```text
   XBrainLab/backend/application/service.py
   XBrainLab/ui/panels/evaluation/
   XBrainLab/ui/panels/visualization/
   XBrainLab/llm/tools/definitions/analysis_def.py
   XBrainLab/llm/tools/application_surface.py
   ```

3. Build a UI-observable render slice:

   ```text
   dataset-ready or trained state
     -> model/training/evaluation state available
     -> user-visible visualization or saliency render command
     -> canvas/panel actually updates
     -> screenshot proves rendered result or human-readable blocked reason
   ```

   Keep the assistant to one verified command per turn. Do not package readiness
   text as render evidence.

4. If render requires broader UI refactor, take the smaller slice first:

   ```text
   ApplicationService result exposes enough render target/state
     -> UI panel consumes same typed result/capability policy
     -> focused UI test
     -> screenshot artifact
   ```

5. If WSL/Qt/GPU limits block true render capture, write the blocker into
   records and do not mark the goal complete.

## Claim Boundary

Current evidence supports:

- true local ChatPanel visible response;
- true local ChatPanel single-tool execution;
- true local ChatPanel two-turn continuity after compact tool history;
- true local ChatPanel Data Interpretation scan -> preview -> validate;
- true local ChatPanel Data Interpretation apply -> preprocess -> epoch ->
  dataset;
- ApplicationService-backed agent tools for evaluate / visualize / saliency;
- true local ChatPanel dataset-ready training confirmation boundary;
- true local ChatPanel controlled tiny training completion with post-training
  evaluation metrics and saliency / visualization readiness summary.

Current evidence does not support:

- completed desktop product;
- completed saliency / visualization canvas render workflow;
- completed Windows Desktop human click-through;
- completed mature import wizard label editor;
- completed MCP Inspector / release configuration;
- completed external thesis experiment package.

Goal status must remain incomplete.
