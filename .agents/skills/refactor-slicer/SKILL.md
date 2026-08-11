---
name: refactor-slicer
description: "Use for bounded XBrainLab backend, UI, or Assistant refactor slices with call sites, baselines, tests, rollback, and ownership. Do not use for broad redesign."
---

# Refactor Slicer

Turn an architectural concern into independently reviewable behavior-preserving slices.

## Workflow

1. Name one workflow, current pain, and observable behavior that must remain.
2. Enumerate entry points, owners, consumers, tests, and same-class call sites.
3. Establish a passing characterization baseline before structural changes.
4. Define the target ownership boundary and the smallest slice that moves toward it.
5. List affected files, non-goals, rollback point, and evidence.
6. Implement one slice; run focused and adjacent regression before starting the next.
7. Remove compatibility code only after all callers and stronger tests have migrated.

For state-changing backend/Assistant work, specify command/service shape and publication contract.
For presentation-only UI refactors, specify widget/layout ownership and visual invariants instead;
do not force a command template where no command exists.

## Slice output

Include scope, current call sites, target boundary, first patch, behavior baseline, tests, source
guard, rollback, and stopping condition. Split UI redesign from backend/test cleanup unless one
shared behavior and validation genuinely require both.
