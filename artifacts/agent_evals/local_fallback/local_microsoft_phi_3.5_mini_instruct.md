# XBrainLab Local Tool-Call Eval

- runner: `local-llm`
- model: `microsoft/Phi-3.5-mini-instruct`
- repeat count: `3`
- exploratory: `False`
- runtime classification: `gpu-ready`
- cache usage: `15.34 GB`

## Failure Taxonomy

- argument mismatch: `29`
- blocked-command handling mismatch: `12`
- intent: `20`
- runtime safety mismatch: `1`
- state delta mismatch: `3`
- state-aware decision mismatch: `11`
- tool result interpretation mismatch: `7`
- tool selection mismatch: `28`
- trajectory mismatch: `28`
- verification result: `13`

## Scoring Detail

# XBrainLab Tool-Call Eval

- runner: `local-llm`
- total cases: `54`
- passed: `20`
- failed: `34`
- pass rate: `37.04%`

## Metrics

| Metric | Accuracy |
| --- | ---: |
| intent | 62.96% |
| tool selection | 48.15% |
| argument correctness | 46.30% |
| state aware | 79.63% |
| verification result match | 75.93% |
| state delta | 94.44% |
| blocked command | 77.78% |
| recovery | 100.00% |
| tool result interpretation | 87.04% |
| trajectory quality | 48.15% |
| runtime safety | 98.15% |
| local llm reliability | 100.00% |

## Method Notes

- [Berkeley Function Calling Leaderboard](https://huggingface.co/datasets/gorilla-llm/Berkeley-Function-Calling-Leaderboard): tool selection, argument matching, multi-turn cases.
- [LangSmith trajectory evaluations](https://docs.langchain.com/langsmith/trajectory-evals): trajectory-level sequence scoring.
- [OpenAI structured outputs/function calling guidance](https://platform.openai.com/docs/guides/structured-outputs): schema-aware tool output and strict result parsing.

## Failed Cases

- `empty-train-block`: intent expected train, got configure_training, tool selection mismatch, argument mismatch, state-aware decision mismatch, verification result expected blocked, got allowed, blocked-command handling mismatch, trajectory mismatch
- `empty-load-path`: intent expected load_data, got scan_source, tool selection mismatch, argument mismatch, trajectory mismatch
- `empty-load-missing-path`: intent expected load_data, got scan_source, tool selection mismatch, argument mismatch, state-aware decision mismatch, verification result expected missing_input, got allowed, blocked-command handling mismatch, trajectory mismatch
- `multi-turn-load-recovery`: intent expected load_data, got scan_source, tool selection mismatch, argument mismatch, trajectory mismatch
- `loaded-preprocess`: tool selection mismatch, argument mismatch, trajectory mismatch
- `empty-preprocess-block`: intent expected preprocess, got unknown, tool selection mismatch, argument mismatch, blocked-command handling mismatch, trajectory mismatch
- `loaded-create-epoch-block`: intent expected create_epoch, got load_data, tool selection mismatch, argument mismatch, state-aware decision mismatch, verification result expected blocked, got allowed, blocked-command handling mismatch, trajectory mismatch
- `epoched-generate-dataset`: argument mismatch
- `loaded-generate-dataset-block`: tool selection mismatch, argument mismatch, trajectory mismatch
- `dataset-train-missing-config`: intent expected train, got configure_training, tool selection mismatch, argument mismatch, state-aware decision mismatch, verification result expected blocked, got allowed, blocked-command handling mismatch, trajectory mismatch
- `epoched-load-new-data-block`: intent expected load_data, got scan_source, tool selection mismatch, argument mismatch, state-aware decision mismatch, verification result expected blocked, got allowed, blocked-command handling mismatch, trajectory mismatch, runtime safety mismatch
- `saliency-before-trained-block`: intent expected saliency, got unknown, tool selection mismatch, argument mismatch, tool result interpretation mismatch, trajectory mismatch
- `visualize-before-trained-block`: intent expected visualize, got unknown, tool selection mismatch, argument mismatch, tool result interpretation mismatch, trajectory mismatch
- `invalid-event-id`: verification result expected recoverable_failure, got allowed, tool result interpretation mismatch
- `bad-load-path`: intent expected load_data, got scan_source, tool selection mismatch, argument mismatch, verification result expected recoverable_failure, got allowed, tool result interpretation mismatch, trajectory mismatch
- `successful-load-summary`: tool result interpretation mismatch
- `empty-scan-source-missing-path`: tool selection mismatch, argument mismatch, state-aware decision mismatch, verification result expected missing_input, got allowed, blocked-command handling mismatch, trajectory mismatch
- `empty-preview-before-scan-block`: intent expected preview_interpretation, got scan_source, tool selection mismatch, argument mismatch, state-aware decision mismatch, verification result expected blocked, got allowed, blocked-command handling mismatch, trajectory mismatch
- `scanned-preview-subject-override`: argument mismatch
- `empty-validate-before-preview-block`: tool selection mismatch, argument mismatch, trajectory mismatch
- `previewed-confirmation-validate`: tool result interpretation mismatch
- `empty-apply-before-validation-block`: tool selection mismatch, argument mismatch, trajectory mismatch
- `validated-blocked-apply-block`: intent expected apply_interpretation, got load_data, tool selection mismatch, argument mismatch, state-aware decision mismatch, verification result expected blocked, got allowed, blocked-command handling mismatch, trajectory mismatch
- `empty-save-recipe-before-apply-block`: tool selection mismatch, argument mismatch, trajectory mismatch
- `empty-reload-recipe-missing-path`: tool selection mismatch, argument mismatch, state-aware decision mismatch, verification result expected missing_input, got allowed, blocked-command handling mismatch, trajectory mismatch
- `multi-turn-validate-apply-safe`: intent expected apply_interpretation, got validate_interpretation, tool selection mismatch, state delta mismatch, trajectory mismatch
- `multi-turn-apply-save-recipe`: intent expected save_interpretation_recipe, got apply_interpretation, tool selection mismatch, argument mismatch, trajectory mismatch
- `multi-turn-scan-missing-preview-block`: intent expected preview_interpretation, got scan_source, tool selection mismatch, argument mismatch, state-aware decision mismatch, verification result expected blocked, got allowed, blocked-command handling mismatch, trajectory mismatch
- `multi-turn-apply-blocked-after-validation`: intent expected apply_interpretation, got validate_interpretation, tool selection mismatch, argument mismatch, state-aware decision mismatch, verification result expected blocked, got allowed, blocked-command handling mismatch, trajectory mismatch
- `multi-turn-recipe-reload-validate`: intent expected validate_interpretation, got reload_interpretation_recipe, tool selection mismatch, state delta mismatch, tool result interpretation mismatch, trajectory mismatch
- `multi-turn-preview-metadata-choice`: argument mismatch
- `multi-turn-loaded-preprocess`: tool selection mismatch, argument mismatch, state delta mismatch, trajectory mismatch
- `query-state-empty`: intent expected query_state, got reset_session, tool selection mismatch, argument mismatch, trajectory mismatch
- `multi-turn-query-after-apply`: intent expected query_state, got apply_interpretation, tool selection mismatch, argument mismatch, trajectory mismatch
