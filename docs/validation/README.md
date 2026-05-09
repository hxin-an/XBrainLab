# XBrainLab Validation

最後更新：`2026-05-09`

Validation in XBrainLab is about claim control. A passing artifact is useful only after we state
what it can and cannot prove.

## Evidence Levels

| Level | What it can support | What it cannot support |
| --- | --- | --- |
| Static / unit / architecture gates | Code health, type/lint cleanliness, architecture guardrails, focused regression checks. | Real user workflow quality or visual product acceptance. |
| Backend replay | `ApplicationService / Command API` contracts, state transitions, structured results, policy boundaries. | Whether the UI is understandable, clickable, or visually polished. |
| UI-observable automated walkthrough | PyQt workflow replay with screenshots, visible text, button state, geometry, and backend snapshots. | Human Windows desktop acceptance, dual-monitor/DPI coverage, long local-model sessions. |
| Local model eval | Tool-call behavior for a specified model, case suite, repeat count, and scorer. | EEG training accuracy, UI usability, release completion. |
| Human desktop acceptance | A person operates the Windows desktop path under real display/GPU/local-model conditions. | This is not yet complete for the current product. |

## Current High-Value Artifacts

| Artifact | Evidence type | Current claim boundary |
| --- | --- | --- |
| `artifacts/quality/latest.md` | Fast engineering dashboard. | PASS means engineering health for the configured fast profile, not product completion. |
| `artifacts/ui/human-like-walkthrough/human-like-walkthrough.md` | Automated UI-observable PyQt walkthrough. | Covers replay conditions only; not human Windows acceptance. |
| `artifacts/agent_evals/dashboard.md` | Tool-call eval dashboard. | Supports the benchmark slice shown there; does not update claims for source-suite changes unless rerun. |
| `artifacts/mcp/stdio-walkthrough.md` | MCP stdio command path. | Headless adapter baseline; no desktop UI refresh. |
| `artifacts/mcp/http-walkthrough.md` | MCP HTTP command path and train job baseline. | No persistence/recovery-grade certification or full client matrix. |
| `artifacts/data_interpretation/format-capability-matrix.md` | Data Interpretation format boundary matrix. | Representative capability evidence, not full real-data manual certification. |
| `artifacts/launcher/windows-launcher-walkthrough.md` | Automated Windows launcher/startup command smoke. | Not human click-through release approval. |

## Standard Gates

Run from repo root.

```bash
poetry run mkdocs build --strict
```

```bash
poetry run python scripts/dev/update_quality_dashboard.py
```

```bash
poetry run pytest --capture=sys tests/integration/io/test_io_integration.py -q
```

```bash
poetry run pytest --capture=sys \
  tests/integration/pipeline/test_full_pipeline.py::TestFullPipeline::test_train_and_evaluate_metrics \
  tests/integration/pipeline/test_study_training_e2e.py::TestStudyTrainCycle::test_full_cycle_eegnet \
  -q
```

## Tool-Call Eval Gates

| Gate | Use when | Model / repeat policy |
| --- | --- | --- |
| Fast dev | Daily prompt, scorer, normalizer, and case wording changes. | Deterministic changed / failed cases; repeat `1`; no fallback model. |
| Candidate | Affected family needs real local model signal. | Primary model subset; repeat `1` or `2`. |
| Release / thesis | Updating formal benchmark or thesis evidence. | Deterministic full suite, primary x3, fallback x3, dashboard refresh, resource notes. |

Full local release/thesis runs must check disk, cache, and VRAM pressure before loading a model.

## Interpretation Rules

- Dashboard PASS is engineering health, not release completion.
- Mock-heavy tests are regression floor, not workflow evidence.
- Automated walkthrough screenshots are UI-observable evidence, not human acceptance.
- Tool-call eval is an agent-behavior claim, not a UI/product claim.
- Public local-only fixture evidence does not guarantee clean-clone always-on CI.
- Optional `llm` group evidence must be explicit before claiming local LLM readiness.

## Reporting Format

When adding or citing validation evidence, record:

| Field | Meaning |
| --- | --- |
| Command | Exact command or artifact generator. |
| Result | Pass/fail and important summary lines. |
| Supports | The claim this evidence can reasonably support. |
| Does not support | The nearest tempting overclaim. |
| Follow-up | The next gate needed for stronger confidence. |
