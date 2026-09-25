# Workflow: Refactor Slice

Use `refactor-slicer` as primary; add `tdd-guard`, `test-quality-reviewer`, and `validation-runner` only when their step begins.

1. Persist problem, evidence, scope, non-goals, steps, validation and stop condition in `docs/planning/now.md`.
2. List entry points, coupled callers/consumers and deletion candidates; define owners, affected files, rollback and the smallest coherent slice.
3. Establish a passing characterization baseline, then implement without mixing unrelated UI redesign, backend cleanup and Assistant work.
4. Re-run the same baseline and directly relevant regression or stable source guard.
5. Record owners before/after and production LOC delta when a root complexity trigger applies.
6. Continue declared work in the authorized outcome after each slice; an independent finding or material expansion needs a new scope record or user request.

Track the original production/tests/scripts/config/docs scope with entries, owners, deletion/retention decisions and evidence; disclose unread or unverified areas. Slice approval is not module closure. Independent final review covers the integrated candidate, unchanged responsibilities and behavioral test quality—not just completed diffs.
For deep cleanup, assess substantial responsibility groups through real entries, state readers/writers, callbacks and side effects. Compare deletion, local consolidation, existing-owner reuse, extraction and retention. Necessary behavior does not justify its present organization: retention needs concrete coupling/reliability tradeoffs, not passing tests, reviewer approval or rejection of line-count-only splits.
The primary agent verifies regression safety and remaining structure against the original outcome. Unresolved analysis means incomplete, not an architecture pass or functional bug. Resolve in-scope blockers and re-review affected boundaries; separate handoff gates still apply. Do not build generic manifests or per-helper paperwork.
For presentation-only work record layout/visual invariants; require command shape only for state-changing workflows. Independent findings do not expand scope.
