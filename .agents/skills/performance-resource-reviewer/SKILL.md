---
name: performance-resource-reviewer
description: "Use for XBrainLab latency, memory, GPU/VRAM, cache, long jobs, Qt responsiveness, WSL stability, and scan cost. Do not use without measurements."
---

# Performance and Resource Reviewer

Require a measured bottleneck before recommending optimization.

## Workflow

1. Define the user-visible operation, workload, environment, and acceptable budget.
2. Capture a reproducible baseline for wall time, CPU, RAM, GPU/VRAM, IO, cache, and UI stalls as
   relevant.
3. Trace the critical path and ownership of large objects, workers, callbacks, and cleanup.
4. Separate cold start, warm cache, steady state, cancellation, and repeated-run behavior.
5. Identify the dominant cost and choose the smallest safe intervention.
6. Re-run the same workload and compare quality/correctness as well as resource metrics.
7. Add a regression budget or observability hook when the metric is stable enough.

## Decision rules

- Prefer batching, bounded caches, lazy loading, cancellation, and lifecycle fixes before native
  rewrites.
- Do not move work off the UI thread without defining publication and shutdown ownership.
- Include model/dataset cache location and cleanup in resource claims.
- A faster path that changes EEG semantics or output quality is not an optimization win.

Report baseline, bottleneck evidence, change, before/after metrics, variance, guard, and remaining
platform boundaries.
