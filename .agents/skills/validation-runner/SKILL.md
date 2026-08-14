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

1. Define changed areas, expected behavior, environment, and intended claim.
2. Select the smallest focused test that directly protects the change.
3. Add a source guard or adjacent regression only when it directly protects the declared contract.
4. Run UI artifacts, source-diverse data gates, exact-source dossiers, and full manifests only when
   the claim or handoff workflow requires them.
5. Distinguish scope-complete work from checkpoint and handoff-ready; do not escalate one into the
   next evidence tier automatically.

## Interpretation

- Dashboard PASS is engineering evidence, not product, thesis, scientific, or human acceptance.
- Mock-heavy unit tests are a regression floor, not a real workflow claim.
- Different formats from one dataset are not dataset diversity.
- Offscreen UI evidence does not replace native Windows acceptance.
- Evidence from a different SHA, dirty source, stale branch, or reduced denominator cannot certify
  the candidate.

Report the minimum relevant command/result, supported and unsupported claims, completion label, and
advisory follow-up. Persist a receipt only when the evidence contract requires one.
