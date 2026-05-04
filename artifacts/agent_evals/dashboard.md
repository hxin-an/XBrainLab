# XBrainLab Tool-Call Eval Dashboard

- eval directory: `artifacts/agent_evals`
- result count: `3`

## Model Comparison

| Runner / Model | Cases | Repeats | Pass Rate | Stability | Exploratory |
| --- | ---: | ---: | ---: | ---: | --- |
| deterministic-scripted-baseline / deterministic | 118 | - | 100.00% | 100.00% | False |
| local-llm / microsoft/Phi-3.5-mini-instruct | 118 | 3 | 100.00% | 100.00% | False |
| local-llm / microsoft/Phi-4-mini-instruct | 118 | 3 | 100.00% | 100.00% | False |

## Metric Pass Rates

| Metric | deterministic | Phi-3.5-mini-instruct | Phi-4-mini-instruct |
| --- | ---: | ---: | ---: |
| argument correctness | 100.00% | 100.00% | 100.00% |
| blocked command | 100.00% | 100.00% | 100.00% |
| clarification behavior | 100.00% | 100.00% | 100.00% |
| confirmation boundary | 100.00% | 100.00% | 100.00% |
| intent | 100.00% | 100.00% | 100.00% |
| local llm reliability | 100.00% | 100.00% | 100.00% |
| recovery | 100.00% | 100.00% | 100.00% |
| runtime safety | 100.00% | 100.00% | 100.00% |
| state aware | 100.00% | 100.00% | 100.00% |
| state delta | 100.00% | 100.00% | 100.00% |
| tool or no tool decision | 100.00% | 100.00% | 100.00% |
| tool result interpretation | 100.00% | 100.00% | 100.00% |
| tool selection | 100.00% | 100.00% | 100.00% |
| trajectory quality | 100.00% | 100.00% | 100.00% |
| verification result match | 100.00% | 100.00% | 100.00% |
| visible response quality | 100.00% | 100.00% | 100.00% |

## Family Pass Rates

| Family | deterministic | Phi-3.5-mini-instruct | Phi-4-mini-instruct |
| --- | ---: | ---: | ---: |
| ambiguous_request | 100.00% (1/1) | 100.00% (1/1) | 100.00% (1/1) |
| baseline | 100.00% (100/100) | 100.00% (100/100) | 100.00% (100/100) |
| bids | 100.00% (6/6) | 100.00% (6/6) | 100.00% (6/6) |
| blocked_command | 100.00% (32/32) | 100.00% (32/32) | 100.00% (32/32) |
| chinese | 100.00% (15/15) | 100.00% (15/15) | 100.00% (15/15) |
| confirmation_boundary | 100.00% (10/10) | 100.00% (10/10) | 100.00% (10/10) |
| data_interpretation | 100.00% (60/60) | 100.00% (60/60) | 100.00% (60/60) |
| destructive | 100.00% (1/1) | 100.00% (1/1) | 100.00% (1/1) |
| domain_phrasing | 100.00% (2/2) | 100.00% (2/2) | 100.00% (2/2) |
| label_ambiguity | 100.00% (2/2) | 100.00% (2/2) | 100.00% (2/2) |
| missing_input | 100.00% (2/2) | 100.00% (2/2) | 100.00% (2/2) |
| mixed_language | 100.00% (11/11) | 100.00% (11/11) | 100.00% (11/11) |
| multi_intent | 100.00% (2/2) | 100.00% (2/2) | 100.00% (2/2) |
| multi_turn | 100.00% (24/24) | 100.00% (24/24) | 100.00% (24/24) |
| no_call | 100.00% (4/4) | 100.00% (4/4) | 100.00% (4/4) |
| recovery | 100.00% (27/27) | 100.00% (27/27) | 100.00% (27/27) |
| should_not_call | 100.00% (2/2) | 100.00% (2/2) | 100.00% (2/2) |
| subject_metadata | 100.00% (1/1) | 100.00% (1/1) | 100.00% (1/1) |
| wrong_tool_temptation | 100.00% (2/2) | 100.00% (2/2) | 100.00% (2/2) |

## Failure Taxonomy

- None.

## Worst Cases

- None.

## Sources And Artifacts

- deterministic source: `/mnt/d/workspace_v2/projects/lab/XBrainLab/scripts/agent/evals/run_tool_call_eval.py`
- deterministic json: `artifacts/agent_evals/latest.json`
- deterministic markdown: `artifacts/agent_evals/latest.md`
- Phi-3.5-mini-instruct source: `/mnt/d/workspace_v2/projects/lab/XBrainLab/scripts/agent/evals/run_tool_call_eval.py`
- Phi-3.5-mini-instruct source: `/mnt/d/workspace_v2/projects/lab/XBrainLab/scripts/agent/evals/run_local_tool_call_eval.py`
- Phi-3.5-mini-instruct json: `artifacts/agent_evals/local_fallback/local_microsoft_phi_3.5_mini_instruct.json`
- Phi-3.5-mini-instruct markdown: `artifacts/agent_evals/local_fallback/local_microsoft_phi_3.5_mini_instruct.md`
- Phi-3.5-mini-instruct latest_json: `artifacts/agent_evals/local_fallback/local_latest.json`
- Phi-3.5-mini-instruct latest_markdown: `artifacts/agent_evals/local_fallback/local_latest.md`
- Phi-4-mini-instruct source: `/mnt/d/workspace_v2/projects/lab/XBrainLab/scripts/agent/evals/run_tool_call_eval.py`
- Phi-4-mini-instruct source: `/mnt/d/workspace_v2/projects/lab/XBrainLab/scripts/agent/evals/run_local_tool_call_eval.py`
- Phi-4-mini-instruct json: `artifacts/agent_evals/local_primary/local_microsoft_phi_4_mini_instruct.json`
- Phi-4-mini-instruct markdown: `artifacts/agent_evals/local_primary/local_microsoft_phi_4_mini_instruct.md`
- Phi-4-mini-instruct latest_json: `artifacts/agent_evals/local_primary/local_latest.json`
- Phi-4-mini-instruct latest_markdown: `artifacts/agent_evals/local_primary/local_latest.md`

## Thesis Claim Boundary

- Local tool-call eval currently supports a thesis-candidate tool-call claim for this benchmark slice.
- This does not claim EEG training accuracy, full UI usability, Windows launcher coverage, or product completion.
