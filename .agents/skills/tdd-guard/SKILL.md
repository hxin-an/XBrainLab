---
name: tdd-guard
description: "Use for XBrainLab bug/core behavior test-first loops and passing characterization baselines for refactors. Do not require artificial red tests for pure refactors."
---

# TDD Guard

Choose the baseline that matches the change.

Use `../../workflows/tdd-change.md` for the procedure. A bug needs the smallest red reproduction for the
observable defect; a behavior-preserving refactor needs a passing characterization baseline, not an
artificial red test. After the change, run the same protection and only directly relevant adjacent
evidence.

Prefer public results, state transitions, recipe traces, UI-observable states, and real side effects.
Use mocks only to isolate expensive/external dependencies. If a test cannot observe the requirement or
fails for an unrelated reason, repair the safe fixture/environment or select another relevant observable
check; do not treat it as red/green evidence or end the authorized task. Never weaken assertions or expand
production scope to manufacture green.
