# Tool-Call Agent Best Practices To XBrainLab Design

最後更新：`2026-05-04`

## Scope

This note records the product design decisions adopted for XBrainLab's local
tool-call agent. It is not a plan for adding a new agent framework. The changes
must remain inside the existing `ContextAssembler -> CommandParser ->
VerificationLayer -> ApplicationService` path.

## Research Inputs

- OpenAI Structured Outputs / function calling: use function calling when a
  model bridges to application tools, prefer schema-constrained arguments over
  free JSON, and validate schemas before execution. OpenAI distinguishes valid
  JSON from schema adherence; `strict` structured outputs are the stricter
  target for argument contracts.
- Berkeley Function Calling Leaderboard: BFCL evaluates function calling across
  simple, multiple, parallel, parallel-multiple, executable, AST, and relevance /
  no-function scenarios. The XBrainLab eval should therefore include no-call,
  wrong-tool temptation, multiple candidate tools, blocked commands, and
  multi-turn recovery instead of only clean single-step prompts.
- LangSmith trajectory evaluation: agent quality cannot be judged only by the
  final response. The expected tool path, tool arguments, intermediate state,
  and visible user response need to be scored as a trajectory.

Sources:

- OpenAI Structured Outputs guide:
  <https://platform.openai.com/docs/guides/structured-outputs>
- Berkeley Function Calling Leaderboard:
  <https://gorilla.cs.berkeley.edu/blogs/8_berkeley_function_calling_leaderboard.html>
- LangSmith evaluation approaches:
  <https://docs.langchain.com/langsmith/evaluation-approaches>
- LangSmith complex agent trajectory eval:
  <https://docs.langchain.com/langsmith/evaluate-complex-agent>

## Adopted XBrainLab Design

### Tool Schema

- `XBrainLab/llm/tools/schema_contract.py` now renders prompt-facing tool
  contracts with taxonomy labels and stricter object boundaries.
- Data Interpretation tools are tagged as the primary data-entry path.
- `load_data` and `attach_labels` are explicitly marked legacy compatibility,
  not the preferred new import mental model.
- Preview choices now expose structured label/event/metadata fields instead of
  a shapeless object: label carrier, event role, class map, anchor, subject,
  session, task, run, and selected EEG files.

### Routing And No-Call Policy

- `infer_user_intent()` now recognizes no-tool concept questions,
  clarification-only requests, Chinese EEG/BCI phrasing, mixed Chinese/English
  requests, reset boundaries, saliency phrasing, and epoch phrasing.
- `LLMController` short-circuits no-tool and ask-clarification turns before
  local model tool execution when the user is asking for an explanation rather
  than an operation.
- The local eval prompt hides tool schemas for no-call turns and asks for a
  user-facing answer without internal tool names, schema, or JSON syntax.

### Parser And Normalizer

- `CommandParser` accepts common function-call variants used by local models:
  `tool_name`, `command`, `name`, `tool`, OpenAI-style function payloads, and
  top-level tool call lists.
- `tool_name: none` / `no_tool` / `ask_clarification` are treated as no-call
  outputs, not invalid hidden tool calls.
- `tool_call_normalizer` repairs local-model structured-output variants without
  bypassing backend policy:
  optional `null` values are dropped, preview label fields are moved into
  `choices`, task/event-role confusions are repaired, explicit load requests
  stay on the legacy load compatibility path, and relative recipe paths are
  replaced by the absolute path from the latest user turn when available.

### Verification And Repair

- `ToolSchemaValidator` now rejects unknown root parameters, validates nested
  object fields, checks nested enums/types, and still keeps the placeholder path
  validator for invented paths.
- Verification failures are converted into user-facing missing-input or blocked
  messages; raw schema errors are not meant to be shown in the visible chat
  transcript.
- The controller still executes at most one verified command per assistant turn
  and reads command availability from `ApplicationService` capability policy.

### Evaluation

- The deterministic and local eval suite now contains `117` cases.
- Added families include Chinese, mixed Chinese/English, ambiguous request,
  missing input, no-call explanatory questions, should-not-call, wrong-tool
  temptation, blocked command, multi-intent, multi-turn recovery, Data
  Interpretation confirmation boundary, BIDS, label ambiguity, subject
  metadata, destructive / long-running confirmation, and EEG/BCI domain
  phrasing.
- Scoring now includes intent, tool/no-tool decision, tool selection,
  arguments, state awareness, clarification behavior, blocked handling,
  confirmation boundary, trajectory, visible response quality, runtime safety,
  and repeated local-model stability.
- `artifacts/agent_evals/dashboard.md` compares deterministic, primary local,
  and fallback local runs, and shows case-family pass rates, metric pass rates,
  failure taxonomy, worst cases, artifact paths, and thesis claim boundaries.

## Latest Evidence Boundary

`2026-05-04` local eval runs:

- primary `microsoft/Phi-4-mini-instruct`: `117 / 117`, repeat count `3`
- fallback `microsoft/Phi-3.5-mini-instruct`: `117 / 117`, repeat count `3`
- runtime: local-only, GPU-ready, existing cache `15.34 GB`, no new download

This supports a thesis-candidate tool-call benchmark claim for this benchmark
slice only. It does not prove UI usability, Windows launcher behavior,
dual-monitor/DPI behavior, long desktop sessions, EEG model training quality,
or product completion.
