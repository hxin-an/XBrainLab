# Workflow: TDD Change

Use `tdd-guard` as primary, with `test-quality-reviewer` and `validation-runner` for evidence.

## Bug or new behavior

1. State observable expected behavior.
2. Add a test that fails for the target reason.
3. Implement the smallest coherent fix.
4. Make it pass, then run same-class and adjacent regression.

## Behavior-preserving refactor

1. Select or add characterization tests.
2. Confirm they pass before structural edits.
3. Refactor one bounded slice.
4. Re-run the identical baseline and source guard.

In both routes, avoid mock choreography, never weaken assertions, and record what the evidence does
and does not support. A refactor does not need an artificial red test.
