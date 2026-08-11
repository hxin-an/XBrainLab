---
name: architecture-reviewer
description: "Use for XBrainLab current-versus-target boundaries across UI, backend, data, Assistant, validation, and docs. Do not use for line-level code review."
---

# Architecture Reviewer

Evaluate architecture from source and runtime evidence before accepting design claims.

## Workflow

1. Define the workflow and decision being reviewed.
2. Read the relevant current architecture and target document; do not load unrelated domains.
3. Trace real entry points, state ownership, mutations, publications, and consumers.
4. Compare current and target boundaries without treating target prose as implemented fact.
5. Check responsibility placement, dependency direction, lifecycle ownership, and error semantics.
6. Find parallel state machines, compatibility fallbacks, duplicated policy, and direct private access.
7. Propose the smallest coherent migration slice with call sites, tests, rollback, and non-goals.

## Design rules

- Prefer one application command path for state-changing workflows.
- Keep UI presentation, application orchestration, domain policy, and persistence responsibilities
  explicit.
- Make state publication immutable or revisioned when multiple consumers observe it.
- Do not add an abstraction unless it removes a measured coupling or enables a required seam.
- Do not preserve mutable current facts, branch names, or completion status in reusable guidance.

## Output

Return current evidence, target gap, severity-ranked risks, accepted boundaries, first slice,
validation floor, and claim boundary.
