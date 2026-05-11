# XBrainLab Local Tool-Call Eval

- runner: `local-llm`
- model: `microsoft/Phi-3.5-mini-instruct`
- repeat count: `3`
- exploratory: `True`
- runtime classification: `gpu-ready`
- cache usage: `15.34 GB`

## Failure Taxonomy

- None.

## Scoring Detail

# XBrainLab Tool-Call Eval

- runner: `local-llm`
- total cases: `5`
- passed: `5`
- failed: `0`
- pass rate: `100.00%`

## Metrics

| Metric | Accuracy |
| --- | ---: |
| intent | 100.00% |
| tool selection | 100.00% |
| argument correctness | 100.00% |
| state aware | 100.00% |
| verification result match | 100.00% |
| state delta | 100.00% |
| blocked command | 100.00% |
| recovery | 100.00% |
| tool result interpretation | 100.00% |
| trajectory quality | 100.00% |
| runtime safety | 100.00% |
| local llm reliability | 100.00% |

## Method Notes

- [Berkeley Function Calling Leaderboard](https://huggingface.co/datasets/gorilla-llm/Berkeley-Function-Calling-Leaderboard): tool selection, argument matching, multi-turn cases.
- [LangSmith trajectory evaluations](https://docs.langchain.com/langsmith/trajectory-evals): trajectory-level sequence scoring.
- [OpenAI structured outputs/function calling guidance](https://platform.openai.com/docs/guides/structured-outputs): schema-aware tool output and strict result parsing.

## Failed Cases

- None.
