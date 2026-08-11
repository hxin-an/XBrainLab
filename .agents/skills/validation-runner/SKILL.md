---
name: validation-runner
description: "Use for selecting and interpreting XBrainLab tests, source guards, dashboards, MkDocs, real-data, UI, and handoff gates. Do not invent commands or overstate results."
---

# Validation Runner

Select evidence proportional to the declared scope and claim.

## Authority

Read the relevant section of `docs/validation/README.md`. Executable handoff gate IDs, order, argv,
timeouts, cache injection, and attestation come only from `scripts/dev/handoff_gate_spec.py`; run
them through the canonical manifest runner. Do not copy or weaken commands in this skill.

## Workflow

1. Define changed areas, expected behavior, same-class risk, environment, and intended claim.
2. Select the smallest focused test that directly protects the change.
3. Add the applicable source guard and adjacent workflow regression.
4. For visible UI, inspect screenshots/walkthroughs; for data workflow handoff, use the required
   source-diverse dataset gate.
5. Record command, exact source identity, result, artifact, and dirty-state boundary.
6. Distinguish complete bounded work from product handoff: a docs-only or narrow internal scope may
   be complete when all its declared gates pass; handoff-ready requires the full handoff workflow.

## Interpretation

- Dashboard PASS is engineering evidence, not product, thesis, scientific, or human acceptance.
- Mock-heavy unit tests are a regression floor, not a real workflow claim.
- Different formats from one dataset are not dataset diversity.
- Offscreen UI evidence does not replace native Windows acceptance.
- Evidence from a different SHA, dirty source, stale branch, or reduced denominator cannot certify
  the candidate.

Report command, result, supported claim, unsupported claim, completion label, and follow-up.
