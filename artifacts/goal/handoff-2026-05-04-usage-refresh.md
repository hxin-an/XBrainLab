# XBrainLab Usage Refresh Handoff

Date: `2026-05-04 12:23 UTC+08`

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
- Do not use China-source models.
- Do disk / VRAM / cache preflight before any model download.
- Commit each verified slice locally.

## Worktree Snapshot

Latest local commits at handoff:

```text
0cb480e assistant: capture import to dataset chain
9513dfa assistant: capture data interpretation tool chain
2958fb9 assistant: compact tool history for workflow turns
e46a35a launcher: capture windows startup walkthrough
5117f9d ui: edit interpretation metadata choices
```

Expected dirty files after the latest committed slice:

```text
 M .vscode/settings.json
 M settings.json
```

These two files are protected user / workspace settings. Ignore them unless the
user explicitly asks otherwise.

## Latest Verified Product Slice

The latest committed slice is `0cb480e assistant: capture import to dataset chain`.

It added true local ChatPanel evidence for the import-to-dataset path:

- `scripts/dev/capture_chatpanel_local_pipeline_chain_walkthrough.py`
- `artifacts/ui/chatpanel-local-pipeline-chain/chatpanel-local-pipeline-chain-walkthrough.json`
- `artifacts/ui/chatpanel-local-pipeline-chain/chatpanel-local-pipeline-chain-walkthrough.md`
- ready screenshot plus seven turn screenshots under
  `artifacts/ui/chatpanel-local-pipeline-chain/`

What the artifact proves:

- Real `MainWindow` / `ChatPanel` / `AgentManager` / `LLMController` /
  `AgentWorker` / `LLMEngine` path ran with the local primary model.
- Runtime was cached local `microsoft/Phi-4-mini-instruct`, `gpu-ready`, with
  cache usage around `15.34 GB`.
- No model download was needed.
- The visible ChatPanel workflow executed one verified tool per turn:
  - `scan_source`
  - `preview_interpretation`
  - `validate_interpretation`
  - `apply_interpretation`
  - `apply_standard_preprocess`
  - `epoch_data`
  - `generate_dataset`
- The script observed the `apply_interpretation` confirmation dialog and
  approved it as an explicit UI boundary.
- Final backend state had:
  - applied interpretation: `True`
  - epoch count: `6`
  - dataset available: `True`
  - dataset count: `1`
- Visible transcript was checked for raw tool / debug markers and stayed
  product-facing.

Important fixes in that slice:

- `apply_standard_preprocess` now routes through
  `PreprocessCommand(operation=STANDARD)` in
  `XBrainLab/llm/tools/application_surface.py` instead of falling through a
  legacy string path.
- `XBrainLab/llm/agent/tool_call_normalizer.py` now extracts multiple event ids
  from prompts like `events left and right`.
- The dataset split audit was not weakened. The first real run failed because a
  single-event, 3-epoch dataset produced an empty validation split; the fix was
  to generate enough epochs through correct event extraction.

Recorded validation for the latest slice:

```bash
poetry run pytest --capture=sys tests/unit/llm/agent/test_tool_call_normalizer.py tests/unit/llm/tools/test_application_surface.py tests/unit/scripts/test_capture_chatpanel_local_pipeline_chain_walkthrough.py -q
poetry run ruff check XBrainLab/llm/agent/tool_call_normalizer.py XBrainLab/llm/tools/application_surface.py scripts/dev/capture_chatpanel_local_pipeline_chain_walkthrough.py tests/unit/llm/agent/test_tool_call_normalizer.py tests/unit/llm/tools/test_application_surface.py tests/unit/scripts/test_capture_chatpanel_local_pipeline_chain_walkthrough.py
poetry run basedpyright XBrainLab/llm/agent/tool_call_normalizer.py XBrainLab/llm/tools/application_surface.py scripts/dev/capture_chatpanel_local_pipeline_chain_walkthrough.py tests/unit/llm/agent/test_tool_call_normalizer.py tests/unit/llm/tools/test_application_surface.py tests/unit/scripts/test_capture_chatpanel_local_pipeline_chain_walkthrough.py
poetry run mkdocs build --strict
git diff --check
timeout 840s env QT_QPA_PLATFORM=offscreen poetry run python scripts/dev/capture_chatpanel_local_pipeline_chain_walkthrough.py --output-dir artifacts/ui/chatpanel-local-pipeline-chain --timeout-seconds 800
```

The compacted run state records the broader targeted pytest command as
`45 passed`; the existing continuation file records the narrower targeted
subset as `32 passed`. Treat the artifact and committed tests as the source of
truth and rerun the broader command before building on this slice.

## Current Known Blockers

Do not claim product completion yet.

- No true ChatPanel dataset -> model selection -> training settings -> train ->
  evaluate / visualize / saliency readiness long-chain walkthrough.
- Post-handoff update: evaluation / visualization / saliency agent-tool exposure
  has been completed. `evaluate`, `visualize`, and `saliency` are registered
  tools and route through ApplicationService. The remaining blocker is the true
  ChatPanel controlled tiny training completion -> metrics / render walkthrough.
- Post-handoff update: the dataset-ready -> model / training settings ->
  training-confirmation boundary -> visualization/saliency readiness artifact
  has been completed under `artifacts/ui/chatpanel-local-training-readiness/`.
  It intentionally rejects training confirmation and does not prove actual
  training completion.
- Windows Desktop launcher human click-through / WSLg multi-monitor behavior has
  not been manually verified. There is automated command-path evidence only.
- MCP stdio server and stdlib client walkthrough exist, but MCP Inspector GUI /
  release config is not completed.
- Label import is recipe-trace compatible but still not a mature import wizard
  embedded label / anchor / MAT variable editor.
- Full UI button-click to real training, evaluation, visualization, and saliency
  completion is not done.
- External thesis experiment runner / statistical report is not done.

## Immediate Resume Plan

Start with the smallest product slice that unlocks the next visible workflow:

1. Re-check worktree:

   ```bash
   git status --short
   ```

   Only `.vscode/settings.json` and root `settings.json` should be dirty.

2. Capture the next UI-observable local-model artifact:

   ```text
   dataset ready -> set model -> configure training -> explicit confirmation -> train or readiness boundary -> evaluate / visualize / saliency readiness
   ```

   If training is too slow or unsafe in the current environment, capture the
   confirmation / readiness boundary and document exactly what it does not
   prove. Do not let the assistant auto-train without explicit confirmation.

3. Run targeted validation for that slice, at minimum:

   ```bash
   git diff --check
   poetry run ruff check <changed files>
   poetry run basedpyright <changed files>
   poetry run pytest --capture=sys <targeted tests> -q
   poetry run mkdocs build --strict
   ```

4. Commit the verified slice locally.

## Do Not Redo Without Reason

- Do not redo the short ChatPanel Data Interpretation chain unless you changed
  scan / preview / validate parsing, verification, or tool schema.
- Do not redo the import-to-dataset chain unless you changed apply /
  preprocess / epoch / dataset behavior.
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
  dataset.

Current evidence does not support:

- completed desktop product;
- completed training / evaluation / saliency ChatPanel workflow;
- completed Windows Desktop human click-through;
- completed mature import wizard label editor;
- completed MCP Inspector / release configuration;
- completed external thesis experiment package.

Goal status must remain incomplete.
