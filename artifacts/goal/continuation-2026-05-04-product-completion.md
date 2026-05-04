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

## Latest Completed Slices

The latest product slices added true local ChatPanel tool-chain evidence.

### Data Interpretation short chain

- `scripts/dev/capture_chatpanel_local_tool_chain_walkthrough.py`
- `artifacts/ui/chatpanel-local-tool-chain/*`

What it proves:

- Real MainWindow / ChatPanel / AgentManager / LLMController / AgentWorker /
  LLMEngine local backend can run a short Data Interpretation tool chain.
- The script creates a deterministic synthetic FIF and sends visible ChatPanel prompts.
- Local primary model `microsoft/Phi-4-mini-instruct` ran offline from cache.
- Tool sequence passed:
  - `scan_source`
  - `preview_interpretation`
  - `validate_interpretation`
- Final interpretation state has scan / candidate / preview / validation decision.
- Validation decision is `needs_confirmation`.
- UI returned idle and visible transcript did not expose raw tool syntax, schema, traceback, or debug payload.

Root cause fixed:

- First real run showed `scan_source` succeeded, but `preview_interpretation`
  failed as if no scan existed.
- Final state showed `latest_scan_id=scan-1`, so ApplicationService state was not lost.
- The local model was generating schema-derived placeholder ids such as
  `latest_scan_id`, which overrode backend latest-state fallback.
- Normalizer now keeps only backend-generated id forms:
  - `scan-<n>` for `scan_id`
  - `candidate-<n>` for `candidate_id`
- Other generated/latest/current/id placeholders are removed so ApplicationService uses current state.

Validated command:

```bash
timeout 620s env QT_QPA_PLATFORM=offscreen poetry run python scripts/dev/capture_chatpanel_local_tool_chain_walkthrough.py --output-dir artifacts/ui/chatpanel-local-tool-chain --timeout-seconds 580
```

### Import-to-dataset pipeline chain

- `scripts/dev/capture_chatpanel_local_pipeline_chain_walkthrough.py`
- `artifacts/ui/chatpanel-local-pipeline-chain/*`

What it proves:

- Real local ChatPanel can continue past Data Interpretation validation.
- The script observes and approves the `apply_interpretation` confirmation dialog.
- Tool sequence passed:
  - `scan_source`
  - `preview_interpretation`
  - `validate_interpretation`
  - `apply_interpretation`
  - `apply_standard_preprocess`
  - `epoch_data`
  - `generate_dataset`
- Final state:
  - applied interpretation: `True`
  - epoch count: `6`
  - dataset available: `True`
  - dataset count: `1`
- UI returned idle and visible transcript did not expose raw tool syntax, schema, traceback, or debug payload.

Root causes fixed:

- `apply_standard_preprocess` now routes directly to `PreprocessCommand(operation=STANDARD)` in the agent application surface instead of legacy string fallback.
- First pipeline-chain run hit split audit failure because only the `left` event was extracted, producing 3 epochs and an empty validation split.
- The split audit guardrail was not relaxed.
- `tool_call_normalizer` now extracts multiple event ids from prompts such as `events left and right`.

Validated commands already run:

```bash
poetry run pytest --capture=sys tests/unit/llm/agent/test_tool_call_normalizer.py tests/unit/llm/tools/test_application_surface.py::test_application_tool_command_routes_standard_preprocess tests/unit/scripts/test_capture_chatpanel_local_pipeline_chain_walkthrough.py -q
poetry run ruff check XBrainLab/llm/agent/tool_call_normalizer.py XBrainLab/llm/tools/application_surface.py scripts/dev/capture_chatpanel_local_pipeline_chain_walkthrough.py tests/unit/llm/agent/test_tool_call_normalizer.py tests/unit/llm/tools/test_application_surface.py tests/unit/scripts/test_capture_chatpanel_local_pipeline_chain_walkthrough.py
poetry run basedpyright XBrainLab/llm/agent/tool_call_normalizer.py XBrainLab/llm/tools/application_surface.py scripts/dev/capture_chatpanel_local_pipeline_chain_walkthrough.py tests/unit/llm/agent/test_tool_call_normalizer.py tests/unit/llm/tools/test_application_surface.py tests/unit/scripts/test_capture_chatpanel_local_pipeline_chain_walkthrough.py
timeout 840s env QT_QPA_PLATFORM=offscreen poetry run python scripts/dev/capture_chatpanel_local_pipeline_chain_walkthrough.py --output-dir artifacts/ui/chatpanel-local-pipeline-chain --timeout-seconds 800
```

Expected results:

- pytest: `32 passed`
- ruff: pass
- basedpyright: `0 errors, 0 warnings, 0 notes`
- walkthrough artifact: `status=passed`

## Immediate Resume Steps

1. Check worktree:

```bash
git status --short
```

Only `.vscode/settings.json` and root `settings.json` should be unrelated protected dirty files after the latest slice is committed.

2. Read current truth and records:

```bash
sed -n '1,220p' docs/current.md
sed -n '1,220p' docs/planning/now.md
tail -n 160 docs/records/worklog.md
tail -n 180 docs/records/implementation_log.md
```

3. Do not redo completed ChatPanel short-chain or import-to-dataset pipeline-chain evidence. The analysis-tool exposure gap has also been closed by the post-handoff slice: `evaluate`, `visualize`, and `saliency` are now ApplicationService-backed agent tools with deterministic and affected-case local LLM smoke evidence. Next highest-value product slice:

```text
ChatPanel dataset -> model / training settings -> train -> evaluation / saliency readiness evidence
```

The next slice should still run one verified command per turn. It should not auto-train without explicit confirmation. If local model behavior is unstable, fix parser / normalizer / verifier / prompt / state snapshot instead of only documenting the failure.

## Remaining Product Blockers

- No true ChatPanel dataset -> train/eval/saliency long-chain walkthrough yet.
- Windows Desktop launcher human click-through / WSLg multi-monitor behavior not manually verified.
- MCP Inspector GUI / release config not completed.
- Label import is recipe-trace compatible but not embedded as a mature import wizard label/anchor/MAT variable editor.
- Full UI button-click to real train/eval/visualization completion not done.
- External thesis experiment runner/statistical report not done.
- Goal must remain incomplete until these are either fixed or explicitly documented as not done.

## Handoff Rule

If another resource / context / GPU / WSL limit appears:

- Do not mark complete.
- Commit verified slices only.
- Update `docs/records/worklog.md`.
- Update `docs/records/implementation_log.md`.
- Add or refresh a continuation prompt in `artifacts/goal/`.
