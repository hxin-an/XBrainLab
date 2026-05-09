# XBrainLab Architecture

最後更新：`2026-05-09`

This is the current implementation overview. Validation boundaries live in
`docs/validation/README.md`.

## Architecture Read

XBrainLab combines:

- PyQt desktop UI.
- EEG import, preprocessing, epoching, dataset, training, evaluation, and visualization workflows.
- Backend managers and a shared application command surface.
- In-app local-only assistant runtime.
- MCP / headless automation adapters.
- Validation and thesis evidence tooling.

The architecture goal is one workflow truth: human UI, assistant tools, scripts, and MCP adapters
should observe the same readiness, policy, command result, and state snapshot.

## Control Surface

```text
Human user
  -> PyQt UI panels / dialogs
  -> ApplicationService.execute(Command)
  -> focused command services
  -> Study / DataManager / TrainingManager / pipeline objects

Assistant / MCP / headless scripts
  -> tool or JSON payload
  -> same ApplicationService command surface
  -> same policy, state snapshot, and structured result envelope
```

## Current Layer Map

| Layer | Responsibility | Current risk |
| --- | --- | --- |
| UI | User workflow, visible state, dialogs, refresh after command results. | Some refresh and fallback paths still mix observer/manual/controller reads. |
| ApplicationService | Dispatch, capability/confirmation policy, state/result envelope. | Must stay a spine, not absorb every workflow implementation again. |
| Focused services | Data Interpretation, dataset generation, training, analysis, lifecycle commands. | Boundaries need continued tests as workflows mature. |
| Backend domain | Study, data managers, training managers, IO/pipeline/model code. | Legacy compatibility paths must not become product defaults. |
| Assistant runtime | Local-only LLM and workflow tool surface. | Long desktop local-model sessions still need acceptance evidence. |
| MCP / automation | Headless access to the same command surface. | HTTP jobs, auth, persistence, and client certification remain bounded baselines. |
| Validation | Evidence generation and claim discipline. | Artifacts must not be read as broader claims than they support. |

## Architecture Documents

| File | Use |
| --- | --- |
| [ui.md](ui.md) | PyQt panels, dialogs, event/refresh boundaries. |
| [backend.md](backend.md) | Backend facade, Study, managers, controllers, command spine. |
| [agent.md](agent.md) | In-app assistant, local-only runtime, tool calls. |
| [../validation/README.md](../validation/README.md) | Evidence tiers, dashboard interpretation, and claim boundaries. |

## Current Architecture Principles

- Stabilize the existing PyQt app before expanding agent autonomy.
- Treat human user and assistant as two control modes over the same backend capability surface.
- Keep product runtime local-only; API / Gemini dependencies remain outside default execution.
- Do not let MCP, scripts, UI, or agent tools bypass `ApplicationService`.
- Make every major claim traceable to source, test, artifact, or runtime evidence.
- Keep records/worklog as history, not active architecture truth.

## Active Architecture Risks

| Risk | Why it matters | Current direction |
| --- | --- | --- |
| UI refresh split truth | Users may see stale state even when command result is correct. | Continue command-result refresh coordinator and changed-state tests. |
| Controller fallback creep | Product runtime can silently diverge from the command spine. | Audit real `Study` paths and keep fallbacks limited to explicit mock/legacy contexts. |
| Data Interpretation maturity | Baseline exists, but common real-world label/event ambiguity remains hard. | Mature wizard review surfaces and recipe reload/diff behavior. |
| MCP job semantics | Headless long-running commands need clear lifecycle and recovery boundaries. | Keep HTTP job support explicit and avoid overclaiming certification. |
