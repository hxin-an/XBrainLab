# XBrainLab Now

最後更新：`2026-09-15`

## Active — PR #141 import-boundary acceptance

The agreed common-EEG, EEG-BIDS and MOABB-converted-data import boundary is implemented in
[PR #141](https://github.com/hxin-an/XBrainLab/pull/141). Product behavior still requires manual
acceptance and explicit merge approval; Git and the PR own exact source/check status.

- The fixed MOABB 1.5.0 denominator remains 147 exports: 134 required representative routes passed
  a fresh native campaign, nine rights entries are deferred and four source/semantic blockers remain.
- The 134 verified storage units are canonical direct children of
  `E:\\XBrainLabData\\datasets\\bids`; 23 unbound units remain isolated under quarantine.
  Manifests, current navigation, source mappings and required historical evidence remain on E.
- Final D-side construction cleanup is complete. Exactly 149 task-owned Recycle Bin entries were
  permanently removed after separate approval, reclaiming 2,180,562,944 bytes. Five task junctions
  were removed without deleting their targets. The worktree retains only ignored public test fixtures.
- The unified 134-case summary still has SHA-256
  `ea44c136d9423caa7e2dd55618e76ec4a7a7eb157a0fa37e8920cd07e490daef`; post-cleanup counts
  remain 134 canonical BIDS directories and 23 quarantine directories.

Next: require successful non-skipped checks on the exact current PR head, then provide one integrated
Windows GUI handtest for the import/label boundary. Do not claim all-subject, training or scientific
validation, accept deferred rights, bypass the four blockers, or merge without user acceptance.

## Closed baseline

Quality-baseline closure was accepted and merged via
[PR #140](https://github.com/hxin-an/XBrainLab/pull/140). Its implementation/evidence history stays in
Git/PR, not active dispatch. Known Assistant limitations below remain deferred.

## Candidate — Assistant reliability repair plan (not active implementation)

Goal: reliable selection and parameter-collection continuity with no unexpected workflow side effects.
LOC, static pass, literal prompt assertions or one improved score are not completion criteria.

1. **Mechanism audit before choosing a fix.** Trace baseline/retained failures from full rendered input/
   RAG through raw output, parser, capability/provenance, typed receipt, GUI terminal and visible response.
   Separate intent errors, missing clarification fields, invalid/stale admission and evaluator assumptions.
   Reproduce a bounded set through normal ChatPanel with real execution, using no patient data.
   No Host intent guessing or new model experiments in this diagnostic phase.
2. **Approve a repair boundary.** Select one evidence-backed hypothesis and existing owner. Explicitly
   decide behavior for unspecified/multiple actions, missing/partial values, correction/cancel and
   unavailable tools. Tool/schema/confirmation/visible-flow or model/RAG changes require separate
   approval; current source/tests do not ratify target. A larger model is neither proven necessary nor
   authorized. No generic evaluator platform, control plane or parallel state owner.
3. **Separate development and acceptance.** Keep frozen 81/scorer unchanged as regression evidence.
   Before implementation, define supplementary development cases and disjoint reviewer-owned holdout
   by failure family. Never tune on the holdout or shrink its denominator; disclose prior exposure to
   frozen cases. Reuse existing runners, review any necessary bounded extension, and agree a candidate/
   resource budget before execution. Do not repeatedly add two more prompt attempts after failure.
4. **Implement/review one coherent repair.** Prefer deletion/reuse; test failing observable behavior
   through actual owners, then passing behavior. Mock external inference only in unit tests; real-model/
   native evidence cannot substitute fake generation or preapproved GUI terminals. Independent reviewer
   checks mechanism, meaningful tests, complexity and scope, not only summary.
5. **One integrated acceptance.** Require 36/36 positive, 10/10 explicit origin, 5/5 missing guards,
   5/5 direct clarification admission, 24/24 product no-action and 7/7 clarification. Holdout must show
   zero unexpected execution/confirmation/navigation/mutation and correct authorized continuations.
   Separate raw-model/Host/product outcomes. Then same-source normal ChatPanel→GUI→Command journey,
   relevant cancel/stale cleanup, applicable CI and one final Windows GUI/English Assistant acceptance.
   No Stable/generalized-safety claim from bounded cases alone. Unsupported mechanism or exhausted
   budget means a documented decision checkpoint, not weaker gates or automatic extra prompt edits.

This proposal does not block the explicitly revised cleanup scope or certify Assistant readiness.
New implementation begins only after diagnostic outcome, scope and budget are approved.

其他候選方向見 [Roadmap](roadmap.md)；不宣稱 Assistant Stable 或零缺陷。
