# Backend Test Hygiene Goal

Goal: Complete the XBrainLab backend/test/validation/clean-code roadmap to a clean,
PR-ready state.

This is not an inventory-only task. This is not a "make it somewhat better" task.
Leave the touched backend/test/validation areas clean, protected, and reviewable.

Use:

- `.agents/skills/pr-branch-governance/SKILL.md`

You may spawn multiple subagents in parallel. The main agent owns final quality and
must reject incomplete or weak work.

## Hard Non-Negotiables

- Do not redesign Load Labels / Match Labels UX.
- Do not make large layout/copy/design changes to Data Import wizard.
- Do not overwrite dirty worktree changes.
- Do not use `git reset --hard` or `git checkout --`.
- Do not delete tests unless stronger replacement coverage already exists.
- Do not create a large planning document.
- Do not call the work complete with only an audit, TODO list, or passing smoke test.
- Do not use vague completion claims like "improved", "cleaner", or "better protected"
  unless backed by concrete code changes and validation.

## Roadmap 1: Backend Cleanup

Required outcome:

- Data Interpretation scan / preview / validate / apply / recipe responsibilities are
  clearly owned by backend services/modules.
- ApplicationService / Command API remains the shared entry point for UI, headless,
  agent, and MCP.
- Real product runtime must not silently fall back from failed command path to legacy
  controller mutation.
- selected scope, scan location, external label sources, metadata choices, label
  matching choices, confirmations, and structured action items are preserved through
  command/result/recipe paths.
- Any duplicated workflow truth found in touched paths must be removed or isolated
  behind one backend source of truth.
- Any backend behavior changed must have focused tests.

Completion is not allowed if:

- a touched path still has duplicate state truth without explanation,
- a real runtime fallback bypasses command validation,
- recipe/state/action-item behavior is untested,
- backend cleanup only consists of comments or docs.

## Roadmap 2: Test Quality

Required outcome:

- Produce a compact test inventory in a canonical place, not a large planning doc.
- Classify the relevant test suite into strong behavior tests, useful unit contract
  tests, mock-heavy but still useful tests, weak implementation-detail tests,
  obsolete tests, duplicated tests, and missing coverage.
- For every weak/obsolete test cluster identified as safe to fix in this scope, either
  replace it with stronger behavior/state/recipe/action-result coverage, or document
  the concrete blocker that prevents replacement.
- Delete obsolete tests only after stronger replacement coverage exists.
- Strengthen tests so failures would indicate real product/backend regressions, not
  only changed implementation details.

Completion is not allowed if:

- inventory exists but no weak tests were strengthened,
- tests only assert mocks were called,
- obsolete tests are deleted without replacement coverage,
- major missing coverage is discovered but left without either a fix or explicit blocker.

## Roadmap 3: Validation Coverage

Required outcome:

Add or strengthen tests for all applicable items:

- Data Import file vs folder vs BIDS scan behavior.
- selected scope vs scan location.
- external label sources outside the EEG folder.
- structured action items.
- recipe replay / reload boundaries.
- UI route uses Data Interpretation command path rather than legacy fallback.
- command/API parity across UI, headless, agent, and MCP where the repo exposes those
  surfaces.

Assertions must check real behavior:

- command result
- backend state
- recipe trace
- loaded files
- label sources
- action items
- UI-visible route/result where UI is touched

Completion is not allowed if:

- coverage is mostly MagicMock call assertions,
- Data Import selected-scope behavior remains fragile,
- recipe reload/apply behavior is not protected,
- structured action items are only documented but not tested.

## Roadmap 4: Clean Code / Refactor

Required outcome:

- Identify large methods/classes, duplicate logic, and fallback/legacy creep in touched
  areas.
- Complete at least one meaningful low-risk refactor that improves responsibility
  boundaries.
- Refactor must be behavior-preserving and test-backed.
- Do not make core files larger or more tangled.
- Do not hide complexity in vague helpers; extracted code must have clearer domain
  ownership.

Completion is not allowed if:

- no refactor lands,
- refactor has no focused validation,
- code movement only renames or shuffles complexity,
- touched core areas become harder to reason about.

## Required Subagents

Subagent 1: Backend Boundary

- Own backend Data Interpretation / command boundary cleanup.
- Implement concrete fixes, not just findings.
- Add tests for touched behavior.

Subagent 2: Test Inventory

- Produce classification.
- Identify weak/obsolete clusters.
- Replace or strengthen high-value weak tests.
- Do not mass-delete tests.

Subagent 3: Validation Coverage

- Add workflow protection tests.
- Prioritize Data Import and command/API behavior.
- Avoid mock-only assertions.

Subagent 4: Clean Code Refactor

- Find and implement low-risk refactor slices.
- Must include focused tests.
- Must not touch UX design decisions.

## Main Agent Duties

- Start with `git status --short` and current branch.
- Read `pr-branch-governance`.
- Assign disjoint ownership.
- Review every subagent diff yourself.
- Do not accept subagent completion without code review and validation.
- Continue into the next roadmap item if a subtask finishes early.
- Update docs/worklog only with factual implementation and validation results.
- If a required gate cannot be completed, mark the whole goal as incomplete and explain why.

## Final Completion Gates

The goal is complete only if all gates pass:

Gate 1: Backend Clean

- No known duplicated workflow truth remains in touched backend command paths.
- No new real-runtime legacy fallback bypass exists.
- Data Interpretation selected scope, label sources, recipe, and action items are tested.

Gate 2: Tests Clean

- Test inventory is present.
- Weak/obsolete clusters in scope are strengthened or blocked with evidence.
- Any removed tests have stronger replacement coverage.

Gate 3: Validation Clean

- Core Data Import workflows have behavior/state/recipe/action-item tests.
- UI route / command route tests exist where relevant.
- Tests can catch real regressions.

Gate 4: Code Clean

- At least one meaningful responsibility-boundary refactor is completed.
- Refactor is validated.
- No touched core area is made more tangled.

Gate 5: Cross-Surface Clean

- UI/headless/agent/MCP command parity is checked.
- Any mismatch is either fixed or documented as a remaining risk with file references.

Gate 6: Validation Run

Run and report:

- focused backend pytest
- focused UI pytest if UI route touched
- ruff on changed Python files
- basedpyright on changed Python files
- mkdocs build if docs changed
- broader smoke/integration tests where touched behavior justifies it

## Final Response Must Say

- Complete or incomplete
- Branch / worktree state
- Roadmap gates passed / failed
- Code changes made
- Tests added / changed / removed
- Validation commands and results
- Remaining risks with file references
- What was intentionally not touched
- Suggested PR scope

Do not say "done" unless every gate passes. If any gate fails, say "incomplete" and
give the exact blocker.
