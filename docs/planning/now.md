# XBrainLab Now

最後更新：`2026-09-16`

## Active — retained E-drive datasets through normal Windows import

User approved this continuation on 2026-09-16. The observable outcome is that a teacher can
choose any of the 134 retained formal dataset roots in `E:\\XBrainLabData\\datasets\\bids`
and complete normal Windows GUI import, with meaningful data and label state, without hidden
manifest choices. The earlier 134 representative backend passes do not establish that outcome.

Scope: inventory every retained recording; resolve all 23 unbound old BIDS directories; verify
single-recording, default and whole-dataset selection through existing import owners; run all 134
roots through native Windows GUI; repair reachable import defects and synchronize navigation/docs.
No new downloads/environments, acceptance of deferred rights, arbitrary cross-dataset combinations,
all-subject claims beyond retained data, training/scientific certification or automatic merge.

Assumptions/authority: reuse PR #141 and the existing shared Windows environment. Preserve unrelated
root changes/settings. User approved cleanup, exact duplicate removal within prior authorization,
and retention/promotion of valid unique recordings. Resolve exact deletion targets and independently
verify replacements first; preserve source and necessary failure evidence. Visible UI changes still
need a concrete proposed change and explicit confirmation before implementation.

Execution and focused validation:
1. Inventory the 134 formal and 23 quarantined roots, recording selections, metadata and sizes.
   Compare each old recording to canonical/source content; assign exact duplicate, superseded
   conversion, valid unique recording or a concrete unresolved difference. An unknown is unfinished.
2. Resolve quarantine dispositions without shrinking the 134 required catalog; validate any promoted
   recordings and retain relocation/source mappings before approved deletion.
3. Exercise all retained recordings and default/whole-root combinations through Scan/Preview/
   Validate/Apply and observable readback. Reuse existing runners; reproduce defects before repair.
4. Exercise all 134 roots via real Windows wizard controls, including label review and final dataset
   display; fail on hidden choices, unexpected dialogs, partial imports or untested recordings.
   Check representative cancel/retry and consecutive imports. Bound native jobs and preserve failures.
5. Review actual evidence coverage, synchronize the stale 127/20 user-doc claim and E navigation,
   run applicable same-commit gates/CI, then open Windows for one consolidated manual acceptance.

Stop condition: all 23 old directories have resolved dispositions; every retained formal recording
is accounted for and verified; all 134 roots have native GUI results; no unexplained import failures,
missing cases or stale navigation remain. A real product decision/resource blocker is reported as
unfinished, never converted into a pass. User handtest/merge is the final separate approval.

Progress (2026-09-16): inventory found 1,179 formal recordings and 63 quarantined recordings.
Seventeen quarantined directories (436 files, 2,194,277,166 logical bytes) were independently
rehashed against canonical replacements and permanently removed under the approved cleanup scope;
the journal and before inventory are at `E:\\XBrainLabData\\evidence\\retained-import-20260916\\duplicate-removal`.
All 26 unique Brain Invaders recordings passed independent waveform/event readback and recipe
replay and were promoted into the three existing formal roots, with refreshed manifest bindings.
The three superseded conversions (Kim2025, Wang2021, Weibo2014) passed exact common-channel/event
comparison against their more complete replacements. All six remaining old directories were then
removed after rechecking replacements; 27 differing small metadata files were archived with the
deletion journal. There are now 134 formal roots, 1,205 retained recordings and zero quarantined units.
Evidence is under `retained-import-20260916/{unique-promotion,quarantine-closure}` on E.
Native GUI default diagnostics are running; these do not yet establish correct label semantics or
the full retained denominator. The stale user-doc 127/20 count is corrected.

Next: synchronize E navigation and finish normal subject-selection/label automation and all retained
GUI/backend cases. Cattan's 240-recording GUI diagnostic terminated during loading; independently,
native profiling measured preview at 51.84 s (with profiling overhead), including 24.41 s in repeated
linear dependency lookup and 1,751,051 path-key calls. Bounded backend repair: characterize existing
index/dependency safety, add a deterministic lookup-cost regression, then derive lookup keys once
inside the existing immutable index and defer unused generic path resolution. No new owner, global
cache, admission bypass, UI change or EEG semantic change. Re-run the same tests/profile/GUI case;
keep native process failure diagnosis separate from the measured lookup cost.
The lookup change is +17/-9 production LOC (two files, net +8, unchanged owners). The same
240-recording profiled Scan/Preview measured 13.01/25.72 s versus baseline 23.08/51.84 s;
profiling overhead and concurrent diagnostic workload mean these are not a general latency SLA.
A Windows identity-mutation test needed explicit mtime change because immediate NTFS operations
can share timestamps; its rejection assertion is unchanged. Payload admission remains separate.

