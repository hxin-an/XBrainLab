---
name: agent-toolcall-designer
description: "Use for XBrainLab Assistant snapshots, backend-owned tool exposure, command verification, and tool-call scoring. Do not use for general architecture or thesis evidence."
---

# Agent Tool-call Designer

Design the Assistant tool surface as a projection of product backend truth.

## Workflow

1. Identify the intent, existing owning command, preconditions, side effects, and current snapshot.
2. Reuse the owning command, capability policy, structured result, and verification path when they
   already express the requirement.
3. Add or change snapshot/schema fields only for an observable contract gap; never create a second
   readiness owner.
4. Verify the smallest risk-relevant set of positive, blocked, confirmation, recovery, or ambiguity
   cases. Do not add every category by default.

## Contract checks

- Never let prompt text, tool descriptions, or UI state become an alternate readiness engine.
- Separate tool admission, user confirmation, execution, and verification.
- Include stable identifiers and bounded evidence; do not expose live controller objects.
- Treat command text parsing as compatibility input, not authoritative state.
- Preserve exact model/revision and runner identity when producing evaluation evidence.

## Output

Report the existing contract, necessary delta, admission owner, verification rule, selected cases,
and unsupported claims.
