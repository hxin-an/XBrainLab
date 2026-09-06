---
name: refactor-slicer
description: "Use for bounded XBrainLab backend, UI, or Assistant refactor slices with call sites, baselines, tests, rollback, and ownership. Do not use for broad redesign."
---

# Refactor Slicer

Turn an architectural concern into independently reviewable behavior-preserving slices.

Use `../../workflows/refactor-slice.md` when its procedure governs the work. Finish each bounded subtask
with focused evidence, then continue directly necessary, declared work in the same authorized outcome.
Independent migration findings do not continue automatically.

For state-changing backend/Assistant work, specify command/service shape and publication contract.
For presentation-only UI refactors, specify widget/layout ownership and visual invariants instead;
do not force a command template where no command exists.

## Slice output

Include scope, current call sites, deletion candidates, owners before/after, production LOC delta,
behavior baseline, directly relevant tests, rollback, and stopping condition. Split independent UI,
backend, and Assistant work; editing UI still requires root authorization.