Brandl default import also reproduced a concrete estimate defect: seven headers describe
10,037,517,840 raw bytes (~16.95 GB with buffers), but including their parser dependencies inflates
the preflight to ~47.4 GiB by counting `.eeg` files again. Next bounded fix: a real BrainVision
fixture must prove header-only and header+dependencies have the same waveform budget; unowned
payloads must still count and genuine oversized selections remain blocked. Move the existing
bounded BrainVision parser out of candidate into `brainvision_preflight.py`, sharing it with
ResourceChecker. Complexity review: no new owner/state/admission contract; move ~180 existing
lines, remove the original block, add only dependency accounting (~30-60 net production lines).
Two real callers need the same unsafe-path policy; do not duplicate parsing or add a compatibility
wrapper. Re-run candidate/index/resource tests and actual Brandl/Jeong GUI selections.
Resource/index/candidate tests now pass 127/127. Actual quarantine is empty after additionally
resolving ten interrupted-download files in two directories: all nonzero bytes matched retained
sources; 98,937,680 logical bytes removed with 167,426 bytes of exact reconstruction masks.
The three existing E navigation files now bind catalog `949a27ce...d70adb` and state that the
all-recording/native campaign remains unfinished.

Kumar all-20 validation reproduces a sub-microsecond end-boundary defect: final row onset
181.58203125 + six-decimal duration 4.417969 = 186.00000025 against 186 stored seconds.
The normal review closes as blocked; do not count that driver timeout as success. Bounded repair:
allow only annotation timestamp representation error at the recording-end interval check
(at most one microsecond and at most half a sample); preserve literal onset/duration, keep onset
at/after the end and real overruns blocked. Add real Command/apply regression plus neighboring
overrun rejections, then retry all 20 through native GUI. No data rewriting or UI edits.
The end tolerance now reuses the existing event-loader annotation precision at both preview and
apply; BIDS/event-loader tests pass 71/71, including source-file preservation and real overruns.
Next execution: finish first diagnostic GUI pass, rerun failures through reviewed visible class
controls, then complete all-retained-recording readback/replay and whole-root native import.
No GUI pass count certifies label semantics or untested retained recordings.
Diagnostic scripts/results live under this worktree's `build/dev-artifacts/retained-import-20260916`.
No UI changes are authorized by this diagnostic finding; no new human-acceptance claim is made.

