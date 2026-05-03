# XBrainLab Local Tool-Call Eval

- runner: `local-llm`
- model: `microsoft/Phi-4-mini-instruct`
- repeat count: `3`
- exploratory: `False`
- runtime classification: `gpu-ready`
- cache usage: `15.34 GB`

## Failure Taxonomy

- argument mismatch: `24`
- blocked-command handling mismatch: `15`
- intent: `15`
- state delta mismatch: `5`
- state-aware decision mismatch: `10`
- tool result interpretation mismatch: `7`
- tool selection mismatch: `23`
- trajectory mismatch: `23`
- verification result: `12`

## Scoring Detail

# XBrainLab Tool-Call Eval

- runner: `local-llm`
- total cases: `54`
- passed: `18`
- failed: `36`
- pass rate: `33.33%`

## Metrics

| Metric | Accuracy |
| --- | ---: |
| intent | 72.22% |
| tool selection | 57.41% |
| argument correctness | 55.56% |
| state aware | 81.48% |
| verification result match | 77.78% |
| state delta | 90.74% |
| blocked command | 72.22% |
| recovery | 100.00% |
| tool result interpretation | 87.04% |
| trajectory quality | 57.41% |
| runtime safety | 100.00% |
| local llm reliability | 100.00% |

## Method Notes

- [Berkeley Function Calling Leaderboard](https://huggingface.co/datasets/gorilla-llm/Berkeley-Function-Calling-Leaderboard): tool selection, argument matching, multi-turn cases.
- [LangSmith trajectory evaluations](https://docs.langchain.com/langsmith/trajectory-evals): trajectory-level sequence scoring.
- [OpenAI structured outputs/function calling guidance](https://platform.openai.com/docs/guides/structured-outputs): schema-aware tool output and strict result parsing.

## Failed Cases

- `empty-train-block`: intent expected train, got configure_training, tool selection mismatch, argument mismatch, state-aware decision mismatch, verification result expected blocked, got allowed, blocked-command handling mismatch, trajectory mismatch
- `empty-load-missing-path`: tool selection mismatch, argument mismatch, state-aware decision mismatch, verification result expected missing_input, got allowed, blocked-command handling mismatch, trajectory mismatch
- `loaded-preprocess`: tool selection mismatch, argument mismatch, trajectory mismatch
- `empty-preprocess-block`: intent expected preprocess, got configure_training, tool selection mismatch, argument mismatch, state-aware decision mismatch, verification result expected blocked, got allowed, blocked-command handling mismatch, trajectory mismatch
- `preprocessed-create-epoch`: argument mismatch
- `loaded-create-epoch-block`: intent expected create_epoch, got unknown, tool selection mismatch, argument mismatch, blocked-command handling mismatch, trajectory mismatch
- `epoched-generate-dataset`: argument mismatch
- `loaded-generate-dataset-block`: intent expected generate_dataset, got load_data, tool selection mismatch, argument mismatch, state-aware decision mismatch, verification result expected blocked, got allowed, blocked-command handling mismatch, trajectory mismatch
- `dataset-train-missing-config`: intent expected train, got configure_training, tool selection mismatch, argument mismatch, state-aware decision mismatch, verification result expected blocked, got allowed, blocked-command handling mismatch, trajectory mismatch
- `epoched-load-new-data-block`: tool selection mismatch, argument mismatch, trajectory mismatch
- `saliency-before-trained-block`: intent expected saliency, got unknown, tool selection mismatch, argument mismatch, tool result interpretation mismatch, trajectory mismatch
- `visualize-before-trained-block`: intent expected visualize, got unknown, tool selection mismatch, argument mismatch, tool result interpretation mismatch, trajectory mismatch
- `invalid-event-id`: verification result expected recoverable_failure, got allowed, tool result interpretation mismatch
- `bad-load-path`: verification result expected recoverable_failure, got allowed, tool result interpretation mismatch
- `successful-load-summary`: tool result interpretation mismatch
- `empty-scan-source-bids-folder`: argument mismatch
- `empty-scan-source-missing-path`: tool selection mismatch, argument mismatch, state-aware decision mismatch, verification result expected missing_input, got allowed, blocked-command handling mismatch, trajectory mismatch
- `empty-preview-before-scan-block`: intent expected preview_interpretation, got scan_source, tool selection mismatch, argument mismatch, state-aware decision mismatch, verification result expected blocked, got allowed, blocked-command handling mismatch, trajectory mismatch
- `scanned-preview-subject-override`: argument mismatch
- `empty-validate-before-preview-block`: tool selection mismatch, argument mismatch, trajectory mismatch
- `previewed-confirmation-validate`: tool result interpretation mismatch
- `validated-safe-apply`: tool selection mismatch, argument mismatch, state-aware decision mismatch, verification result expected allowed, got blocked, state delta mismatch, blocked-command handling mismatch, trajectory mismatch
- `empty-apply-before-validation-block`: blocked-command handling mismatch
- `validated-blocked-apply-block`: blocked-command handling mismatch
- `empty-save-recipe-before-apply-block`: blocked-command handling mismatch
- `empty-reload-recipe-missing-path`: tool selection mismatch, argument mismatch, state-aware decision mismatch, verification result expected missing_input, got allowed, blocked-command handling mismatch, trajectory mismatch
- `multi-turn-scan-preview`: intent expected preview_interpretation, got scan_source, tool selection mismatch, state delta mismatch, trajectory mismatch
- `multi-turn-validate-apply-safe`: intent expected apply_interpretation, got validate_interpretation, tool selection mismatch, state delta mismatch, trajectory mismatch
- `multi-turn-apply-save-recipe`: intent expected save_interpretation_recipe, got apply_interpretation, tool selection mismatch, trajectory mismatch
- `multi-turn-scan-missing-preview-block`: intent expected preview_interpretation, got scan_source, tool selection mismatch, argument mismatch, state-aware decision mismatch, verification result expected blocked, got allowed, blocked-command handling mismatch, trajectory mismatch
- `multi-turn-apply-blocked-after-validation`: intent expected apply_interpretation, got validate_interpretation, blocked-command handling mismatch
- `multi-turn-recipe-reload-validate`: intent expected validate_interpretation, got reload_interpretation_recipe, tool selection mismatch, state delta mismatch, tool result interpretation mismatch, trajectory mismatch
- `multi-turn-preview-metadata-choice`: argument mismatch
- `multi-turn-loaded-preprocess`: tool selection mismatch, argument mismatch, state delta mismatch, trajectory mismatch
- `query-state-empty`: tool selection mismatch, argument mismatch, trajectory mismatch
- `multi-turn-query-after-apply`: intent expected query_state, got apply_interpretation, tool selection mismatch, argument mismatch, trajectory mismatch
