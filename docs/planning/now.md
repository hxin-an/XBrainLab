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

- Keep the full 147-entry denominator and per-entry source/conversion/Command receipts in
  `docs/validation/moabb-inventory.md`; do not make a second campaign status registry.
- Product repairs are committed at `3697f95b` on the existing PR #141. They include format reporting,
  explicit no-label BIDS, missing-events embedded review, timeline/sidecar freshness, selected timestamp
  label-field authority, and bounded recipe persistence/public diagnostics. No new authoritative owner,
  public class or compatibility layer was introduced; unrelated root settings/UI/test edits remain intact.
- Recipe persistence retains complete explicit choices/content identities and the 1 MiB read cap,
  bounds only regenerable diagnostic evidence, and rejects oversized choices before overwrite.
  BIDS timestamp/interval classes come from the selected field; actual event-code collisions still block.
  Recipe/projection tests: 17 passed. Strict BIDS and timestamp integration: 63 passed with a short
  Windows basetemp; the previous MAX_PATH fixture error occurred before product code.
- Source-diverse, native startup, visual/DPI and most regression gates pass at `3697f95b`.
  Linux integration fails because the new generated fixture used optional pybv, absent from that shard.
  The fixture-only repair now writes tiny real BrainVision files directly; the same two Command/recipe
  regressions pass on Windows and Ruff passes. Do not add a dependency, skip or weaken the assertions.
  The next commit must pass all applicable CI on its own exact SHA.
- Remaining-blocker work proved `return_all_modalities=True` preserves non-STIM channels in the pinned
  official converter. Root independently reviews actual scripts and receipts, including sidecar channel
  types, fresh source objects, exact class/sample arrays, full chunked waveforms and recipe replay.
  Huebner unitless MISC fidelity uses exact float32 storage representation, not an invented physical
  tolerance. Kojima B's old failure paired the wrong source/BIDS run.
- BNCI2019 now passes numerical transport and App/replay checks, but source EOG unit semantics remain
  ambiguous: original GDF unit code 0 and asymmetric pinned loader scaling. Do not silently correct
  units. Triana's unmodified official converter fails for missing head-coordinate fiducials; its old
  manually altered export is not official-converter evidence. Other source/license/dependency/large
  archive blockers remain specific inventory rows, not importer failures or unexamined entries.
- BNCI2025_001 and Weibo supplemental receipts are complete and independently inspected: every
  class/sample pair, sidecar type, initial/replayed full waveform and fresh post-run source hash passes.
  The inventory now records 127 representative BIDS-route passes and 20 specific blockers out of 147;
  payload/runtime evidence is 129/18. BNCI2025 source-reader boundary warnings do not establish
  discontinuous recording support; the selected public-loader/BIDS timeline is continuous.
- Some original sources reside in the task worktree's `E-/XBrainLabData` because the upstream downloader
  sanitized a Windows drive path. Use exact retained-file bindings plus hard offline guards, not guessed
  cache paths or new downloads. One BNCI2025 subject archive was duplicated during path resolution;
  retain it pending safe post-merge cleanup, not another download. New supplementary receipts are
  workspace-local when external E: writes are rejected. Do not delete original data or shared environments.

Complexity review: the initial repair touched nine production files, +401/-25 (net +376); the two
follow-up backend fixes add +88/-38 (net +50) across existing owners. Removed redundant mapping logic
and reused existing evidence projection; no owner/state/control-plane increase. Rollback remains
slice-level while the user receives one integrated handtest.

Next steps, in order:

1. The final supplemental fidelity checks, 147-row arithmetic and inventory/current/user-facing
   claim synchronization are complete. No all-MOABB or full-corpus certification claim.
2. Commit only explicit tests/docs paths and push the fixture repair and final facts to PR #141.
   Require same-head non-skipped CI success, including source-diverse data, visual/DPI/platform gates
   and both strict docs builds. Reuse equivalent CI; do not repeat a full local suite.
3. Review changed-surface native screenshots, prepare the exact Windows manual checkout using the
   single retained interpreter, then launch with one visible PowerShell console as its live log.
   Confirm responsiveness and provide the GUI/English-Assistant handtest checklist and repeat command.
   Do not merge until the user passes this source and explicitly approves merging.

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
