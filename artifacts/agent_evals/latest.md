# XBrainLab Tool-Call Eval

- runner: `deterministic-scripted-baseline`
- total cases: `121`
- passed: `121`
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
| tool or no tool decision | 100.00% |
| clarification behavior | 100.00% |
| confirmation boundary | 100.00% |
| visible response quality | 100.00% |

## Method Notes

- [Berkeley Function Calling Leaderboard](https://huggingface.co/datasets/gorilla-llm/Berkeley-Function-Calling-Leaderboard): tool selection, argument matching, multi-turn cases.
- [LangSmith trajectory evaluations](https://docs.langchain.com/langsmith/trajectory-evals): trajectory-level sequence scoring.
- [OpenAI structured outputs/function calling guidance](https://platform.openai.com/docs/guides/structured-outputs): schema-aware tool output and strict result parsing.

## Case Families

| Family | Cases | Passed | Pass Rate |
| --- | ---: | ---: | ---: |
| ambiguous_request | 1 | 1 | 100.00% |
| baseline | 94 | 94 | 100.00% |
| bids | 6 | 6 | 100.00% |
| blocked_command | 33 | 33 | 100.00% |
| blocked_state | 1 | 1 | 100.00% |
| chinese | 15 | 15 | 100.00% |
| confirmation_boundary | 10 | 10 | 100.00% |
| data_interpretation | 68 | 68 | 100.00% |
| destructive | 1 | 1 | 100.00% |
| domain_phrasing | 2 | 2 | 100.00% |
| label_ambiguity | 3 | 3 | 100.00% |
| legacy_compatibility | 1 | 1 | 100.00% |
| missing_input | 4 | 4 | 100.00% |
| mixed_language | 11 | 11 | 100.00% |
| multi_intent | 2 | 2 | 100.00% |
| multi_turn | 24 | 24 | 100.00% |
| no_call | 4 | 4 | 100.00% |
| recipe_reload | 3 | 3 | 100.00% |
| recovery | 29 | 29 | 100.00% |
| should_not_call | 2 | 2 | 100.00% |
| subject_metadata | 1 | 1 | 100.00% |
| wrong_tool_temptation | 2 | 2 | 100.00% |

## Failure Taxonomy

- None.

## Worst Cases

- None.

## Sources And Artifacts

- case source: `/mnt/d/workspace_v2/projects/lab/XBrainLab/scripts/agent/evals/run_tool_call_eval.py`
- json: `artifacts/agent_evals/latest.json`
- markdown: `artifacts/agent_evals/latest.md`

## Thesis Claim Boundary

- This report measures tool-call trajectory behavior, not EEG model training accuracy.
- Thesis-ready claims require local primary/fallback runs with at least three repeats and matching UI-observable workflow evidence.

## Failed Cases

- None.
