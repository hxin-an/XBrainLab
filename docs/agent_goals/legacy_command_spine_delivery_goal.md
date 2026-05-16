# Legacy Command Spine Delivery Goal

Goal: Deliver the target backend/runtime architecture for XBrainLab product
mutating workflows: `ApplicationService / Command API` is the only product runtime
spine, legacy product fallback is gone, and `BackendFacade` is removed from product
paths.

This is a single-agent execution goal. Do not spawn subagents. Do not stop after an
audit. The agent owns discovery, implementation, tests, docs, validation, commits,
and final review. Work from the final product state backward; do not define success
around transitional architecture.

## Required Skills / Docs

Read and follow:

- `.agents/skills/pr-branch-governance/SKILL.md`
- `AGENTS.md`
- `docs/current.md`
- `docs/target/README.md`
- `docs/architecture/README.md`
- `docs/planning/now.md`
- `docs/validation/README.md`
- `.agents/README.md`
- `.agents/stack.md`

## Hard Rules

- No subagents.
- No UX redesign.
- Do not change Load Labels / Match Labels layout, visual design, or product copy.
- Do not use `git reset --hard`, destructive checkout, or overwrite unrelated user
  work.
- Do not create another planning document.
- Do not call the goal complete with only inventory, dashboard PASS, smoke PASS, or
  docs.
- Do not leave a product mutating path silently falling back to legacy controller
  mutation.
- Do not leave any product mutating path outside `ApplicationService / Command API`.
- Do not leave duplicate workflow truth in UI, agent, MCP, headless, facade, or
  controller paths.
- Do not leave `BackendFacade` in product runtime paths.
- Do not delete tests unless stronger replacement coverage is already committed.

## Start Gate

1. Run `git status --short` and `git branch --show-current`.
2. State current branch, intended branch/PR scope, and files intentionally not touched.
3. If not already on a suitable non-main branch, create one.
4. Inspect current command spine and legacy paths before editing.

## Target Product State

The finished repo must behave as if the legacy product architecture is gone for the
main mutating workflows in scope:

- load/import data
- data interpretation scan / preview / validate / apply / recipe reload
- preprocess
- epoch
- dataset creation / reset
- training command readiness / blocked reasons

For those workflows:

- UI actions call command-backed services.
- Headless scripts call command-backed services.
- Agent tools and MCP adapters call command-backed services.
- State, readiness, blocked reasons, confirmations, recipe traces, and capability
  policy come from backend command/state contracts.
- Direct mutation of `Study`, controller, data manager, preprocess, epoch, dataset,
  or training state from product callers is removed.
- `BackendFacade` is not a product runtime layer.
- Any invalid action is represented by a structured command failure or blocked result,
  not by a legacy fallback or silent best-effort mutation.

Non-product legacy code may remain only if it is test-only, read-only, unreachable
from product runtime, and documented as outside the product path. It must not be used
to satisfy any completion gate.

## Required Work

### 1. Legacy Product Path Removal

- Find product UI/headless/agent/MCP paths that still mutate `Study`, controller, data
  manager, preprocessing, epoching, dataset, or training state outside the command
  spine.
- Replace them with command calls.
- If the command does not exist, implement the command/API behavior instead of keeping
  the legacy route.
- If the action should not be allowed, return a structured command blocked/error result
  with a clear reason.
- Delete fallback success paths from product callers.
- Add architecture/guard tests proving fallback success paths cannot return as product
  success.

Completion is forbidden if a real user action can bypass command validation and still
look successful. Completion is forbidden if any product runtime fallback remains.

### 2. BackendFacade Removal / De-Scope

- Treat `BackendFacade` as legacy product architecture to remove, not a boundary to
  polish.
- Remove `BackendFacade` call sites from product runtime paths.
- Route callers to `ApplicationService / Command API` directly, or through a smaller
  command-specific adapter that contains no workflow policy.
- Remove duplicated readiness, capability, or workflow decisions from facade/UI/agent
  paths when backend state already owns them.
