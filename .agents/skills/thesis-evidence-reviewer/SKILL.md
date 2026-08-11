---
name: thesis-evidence-reviewer
description: "Use for XBrainLab thesis evidence on local-LLM tool calls, cases, scorers, trajectories, reproducibility, and claims. Do not use for product readiness."
---

# Thesis Evidence Reviewer

Review whether an experiment supports the written claim.

## Workflow

1. State the hypothesis, unit of analysis, population/task boundary, and success metric.
2. Freeze exact model, revision, quantization/runtime, prompt, tool registry, dataset/cases, scorer,
   seed, repeats, environment, and source SHA.
3. Check positive, negative, blocked, recovery, ambiguity, and multi-step coverage.
4. Separate tool selection, arguments, admission, execution, verification, trajectory, and final
   answer scoring.
5. Audit scorer false positives/negatives with blinded human review.
6. Report per-case outcomes, variance, failures, exclusions, and reproducible artifact identity.
7. Compare only runs with equivalent protocols; never silently substitute model or revision.

## Claim boundaries

- Deterministic tool tests are engineering evidence, not local-model accuracy.
- Tool-call accuracy is not EEG training accuracy, clinical validity, or product usability.
- A product checkpoint is not thesis evidence until the suite and protocol are frozen.
- Failed exact-model runs remain failures; retry policy must be declared and cannot become fallback.

Report supported claim, unsupported extensions, threats to validity, missing cases, scorer audit,
and exact reproduction command/source identity.
