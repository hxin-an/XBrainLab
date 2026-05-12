# Backend Product Runtime Zero-Legacy And Test Hygiene Goal

Goal: Bring XBrainLab backend product runtime to a zero-legacy-fallback
engineering standard, with backend command truth, UI refresh truth, controller
compatibility boundaries, dataset generation, and test hygiene all brought to a
reviewable MVP-stabilization baseline.

This is not an audit-only goal. Do not stop after inventory. Do not scope
completion to files you happened to touch. Work from the final product backend
target state backward.

This goal is strict by design. If any hard completion blocker remains, final
status is `incomplete`.

## Required Skills / Docs

Read and follow:

- `.agents/skills/pr-branch-governance/SKILL.md`
- `.agents/skills/tdd-guard/SKILL.md`
- `.agents/skills/refactor-slicer/SKILL.md`
- `.agents/skills/clean-code-reviewer/SKILL.md`
- `.agents/skills/test-quality-reviewer/SKILL.md`
- `AGENTS.md`
- `docs/current.md`
- `docs/target/README.md`
- `docs/target/architecture.md`
- `docs/architecture/README.md`
- `docs/architecture/backend.md`
- `docs/architecture/ui.md`
- `docs/architecture/agent.md`
- `docs/planning/now.md`
- `docs/validation/README.md`
- `.agents/README.md`
- `.agents/stack.md`

## Hard Rules

- Do not merge or target `main` while product runtime is unstable.
- Do not redesign Data Import UX.
- Do not change Load Labels / Match Labels layout, visual design, or product
  copy unless the user explicitly changes scope.
- Do not use `git reset --hard`, destructive checkout, or overwrite unrelated
  user work.
- Do not create a new roadmap/planning document.
- Do not call the goal complete with inventory, dashboard PASS, smoke PASS, or
  docs only.
- Do not scope completion to touched files.
- Do not leave a real `Study` product mutating path able to bypass
  `ApplicationService / Command API` and still appear successful.
- Do not leave product readiness / blocked-reason truth duplicated in UI,
  agent, MCP, headless, facade, or controller paths when backend capability
  exists.
- Do not leave `BackendFacade` in product runtime paths.
- Do not let tests bless `BackendFacade` or controller fallback as product
  success.
- Do not delete tests unless stronger replacement coverage is already committed.

## Branch / Worktree Gate

1. Run `git status --short` and `git branch --show-current`.
2. State current branch, intended branch / PR scope, and files intentionally not
   touched.
3. Work from the current stabilization line or a small branch off it. Do not work
   directly on `main`.
4. Keep commits reviewable by slice.
5. End with `git status --short` clean.

## Product Runtime Definition

Product runtime means real user or product-facing execution through:

- PyQt UI actions and refresh / readiness paths.
- in-app assistant / LLM controller / real tools.
- MCP stdio / HTTP adapters.
- current headless scripts and dev walkthrough scripts used as product evidence.
- backend command API used by the above surfaces.

Compatibility code may remain only if it is unreachable from product runtime,
explicitly named as legacy / compatibility / mock-only, guarded against real
`Study` product mutation, documented with file references, and not used as
completion evidence.

## Required Phases

### 1. Full Inventory Before Edits

Before changing production code, inventory all product runtime paths for:

- load / import data
- Data Interpretation scan / preview / validate / apply / save recipe / reload
  recipe
- metadata update / smart parse / remove files
- label import / label attachment
- preprocess
- epoch
- dataset split / generate / reset
- training configure / start / stop / clear history
- evaluation / visualization / saliency
- reset / new session
- UI refresh / readiness / blocked reasons
- assistant tools / LLM controller
- MCP tools
- current headless and dev walkthrough scripts
- tests that assert product workflow success

Classify each path as exactly one of:

- command-backed product path
- backend-owned read-only query / state path
- UI read-only rendering / population
- mock-only compatibility path
- legacy compatibility path, unreachable from product runtime
- legacy mutation fallback
- obsolete / dead path

Record a compact inventory in an existing canonical document or worklog section.
Completion is forbidden if the inventory is only in chat.

### 2. Machine-Enforced Architecture Guards

Add or strengthen architecture tests so product runtime cannot:

- import or instantiate `BackendFacade`;
- call `Study.get_controller(...)` for real product mutation fallback;
- call controller mutation methods after command failure or missing command
  result;
- read mutable `Study`, `DataManager`, or `TrainingManager` state for readiness
  when backend command state / capability exists;
- convert a command-backed failure into legacy success;
- keep tests that assert legacy fallback as product success.

Guards must use AST or semantic checks where practical, not fragile text grep
only. Guard tests must include realistic forbidden examples and allowed
compatibility examples.

### 3. Remove Product Legacy Fallback

Remove, replace, or fail-close every real `Study` product mutation fallback
outside `ApplicationService / Command API`.

For each product workflow:

- UI actions call command-backed services.
- Agent tools and MCP adapters call command-backed services.
- Headless product scripts call command-backed services.
- Invalid actions return structured command failure / blocked result.
- Command failure is never converted into controller / facade success.
- Any remaining compatibility helper is named as legacy / mock-only and rejects
  real `Study` product runtime.

`BackendFacade` may be quarantined or retired, but it cannot be a product runtime
layer. Facade tests may remain only as compatibility tests and may not satisfy
product completion gates.

### 4. UI Refresh / Controller Boundary Cleanup

UI readiness and refresh for product workflows must use backend state,
capability, command result, or `changed_state` where available.