All eight initially unfinished default GUI roots subsequently loaded via reviewed visible controls.
Dreyer baseline recordings remain alongside MI runs; the diagnostic driver now waits for import
completion rather than querying a busy review. Jeong's complete eleven-class mapping was checked
against the retained pinned loader. A 108-recording pilot passed 106 readback/replay cases; the two
baseline cases exposed a verifier that demanded the missing-label blocker even when explicit
context-only review correctly publishes a missing-reviewed-target blocker. Extend the verifier's
real-command baseline fixture, keeping zero class-map/readiness assertions and negative controls.
Independent review additionally found Decimal-preview versus float-apply disagreement at the exact
annotation end tolerance (one ULP, e.g. 1 sample at 3 Hz). Add real Preview/Apply boundary regression,
then use the same bounded numeric predicate at both owners without changing source timestamps,
onset admission or whole-sample-overrun rejection. These directly related corrections precede the
final clean-source recording/native campaigns; earlier diagnostics remain non-final evidence.
The real 3/7 Hz reproduction additionally confirmed MNE crop rejection at a microsecond boundary.
Both owners now share numeric admission plus the pinned MNE timedelta representability predicate;
the original Kumar quarter-microsecond case still imports without changing literal source bytes.
Context-only verification accepts the existing missing-reviewed-target code as well as missing
labels, while still rejecting any published classes/readiness. Related tests pass 89/89; independent
review found no remaining blocker in this fix. Cattan whole-root GUI exceeded the diagnostic
deadline (240 files, initial review ~125 s); measure its actual GUI/worker bottleneck before repair,
do not raise timeouts or substitute the 120-file default pass for full-root evidence.
Native stack samples at15/30seconds locate the Cattan regression in the new resource accounting:
`estimate_dataset_ram` rebuilds the entire resolved path-key set for each dependency. Precompute
that invocation-local set once; characterize real estimate equality and linear path-resolution
counts, then rerun the same240-file GUI budget. No new cache/owner or admission bypass.
The separate visible external-to-internal label switch cannot fetch absent internal evidence because
Next is disabled. Concrete reuse of the existing Refresh label preview flow was requested from the
user; UI edits remain unauthorized until that reply. Other diagnostics continue.
Current large diagnostics are not final-source evidence: Windows Git could not read the WSL `.git`
pointer. Explicit task-local GIT_DIR/GIT_COMMON_DIR/GIT_WORK_TREE were verified against2aef3621;
future candidate runs must fail closed on unavailable identity and record the wrapper/driver hashes.
The linear-path regression failed at642 canonicalizations for18 paths; the invocation-local set
fix passes it with unchanged waveform memory, and112 resource/candidate tests pass. The two
old diagnostic supervisors were identity-checked and stopped (only owned process/job trees);
partial results/timeouts remain. Restart from a clean commit using the explicit Windows Git entrypoint.

Clean `3cfd9d70` baseline is complete: all 1,205 unique recordings passed full waveform/event
readback and fresh recipe replay across `retained-all2`, `retained-retry1`, `retained-retry2`.
The first run was 1,180 pass/25 fail; failures remain preserved. Corrections were diagnostic-only:
Gao/PhysioNet additional task classes were checked against the pinned loader; six ERP CORE source
TSVs have one-based `sample` but all 4,251 onsets/values match source EEG events exactly; two
Mainsah P runs need their absent Target removed from both selected labels and legacy event roles.
No source EEG/TSV bytes or product admission rules changed for these corrections. Same-head native
representatives passed 134/134 and CI completed successfully. Four existing native recovery tests
passed (CI had skipped them for missing fixtures), and two consecutive AlexMI imports passed.

The original native whole-root driver is not final GUI evidence: it sometimes stopped at backend
commit before table publication and its supervisor did not fail on failed cases. The tightened driver
binds all 1,205 expected paths independently, waits for visible table/count/filenames/current
generation and settled commands, and fails closed on missing/failed IDs. AlexMI/Gao/Weibo pilots
pass, including Weibo's existing visible field-refresh action. All 134 roots plus 19 multi-subject
default selections still need that final native pass. No UI product files have been edited.

Next bounded repair: Thielen2021 whole-root (10 recordings) exceeds the unchanged 150 s diagnostic
budget. Profiling measured Scan 17.625 s and Preview 66.281 s (profiling overhead included), with
23.408 s in `InterpretationCandidate.to_public_dict` copying full evidence via `asdict` before the
existing public projector drops it. Pass dataclass fields directly through that existing projection,
recursively preserve dataclass/tuple semantics and detach retained leaves; never traverse discarded
row evidence. Keep full private `to_dict`, source identities, counts, policy and UI unchanged. Do not
add a BrainVision header estimator despite its separately measured cost. Owners remain unchanged.
First require old-output equivalence and mutable-output isolation, plus a red no-traversal regression;
then candidate/projection/recipe/BIDS focused tests, independent diff review and the same native
Thielen/Cattan budgets. Earlier waveform/recipe runs are baseline only after source changes; final
claims require re-established exact-head evidence. UI internal-source refresh approval is still pending.
The no-traversal regression failed exactly on the old `asdict` path (1 fail/9 pass). After the
projection-order change, all 121 candidate/projection/recipe/BIDS tests pass; lint passes and the
independent actual-diff review found no blocker. Next: commit, rerun the original Thielen/Cattan
native budgets, then re-establish final recording/native/CI evidence on that exact source.

### Previous evidence and storage checkpoint

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

This checkpoint predates the approved all-retained-recordings continuation above. Its passing
representative evidence does not complete the current scope or replace the final Windows handtest.

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
