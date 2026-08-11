---
name: agent-toolcall-designer
description: "Use for XBrainLab Assistant snapshots, backend-owned tool exposure, command verification, and tool-call scoring. Do not use for general architecture or thesis evidence."
---

# Agent Tool-call Designer

Design the Assistant tool surface as a projection of product backend truth.

## Workflow

1. Identify the user intent, owning backend command, observable preconditions, and side effects.
2. Read only the relevant Assistant/backend architecture and command specification.
3. Define an immutable state snapshot containing facts the model may rely on.
4. Derive tool availability and blocked reasons from backend capability policy.
5. Keep schemas narrow; avoid competing tools that express the same action.
6. Route state-changing calls through the owning application command and structured result.
7. Verify postconditions from a fresh snapshot or explicit result evidence.
8. Add positive, blocked, confirmation, recovery, and ambiguity cases.

## Contract checks

- Never let prompt text, tool descriptions, or UI state become an alternate readiness engine.
- Separate tool admission, user confirmation, execution, and verification.
- Include stable identifiers and bounded evidence; do not expose live controller objects.
- Treat command text parsing as compatibility input, not authoritative state.
- Preserve exact model/revision and runner identity when producing evaluation evidence.

## Output

Report the intent-to-command mapping, snapshot fields, admission owner, schema delta, verification
rule, cases, and claims the evidence cannot support.
