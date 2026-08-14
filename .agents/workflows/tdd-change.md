# Workflow: TDD Change

Use `tdd-guard` as primary, with `test-quality-reviewer` and `validation-runner` for evidence.

## Bug or new behavior

1. Confirm the problem, evidence, bounded repair steps, and validation are current in the single
   active plan in `docs/planning/now.md`.
2. State observable expected behavior.
3. Add a test that fails for the target reason.
4. Implement the smallest coherent fix.
5. Make it pass, then run only directly relevant adjacent evidence.

## Behavior-preserving refactor

1. Confirm the bounded slice is current in the single active plan.
2. Select or add characterization tests.
3. Confirm they pass before structural edits.
4. Refactor one bounded slice.
5. Re-run the identical baseline; add a source guard only for a stable repeated rule.

In both routes, avoid mock choreography, never weaken assertions, and record what the evidence does
and does not support. A refactor does not need an artificial red test.
