---
name: docs-curator
description: "Use for XBrainLab doc consolidation, current-truth conflicts, historical cleanup, and navigation repair. Do not use for visual MkDocs redesign."
---

# Docs Curator

Keep one authority for each kind of truth.

## Routing

- Current product fact: `docs/current.md` or `docs/architecture/`.
- Target requirement: `docs/target/`.
- Active work: `docs/planning/now.md`; long-term order: `docs/planning/roadmap.md`.
- Decision: `docs/decisions/README.md`.
- Evidence and claim contract: `docs/validation/README.md`.
- Important implementation history: `docs/records/implementation_log.md`.
- Chronological work note: `docs/records/worklog.md`.
- Agent method/trigger only: `.agents/`.

## Workflow

1. Verify disputed statements against Git, source, runtime evidence, and canonical docs.
2. Classify each statement by the routing table.
3. Merge useful content into the existing authority; prefer deletion over redirect-only duplicates.
4. Mark retained records historical and remove them from dispatch/navigation labels.
5. Repair links, MkDocs navigation, and instruction references.
6. Run the guidance audit and MkDocs strict build.

Do not create a new top-level plan for a one-time cleanup. Do not put branch names, gate argv,
test totals, or current completion status in reusable skills.
