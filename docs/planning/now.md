# XBrainLab Now

最後更新：`2026-09-13`

## Active — Import support boundary and conformance

### Problem, evidence and outcome

User approved a format-independent import contract: common EEG files and EEG-BIDS are parallel
entry points; MOABB-loader-to-EEG-BIDS compatibility is a minimum acceptance requirement, not the
only entry point or proof that all datasets already work. Internal, external, combined and explicitly
absent labels belong to this contract. Unlabelled recordings remain inspectable/preprocessable;
the current supervised epoch workflow requires reviewed usable classes.

Current docs enumerate readers and representative evidence, but do not give users one complete
boundary. Existing MOABB examples are a small selection, not the full release inventory. Establish
a discoverable user guide, separate accepted target from actual evidence, and verify existing
production paths before making support claims.

### Scope, assumptions and non-goals

- Common formats: EDF/EDF+, BDF/BDF+, BrainVision, EEGLAB, GDF, FIF/FIF.gz; retain existing
  Neuroscan CNT without promising other CNT variants. EEG-BIDS remains independent of MOABB.
- Preserve events, units, channel metadata and subject/session/run provenance through conversion
  and import. Arbitrary MAT/CSV waveforms, new device readers, a MOABB download UI, MRI/MEG/iEEG,
  derivatives and a new unlabelled epoch workflow are not included.
- Use the existing reviewed import/Command spine and readiness checks. No additional owner/state,
  post-preprocessing label replacement protocol, prompt/model changes or broad cleanup.
- For the remaining evidence campaign, keep up to four disjoint Windows workers active when the host
  and source permit it. Download only the minimum representative subject/session/run needed for each
  export, reuse checksum-verified retained sources, and refill a freed worker slot immediately. Keep
  downloads/conversions parallel but serialize final E: publication under the existing writer lock;
  do not fetch an entire corpus merely to improve worker utilization.
- Use the merged origin/main baseline in an isolated worktree; preserve existing dirty files/settings,
  running Windows app, datasets and shared environments. User now authorizes additional validation
  data on E: up to 500 GB (500,000,000,000 bytes), including archives, extraction, conversion and
  temporary files. Use `E:\XBrainLabData` without relocating or deleting the existing D: datasets.
  Inspect sources, licenses, transfer/extraction sizes and dependency compatibility before acquisition;
  do not create another virtual environment or silently upgrade the retained product dependencies.
- UI confirmation: user approved reporting corrections and now explicitly authorized exposing BIDS
  Continue without labels (2026-09-12, reply: 授權). Reuse the existing handler/review flow; preserve
  supervised epoch blocking. A separate current blocker is now reproduced: BIDS without `events.tsv`
  remains blocked even after the existing embedded-event review supplies explicit selections/class names.
  User approved prioritizing these importer repairs (2026-09-13, reply: 我同意), including the visible
  embedded-event admission/review and invalid-timeline blocking outcomes. Reuse the existing event
  preview and complete selection checks; keep `events.tsv` preferred when present and never infer class
  mappings. No unrelated layout redesign,
  new readers or inferred class mappings.
- Existing MOABB v1.5.0 three-example registry is historical bounded evidence, not a silently selected
  full-support version. A full release inventory and reproducible conversion provenance remain required.

### Steps and focused validation

Immediate repair order: reproduce missing-events BIDS with a real copied BrainVision fixture, then
share the existing embedded-event review path and prove complete explicit mapping, rejected incomplete
choices, source/event preservation, epoch readiness and recipe replay. In a disjoint worker, protect BIDS
timestamp placement against declared epoched/discontinuous timelines using inherited EEG metadata and
the existing resource admission/semantic boundary. Review both actual diffs and focused evidence before
parallel retained-source Mainsah/Zuo/Yi reruns. Keep acquisition/environment limitations separate from
observed importer and source-to-export fidelity failures; do not reduce the acceptance denominator.

1. Trace file/BIDS scan, internal/external label review, apply, epoch admission and existing real-data
   evidence. Inspect the pinned official converter/release inventory, then acquire missing public data
   in bounded batches within the authorized E: budget; do not mutate retained source datasets.
2. Publish one user-facing support page and link it from workflow/limits/navigation. Keep current truth
   in docs/current.md and engineering evidence rules in docs/validation/README.md; no duplicate status
   platform. Document genuine gaps rather than shrinking the user's accepted requirement.
3. Run existing bounded loader, label/placement, no-label/epoch and BIDS integration tests with shared
   environment, native core disabled and explicit timeouts. Add a meaningful regression only if an
   untested directly relevant behavior needs proof. Existing public fixtures only, no silent skips as PASS.
4. Run source/doc audit and both applicable strict site builds. Inspect the actual diff and report the
   verified subset, exact limits and next repairs. Continue across independent acquisition/conformance
   lanes; request one integrated Windows handtest only after every pinned inventory entry has either
   representative runtime evidence or a specific reviewed blocker and all applicable handoff gates pass.
