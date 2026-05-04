# XBrainLab Product Completion Continuation

Date: `2026-05-04`

Use this after usage refresh. Continue from active repo:

```text
/mnt/d/workspace_v2/projects/lab/XBrainLab
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

## Latest Completed Slice

The latest product slice added a true local ChatPanel Data Interpretation tool-chain walkthrough.

Files changed in that slice:

- `XBrainLab/llm/agent/tool_call_normalizer.py`
- `tests/unit/llm/agent/test_tool_call_normalizer.py`
- `scripts/dev/capture_chatpanel_local_tool_chain_walkthrough.py`
- `tests/unit/scripts/test_capture_chatpanel_local_tool_chain_walkthrough.py`
- `artifacts/ui/chatpanel-local-tool-chain/*`
- `docs/current.md`
- `docs/planning/now.md`
- `docs/validation/README.md`
- `docs/records/worklog.md`
- `docs/records/implementation_log.md`
- this continuation prompt

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

Important root cause fixed:

- First real run showed `scan_source` succeeded, but `preview_interpretation`
  failed as if no scan existed.
- Final state showed `latest_scan_id=scan-1`, so ApplicationService state was not lost.
- The local model was generating schema-derived placeholder ids such as
  `latest_scan_id`, which overrode backend latest-state fallback.
- Normalizer now keeps only backend-generated id forms:
  - `scan-<n>` for `scan_id`
  - `candidate-<n>` for `candidate_id`
- Other generated/latest/current/id placeholders are removed so ApplicationService uses current state.

Validated commands already run:

```bash
poetry run pytest --capture=sys tests/unit/llm/agent/test_tool_call_normalizer.py tests/unit/scripts/test_capture_chatpanel_local_tool_chain_walkthrough.py -q
poetry run ruff check XBrainLab/llm/agent/tool_call_normalizer.py scripts/dev/capture_chatpanel_local_tool_chain_walkthrough.py tests/unit/llm/agent/test_tool_call_normalizer.py tests/unit/scripts/test_capture_chatpanel_local_tool_chain_walkthrough.py
poetry run basedpyright XBrainLab/llm/agent/tool_call_normalizer.py scripts/dev/capture_chatpanel_local_tool_chain_walkthrough.py tests/unit/llm/agent/test_tool_call_normalizer.py tests/unit/scripts/test_capture_chatpanel_local_tool_chain_walkthrough.py
timeout 620s env QT_QPA_PLATFORM=offscreen poetry run python scripts/dev/capture_chatpanel_local_tool_chain_walkthrough.py --output-dir artifacts/ui/chatpanel-local-tool-chain --timeout-seconds 580
```

Expected results:

- pytest: `30 passed`
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

3. Do not redo the completed short chain. Next highest-value product slice:

```text
ChatPanel confirm/apply -> preprocess -> epoch -> dataset workflow evidence
```

The next slice should still run one verified command per turn. It should not auto-train without explicit confirmation. If local model behavior is unstable, fix parser / normalizer / verifier / prompt / state snapshot instead of only documenting the failure.

## Remaining Product Blockers

- No true ChatPanel confirm/apply -> preprocess -> epoch -> dataset -> train/eval/saliency long-chain walkthrough yet.
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
