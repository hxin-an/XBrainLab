# Workflow: Agent Tool-call Scoring

Use only after current product planning and validation confirm the Assistant/backend/local-runtime
surface is stable enough to freeze. Primary skills are `agent-toolcall-designer` and
`thesis-evidence-reviewer`.

1. State hypothesis, intended claim, exact source SHA, and product prerequisite evidence.
2. Freeze exact model/revision/runtime, prompt, tools, cases, scorer, seed, retries, and repeats.
3. Define case schema with positive, negative, blocked, recovery, ambiguity, and multi-step routes.
4. Score intent, tool, arguments, admission, execution, verification, trajectory, and final answer
   separately.
5. Preserve per-run machine-readable traces and a bounded human-readable report.
6. Blind-review a sample to estimate scorer false positives/negatives.
7. Report variance, failures, exclusions, and reproducible identity.

Never silently switch model/revision or reinterpret a failed exact-model run as fallback success.
Do not equate deterministic command tests, tool-call accuracy, EEG model accuracy, usability, or
clinical validity.