Panels may keep read-only rendering helpers and observer bridges, but they must
not own workflow policy or readiness truth already owned by backend capability.

For remaining controller access:

- classify it as read-only rendering, observer wiring, mock-only compatibility,
  or legacy compatibility;
- guard real `Study` product mutation fallback;
- document remaining compatibility with file references and removal criteria.

Completion is forbidden if real user UI runtime can silently mutate through a
controller path after command failure or missing command result.

### 5. Dataset Split / Generation Blocker

If dataset split / generate is failing, treat it as the first blocker.

Required work:

- reproduce the current failure with a failing test, smoke, or documented command;
- identify whether the failure is command capability, split config, label/event
  state, epoch state, dataset generator, rollback, UI route, or test fixture;
- fix it through `ApplicationService / DatasetGenerationCommandService`;
- add regression coverage for success and structured failure / rollback;
- ensure downstream training readiness sees the correct backend state.

Completion is forbidden if representative dataset split / generation still fails
or if the fix adds a new legacy bypass.

### 6. Test Cleanup To Engineering Standard

Inventory tests in backend / UI / agent / MCP / headless areas adjacent to the
product runtime paths above.

Classify test clusters as:

- strong behavior / state tests
- useful unit contract tests
- mock-heavy but still useful tests
- implementation-detail tests
- duplicated tests
- obsolete tests
- legacy-blessing tests
- missing non-mocked evidence

Required work:

- rewrite or delete tests that bless legacy fallback as product success;
- replace weak or obsolete tests with stronger behavior, state, `CommandResult`,
  capability, recipe, UI-visible, or non-mocked assertions before deleting them;
- keep mock-heavy tests only when they protect a real contract and cannot be
  replaced cheaply;
- record deleted / rewritten / retained legacy-adjacent tests and why.

Completion is forbidden if test cleanup is only an inventory or if obsolete tests
are deleted without replacement coverage.

### 7. Clean Code / Responsibility Boundary

Complete meaningful responsibility-boundary cleanup in the affected backend,
UI refresh, controller compatibility, or test support code.

The cleanup must do at least one of:

- reduce duplicate workflow truth;
- shrink a legacy adapter surface;
- move readiness / blocked reason / state truth to the backend owner;
- split a god-object or long-method responsibility into a named domain owner;
- remove a fallback helper that masked product runtime failure.

Completion is forbidden if the refactor only renames or moves complexity, or if
core files become harder to reason about.

### 8. Docs Closure

Update canonical docs only.

Record:

- inventory summary;
- removed product legacy paths;
- exact remaining compatibility code and guards;
- dataset split root cause and fix;
- tests added / rewritten / deleted;
- validation results;
- claims still not supported.

Do not add a new roadmap/planning document.

## Hard Completion Blockers

The goal is incomplete if any of these are true:

- any product mutating path can bypass `ApplicationService / Command API` and
  appear successful;
- any product readiness / blocked decision is duplicated in UI, agent, MCP, or
  headless when backend capability exists;
- any real `Study` controller mutation fallback remains outside explicit
  fail-closed legacy / mock-only helper;
- any product runtime path imports or instantiates `BackendFacade`;
- any test still expects `BackendFacade` or controller fallback as product
  success;
- dataset split / generation still fails in the representative path;
- architecture guards only check fragile string grep and do not cover realistic
  forbidden examples;
- final docs do not list remaining compatibility code and why it is non-product;
- required validation is not run and passing.

## Required Validation

Run focused tests first, then broaden as needed:

- `poetry run pytest --capture=sys tests/architecture_compliance.py -q`
- `poetry run pytest --capture=sys tests/unit/test_architecture_compliance.py -q`
- `poetry run pytest --capture=sys tests/unit/backend/application -q`
- focused dataset generation / split regression tests
- representative pipeline smoke that proves dataset split can feed downstream
  training readiness
- focused UI refresh / controller fallback tests if UI paths are touched
- `env MNE_DONTWRITE_HOME=true poetry run pytest --capture=sys tests/unit/llm/tools tests/unit/mcp -q`
- `poetry run ruff check <changed Python files>`
- `poetry run basedpyright <changed Python files>`
- full `poetry run basedpyright` before completion when feasible
- `poetry run mkdocs build --strict`
- `poetry run python scripts/dev/update_quality_dashboard.py`

If a required validation command fails, the goal is incomplete until fixed. Do
not downgrade failures to warnings to claim completion.

## Commit Rules

- Keep commits reviewable by slice.
- Suggested commit scopes:
  - `test: inventory product runtime legacy paths`
  - `test: guard product runtime command spine`
  - `fix: repair dataset generation split path`
  - `refactor: remove ui controller fallback mutation`
  - `refactor: tighten backend command boundaries`
  - `test: replace legacy fallback assertions`
  - `docs: record zero legacy runtime cleanup`
- Do not commit local settings.
- End with `git status --short` clean.

## Final Response Must Include

- `complete` or `incomplete`
- branch and worktree state
- commits created
- inventory summary counts by path class
- all product legacy paths removed
- confirmation that product runtime fallback is gone, or `incomplete`
- confirmation that `BackendFacade` is gone from product runtime paths, or
  `incomplete`
- remaining compatibility code with file references, guards, and removal criteria
- dataset split root cause and fix
- tests added, rewritten, deleted, and retained as compatibility-only
- validation commands and exact results
- dashboard result and exact failures if any
- files / areas intentionally not touched, including Data Import UX layout/copy
- what still cannot be claimed complete
- suggested PR title and PR scope