- Delete facade tests that only bless facade policy after replacing them with command
  behavior/parity tests.
- Add or update tests proving product callers no longer need facade workflow policy.

Completion is forbidden if the facade reimplements workflow policy. Completion is also
forbidden if `BackendFacade` remains in touched product runtime paths.

### 3. State / Capability Truth

- Ensure command results, state snapshots, readiness, blocked reasons, and capability
  policy are aligned for touched workflows.
- Replace stale local UI/agent checks with backend state.
- Add tests for blocked and recovery cases, not only success cases.

Completion is forbidden if UI, agent, and backend disagree on whether a touched command
is allowed.

### 4. Test Cleanup With Replacement

- Identify weak tests in the touched areas: mock-only, implementation-detail,
  duplicated, obsolete, or asserting legacy fallback as success.
- Replace weak tests with behavior/state/result/recipe/tool/UI-visible assertions.
- Remove obsolete tests only after replacement coverage is in place.
- Keep a compact inventory in an existing canonical doc or worklog section.

Completion is forbidden if tests still bless a legacy bypass as the product path.

### 5. Clean Code Refactor

- Complete at least one meaningful responsibility-boundary refactor in touched legacy
  or command-spine code.
- The refactor must reduce duplicate workflow truth, shrink a legacy adapter surface,
  or move logic to the correct backend owner.
- Validate behavior before final commit.

Completion is forbidden if the refactor only renames or moves complexity.

### 6. Docs Closure

- Update canonical docs only.
- Record implemented changes, validation, removed legacy paths, and exact remaining
  non-product legacy code if any.
- Do not add a new roadmap/planning document.

## Required Validation

Run the focused tests first, then broaden as needed:

- `poetry run pytest --capture=sys tests/architecture_compliance.py -q`
- `poetry run pytest --capture=sys tests/unit/backend/application -q`
- `env QT_QPA_PLATFORM=offscreen MNE_DONTWRITE_HOME=true poetry run pytest --capture=sys tests/unit/ui -q`
- `env MNE_DONTWRITE_HOME=true poetry run pytest --capture=sys tests/unit/llm/tools tests/unit/mcp -q`
- `poetry run ruff check <changed Python files>`
- `poetry run basedpyright <changed Python files>`
- `poetry run mkdocs build --strict`
- `poetry run python scripts/dev/update_quality_dashboard.py`

If a required validation command fails, the goal is incomplete until it is fixed. Do
not downgrade failures to warnings to claim completion. Pre-existing failures may be
reported, but they still prevent a `complete` final status for this goal if they are
in the required validation gate.

## Commit Rules

- Keep commits reviewable by scope.
- Suggested commit scopes:
  - `refactor: route product paths through command spine`
  - `test: guard legacy fallback removal`
  - `fix: align backend capability state`
  - `docs: record command spine cleanup`
- Do not commit local settings.
- End with `git status --short` clean.

## Final Completion Gate

The goal is complete only if all are true:

- All in-scope product mutating paths route through `ApplicationService / Command API`.
- No product runtime legacy fallback remains.
- `BackendFacade` is removed from product runtime paths.
- UI/headless/agent/MCP touched surfaces agree on state, capability, and blocked
  reasons.
- Weak tests in touched areas were strengthened or removed after replacement.
- At least one real responsibility-boundary refactor landed.
- Required validation was run and passed.
- Worktree is clean.

If any item is false, final status must be `incomplete`.

## Final Response Must Include

- `complete` or `incomplete`
- branch and worktree state
- commits created
- legacy product paths removed
- confirmation that product runtime fallback is gone, or `incomplete`
- confirmation that `BackendFacade` is gone from product runtime paths, or `incomplete`
- any remaining non-product legacy code with file references
- tests added, changed, removed
- validation commands and exact results
- dashboard result and exact failures if any
- files/areas intentionally not touched, including Data Import UX layout/copy
- suggested PR title and PR scope
