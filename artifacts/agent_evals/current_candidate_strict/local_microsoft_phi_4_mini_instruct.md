# XBrainLab Local Tool-Call Eval

- runner: `local-llm`
- artifact schema: `xbrainlab.local_tool_call_eval.v5`
- model: `microsoft/Phi-4-mini-instruct`
- prompt condition: `state_capability_unassisted`
- prompt evidence role: `primary raw-accuracy condition`
- prompt condition description: User conversation plus compact backend workflow state, a state-derived complete state-derived action policy, enabled tool contracts, and a model-owned structured decision envelope; no evaluator-derived answer or host intent hint.
- engineering baseline protocol complete: `False`
- thesis-candidate protocol complete: `False`
- claim boundary: Scores support decision and strict host-safety comparisons only. Backend state delta and result interpretation require separately executed outcome evidence. A thesis-candidate decision-accuracy claim also requires primary and fallback reruns from a clean checkpoint with accepted artifacts.
- backend execution observed: `False`
- generated at: `2026-07-19T13:18:36.702798+00:00`
- git commit: `faabfe388e3f21434796aafed1cde3f09535063f`
- worktree dirty: `True`
- case fingerprint: `590ec6ad3af2a01daa40b1a2da8133135b48cec7dd9a3dea7d070d748625da6e`
- prompt fingerprint: `312f26a5fdac9c6d0970e4a38111ee826576db873a6e9547f2db0d300da1946e`
- tool contract fingerprint: `ab4c679a8f19228d3a5c018eb1dc1f329ae544ada6b31c56ae81e428547a6b19`
- model revision: `cfbefacb99257ffa30c83adab238a50856ac3083`
- repeat count: `3`
- exploratory: `True`
- CLI gate mode: `report_only`
- CLI gate passed: `False`
- CLI gate exit code: `0`
- runtime classification: `gpu-ready`
- cache usage: `15.34 GB`
- generation constraint: `hf_lexical_constraint`
- raw output postprocessed: `False`

## Score Interpretation

### Raw Model Score

- pass rate: `50.00%`
- computed before tool alias normalization, argument repair, or safe backend blocking
- host-assisted and backend outcome dimensions are N/A/excluded

### Host-Assisted Product Score

- pass rate: `100.00%`
- includes product normalization, verification, and capability-policy blocking
- backend state delta and result interpretation remain N/A/excluded because this runner does not execute commands
- this score must not be reported as raw model tool-call accuracy

## Resource Preflight

- ok: `True`
- gate: `release local subset`
- eval gate: `release`
- resource pressure: `normal`
- selected cases: `12`
- cache usage: `15.34 GB`
- available disk: `127.62 GB`
- estimated VRAM: `9.0` GB
- GPU: `NVIDIA GeForce RTX 5070 Ti`
- VRAM used/free/total MiB: `991` / `15005` / `16303`
- message: Resource preflight passed for this eval gate.

## Failure Taxonomy

- blocked-command handling mismatch: `6`
- clarification behavior mismatch: `1`
- intent: `3`
- missing-input field mismatch: `1`
- state-aware decision mismatch: `5`
- tool/no-tool decision mismatch: `5`
- trajectory mismatch: `5`

## Strict Envelope Recovery

- first_attempt_blocked: `3`
- first_attempt_tool: `33`

## Scoring Detail

# XBrainLab Tool-Call Eval

- runner: `local-llm`
- total cases: `12`
- passed: `6`
- failed: `6`
- pass rate: `50.00%`
- score scope: `raw_model_decision`
- excluded dimensions: `verification_result, runtime_safety, confirmation_boundary, state_delta, tool_result_interpretation`

## Metrics

