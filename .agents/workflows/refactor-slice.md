# Workflow: Refactor Slice

Use `refactor-slicer` as primary. Add `tdd-guard`, `test-quality-reviewer`, and
`validation-runner` only when their step begins.

1. Persist the problem, evidence, scope, non-goals, repair steps, validation, and stop condition in
   the single active plan in `docs/planning/now.md`.
2. List entry points, directly coupled call sites, owners, consumers, and deletion candidates.
3. Establish a passing characterization baseline.
4. Define target ownership, affected files, rollback, and the smallest coherent slice.
5. Implement the slice without mixing unrelated UI redesign, backend cleanup, and Assistant work.
6. Re-run the identical baseline and directly relevant regression or stable source guard.
7. Record owners before/after and production LOC delta when a root complexity trigger applies.
8. Stop after this slice. A next slice needs a new scope record or user request.

For presentation-only UI work record layout/visual invariants; require command shape only for
state-changing workflows. Independent findings do not expand this slice.
