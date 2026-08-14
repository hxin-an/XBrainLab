---
name: docs-curator
description: "Use for XBrainLab doc consolidation, conflicting claims, historical cleanup, and navigation repair. Do not use for visual MkDocs redesign or a read-only status/current-fact summary with no documentation change."
---

# Docs Curator

Keep one authority for each kind of truth.

Use the authority map in root `AGENTS.md`; do not reproduce it in another guidance layer.

## Workflow

1. Verify disputed statements against Git, source, runtime evidence, and canonical docs.
2. Classify each statement by the routing table.
3. Merge useful content into the existing authority; prefer deletion over redirect-only duplicates.
4. Mark retained records historical and remove them from dispatch/navigation labels.
5. Repair links, MkDocs navigation, and instruction references.
6. Update a canonical document only when its truth changed; a final task report is enough for
   ordinary focused validation.
7. Run the relevant link/audit check and MkDocs strict build when the docs site changed.

Do not create a new top-level plan for a one-time cleanup. Do not put branch names, gate argv,
test totals, or current completion status in reusable skills. Do not write both implementation log
and worklog for the same event.
