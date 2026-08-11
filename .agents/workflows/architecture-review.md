# Workflow: Architecture Review

Use for a cross-area review that must end in a bounded engineering decision.

## Skills

Primary: `architecture-reviewer`. Add `agent-toolcall-designer`,
`data-interpretation-reviewer`, or `validation-runner` only for the areas actually reviewed.

## Steps

1. Define the decision, workflows, affected consumers, and non-goals.
2. Read the relevant current and target architecture sections.
3. Trace source entry points, state ownership, mutations, publication, errors, and cleanup.
4. Record current evidence, target gap, risk, and duplicated/fallback paths by area.
5. Rank gaps by user impact and architectural leverage.
6. Define the smallest first slice with call sites, behavior baseline, rollback, and validation.
7. Update `docs/architecture/`, `docs/planning/now.md`, or decisions only when their truth changed.

If the request is review-only, stop before implementation. Do not dispatch from historical records
or turn every observation into one mixed refactor.
