# XBrainLab Local Tool-Call Eval

- runner: `local-llm`
- model: `microsoft/Phi-3.5-mini-instruct`
- repeat count: `3`
- exploratory: `False`
- runtime classification: `gpu-ready`
- cache usage: `15.34 GB`

## Failure Taxonomy

- argument mismatch: `4`
- blocked-command handling mismatch: `1`
- intent: `3`
- state delta mismatch: `1`
- state-aware decision mismatch: `1`
- tool selection mismatch: `4`
- trajectory mismatch: `4`
- verification result: `1`

## Scoring Detail

# XBrainLab Tool-Call Eval

- runner: `local-llm`
- total cases: `54`
- passed: `50`
- failed: `4`
- pass rate: `92.59%`

## Metrics

| Metric | Accuracy |
| --- | ---: |
| intent | 94.44% |
| tool selection | 92.59% |
| argument correctness | 92.59% |
| state aware | 98.15% |
| verification result match | 98.15% |
| state delta | 98.15% |
| blocked command | 98.15% |
| recovery | 100.00% |
| tool result interpretation | 100.00% |
| trajectory quality | 92.59% |
| runtime safety | 100.00% |
| local llm reliability | 100.00% |

## Method Notes

- [Berkeley Function Calling Leaderboard](https://huggingface.co/datasets/gorilla-llm/Berkeley-Function-Calling-Leaderboard): tool selection, argument matching, multi-turn cases.
- [LangSmith trajectory evaluations](https://docs.langchain.com/langsmith/trajectory-evals): trajectory-level sequence scoring.
- [OpenAI structured outputs/function calling guidance](https://platform.openai.com/docs/guides/structured-outputs): schema-aware tool output and strict result parsing.

## Failed Cases

- `saliency-before-trained-block`: intent expected saliency, got unknown, tool selection mismatch, argument mismatch, trajectory mismatch
- `visualize-before-trained-block`: intent expected visualize, got unknown, tool selection mismatch, argument mismatch, trajectory mismatch
- `invalid-event-id`: intent expected create_epoch, got generate_dataset, tool selection mismatch, argument mismatch, state-aware decision mismatch, verification result expected recoverable_failure, got blocked, blocked-command handling mismatch, trajectory mismatch
- `multi-turn-loaded-preprocess`: tool selection mismatch, argument mismatch, state delta mismatch, trajectory mismatch
