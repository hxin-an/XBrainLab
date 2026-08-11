---
name: tdd-guard
description: "Use for XBrainLab bug/core behavior test-first loops and passing characterization baselines for refactors. Do not require artificial red tests for pure refactors."
---

# TDD Guard

Choose the baseline that matches the change.

## Bug or behavior change

1. State the observable expected behavior.
2. Add the smallest test that fails for the intended reason before implementation.
3. Confirm the failure is caused by the target defect, not fixture/environment noise.
4. Implement the minimum coherent change.
5. Make the test pass, then run same-class and adjacent regression.

## Behavior-preserving refactor

1. Identify public behavior and risky side effects.
2. Add or select characterization tests and confirm they pass before refactoring.
3. Change one bounded slice.
4. Re-run the identical baseline and relevant source guard.
5. Add a failing test only if the refactor uncovers an actual missing behavior contract.

Prefer public results, state transitions, recipe traces, UI-observable states, and real side effects.
Use mocks only to isolate expensive/external dependencies. Stop and reassess when a test cannot
observe the requirement or fails for an unrelated reason; never weaken assertions to manufacture
green.
