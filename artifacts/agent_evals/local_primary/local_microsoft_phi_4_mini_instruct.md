# XBrainLab Local Tool-Call Eval

- runner: `local-llm`
- model: `microsoft/Phi-4-mini-instruct`
- repeat count: `3`
- exploratory: `False`
- runtime classification: `gpu-ready`
- cache usage: `15.34 GB`

## Failure Taxonomy

- argument mismatch: `3`
- intent: `2`
- state delta mismatch: `1`
- tool selection mismatch: `3`
- trajectory mismatch: `3`

## Scoring Detail

# XBrainLab Tool-Call Eval

- runner: `local-llm`
- total cases: `54`
- passed: `51`
- failed: `3`
- pass rate: `94.44%`

## Metrics

| Metric | Accuracy |
| --- | ---: |
| intent | 96.30% |
| tool selection | 94.44% |
| argument correctness | 94.44% |
| state aware | 100.00% |
| verification result match | 100.00% |
| state delta | 98.15% |
| blocked command | 100.00% |
| recovery | 100.00% |
| tool result interpretation | 100.00% |
| trajectory quality | 94.44% |
| runtime safety | 100.00% |
| local llm reliability | 100.00% |

## Method Notes

- [Berkeley Function Calling Leaderboard](https://huggingface.co/datasets/gorilla-llm/Berkeley-Function-Calling-Leaderboard): tool selection, argument matching, multi-turn cases.
- [LangSmith trajectory evaluations](https://docs.langchain.com/langsmith/trajectory-evals): trajectory-level sequence scoring.
- [OpenAI structured outputs/function calling guidance](https://platform.openai.com/docs/guides/structured-outputs): schema-aware tool output and strict result parsing.

## Failed Cases

- `saliency-before-trained-block`: intent expected saliency, got unknown, tool selection mismatch, argument mismatch, trajectory mismatch
- `visualize-before-trained-block`: intent expected visualize, got unknown, tool selection mismatch, argument mismatch, trajectory mismatch
- `multi-turn-loaded-preprocess`: tool selection mismatch, argument mismatch, state delta mismatch, trajectory mismatch
