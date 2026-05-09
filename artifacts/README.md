# XBrainLab Artifacts

最後更新：`2026-05-09`

`artifacts/` contains generated evidence, screenshots, dashboards, and walkthrough outputs. It is
not the source of current truth. Current truth lives in `docs/current.md`; validation interpretation
lives in `docs/validation/README.md`.

## Governance Rules

- Treat artifacts as evidence with a generator, date, environment, and claim boundary.
- Do not edit generated artifacts by hand to make a claim look better.
- Do not read a PASS result as broader than the artifact's documented scope.
- Prefer linking from docs to a small set of high-value artifact families instead of surfacing every
  raw output.
- If an artifact contradicts current docs, verify runtime/source first, then update the canonical
  doc or regenerate the artifact.

## Artifact Families

| Family | Produced by | Supports | Does not support |
| --- | --- | --- | --- |
| `quality/` | `scripts/dev/update_quality_dashboard.py` and related test commands. | Fast engineering health for lint, type, architecture, startup, UI baseline, IO. | Product completion, thesis evidence, human acceptance. |
| `ui/human-like-walkthrough/` | `scripts/dev/capture_human_like_product_walkthrough.py`. | Automated PyQt workflow replay, screenshots, visible text, button states, geometry checks. | Human Windows desktop acceptance, long local-model soak, release approval. |
| `ui/data-interpretation-*` | Data Interpretation replay scripts. | UI-observable import wizard and dataset table evidence for representative fixtures. | Full real-data manual certification or final import-system completeness. |
| `agent_evals/` | `scripts/agent/evals/run_tool_call_eval.py`, `run_local_tool_call_eval.py`, dashboard builder. | Tool-call behavior for named cases, models, repeats, and scorer version. | UI usability, EEG training accuracy, product completion. |
| `mcp/` | MCP stdio / HTTP walkthrough and config capture scripts. | Headless adapter baseline and command-surface exposure. | Full client certification, desktop UI refresh, persistence/recovery guarantees. |
| `data_interpretation/` | Format capability reporting scripts. | Representative format boundary matrix from live command path. | XDF / LSL parser support or every-format real-dataset certification. |
| `launcher/` | Windows launcher walkthrough scripts. | Automated desktop command/startup smoke for the active repo. | Human click-through release approval. |
| `goal/` | Long-running goal/handoff records. | Operational continuity for agents. | Current truth or validation proof by itself. |

## High-Value Entrypoints

| Artifact | Read first when |
| --- | --- |
| `quality/latest.md` | You need the latest fast engineering dashboard summary. |
| `ui/human-like-walkthrough/human-like-walkthrough.md` | You need UI-observable product workflow evidence and screenshot list. |
| `agent_evals/dashboard.md` | You need tool-call benchmark comparison and claim boundary. |
| `mcp/http-walkthrough.md` | You need MCP HTTP transport and train-job baseline evidence. |
| `mcp/stdio-walkthrough.md` | You need MCP stdio tool-call baseline evidence. |
| `data_interpretation/format-capability-matrix.md` | You need Data Interpretation format capability boundaries. |
| `launcher/windows-launcher-walkthrough.md` | You need automated Windows launcher/startup smoke evidence. |

## Claim Boundary Template

When adding a new artifact, include:

```text
status:
generator:
environment:
supports:
does_not_support:
next_human_or_runtime_gate:
```