5. For every nonblocked pinned export, close the literal MOABB-to-BIDS contract: use the pinned
   `BaseDataset.convert_to_bids` path (or record a specific converter failure), retain converter version,
   options and output identities, then scan the generated dataset root with `source_hint="bids"` and
   assert BIDS source diagnostics, selected recording/event pairing, fresh Preview/Validate/Apply,
   waveform/event fidelity and recipe BIDS provenance. Existing direct BrainVision Command receipts are
   a payload-reader baseline, not a substitute for this route. Shared physical recordings may be reused,
   but every registry export needs an explicit mapping and observed BIDS-root outcome.

### Stop condition and next action

Scope-complete requires the published boundary and evidence disposition for all 147 pinned entries:
representative runtime evidence under the user-approved sampling rule, or a specific reviewed source,
license, dependency or upstream-loader blocker. An unexamined entry is neither PASS nor BLOCKED. Missing
required UI/public-flow decisions remain explicit blockers. Exhaust authorized work and independent lanes,
then run one integrated handoff; do not stop merely because one batch, download, or context compaction ends.
For a runtime entry, "representative runtime evidence" now explicitly includes the newly generated
EEG-BIDS and BIDS-root Command route above; payload-file import alone cannot satisfy the stop condition.

The pre-repair per-row route denominator closed at 88 representative route passes and 59 specific
blockers, with zero undispositioned export. The authorized missing-events and timeline repairs are now
implemented; retained-source reruns must establish the new route counts before the product handoff.
### Current checkpoint and remaining work

- The complete pinned denominator and per-entry source/route receipts live only in
  `docs/validation/moabb-inventory.md`. Campaign downloads are complete for the current representative
  reruns; rights/source/loader/converter failures remain explicit and are not importer failures.
- Implemented authorized fixes: format reporting (Neuroscan CNT/BDF/XDF); explicit no-label BIDS wizard;
  embedded-event BIDS review without events.tsv; exact selected-code/class-map agreement and recipe
  replay; inherited EEG RecordingType/EpochLength checks; reviewed sidecar byte/directory identity.
- Independent review reproduced and closed extra/unknown class-map keys, new sidecars after Preview or
  Validate, and recording-specific EEG JSON leaking to another recording. No new authoritative owner,
  public class, production module or compatibility layer was added.
- Native Windows embedded-label wizard passed; both Match Labels and fresh Review screenshots were
  inspected. This is automated workflow evidence, not manual acceptance or a final exact-head gate.
- The first combined run was 400 PASS / 5 FAIL. Junction fixture paths and Windows MAX_PATH were
  environment issues: use the canonical retained fixture root and a short task-owned pytest basetemp.
  Product corrections retain the existing canonicalization budget and prevent unnecessary fresh review
  when no class event is selected. The BBCI driver now clicks the exact dropdown options instead of
  depending on partial-text autocomplete timing; publication assertions remain exact. Final combined
  Windows run: 405 passed, 95 upstream/runtime warnings, no skips. Changed-file Ruff/diff checks pass.
- Mainsah's 20 retained exports plus Zuo/Yi passed Commands, exact readback and recipe replay; the root
  independently read all receipts and matched all six affected backend hashes. Inventory is now
  110 route passes / 37 reviewed blockers / 0 undispositioned. Yi's old missing-events claim was wrong:
  a supplemental retained-source audit verifies all eight event sequences and full run-0 waveform,
  explicitly disclosing sampled waveforms for runs 1–7 and the missing historical converter script/log.
- Shared Windows environment remains the only runtime. Native interop requires the approved escalated
  process boundary; do not restart WSL or create an environment. Original-checkout dirty UI/tests and
  settings.json remain untouched. Task-local acquisition scripts and generated data are not PR content.

Complexity review: nine production files, +401/-25 (net +376). Existing
candidate, BIDS semantic review and Command service retain authority. The ninth file is necessary to
invalidate a review when a new matching sidecar appears; byte hashing alone cannot discover additions.
Removed the unused flat helper and duplicate result construction; catalog matching reuses indexed paths
without repeated canonicalization. Logical rollback units are reporting, no-label/embedded-label
admission, and timeline/source validity. Keep one integrated user handtest.

Next steps, in order:

1. Product tests and scoped review are complete. Finish user-site/source audits and strict docs builds
   for the synchronized support facts; retain the explicitly described evidence/provenance limits.
2. Commit only explicit product/tests/docs paths, push one task PR against main, and require same-head
   non-skipped CI success, including source-diverse data, visual comparison and Windows DPI gates.
   Reuse CI evidence instead of duplicating full regression locally. Run both strict documentation
   builds and applicable source audits. No merge approval has been given for this source.
3. Inspect changed artifacts, launch the exact Windows candidate with visible PowerShell log, confirm
   responsiveness, and provide one GUI/Assistant handtest checklist and repeatable command.
   Stop at handoff only after applicable gates; pending evidence is a checkpoint, not completion.

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
