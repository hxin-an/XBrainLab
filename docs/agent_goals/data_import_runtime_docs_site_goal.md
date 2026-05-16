# Data Import Runtime Stabilization And Docs Site Goal

Last updated: 2026-05-13

## Objective

Build a clean integration checkpoint that includes the current Data Import UX work,
then raise engineering quality across runtime cleanup, tests, docs truth, artifact
hygiene, and finally a private MkDocs site polish. This is not a request to finish
Match Labels or Review and Import product design tonight.

Treat the target as a 9.5/10 engineering-quality gate for every area that can be
validated without the user: backend command spine, legacy runtime cleanup, UI refresh
truth, test quality, docs/evidence hygiene, artifact hygiene, and private docs-site
readability. Do not use a self-assigned score as evidence; meet the objective gates
below or explain the exact blocker.

## Workspaces And Branches

Work only in:

```text
/mnt/d/workspace_v2/projects/lab/XBrainLab
```

Do not edit:

```text
/mnt/d/workspace_v2/projects/lab/XBrainLab-ux-match-labels
.vscode/settings.json
```

Use this branch sequence:

1. Runtime integration branch: `stabilize/data-import-runtime`
2. Docs site branch after runtime/docs truth is clean: `docs/data-import-private-portal`

Do not merge to `main`.

## Phase 1: Integrate Current UX Checkpoint

Create or switch to `stabilize/data-import-runtime` from the current runtime cleanup
line. Then integrate UX checkpoint commit:

```text
1c748dd5 feat: add placement evidence for label matching
```

This checkpoint must preserve the current Data Import wizard and backend placement
evidence for mainstream label matching:

- EEG event order
- Label time
- Label interval
- Label event code

Do not redesign Match Labels or Review and Import. Record remaining UX debt instead.

Minimum gate for Phase 1:

- UX checkpoint is present in branch history.
- Worktree is clean except explicitly pre-existing local-only files.
- Focused Data Import backend/UI tests still pass or exact blockers are documented.

## Phase 2: Engineering Stabilization

Work until the runtime cleanup is objectively stronger, not merely renamed.

Required outcomes:

- Product UI, agent, headless, and MCP paths use `ApplicationService / Command API`
  as backend truth.
- No product runtime dependency on `BackendFacade` or silent legacy fallback remains.
- Remaining compatibility exceptions, if any, are quarantined, named as compatibility
  only, tested, and documented.
- UI controller construction and read-only population fallback are removed from
  product paths where feasible.
- Major UI refresh paths touched by dataset/import/preprocess/epoch/train/reset rely
  on command result `changed_state`, backend snapshot, or observer state, not a second
  local truth.
- Mock-heavy or obsolete tests are replaced by behavior/state/command-result tests
  before deletion.
- Architecture guards fail if removed legacy runtime paths are reintroduced.
- The final state should be strong enough that a reviewer could reasonably score
  backend command spine, legacy cleanup, UI refresh truth, and test quality at 9.5/10
  based on code, tests, and validation evidence, not agent assertion.

Validation should include the smallest meaningful set for touched areas:

- focused backend/ApplicationService tests
- focused UI tests with `QT_QPA_PLATFORM=offscreen`
- architecture or quality guards
- fast quality dashboard if feasible
- `poetry run mkdocs build --strict`

Do not stop only because tests pass if obvious legacy runtime fallback, stale docs, or
weak tests remain.

## Phase 3: Docs Truth And Artifact Hygiene

Before making the site prettier, make the source truth readable and correct.

Update canonical docs only when code/tests support the claim:

- `docs/current.md`
- `docs/architecture/*`
- `docs/target/*`
- `docs/planning/now.md`
- `docs/validation/README.md`
- `docs/records/worklog.md` if useful

Artifact cleanup rules:

- Do not delete evidence just because the folder is crowded.
- Delete only obsolete, duplicated, unreferenced files.
- Add or improve a human-readable artifact index so useful screenshots and runtime
  evidence can be found quickly.
- Preserve Data Import UX screenshots that support current review.

Docs truth gate:

- stale claims contradicted by code/tests are removed or corrected.
- claim boundaries remain explicit: no full BIDS claim, no final Match Labels UX claim,
  no human Windows acceptance claim unless actually performed.
- `mkdocs build --strict` passes.

## Phase 4: Private Docs Site Polish

Only after Phases 1-3 are committed, create/switch to:

```text
docs/data-import-private-portal
```

Redesign the MkDocs source as a quiet engineering dashboard for private review. Do not
hand-edit `site/` build output.

Homepage must show, in the first useful viewport:

- current product status
- product readiness and blockers
- Data Import status
- validation evidence
- important artifacts/screenshots
- next work

Use MkDocs Material features and restrained CSS. Avoid marketing-page hero design,
decorative gradients, and raw worklog dumps as the main experience.

Site gate:

- `poetry run mkdocs build --strict` passes.
- A built-site screenshot is captured or manually inspected.
- If configured deployment works, publish to the configured GitHub Pages target for
  private review.
- If deployment config/credentials are missing, do not invent secrets; report the
  exact blocker and push the branch.

## Non-Goals

- Do not finish or redesign Match Labels final UX.
- Do not finish or redesign Review and Import final UX.
- Do not merge to `main`.
- Do not hide fallback behavior behind passing tests.
- Do not delete tests without stronger replacement coverage.

## Final Report Requirements

Report:

- branches created/used
- commits made
- exact validation commands and results
- tests replaced or deleted, with reason
- artifact cleanup performed
- docs/site changes made
- pushed branches
- site URL or deployment blocker
- remaining risks
- remaining UX debt for Match Labels and Review and Import

Completion means the integration branch is clean, pushed, validated, and documented;
the docs site branch is either deployed for private review or has a precise deployment
blocker. It does not mean the Data Import UX is final.
