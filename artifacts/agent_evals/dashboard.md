# XBrainLab Tool-Call Eval Dashboard

- eval directory: `artifacts/agent_evals`
- result count: `2`

## Model Comparison

| Runner / Model | Cases | Repeats | Raw Model Pass Rate | Host-Assisted Pass Rate | Stability | Exploratory |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| deterministic-scripted-baseline / deterministic | 121 | - | 100.00% | - | 100.00% | False |
| local-llm / microsoft/Phi-4-mini-instruct | 12 | 3 | 50.00% | 100.00% | 100.00% | True |

## Robustness / Anti-Overfit Gate

| Slice | Model | Cases | Repeats | Raw Model | Host Safety | Raw Gate |
| --- | --- | ---: | ---: | ---: | ---: | --- |
| Anti-overfit paraphrases | Phi-4-mini-instruct | 7 | 3 | 14.29% | 100.00% | FAIL |

- Raw gate failed: product safety may still pass, but raw local-model accuracy is not release- or thesis-ready.

## Metric Pass Rates

| Metric | deterministic | Phi-4-mini-instruct |
| --- | ---: | ---: |
| argument correctness | 100.00% | 100.00% (6/6) |
| blocked command | 100.00% | 50.00% (6/12) |
| clarification behavior | 100.00% | 91.67% (11/12) |
| confirmation boundary | 100.00% | N/A (0/0) |
| intent | 100.00% | 72.73% (8/11) |
| local llm reliability | 100.00% | 100.00% (12/12) |
| missing input fields | N/A | 0.00% (0/1) |
| output format | N/A | 100.00% (12/12) |
| recovery | 100.00% | 100.00% (12/12) |
| runtime safety | 100.00% | N/A (0/0) |
| state aware | 100.00% | 58.33% (7/12) |
| state delta | 100.00% | N/A (0/0) |
| tool or no tool decision | 100.00% | 58.33% (7/12) |
| tool result interpretation | 100.00% | N/A (0/0) |
| tool selection | 100.00% | 100.00% (6/6) |
| trajectory quality | 100.00% | 58.33% (7/12) |
| verification result match | 100.00% | N/A |
| visible response quality | 100.00% | 100.00% (12/12) |

## Metric Definitions

- Tool selection is measured only on cases that expect a direct tool call.
- Argument correctness is conditional on correct tool selection; wrong-tool and no-tool cases are excluded from its denominator.
- Tool/no-tool decision is measured across all cases.
- Missing-input fields require an exact set of machine-readable field identifiers.
- Raw model and host-assisted scores remain separate; host safety cannot replace raw model accuracy.

## Family Pass Rates

| Family | deterministic | Phi-4-mini-instruct |
| --- | ---: | ---: |
| ambiguous_request | 100.00% (1/1) | - |
| baseline | 100.00% (94/94) | 44.44% (4/9) |
| bids | 100.00% (6/6) | - |
| blocked_command | 100.00% (33/33) | 0.00% (0/6) |
| blocked_state | 100.00% (1/1) | - |
| chinese | 100.00% (15/15) | - |
| confirmation_boundary | 100.00% (10/10) | - |
| data_interpretation | 100.00% (68/68) | 66.67% (2/3) |
| destructive | 100.00% (1/1) | - |
| domain_phrasing | 100.00% (2/2) | - |
| label_ambiguity | 100.00% (3/3) | - |
| legacy_compatibility | 100.00% (1/1) | - |
| missing_input | 100.00% (4/4) | 0.00% (0/1) |
| mixed_language | 100.00% (11/11) | - |
| multi_intent | 100.00% (2/2) | - |
| multi_turn | 100.00% (24/24) | 100.00% (1/1) |
| no_call | 100.00% (4/4) | - |
| recipe_reload | 100.00% (3/3) | - |
| recovery | 100.00% (29/29) | 50.00% (1/2) |
| should_not_call | 100.00% (2/2) | - |
| subject_metadata | 100.00% (1/1) | - |
| wrong_tool_temptation | 100.00% (2/2) | - |

## Failure Taxonomy

- Phi-4-mini-instruct: blocked-command handling mismatch=6, clarification behavior mismatch=1, intent=3, missing-input field mismatch=1, state-aware decision mismatch=5, tool/no-tool decision mismatch=5, trajectory mismatch=5

## Worst Cases

- Phi-4-mini-instruct `empty-train-block`: intent expected train, got unknown, state-aware decision mismatch, blocked-command handling mismatch, trajectory mismatch, tool/no-tool decision mismatch
- Phi-4-mini-instruct `empty-load-missing-path`: state-aware decision mismatch, blocked-command handling mismatch, trajectory mismatch, tool/no-tool decision mismatch, clarification behavior mismatch, missing-input field mismatch
- Phi-4-mini-instruct `empty-preprocess-block`: blocked-command handling mismatch
- Phi-4-mini-instruct `loaded-create-epoch-block`: intent expected create_epoch, got unknown, state-aware decision mismatch, blocked-command handling mismatch, trajectory mismatch, tool/no-tool decision mismatch
- Phi-4-mini-instruct `loaded-generate-dataset-block`: state-aware decision mismatch, blocked-command handling mismatch, trajectory mismatch, tool/no-tool decision mismatch
- Phi-4-mini-instruct `dataset-train-missing-config`: intent expected train, got configure_training, state-aware decision mismatch, blocked-command handling mismatch, trajectory mismatch, tool/no-tool decision mismatch

## Sources And Artifacts

- deterministic source: `/mnt/d/workspace_v2/projects/lab/XBrainLab/scripts/agent/evals/run_tool_call_eval.py`
- deterministic json: `artifacts/agent_evals/latest.json`
- deterministic markdown: `artifacts/agent_evals/latest.md`
- Phi-4-mini-instruct source: `/mnt/d/workspace_v2/projects/lab/xbrainlab/scripts/agent/evals/run_tool_call_eval.py`
- Phi-4-mini-instruct source: `/mnt/d/workspace_v2/projects/lab/xbrainlab/scripts/agent/evals/run_local_tool_call_eval.py`
- Phi-4-mini-instruct json: `artifacts/agent_evals/current_candidate_strict/local_microsoft_phi_4_mini_instruct.json`
- Phi-4-mini-instruct markdown: `artifacts/agent_evals/current_candidate_strict/local_microsoft_phi_4_mini_instruct.md`
- Phi-4-mini-instruct latest_json: `artifacts/agent_evals/current_candidate_strict/local_latest.json`
- Phi-4-mini-instruct latest_markdown: `artifacts/agent_evals/current_candidate_strict/local_latest.md`

## Thesis Claim Boundary

- Local model results do not cover the latest deterministic case suite; rerun primary and fallback local models before claiming thesis evidence for new cases.
- Deterministic-only new cases cannot be claimed as local LLM tool-call evidence.
