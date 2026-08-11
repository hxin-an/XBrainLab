# Workflow: Refactor Slice

Use `refactor-slicer` as primary. Add `tdd-guard`, `test-quality-reviewer`, and
`validation-runner` only when their step begins.

1. Define one workflow, current pain, observable behavior, scope, and non-goals.
2. List entry points, call sites, owners, consumers, and same-class locations.
3. Establish a passing characterization baseline.
4. Define target ownership, affected files, rollback, and the smallest coherent slice.
5. Implement the slice without mixing unrelated UI redesign, backend cleanup, and Assistant work.
6. Re-run the identical baseline, source guard, and adjacent regression.
7. Remove compatibility code only after callers and stronger tests migrate.
8. Update architecture/current docs only when their truth changed.

For presentation-only UI work record layout/visual invariants; require command shape only for
state-changing workflows. Stop at checkpoint if same-class sweep or regression remains open.
