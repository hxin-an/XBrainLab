---
name: validation-runner
description: "Use for selecting and interpreting XBrainLab tests, source guards, dashboards, MkDocs, real-data, UI, and handoff gates. Do not invent commands or overstate results."
---

# Validation Runner

Select evidence proportional to the declared scope and claim.

## Authority

Read the relevant section of `docs/validation/README.md`. Scope and claim selection come from the
descriptor and immutable plan in `scripts/dev/validation_control_plane.py`. Executable gate IDs,
order, argv, timeouts, cache injection, and attestation come only from
`scripts/dev/handoff_gate_spec.py`. Execute and verify the plan through
`scripts/dev/run_validation_control_plane.py`; do not copy or weaken commands in this skill.

## Workflow

1. Declare intent, affected layers, risk floor, intended claim, expected behavior, and same-class
   risk in a descriptor. Path inference may add scope but never remove declared scope.
2. Fetch or otherwise obtain the reviewed target identity from an authoritative remote/PR event,
   resolve it to an immutable SHA, then generate the source-bound plan against its merge base. A
   mutable or merely local ref name alone is not authorization. Unknown paths, unresolved rules,
   or a stale base are blockers; do not hand-select a smaller replacement list.
3. Execute the registered plan. Use focused gates first for iteration, but only the complete selected
   denominator can support the declared claim.
4. For visible UI, inspect screenshots/walkthroughs; for data workflow handoff, use the required
   source-diverse dataset gate.
5. Verify the receipt against the exact-source dossier; structural `report` output is never PASS.
6. Record plan/receipt/dossier identity, result, artifact review, and dirty-state boundary.
7. Distinguish complete bounded work from product handoff: a docs-only or narrow internal scope may
   be complete when all its declared gates pass; handoff-ready requires the full handoff workflow.

`scripts/dev/run_handoff_validation_manifest.py` is only a compatibility entrypoint for a full
handoff inventory. It delegates to the same plan/execute/verify control plane and is not a second
manifest or permission to select commands manually.

## Interpretation

- Dashboard PASS is engineering evidence, not product, thesis, scientific, or human acceptance.
- Mock-heavy unit tests are a regression floor, not a real workflow claim.
- Different formats from one dataset are not dataset diversity.
- Offscreen UI evidence does not replace native Windows acceptance.
- Evidence from a different SHA, dirty source, stale branch, or reduced denominator cannot certify
  the candidate.

Report command, result, supported claim, unsupported claim, completion label, and follow-up.