| Metric | Accuracy | Included | Excluded | Status |
| --- | ---: | ---: | ---: | --- |
| verification result | N/A | 0 | 12 | excluded |
| intent | 72.73% | 11 | 1 | partial |
| tool selection | 100.00% | 6 | 6 | partial |
| argument correctness | 100.00% | 6 | 6 | partial |
| state aware | 58.33% | 12 | 0 | measured |
| blocked command | 50.00% | 12 | 0 | measured |
| recovery | 100.00% | 12 | 0 | measured |
| trajectory quality | 58.33% | 12 | 0 | measured |
| local llm reliability | 100.00% | 12 | 0 | measured |
| tool or no tool decision | 58.33% | 12 | 0 | measured |
| clarification behavior | 91.67% | 12 | 0 | measured |
| missing input fields | 0.00% | 1 | 11 | partial |
| visible response quality | 100.00% | 12 | 0 | measured |
| output format | 100.00% | 12 | 0 | measured |
| runtime safety | N/A | 0 | 12 | excluded |
| confirmation boundary | N/A | 0 | 12 | excluded |
| state delta | N/A | 0 | 12 | excluded |
| tool result interpretation | N/A | 0 | 12 | excluded |

## Method Notes

- [Berkeley Function Calling Leaderboard](https://huggingface.co/datasets/gorilla-llm/Berkeley-Function-Calling-Leaderboard): tool selection, argument matching, multi-turn cases.
- [LangSmith trajectory evaluations](https://docs.langchain.com/langsmith/trajectory-evals): trajectory-level sequence scoring.
- [OpenAI structured outputs/function calling guidance](https://platform.openai.com/docs/guides/structured-outputs): schema-aware tool output and strict result parsing.

## Case Families

| Family | Cases | Passed | Pass Rate |
| --- | ---: | ---: | ---: |
| baseline | 9 | 4 | 44.44% |
| blocked_command | 6 | 0 | 0.00% |
| data_interpretation | 3 | 2 | 66.67% |
| missing_input | 1 | 0 | 0.00% |
| multi_turn | 1 | 1 | 100.00% |
| recovery | 2 | 1 | 50.00% |

## Failure Taxonomy

- blocked-command handling mismatch: `6`
- clarification behavior mismatch: `1`
- intent: `3`
- missing-input field mismatch: `1`
- state-aware decision mismatch: `5`
- tool/no-tool decision mismatch: `5`
- trajectory mismatch: `5`

## Worst Cases

- `empty-train-block` (baseline, blocked_command): intent expected train, got unknown, state-aware decision mismatch, blocked-command handling mismatch, trajectory mismatch, tool/no-tool decision mismatch
- `empty-load-missing-path` (blocked_command, data_interpretation, missing_input, recovery): state-aware decision mismatch, blocked-command handling mismatch, trajectory mismatch, tool/no-tool decision mismatch, clarification behavior mismatch, missing-input field mismatch
- `empty-preprocess-block` (baseline, blocked_command): blocked-command handling mismatch
- `loaded-create-epoch-block` (baseline, blocked_command): intent expected create_epoch, got unknown, state-aware decision mismatch, blocked-command handling mismatch, trajectory mismatch, tool/no-tool decision mismatch
- `loaded-generate-dataset-block` (baseline, blocked_command): state-aware decision mismatch, blocked-command handling mismatch, trajectory mismatch, tool/no-tool decision mismatch
- `dataset-train-missing-config` (baseline, blocked_command): intent expected train, got configure_training, state-aware decision mismatch, blocked-command handling mismatch, trajectory mismatch, tool/no-tool decision mismatch

## Sources And Artifacts


## Thesis Claim Boundary

- This report measures tool-call trajectory behavior, not EEG model training accuracy.
- Thesis-ready claims require local primary/fallback runs with at least three repeats and matching UI-observable workflow evidence.

## Failed Cases

- `empty-train-block`: intent expected train, got unknown, state-aware decision mismatch, blocked-command handling mismatch, trajectory mismatch, tool/no-tool decision mismatch
- `empty-load-missing-path`: state-aware decision mismatch, blocked-command handling mismatch, trajectory mismatch, tool/no-tool decision mismatch, clarification behavior mismatch, missing-input field mismatch
- `empty-preprocess-block`: blocked-command handling mismatch
- `loaded-create-epoch-block`: intent expected create_epoch, got unknown, state-aware decision mismatch, blocked-command handling mismatch, trajectory mismatch, tool/no-tool decision mismatch
- `loaded-generate-dataset-block`: state-aware decision mismatch, blocked-command handling mismatch, trajectory mismatch, tool/no-tool decision mismatch
- `dataset-train-missing-config`: intent expected train, got configure_training, state-aware decision mismatch, blocked-command handling mismatch, trajectory mismatch, tool/no-tool decision mismatch
