# XBrainLab Roadmap

最後更新：`2026-05-09`

This roadmap is the product spine. It is not a worklog and it does not list every completed slice.

## North Star

XBrainLab should become a local-first EEG / BCI desktop analysis tool:

```text
choose source
-> interpret data / labels / events
-> confirm ambiguous semantics
-> preprocess / epoch / dataset / train
-> evaluate / visualize / inspect saliency
-> let UI, assistant, MCP, and scripts share the same workflow truth
```

Completion cannot be claimed from backend JSON, mock tests, deterministic eval, or written reports
alone. The product path needs visible UI evidence and eventually human desktop acceptance.

## Product Tracks

| Track | Goal | Current read | Done when |
| --- | --- | --- | --- |
| Documentation Truth | Readers can find current truth, plan, architecture, validation, and artifact boundaries quickly. | This redesign is the active reset. | `current.md`, roadmap, validation, and artifact governance are concise and build cleanly. |
| Backend Command Spine | UI, agent, headless scripts, and MCP all use `ApplicationService / Command API`. | Spine is the main route; focused services now own many workflows. | Product runtime does not silently mutate through controller fallbacks; command results drive major refresh scopes. |
| Data Interpretation | Data Interpretation is the primary new data-entry language. | Scan / preview / validate / confirm/apply / recipe baseline exists. | Common label/event review can be completed without returning to legacy import-label mental models. |
| UI Product Experience | The desktop feels like an EEG workflow tool, not a debug panel. | Automated walkthrough and screenshots exist after multiple polish rounds. | Import through analysis can be operated by a person, with human Windows launcher / DPI / local-model evidence. |
| Agent Runtime | Assistant acts as workflow operator using state snapshot, policy, and typed command results. | Formal local tool-call benchmark slice exists; source suite has since changed. | Tool-call reports separate metrics, failure taxonomy, model comparison, and claim boundary. |
| Automation / MCP | External agents can operate the same command surface. | stdio, Inspector, and HTTP train-job baselines exist. | Job semantics, authorization, persistence/recovery, and client certification boundaries are explicit. |
| Packaging / Release | A Windows user can launch and complete a representative workflow. | Automated launcher/startup baseline exists. | Human click-through release acceptance passes with logs and recovery guidance. |

## Current Priority Order

1. Documentation reset.
2. Architecture health: command spine, refresh coordinator, controller fallback audit.
3. Data Interpretation mature wizard.
4. UI / assistant product walkthrough toward human acceptance.
5. Release / thesis gates after product path stabilization.

## Future Work

These are product directions, not current blockers.

| Direction | Purpose | Boundary |
| --- | --- | --- |
| Expert Workflow Mode | Let experienced EEG users jump, rerun, and compare workflow segments. | Still must use Command API and capability policy; no arbitrary Python execution in v1. |
| Workflow Recipe DSL | Replace fragile long tool-call chains with a restricted declarative workflow recipe. | Every step still needs verification and confirmation where appropriate. |
| EEG Training Model Registry | Track task fit, input requirements, resource profile, and explainability support for EEG models. | This is about EEG models, not LLM selection. |
| Training Model Node Visualization | Show model layers, tensor shapes, parameter count, and activation memory estimate. | Avoid heavy live activation animation until the product path is stable. |
| Training Compatibility Check | Warn before model selection when dataset shape or resource fit is poor. | First version should be a low-risk preflight, not a full AutoML system. |

## Non-Goals

- Do not treat future work as the current checklist.
- Do not let API / Gemini / remote LLM return to product execution.
- Do not let MCP, UI, or agent bypass `ApplicationService`.
- Do not use Chinese-company or China-source LLM models.
- Do not interpret tool-call eval as product completion.
