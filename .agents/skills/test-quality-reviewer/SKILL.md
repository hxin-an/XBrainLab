---
name: test-quality-reviewer
description: "Use for judging whether XBrainLab tests detect real failures, including mock-heavy tests, detail assertions, weak fixtures, and overstated evidence. Do not use merely to run tests."
---

# Test Quality Reviewer

Judge tests by the defects and claims they can actually protect.

## Review

1. Map each test to a user/backend behavior, state transition, side effect, or claim.
2. Inspect fixtures, mocks, monkeypatches, assertions, and failure messages.
3. Mutate or reason about the protected behavior: would a realistic defect make the test fail?
4. Check that test setup does not bypass the production entry point or precondition owner.
5. Require at least one lower-mock workflow path for important side effects.
6. Separate unit contract, integration smoke, UI baseline, real-data evidence, and scientific/eval
   evidence.
7. Recommend the smallest stronger replacement before deleting weak tests.

## Output

Classify strong tests, weak/mock-heavy tests, duplicated/obsolete tests, missing non-mocked evidence,
and the next highest-value test. State what the suite supports and cannot support. Passing counts,
dashboard status, or a mocked happy path never establish product completion by themselves.
