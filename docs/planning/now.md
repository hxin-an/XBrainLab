# XBrainLab Now

最後更新：`2026-09-10`

## Active

## Module-by-module quality baseline

User approved the complete modular cleanup plan and requested implementation on 2026-09-10.
Earlier PR #131 acceptance is historical; it does not approve this stage's source or merge.

### Outcome and scope

Establish a reliable, understandable baseline by deleting historical overdesign, duplicated work and
unnecessary waits. Audit all tracked production, tests, scripts, dependencies, development configuration
and docs. File/LOC/test counts are inventory, not proof of quality or completion.

Preserve visible UI behavior, Command/query/Assistant public contracts, EEG semantics, settings,
recipes and existing result reading. Behavior-preserving UI internals are explicitly authorized.
Unused Python convenience APIs may be removed after checking dynamic registration, configuration,
scripts and documentation. Preserve necessary safety, cancellation, publication and consistency.
No feature/UI redesign, architecture rewrite, model/prompt/RAG experiment, new control plane,
new environment, WSL compaction, backup deletion or unrelated local cleanup.

The user additionally confirmed large-file and code-quality assessment: inspect mixed responsibilities,
coupling, duplicated branches, typing diagnostics and test effectiveness, not only physical LOC. Record
before/after evidence for changes; splitting a file or improving a number alone is not closure.
Previously authorized withdrawal of WSL-compaction tooling and exact residual cleanup remains a
separate infrastructure task; do not restart compaction/shutdown or mix destructive cleanup into
product refactor commits. Revalidate exact targets and active use before that task executes.

### Stage integration exception

One integration branch/PR contains small independently reversible commits, reviewed by module.
The user explicitly approved accumulated stage-level diff and one final Windows manual acceptance;
this stage does not require a PR/manual merge per slice. Slice-level complexity review still applies:
record deletion candidates, owner delta, production +/-/net LOC and split any oversized coherent slice.
This exception does not weaken CI, data/native/Assistant evidence or exact-source merge approval.

Use the existing Windows environment and model/data caches. Preserve the original checkout's dirty
UI/test files and root settings. Worktree/branch/source facts come from Git, not historical paths.

### Module order and ownership

| Module | Includes | Status |
| --- | --- | --- |
| 1 Command/state spine | Admission, capabilities, confirmation, publication, owned work, shared domain ports | Responsibility review closed at 1247cf7c; native 178 passed; domain branches explicitly remain modules 2–6 |
| 2 Import/interpretation | Loaders, BIDS, labels/classes, channel/montage, metadata, recipes, related UI | Audited core reviewed; not closed: two confirmed visible defects await authorization; inventory reconciliation in progress |
| 3 Preprocess/epoch/split | Processing, copies, invalidation, preview/materialization, related UI/tools | 3A–3G bounded changes reviewed; remaining epoch dispatch migration, UI/domain audit and inventory reconciliation stay open |
| 4 Models/training | Catalog, resource preflight, settings, stop/rerun, history/checkpoints | Pending |
| 5 Evaluation/saliency/views | Read/publication, SmoothGrad/recompute, four views, stale work/render lifecycle | Pending |
| 6 Assistant/chat | Tool adapters, turns/confirmation/execution, model/RAG lifecycle and shutdown | Pending |
| 7 Shared desktop/runtime | Shell/navigation, shared components, configuration, errors/logging/start/close | Pending |
| 8 Scripts/dev/CI | Launch/setup, Poe/hooks, runners, walkthroughs/evaluators/reports and artifacts | Read-only inventory |
| 9 Cross-module tests/docs | Shared fixtures/guards, dependencies, canonical truth/navigation and coverage gaps | Pending |

Each module includes its callers, tests and related scripts. Domain UI belongs to its domain module;
shared UI belongs to module 7. Script infrastructure has a separate complete review in module 8.
Assign every tracked file to a module (or an explicit retained static/vendor asset group); count and
resolve uncovered files before final review. Generated files are not production inspection evidence.

### Per-module procedure and closure

1. Read owned implementation/tests; trace entry points, authoritative state, mutation/publication,
   async lifecycle and consumers. Record deletion/consolidation candidates and concrete retain reasons.
2. Obtain passing behavior characterization before refactors; reproduce bugs before fixing them.
   Measure only suspected redundant work/waits and their directly relevant paths.
3. Make small deletion/reuse-first changes. Do not replace wrappers with another owner or move code
   solely to reduce file size. Update this plan before each new coherent slice.
4. Improve behavior evidence before removing weak/obsolete tests. Important side effects need a
   lower-mock internal workflow; keep valid external/native isolation. Check selected high-risk tests
   with a bounded intentional behavior break. Preserve known regression cases.
5. An independent non-author reviewer examines actual source/diff/callers/evidence and audit coverage;
   the main agent inspects the resulting diff/evidence. Fix blocking in-scope findings and re-review.

Closure requires complete file responsibility/disposition, resolved confirmed in-scope redundancy,
credible normal/failure/cancel behavior protection and explicit independent review approval. Unknown
in-scope items are not done. Public-contract/visible-behavior decisions require user input; continue
independent authorized work. Later shared-boundary edits reopen only affected module evidence.

### Validation and final endpoint

Focused checks per slice; widen early for shared state/data/publication/lifecycle risk. Preserve the
existing 85% line coverage gate and branch evidence without shrinking the denominator. Select commands
from the existing validation contract/runner; do not create another test-selection or gate framework.

After all modules close, independently review cross-module integration and inventory completeness.
Freeze a final exact commit and require applicable same-head CI, source-diverse data, platform/UI and
affected real-model Assistant evidence. Reuse equivalent successful CI; fill only missing local evidence.
Keep the Assistant's accepted bounded limitations; this stage is not Stable promotion.

Required scenarios include failed import retaining prior data, old recipe/result reading, processing
and split semantics, training stop/rerun, saliency completion/cancel/SmoothGrad/recompute/selector changes,
stale work rejected, Assistant confirmation/failure recovery and runtime shutdown/resource release.
Scripts additionally need honest exit/output outcomes, rerun behavior and safe cleanup boundaries.

Only after all closure conditions pass, deliver one Windows native GUI with its PowerShell live log
(no separate Live Log window), exact source and restart command, consolidated manual checklist, measured
changes and limitations. Confirm responsiveness, then hand control to the user. A slice, commit,
compaction or pending CI is not a stopping condition. Genuine authority/resource blockers are reported.
Manual findings receive affected/adjacent revalidation and an updated delta checklist, not automatic
whole-suite human retesting. Merge only after explicit final-source acceptance and permission.

### Current slice / next step

Git recovery: product branch `cleanup/module-quality`, HEAD `96366558`, 71 commits after baseline
`4770b049`. Original checkout UI/test/settings dirt remains protected. Recheck Git after reboot;
old session IDs and plan text do not prove a process is running. No manual candidate or merge request.

**Current work — module3 cleanup; module2 visible decisions remain open.**

Completed2AD–2AG and8C–8E are indexed below and fully traceable in Git. For source-bound Windows
capture tests only, use process-local GIT_DIR/GIT_WORK_TREE pointing to the actual Windows paths:
Windows Git cannot follow the WSL-absolute worktree pointer. Keep the existing identity guard;
do not edit .git pointers, shared environments or substitute a synthetic source digest.

**Module2 independent closure review.** Reviewer did not approve module closure: two confirmed
visible defects below remain unresolved, not merely documentation or LOC concerns. The audited
interior has one command spine, separate backend mutation/publication and UI draft/presentation;
large file size alone did not establish a competing owner. Three stale tracker pending rows were
actually inspected (montage capability80 +owner170, empty loader test package marker needed for
relative imports, DrawRegion148 +owner75–250). Reconcile these; DrawRegion belongs to module3.
Main fully read wizard runtime145 (real Scan/Preview/Validate +Qt draft handoff, intentionally invalid
FIF not actual EEG Apply). Main1–440 +independent441–1788 fully cover real-fixture wizard acceptance:
retain all five-step, exact fresh review, no-publication, cancellation/drain/retry and BIDS recovery
contracts. Optional fixtures were not run here; final required-source gate still applies.
Continue authorized module3 while awaiting visible decisions; do not markmodule2closed or handoff.

**Completed 3A — split illustration math cleanup and stronger tests.** Main/independent read
DrawRegion75–250, actual update_preview/testing/validation callers and direct148; change_to and
decrease_w_tail have no production/dynamic/script/doc caller, only two exclusive tests. Remove
only these unused methods and exclusive tests from data_splitting_dialog.py/direct test after
characterization. Strengthen mask from merely changed-array to exact masked/unmasked canvases and
unchanged source, and parameterize real fractional bounds in set_to. Then retire three duplicate
DrawRegion checks in dialogs/test_data_splitting.py only after their exact behavior is covered by
the stronger direct tests; preserve actual PreviewCanvas pixel and dialog strategy/rendering cases.
No visible/UI/EEG/split policy change, no owner/abstraction; source target is data_splitting_dialog.py,
NOT protected original-checkout data_splitting_preview_dialog.py. Main owns plan/native runs and
independent review; assigned worker may own these three files after baseline. Use22 original
direct/sibling/canvas/grid/strategy cases; migrated characterization before production deletion,
same retained cases afterward, Ruff and bounded in-memory wrong-mask fault. One reversible commit
then continue module3 full preprocess/epoch/split responsibilities, not final acceptance.
Original22 nativecases passed1.35s; worker now strengthens tests first, without deleting production
or obsolete cases until main characterization passes. Keep original checkout's split/settings dirt.
Stronger full-canvas fractional/mask characterization23passed1.36s before production edits. Worker
now removes two unused methods/twoexclusive cases/three replaced sibling cases; retainedexpected18.
Retained18passed1.37s (23strengthened minus2exclusive and3duplicates). Main nonauthor actualdiff
review approved source-23/tests+50/-66/net-16; three-file Ruff/check/format passed. In-memory wrong-
overlap fault failed at all four changed cells (3instead of2),1failed0.13s; no faulty source saved.
Independent full Step1source1037/direct726/sharedfixture81 review retains detached-context/strategy
projection, illustrative drawing and draft handoff. Actual Step2 materialization remains separate.

**Completed 3B — unused MAT Export convenience.** Independent full11-preprocessor1541-line source/
1554-line direct test audit and main Export55/exporttest71/package26/caller read confirm Export is
only re-exported by preprocessor.__init__ and consumed by its own tests. No current UI, Command,
Assistant, script/config/doc or dynamic resolver uses it. Remove export.py, package import/__all__
entry, exclusive directtest file and combined test_preprocess export case/unusedimports only.
Do not add read-back tests for a retired-only behavior. Preserve every supported transformation,
EEG/event/copy/cancel semantics and actual result/recipe reading; zero new owner or compatibility.
Main owns fourfiles and existing-environment runs. Baseline fullpreprocessor direct suite once
because package export membership is shared; repeat retained suite afterward, Ruff and independent
actual-diff review then separatecommit. Review actual parametrized removedcase count, not assumed4.
No actual export files/user weights/data are removed, only Git-tracked dead source/tests.
Native preprocessor baseline78passed3.04s; retained73passed3.02s, exactlyfive obsolete Export cases
removed (three direct plus raw/epoch parametrizations). Same17 upstream MNE/NumPy/expected short-
signal/drop warnings before/after. Source-57, tests-98; independent actualdiff review/Ruff/check/format
passed. No actual export artifacts were deleted; removed source is recoverable from Git.

**Module3 shared owner audit, not yet an implementation slice.** Independently fully read
preprocess_service996/preparation120/render536/state524 and directservice985/state526/render240.
Prepared application path owns detached work, source/publication/training identity, short mutation
and rollback. Render's copied immutable buffers/generation guard is a distinct live boundary.
Old direct handlers duplicate supported operations but SET_MONTAGE is a live generic confirmation
branch (actual montage mutation is ApplyMontageCommand); invalid-operation parsing also matters.
Do not delete whole handler/map from text-search alone. Map every legacy epoch resource/boundary/
receipt/handoff assertion to actual prepared/ApplicationService evidence before declaring3C.

**Completed 3C — retire unreachable ordinary preprocess dispatch, not epoch safety.** Main and
independent execute trace confirms every valid PreprocessCommand except SET_MONTAGE is intercepted
by _uses_prepared_preprocess before generic dispatch. Invalid operation parses and SET_MONTAGE's
existing confirmation error must remain. After real ApplicationService characterization for bandpass/
notch/resample/normalization/reference/channel aliases/standard pipeline, remove those unreachable
handle_preprocess branches, exclusive _handle_standard_preprocess/_normalization_target_counts
chain and three obsolete fake-controller operation tests plus exclusively used fake methods/classes.
Do not delete handle_create_epoch or its safety tests: exact RAM-before-copy, boundary ratio/message,
duration receipt scope, handoff aliases/corrupt-state assertions lack equivalent real route evidence.
They remain an explicit next migration obligation, not proof that the prepared epoch path is covered.
No Command/UI/message/diagnostic/owner change; no compatibility layer. Main owns source/validation,
assigned worker may author test-only real operation characterization first in existing service test.
Use real Study/Raw/MNE, exact messages and actual transformed/deferred state with original data
unchanged; service.close in finally. No fake two-phase harness. Baseline new characterization before
production deletion, then retained direct service tests +actual ApplicationService cancel/stale/commit
and SET_MONTAGE/invalid-operation neighbors; Ruff and independent actualdiff review, separatecommit.
Legacy worker now authors only real-operation tests; main retains source ownership. No production
change yet. First characterization36passed/2failed4.15s: both channel-alias cases incorrectly assumed
loaded-data identity survives channel selection. Existing channel commit intentionally publishes a
selected copy as loaded and preprocessed data; correct this fixture assertion after tracing that path,
retain original object nonmutation, and rerun before deletion. This is not a product failure.
Main fully read epoch_handoff_blockers59, epoch_context1247 and direct759. Retain duration evidence,
half-open sample math, source/handoff matching and scoped confirmation. Direct lightweight data ports
cover real context policy, not actual epoch materialization; that migration obligation remains3Cnext.
Step2 preview source1501 +applicationDTO/publisher936 and direct backend745/boundary36/UI376/UI828/
layout397/Step1dialogs726/support81 full independent read retains generation/cancellation/claim/receipt,
state restoration, real Thread/Event close and geometry ownership. The previously suspected duplicate
evidence_reference assignment is absent in current source; do not claim it as a deletion.

**Completed bounded 3D — split preview handoff protection and unused no-op.** Independently confirmed
DataSplitterHolder.to_thread is empty, absent from the base contract and has no actual caller.
Add focused existing-file tests first for a typed receipt invalidated by changed controls and a stale
generation unable to replace current preview rows/status/receipt. Use actual dialog typed publication
and existing fixtures, no parallel authority or new harness. Baseline direct UI/split-layout cases;
after passing characterization remove only the no-op (no thread policy/layout/copy changes), rerun
the relevant cases and bounded in-memory guard faults, Ruff and independent actualdiff review.
Main owns source; independent worker may author only tests/unit/ui/test_data_splitting.py or the
existing direct dataset/test_data_splitting.py as appropriate. UI internal deletion already authorized;
no visible change/new owner. Commit separately, then continue the remaining module3 epoch/split audit.
3D baseline24passed/3failed1.78s: new stale case assumed running while actual debounce enters idle;
corrected to existing idle/render semantics, direct16passed1.29s before source deletion. Two existing
compact-layout cases at752/760px fail with horizontal ranges30/22px on Windows. This is unrelated to
the no-op and remains an explicit phase UI issue: inspect header/style widths and native screenshot
before requesting visible-change approval; do not weaken the layout assertions or claim green.
Main removes only unused to_thread after the passing direct baseline. Reviewer strengthened receipt
test to retain old cached successful evidence after control edit, so it tests fingerprint rejection
and not merely schedule_preview clearing the receipt. Retained16passed1.27s; removing both guards
only in memory causes exactly their two tests to fail0.21s. Source-3/tests+87, Ruff passed.
Native QPA windows measurement supersedes the suspected visible defect: both compact cases pass0.31s;
752px viewport/header388px,760px396px, horizontal range0 at both, Microsoft JhengHei UI9pt/DPR1.
Main inspected the752px screenshot: no clipped headers/footer/overflow. Earlier failure is an
offscreen font/platform limitation, not established product layout defect. Full native27 ran:
26passed/1failed2.08s, remaining client-center assertion differs31px from screen center. Preserve this
separate native placement investigation in shared-runtime module7; no-op deletion does not cause it.
Do not claim the whole layout suite green or final module closure. Retain all assertions; no font/
layout workaround. Main/nonauthor actualtest review and independent source-deletion review approved3D.

3C corrected real characterization38passed4.07s before deletion; admission/cancel/stale/rollback
neighbors44passed/1failed7.54s only because invalid-operation test guessed a custom message rather
than existing Enum ValueError. Corrected exact enum-message/no-mutation pair2passed3.68s before source
deletion. Retained full selection42passed7.16s after deleting exactlythree obsolete fake-operation
cases; all epoch safety cases remain. Main/independent actualdiff review and four-file Ruff passed.
Final formatted3C source-76/tests+233/-196/net+37; fewer duplicate production paths, stronger real
side-effect evidence rather than a claim of test LOC reduction. Epoch legacy migration remains open.

**Completed bounded 3E — real prepared epoch boundary admission characterization.** Reuse existing
_write_reviewed_epoch_fixture/_apply_reviewed_epoch_fixture in test_application_service.py; permit
explicit synthetic event coordinates in the existing writer while preserving its default recordings.
Add actual Scan/Preview/Validate/Apply/CreateEpoch cases at1% and above1% boundary exclusion, with
exact diagnostic counts/message, unchanged source arrays/identity and real resulting epoch counts or
atomic rejection. No mocked boundary summary, generator or command result; isolate only resource RAM
reading if required for determinism. This is test-only first; keep all old epoch cases until main
baseline and evidence mapping pass. Then retire only the two replaced legacy boundary cases if their
multirecord/count semantics have equivalent real evidence; do not delete remaining legacy handler yet.
Main owns plan/review/native evidence; legacy worker owns only existing application test file.
Run new cases plus existing reviewed-epoch lifecycle and all-dropped safety neighbors; bounded wrong
threshold fault, Ruff and independent actualdiff review. Receipt/RAM/aliases migration remains next;
no epoch/UI/data policy change, new fixture platform or production owner. Continue module3 afterward.
Final real cases include100/1 and99/1 boundary events plus300/2 across three recordings; exact
diagnostics, actual epochs/lock and unchanged loaded/source data are asserted. Retired only two
legacy boundary-summary mock cases. In-memory threshold0.02 fault makes above1% rejection fail;
no faulty source persisted. Initial fixture mistakes (extra EEG in message and raw rather than
normalized label IDs in the separate3G case) were corrected against actual behavior, not product.
Recovered final3E/3G/preprocess selection291passed10.14s with601 upstream/expected MNE warnings;
prior terminal output was lost across context recovery, so it was rerun rather than assumed green.
Independent actualdiff approved; nine changed source/test files pass Ruff/check/format. 3E tests
+124/-81/net+43, no production change. Remaining RAM/receipt/handoff cases are explicitly retained.

**Completed bounded 3F — actual Preprocess plotter contract, not obsolete async compatibility.** Main fully
read plotter204/direct252, PreviewWidget1135/directpreview127, panel304/history124/dataquery83/direct159.
All three live plotter constructors receive PreviewWidget; Welch calculation/application are synchronous
inside the existing reentrancy guard. Local plot-generation state/check has only an artificial direct
test; it is not the live backend publication/stale-work guard. First add real PreviewWidget/PyQtGraph
curve characterization for time/PSD with/without original signals and exact distinct-rate Welch output.
Keep old tests until passing baseline; then remove only local synchronous generation and duck-typed
widget fallbacks, replacing calls with the actual typed widget methods. Retain nonreentrancy, deferred
PSD until selected, backend generation guards and all native detach/resume/finalize lifecycle.
Also replace PreviewWidget's test-only locked_status_label alias with its same existing QLabel owner,
migrating assertions before deletion. No visible/state/plot math change, new owner or thread.
Main owns these files; select direct plotter/preview/presentation and existing native lifecycle stress
evidence, bounded wrong-PSD fault, Ruff and independent nonauthor review before separatecommit.
New four real time/PSD/current/overlay cases plus original direct preview/presentation30passed3.37s
before production edits. Alias assertions now target the identical existing locked_state_detail;
run that migrated baseline before deleting the alias. Native lifecycle source65 fully read: subprocess
uses actual checked-in GDF, eight destroy/recreate and cancelled-close resume cycles with bounded timeout.
Migrated QLabel-owner assertions7passed0.43s before alias deletion. Initial production patch was
rejected by auto-review as possibly removing required asynchronous guards; no source changes applied.
Independent reviewer then traced ALL three real plotter callers: panel75/update_plot_only, capture399,
native stress194/197/249; _apply_psd_result has only inline caller180 after synchronous Welch, no worker,
queued callback, executor or event processing. Existing _is_plotting covers synchronous Qt reentry.
Backend publication-ledger and saliency worker generations remain untouched. This concrete evidence
supports resubmitting only the declared synchronous-state deletion, not bypassing review or weakening
any live asynchronous boundary. If rejected again, retain it and report the authority blocker.
The evidence-backed resubmission was accepted; actual source deletion then applied. Retained29 direct
plus existing real-GDF native lifecycle1 passed7.33s, including eight detach/resume/finalize cycles.
Wrong PSD-frequency fault is caught by actual curve data (250/251bins mismatch),1failed0.19s.
Before retiring four now-redundant mock happy-path cases (time data/events, frequency sampling,
Welch-called, no-data clear), strengthen the new real-widget cases with exact time view range and
repeat-render-to-no-data clearing of all four native curves and marker visibility; baseline those
assertions first. Keep actual reentrant/failure/deferral seam tests and raw-offset data regression.
Strengthened14plottercases passed1.96s before four duplicate mock cases were removed. Recovered
retained direct25passed2.60s; existing native8cycle stress above remains applicable. Independent
review of the FINAL applied source/tests approved synchronous caller coverage, actual widget API,
alias migration and replacement protection. Production+15/-44/net-29; tests+84/-85/net-1.

**Completed bounded 3G — retire legacy Epochs picker chain after real allocator characterization.** Independent
full dataset7-source4071-line/direct7-test4037-line audit (verify counts from wc, not inventory) traces
pick_subject/session/trial and their exclusive helpers to tests only; current DatasetGenerator owns all
materialization. Characterize successful Generator Manual Trial index selection expanding the entire
overlap group, preserving train classes and passing actual split audit before deleting old picker tests.
Existing old class-incomplete audit case should use explicit masks to test the audit, not obsolete pickers.
Do not recreate old expanded_indices evidence: its only writers are legacy pickers; actual Generator
never produces it and no current canonical promise requires it. Retain artifact builder/writer/schema/
reader and rollback fields in this slice; any orphan evidence chain needs separate contract review.
Worker may author test-only changes in existing test_atomic_trial_groups.py first. Passing real manual
baseline plus actual generator/atomic/epoch direct tests precede the bounded picker deletion. Main owns
source until migration map/deletion count reviewed; zero new owner, no allocation/data/visible policy
change. Keep pick_subject_mask_by_idx (live Dataset caller), provenance/atomic group construction and
channel/order/copy semantics. Independent review, retained tests/Ruff and rollback-small commit follow.
Corrected real manual allocator plus explicit class-incomplete audit cases2passed3.60s before source
deletion. Production-538 removes only the obsolete picker/helper/enum chain; current Generator,
live subject mask, provenance, artifact schema/readers and rollback state remain. Main read the full
deletion diff; independent nonauthor source/test review approved. Final retained291-case combined
selection and Ruff pass as recorded3E; this is not all of module3 or final-source certification.
Removed case count corrected by executing historical/current parametrization definitions in memory:
307 (301 old Epochs picker/helper parametrizations and six atomic-picker cases). Earlier static309
overcounted the generated trial list: actual108 entries times2 is216, not218. Baseline563 already
included the new real manual case; retained256 plus35 current preprocess-service cases equals291.
No historical source or product file was modified by this counting probe. Test count reduction follows deletion
of the unused allocator, not reduced protection for the actual Generator.

**Completed bounded 3H — real epoch RAM-before-copy admission.** Existing UI runtime evidence has a fake
dialog seam; old direct service case uses a fake materializing controller. Add one direct actual
ApplicationService case using the existing real FIF import helpers. After confirmed Apply, isolate
only the resource check to deny admission and observe the processor's actual deepcopy allocation seam.
Assert exact resource failure diagnostics, unchanged loaded/preprocessed objects and data, no epoch,
no lock and no copying. Keep existing UI delivery test. Passing new characterization allows removal
of only the replaced legacy RAM case and its exclusive fixture members, not receipt/alias/handoff
cases. No production behavior/owner change; main owns plan/native runs/review, legacy worker owns
test_application_service.py initially. Focused new case plus epoch materialization safety/UI resource
neighbors, bounded omitted-resource-check fault, Ruff and independent actualdiff review. Then
continue scoped receipt/context/alias migration, remaining UI/domain audits and modules4–9.
Initial new/legacy/adjacent38passed8.81s; retained37passed8.72s after one obsolete case was removed.
The omitted-resource-check fault correctly failed because epochs were created, but also revealed
Raw.copy was NOT the live preparation allocation path (PreprocessBase uses deepcopy). Main traced
the actual TimeEpoch preparation and corrected the new witness to that exact deepcopy seam; rerun
this strengthened case and its fault before claiming ordering evidence or committing3H.
Corrected live-deepcopy witness1passed7.34s; omitted admission guard now fails at the real allocation
seam with INTERNAL instead of PRECONDITION,1failed7.19s. No faulty source persisted. Main and
independent final-diff review approved; Ruff passed. Tests+64/-71/net-7, no production change.

**Completed bounded 3I — normalize split commands once.** Main fully read generation service1146/direct876/
contract245 and actual deferred command callers. `config_from_payload` already validates before
returning, so handle_save's immediate repeat is unnecessary. `_build_data_splitting_config` has one
production caller only after split_config is None; its structured-payload branch serves only a private
test. `_enum_from_value.default` has no caller. First protect default None versus explicit empty
payload through the actual ApplicationService fixture in deferred split tests; preserve exact saved
specification and failed-empty/no-mutation behavior. Then remove only duplicated validation, the
unreachable branch and unused keyword; migrate the exclusive private test after passing baseline.
Keep structured/headless public Command fields, all validation policies/messages, preview receipt,
digest, allocation, publication, cache and training rollback. Zero new owner, production net negative.
Main owns source/test changes. Focused contract/generation/deferred save+preview/preparation cases
before/after, Ruff and independent actualdiff review; separate reversible commit then continue audits.
Baseline47passed/1new fixture message mismatch7.95s: public specification parser reports
`train_type is required`, not the deeper config parser's prefixed message. Corrected new case1passed
5.80s before source deletion; retained47passed7.97s after one replaced private case was removed.
Independent final-diff review approved; an alleged third enum argument was a reviewer misread,
retracted after exact source reread without changing the caller. Ruff passed. Production+1/-11/net-10;
tests+48/-18/net+30. Actual speculative allocation/rollback and public configuration rules unchanged.
Main1–1080 and independent1081–1833 now fully cover deferred-split tests. Retain distinct start,
restart, append, cleanup, rollback-failure, receipt/token and bounded-audit failure windows; targeted
failure mocks are necessary seams. Missing close calls in synchronous/mocked-start fixtures are a
convention risk, not a measured worker leak or permission to add broad lifecycle machinery.

**Completed bounded 3J — preprocessing setting dialogs reuse their existing geometry owner.** Full main/
independent reads confirm common.fit_preprocess_dialog_to_content only forwards six calls in four
BaseDialog subclasses. Replace calls with the same inherited fit_to_content keyword, remove wrapper
and unused import; remove RereferenceDialog avg_check/toggle_avg compatibility members with no
source/test/script/doc/dynamic consumer. Exactly five production files, zero new owner and no layout,
wording, interaction, sizing or Command change. Existing UI-internal authorization applies.
Use actual setting-dialog content sizing, filter center/keyboard/Nyquist/mode checks, reference
radio/selection acceptance and actual rereference command route before/after; no new mock tests.
Main owns plan/validation and nonauthor final-diff review; worker may implement after passing baseline.
Ruff and separate reversible commit; remaining sidebar argument cleanup and epoch receipt migration
remain separately declared work, not implicit additions to3J.
Same real Windows QPA windows24cases pass4.94s before/5.09s after; five-file Ruff/check/format and
main nonauthor actualdiff review passed. Exactly six inherited calls, same keyword/geometry path;
production+6/-28/net-22, no test changes or visible behavior change.

**Completed bounded 3K — unused dataset metadata conveniences and direct test quality.** Main/independent
full dataset/data_splitter source and tests plus whole-tree callers identify get_ori_name, three
enum repr conveniences and get_raw_value as test-only. Remove these five methods/exclusive
assertions after baseline, retaining actual get_name/get_value/get_split_unit/get_splitter_option,
parser policy, mask copy and resource revision. Restore a missing assertion on the empty remaining
mask in test_dataset_set_test_mask before deletion; remove one exactly duplicated intersection
param only after baseline. Two production/two existing test files, zero new owner/semantic change.
Use direct splitter/dataset/generator cases before and same retained cases after, exact removed
count, Ruff and independent actualdiff review; a separate reversible commit, then continue module3.
Stronger baseline113passed4.37s; retained112passed4.35s, exactly one duplicate parametrization
removed. Production-49/tests+1/-12/net-11; parser/name/mask consumers unchanged. Independent actual
diff and main review approved; four-file Ruff passed.

**Completed bounded 3L — real BIDS epoch receipt scope/context.** Extend the existing integration duration
fixture and genuine Scan/Preview/Validate/Apply workflow. Cover changed t_min/t_max/event IDs with
old receipt, refreshed requirement and no mutation; cover changed duration through actual reimport,
keeping command scope constant so context, not a new proposed window, causes invalidation. Compare
same-duration reimport where appropriate to rule out a mere fresh-service token failure. Keep actual
basic challenge/accepted materialization, current raw identity/data/lock/epoch state and close owned
services in finally. Worker owns only test_bids_epoch_duration_handoff.py initially. Main baseline
before retiring only corresponding legacy receipt cases; no production/receipt/EEG/visible changes.
Use this existing BIDS file plus remaining direct service cases, bounded stale-receipt admission fault,
Ruff and nonauthor actualdiff review. Actual defaults/raw IDs already have real command protection;
display-alias materialization and semantic unavailable-context remain explicit migration gaps.
Legacy _get_state callback exceptions are not a second public read contract: real prepared epoch
uses captured plan.application.state and validated_epoch_handoff, while ApplicationService owns
generic read-failure admission. Remove obsolete callback-only tests with that dead path, not recreate
its error semantics. Current public state-read-failure test remains required evidence.
Baseline45passed6.66s; after removing five exclusive legacy receipt cases/helper, retained40passed
6.61s (352 upstream MNE deprecation warnings). In-memory acceptance of any nonempty receipt makes
all four stale scope/context cases fail4.62s; no faulty source persisted. Same-context reimport
control passes, distinguishing changed context from fresh-service identity. Main nonauthor actual
diff review approved; production unchanged, tests+206/-139/net+67. Native runner uses prlimit --core=0
and bounded timeout; no new environment or dependency.

**Completed bounded 3M — dataset dialog lazy exports match supported classes.** Full package init38 and
root package tests39 read: __all__ lists retired ImportLabelDialog absent from its lazy export map;
whole-tree source/test/script/doc references show no consumer or replacement class. Add one dynamic
export-resolution regression to existing test_init.py that imports every declared class and checks
the four supported names. Observe the actual missing-attribute failure, then reuse list(_EXPORT_MODULES)
as the export list, preserving all four lazy module targets and no eager import. One production/one
test file, no new owner/UI behavior/public Command change. Focused package tests plus relevant lazy
panel constructor protection, Ruff and independent actualdiff review; separate reversible commit.
Observed exact missing ImportLabelDialog red1failed/11passed6.81s; after map-owned exports all12passed
6.71s. Independent actualdiff review approved; production+1/-7/net-6, tests+13, lazy targets unchanged.

**Completed bounded 3N — preprocess Sidebar removes an ignored error prefix.** Independent source899 and
direct TestPreprocessSidebar125–861/error350–470 trace confirms failure_prefix is not read. Remove
that argument, five production literal calls and two private error-test call arguments only. Preserve
actual mapped messages/diagnostics, expected generation, async-only execution, cancellation/busy and
error UI. Main owns scope/native baseline; assigned worker may author Sidebar and the two direct
test edits after passing baseline. Use real rereference route, async scheduling failure and selected
stale/epoch/worker exception cases; same after, Ruff and main nonauthor diff review. No visible change.
Same28passed7.27s before/7.35s after. Main nonauthor actualdiff review confirms mapped result/error,
generation and scheduling paths unchanged; production-6/tests-2, zero new owner.

**Declared 3O — actual reviewed display aliases before retiring legacy epoch handler.** Add one
parametrized real FIF Scan/Preview/Validate/Apply/CreateEpoch characterization in existing application
tests: raw769/770 reviewed as Left hand/Right hand must materialize correct epoch labels/count;
unknown list/dict targets must return the current precondition and preserve actual data identity,
samples, lock and absent epoch. Worker owns this one test file, no production/legacy deletions yet.
Use focused new nodes and existing prepared epoch/default/raw-ID evidence; inspect real event labels,
Ruff and nonauthor review. No new helper unless existing fixture reuse needs bounded optional fields.
Semantic unavailable codes already have exact owner tests in test_epoch_context; callback-only error
tests are not a second public API. After this evidence, separately declare dead handler retirement
and audit every coupled constructor/dynamic caller before deletion. No visible or EEG semantic change.

**Declared 3Q — real preview debounce signal instead of rewired mocks.** Full55-line performance test
disconnects the production timer and substitutes a mocked plotter, so it cannot detect a broken
timer-to-request connection; it also manually calls private slots instead of changing controls.
Main replaces these two cases with real PreviewWidget slider/spin value changes, reciprocal values,
zero immediate requests and exactly one eventual production request; retain single-shot and shutdown
silence, with owned native teardown. No production changes or speed claims. First run existing two
cases, add stronger parametrized control tests, run before removing old cases, and use an in-memory
omitted signal forwarding fault. Focused native tests/Ruff and independent actualdiff review; keep
plot rendering coverage in the existing real-curve tests rather than duplicating it here.
Old2passed2.19s; stronger+old4passed2.33s; retained2+15 direct preview/presentation cases17passed0.83s.
In-memory omitted forwarding causes both new cases to time out2.16s; no faulty source persisted.
Evidence establishes real wiring/coalescing/control synchronization/shutdown, not precise timer
restart latency. Independent review accepts the stronger boundary; exact restart timing remains an
unclaimed property, not a reason to retain old tests that never checked it either.

**Declared 3P — retire unused synchronous epoch handler after real migration.** 3O and its real
boundary/RAM/default/semantic neighbors40passed8.79s; actual epoch label sequence Left/Right/Left and
class counts2/1 verified. Main nonauthor review corrected helper defaults before the passing run.
Independent dispatch audit confirms every CreateEpochCommand uses two-phase preparation/commit;
no dynamic/script/config caller of handle_create_epoch. Remove only that duplicate method, its
get_state constructor callback/field, _epoch_handoff callback wrapper and old normalization-count
forwarder; remove the one matching constructor keyword in ApplicationService. Retain captured-state
validation, actual prepared policies/receipt/RAM/alias/boundary/normalization, transaction/cancel and
SET_MONTAGE confirmation. Remove exclusive fake-handler tests/classes, retaining real prepared cases
and the SET_MONTAGE safety assertion with real ApplicationService ownership. Worker owns these two
production files and test_preprocess_service.py, not the 3O characterization file. Zero new owner;
estimated production-125, below slice complexity ceiling. Native retained3O set plus actual
cancel/stale/public-read failure/BIDS/epoch-context/state-service neighbors, Ruff and main nonauthor
review before separate commit. Concrete state-service apply_epoching/Protocol follow-up separately
declared after full callers/cancellation mapping, not bundled silently.

**Module3 unresolved artifact decision.** Independent full validator123/direct45/schema134/split_audit1085
and thesis protocol285–375 audit found artifact writers have no product producer, but the documented
CLI/schema remain a public thesis evidence entry. Validator only checks reported audit and cross-split
overlap, not the full claimed schema/provenance. User asked asynchronously to retire the unused entry
or retain-and-align its contract. No deletion, acceptance-strengthening or scientific claim until choice.
Unused build_training_ready_state test helper is separately removable; actual saved split/receipt seam
helpers retain live integration callers. Continue independent cleanup; module3 not closed.

**Module4 bounded read-only audit (not closure or implementation permission).** Independent full
model_catalog892/braindecode_catalog408/catalog_contract20/model_holder117/input_contract201/
option909/training_service687/model_base.__init__7/training.__init__23 =3264source lines, plus
catalog662/model_holder114/option450direct tests. Resource guard only1290–1925,2255–2341 and
training_runtime1–190,280–355 were read; full resource/training closure stays pending. Retain static
catalog browsing (no provider import), stable identity/provider admission, numeric/device/class-weight
validation, conditional model context and single configure/build/preflight/receipt owner. Actual
preflight differs intentionally from advisory preview. Catalog command-name helper/input aliases and
optimizer repr duplicate have no consumers; TestOnlyOption and its export are used only by exclusive
tests, while actual manager accepts base TrainingOption. Declare separate baseline slices before
removing these. Manager option contract310–456/direct346–429 read only; not whole-manager audit.

Completed2X–2AC are indexed below; their full scope/evidence remains in Git history.
2AC found an existing shared-environment source hazard: Windows .pth adds the original checkout
to sys.path, making scripts.dev a two-checkout namespace. For subsequent native validation, remove
only that exact oldroot from the process search path before imports, then call unchanged
assert_active_checkout_import(Path.cwd()). Do not edit the environment/.pth or weaken the gate.
The first2AC run had two expected root failures plus this separate origin failure; isolated rerun
had only two expected failures, then allsix passed after the resolver fix. No real fixture ran.


- Main fully read load_labels_step462 and wizard preview4850; independent reviewer fully read
  label_placement_step2179 and coupled caller/test ranges. Independent workers fully read all7,359
  original direct preview test lines in two contiguous halves; real Qt controls/signals/serialized
  choices are useful UI evidence, not actual backend workflow evidence.
  ReviewImportStep1556 and InternalEventStep879 full independent audits are complete. No whole-family
  closure yet; confirmed remaining candidates and UI decision items still need disposition.
- Independent coordinator audit fully read recipe reload431/payload126/ActionCoordinator2400 and
  all4660 lines of direct async-flow tests across explicit non-overlapping ranges. Retain
  generation-bound apply, modal cleanup, live Cancel, exact
  warning-receipt retry, real QThread heartbeat/cleanup and shared operation presenter ownership.
- Independent integration audit completed external-label preview71, semantic render539/safety365,
  BIDS epoch duration414 and shared support55. Retain real file/recipe/atomicity evidence; render tests
  synthesize training records and do not prove actual training. Several standalone ApplicationService
  fixtures lack finally-close; no global autouse service close exists. This is an advisory hygiene
  candidate, not a demonstrated leak or permission to rewrite these fixtures during 2X.
- Remaining UI family source fullreads: subject chooser241/loading302/normalizer28, smart parser1035/
  channel chooser183/source chooser298, event editor644; direct tests237/63/407/109/125/431 retained.
  Actual BIDS editor157 integration proves real file -> Qt choices -> backend recheck -> confirmed Apply.
  Actions678/panel991/sidebar860 source read; import/review/recipe facets reviewed, other domain tests
  remain partial: panel450–620, sidebar1–75/514–644/945–963, minimal51. Preserve live public façade.
- Main fully read receipt authority153 (distinct from deleted label receipt), real receipt integration99,
  event-value workflow290, metadata111, optional BIDS montage130/public480/multisubject416/
  responsiveness165, Assistant exact-review cancellation130. Retain one-shot/semantic/atomic paths;
  Assistant cancellation seeds pending handoff directly and does not close actual model-attempt gap.
  External-label real Qt/GDF/MAT workflow934 is fully reviewed, including async remove/re-add andrecipe.
- Coverage routing found module2 consumers hidden by initial keyword mapping: Data Import capture/
  replay/report scripts and their tests and wizard harness617 still require body audits; module8
  infrastructure ownership does not make them out ofscope. Main fully read shared DataManager244/
  direct206: retain copy-on-preprocess, channel-undo deep backup, force-clean guards and invalidation;
  MagicMock dataset fixtures do not prove actual training transitions (module3/4 remain open).
- Independent full audits: wizard harness617 uses real Study/Qt/application runtime, visible modal
  controls and terminal fail/stop paths; retain. Format matrix2953/direct639/UI integration248
  retain real commands, fixed requirements, strict failure/artifact exit and honest generated-vs-public
  claim boundaries. Dataset matrix781/direct453 retains fixed denominator/diversity and lifecycle
  checks as a renderer, not a new command owner. Teacher1259/unit430/integration197 retains actual
  command/epoch/digest contracts, sidecar nonpromotion and explicit best-effort raw/service cleanup.
  Replay1329/direct572 retains live command/widget capture, geometry/artifact/identity guards and
  explicit noncanonical claim boundary. Its persistent-visible close timeout lacks a direct test;
  declare that focused evidence improvement separately before authoring. Script cleanup
  findings do not authorize shrinking existing evidence inventory or relaxing fail-closed outcomes.
- Confirmed backend candidates: two definition-only tabular multiplier aliases; CommandService
  pure pending-receipt/scope forwarders and raw-presence double-copy convenience. The preflight
  path-set method has two actual consumers and transforms/validates diagnostics; retain it rather
  than treating it as a one-call alias. Declare exact coherent scope/baseline before further edits.
  Actual memory multipliers/maps, preflight policy, receipts and candidate scope must remain.
- Coordinator payload wrappers and wizard source/state copies remain candidates, not approved changes.
  Trace dynamic bindings and real widget lifecycle before removal. Do not move large classes merely
  to improve file-size numbers or introduce another UI/backend owner.

**Pending visible-state decision — interval onset preview.** Placement source972/direct429 and
downstream candidate/event-code/interval tests were read. A real TSV with two labels, one nonnumeric
onset and two numeric durations currently overwrites time-field needs_review with ready; atomic apply
then rejects the nonnumeric onset without mutation. The matching-count interval and event-code
ready/repeated/conflict cases exist, but partial-onset preview evidence is missing. A visible-state
correction needs user approval, requested asynchronously; no reply yet. Do not silently change
readiness/UI behavior. Continue all independent authorized cleanup while awaiting that decision.

**Pending visible-UI decision — floating remap confirmation.** Main traced parentless confirmation_label
construction and its setVisible call. A read-only in-memory pytest profile of the actual recipe remap
widget test passed and observed parentWidget=None, isWindow=True, isVisible=True with replacement-file
confirmation text. This confirms an extra top-level Qt label, not Windows window-manager acceptance.
User approval requested asynchronously to contain the text in the wizard; no source/UI change yet.
Keep this separate from dead-helper removal and continue independent authorized cleanup.

**Recently closed source/test audits — retain reasons.**

- Candidate1348/choice-schema303, candidate tests2518/56 cases and event-value candidate342:
  retain source/scope/remap/identity/class choices and external reader isolation. 2P removed only
  the confirmed one-use missing-files forwarder; shared actual missing-path policy remains.
- Scan1493/direct1245/38 cases: retain explicit-vs-recursive discovery, admitted payload materialization,
  shared budget, identity/link guards and indexed BIDS traversal. No confirmed deletion.
- Main ApplyService1479/CommandService2309, apply preparation230/discovery142/public projection124
  and projection tests253; independent service tests2464/BIDS1375/event-value apply447/timestamp279:
  retain detached staging/rollback, one-shot command receipts, per-run EEG semantics, bounded/public
  projections and Windows freshness. DatasetState1877/direct1055 retains revision/generation,
  one-shot staging/checkpoints and legacy mutation invalidation; domain UI closure remains separate.
- EEGLAB preflight962/label estimator360/direct EEGLAB522 are fully read. Resource-guard tests were
  read only at190–275/480–535/570–815/840–890 of1632. Preserve pre-MNE bounded MAT parsing, compressed
  budgets, exact FDT shape/size/path checks and shared multi-file MAT budget. Real savemat/read-counter,
  parser-denial and pandas/tracemalloc tests are useful, not final source-diverse certification.
- Montage preparation1282/coordinator460/lifecycle355, their direct tests809/630 and fixture130:
  preserve geometry/resource admission, generation/manual precedence and publication as distinct
  responsibilities. 2Q adds failed-refresh retry protection at the coordinator level, not an extra
  service-level integrated claim.
- Module 8 full reads include run_tests961/direct1174, attestation195/direct185, required-wrapper260/
  direct409, Windows bootstrap881/direct436, run.py370 and startup test bodies, WSL launcher276/cmd42,
  setup ps1/cmd, ci_change_scope109 and artifact verifier216. Whole CI925, all Poe/dependency entries,
  other scripts and handoff/dashboard adapters remain open. Actual CI aggregation already installs
  only lock-derived coverage, not a duplicate product environment; retain non-equivalent gates.
  No measured unnecessary startup/CI wait was established.

**Recent evidence limitations.** 2T's unedited native baseline had two geometry assertion failures:
the intended150px minimum exceeded natural143px layout hint, legitimately adding footer surplus.
Tests now allow only that derived surplus plus existing rounding and explicitly require minimum150;
no product geometry change. 2U's first fixture migration failed two obsolete session.load diagnostic
assertions although generic forbidden-import checks already rejected the unsafe UI. Automated safety
review rejected deleting the specific gate, so all existing checks were retained and extended to
actual direct/symbol/module-alias factories; assertions were not removed. 2W's first sandboxed Windows
launch failed before collection; required escalated interop succeeded without restarting/installing.
Native Qt unit runs are offscreen, not Windows window-manager/DPI/manual acceptance.

After closing each scoped edit/review, continue the unfinished module audit immediately. Modules3–9
and same-source final integration gates remain required. A commit, context recovery or pending CI
is not an endpoint.

### Responsibility closure and retained boundaries

- Module 1: independent reviewer approved shared-spine responsibility closure at `1247cf7c`.
  Native same-source selection: 178 passed, covering runtime/cache, confirmation, publication/delivery,
  owned work, state/read models, observer batching and actual query/shutdown cases. Service domain
  branches and state/snapshot projections remain explicit module 2–6 obligations. Later changes to
  shared identity/publication/lifecycle reopen affected evidence.
- The state-service test audit read all 2,063 lines / 49 functions: retain distinct failure, detachment
  and retry contracts. Actual data_lists cases already protect nonwaiting lock rejection,
  stale-generation admission and committed-state reads; do not invent another concurrency owner.
- Results, automation, pipeline-transaction and workflow-projection test audit read 1,761 lines:
  retain privacy/public-JSON, real command/subprocess, mutation-port and fail-closed behavior.
- Module 2: content identity source (1,010 lines) and direct/hash-cancel tests (945 lines) retain
  streaming SHA, path scope, admitted digest reuse, bounded workers and owned-context cancellation.
  PathIdentity lexical/resolved matching and parser-window ResourceReader checks protect different
  boundaries from cross-review SHA; they are not redundant caches.
- Recipe source/direct tests retain save/replay, legacy class-map migration into unconfirmed
  suggestions and current label-audit reconstruction. Target provenance/schema additions are not
  current guarantees or authorized schema work.
- Loader orchestration/factory/registration and direct tests have been read. Native installed MNE
  source refuted the proposed Raw lazy-handle leak: relevant Raw readers reopen paths per read,
  while EpochsFIF legitimately retains its live descriptor. Do not add a disposal owner without
  evidence. No measured startup/performance improvement is claimed.
- Study convenience cleanup does not certify training/domain methods. EvalRecord.export_csv remains
  a module-5 caller/disposition question, not a claim of reachable product CSV export.
- Module 6 must close the actual Assistant attempt -> pending confirmation -> application workflow
  evidence gap; separately tested halves do not prove stale approval rejects with exactly one
  authorized mutation. Preserve accepted bounded Assistant limitations, not Stable promotion.
- Module 8 initial inventory: 106 scripts, 66,204 physical lines. This is not deep-review evidence.
  Current CI routing correction covers only helpers actually used by visual lanes; separate handoff
  producers are not grounds for extra unrelated CI waits.

### Completed slices — compact recovery index

Each entry was inspected by the main agent and independently reviewed unless a limitation is stated.
These focused counts are not additive whole-project evidence. Owners/public contracts did not increase.
Detailed scope declarations and chronological corrections remain in the associated Git history;
this table replaces their duplicated active-plan narrative, not any unresolved module obligation.

| Slice / commit | Change and production LOC | Focused evidence / limitation |
| --- | --- | --- |
| Stage / `5346a296` | One integrated phase plan, small-commit exception; no runtime change | Baseline main `4770b049`; source-only worktree, existing Windows environment |
| 1A / `0d67870f` | Snapshot uses existing pure training serializers; +16/-50/net -34 | 139 before/after; lazy imports and publication preserved |
| 1B / `f498e436` | Unused state exports/aliases/lazy forwards; handle_evaluate registry retained | 92 original -> 94 retained with real model-name/detachment cases; live-alias fault detected; fresh-cache native 84 later |
| 1C / `25aca4a8` | Delete four-line registry.start forwarding alias | 29 before/after; all seven migrated files 112; 20 calls changed, assertions unchanged |
| 1D / `1f0329fd` | Retired runtime serialization helpers; +2/-34/net -32 | 55 before/after; explicit public/internal serializers retained |
| 1E / `3a8143f0` | Publication-only Assistant stage, remove mock/Study derivation; +4/-107/net -103 | 138 -> 127; typed mapper and actual assembler; two wrong-stage probes detected; new typed cases were not run against old signature |
| 1F / `8044302c` | Derive lazy exports from existing mapping; +2/-116/net -114 | 4 original/strengthened cases; exact 114 names/order preserved; cold import/memoization retained |
| 1G / `b5d6dc4b` | Unused Assistant conveniences/type aliases; +2/-49/net -47 | Same 89 plus 4 selected before/after; no tool/policy/receipt changes |
| 1H / `f5c7fd77` | Unread snapshot/query dependencies; +1/-8/net -7 | Main selection 88; reviewer's 84 omitted four read-model cases, not failures |
| 1I / `264ef571` | Reuse detached prepare failure envelope in three callers; +6/-79/net -73 | Original 5, strengthened 6 before/after; concurrent winning publication/cancellation retained |
| 1J / `a5101683` | Lifecycle unread dependencies/fallback/forwarders; +5/-22/net -17 | 10 baseline, 26 extended reset/rollback/import cases; injected transaction remains owner |
| 1K / `e2f483dd` | Reuse six identical fence release blocks; +15/-36/net -21 | 17 + consumer -> 18; missing-release fault detected; locks/flags/finally order unchanged |
| 1L / `3a35efee` | Unread Qt callback member and empty test subclass; production -2 | 34 before/after, real Qt delivery/ack/teardown; visible behavior unchanged |
| 1M / `8d51502e` | Unused observer batch compatibility properties; production -17 | 33 original/characterized/after; public notify/deferred outcomes retained |
| 1N / `0b0a8e7b` | Unused Study and exclusive manager convenience chains; +2/-63/net -61 | Four-file 158 -> 146 (exactly 12 obsolete cases), 7 analysis/readback neighbors; real saliency/manager behavior retained |
| 1O / `6c0ee806` | Consolidate duplicate runtime identity test; no production change | 10 -> 9; both construction orders, concurrency/retry and explicit-close cache isolation retained |
| 2A / `d1dc62ff` | Fix raw cleanup retaining channel backup; +1/-0 | 3 red -> 59 green; two real FIF apply/session/reset cases; 8,000-byte weakref witness is retention evidence, not OS RSS promise |
| 2B / `930c2a6a` | Resource admission guard targets actual prepare, not dead handler; test-only | Unsafe actual path red -> 15 pass; no security rule weakening |
| 2C / `1c7ba6fc`, `d3ef1ac4` | Actual prepared-path characterization, then remove old direct apply/helpers; +2/-186/net -184 | 28 real command replacement cases; after 79 actual application and 134 retained cases; 21 legacy functions/35 cases removed; retained AST bodies unchanged; bypass-content-check fault detected |
| 2D / `7b4fc8a0` | Dead DatasetStateService import/port and raw prepare convenience; production -81 | Main 24 original/characterized -> 53 after; worker 10 before/after; stale no-import sentinels now watch actual loader |
| 2E / `722207cc` | Fix Windows recipe descriptor/path ctime mismatch; +16/-4/net +12 | 2 red/1 pass -> 3 pass; 18 selected, 107 full service/receipt cases resolve three native failures; complete within-channel checks and cross-channel dev/inode/size/mtime retained |
| 2F / `1247cf7c` | Duplicate current-session check and single-use verification wrappers; +9/-21/net -12 | 49 + 6 before, identical 55 after; SHA, contexts, cancellation unchanged |
| 2G / `aba4eea7` | Three unused interpretation mutation APIs; production -55 | Strengthened actual checkpoint/one-shot/recipe rollback protection; final historical-source 82 and current 82 pass; chronology qualification below |
| 2H / `7c89b532` | Six test-only Raw display conveniences; production -49 | 113 original, strengthened retained 116; 13 external-fixture skips; eight wipe cases before deletion and imported-event fault detection; 11 typed-summary + 3 rollback neighbors passed |
| 8A / `c0425f43` | Route three actual visual-CI helpers | 10 baseline, 1 red/10 pass, 11 corrected; five unrelated producer additions rejected before commit |
| 2I / `73002524` | Remove eight duplicate loader cases; no production change | 39 original/strengthened -> 31; exact SET codec/preload strengthened; actual FIF/epochs retained; plan history consolidated |
| 2J / `daaf1a59` | Retire unused flat sequence/force and catch-to-zero label chain; +9/-223/net -214 | 79 original/migrated -> 68 after (11 dead cases), 18 actual sequence/recipe neighbors; nine checked-batch cases retain explicit error phases/real Raw rollback; actual public state entry unchanged |
| 2K / `0e1c096c` | Remove identity alignment helper/index copies/unreachable warning; +5/-126/net -121 | 36 original -> 39 real Raw characterization -> 37 after two replaced mocks; 18 actual consumers; reversed-row fault detected |
| 2L / `d575fba4` | Unused BIDS admitted size-only property; production -7 | Identical native 28 before/after; property is not a dataclass field; content identity/budget unchanged |
| 2M / `e0df098d` | Three unused label-carrier convenience helpers; production -37 | 35 original/migrated -> same35 + six event-value consumers after; four full maps unchanged through actual derive_class_views |
| 8B / `323241a9` | Correct WSL launcher terminal-only output description; script +1/-1 | 5 original -> 1 red/4 pass -> 5 corrected; existing privacy source assertions; no launcher/app executed |
| 2N / `2a61245b` | Unused metadata readers/budget alias; production -30 | Native27 original/migrated/after; admitted cache/budget behavior retained |
| 2O / `f485c36f` | Reuse ordered path projection and target routing; +8/-23/net -15 | Same80 original/strengthened/after; duplicates/blanks/None recipe paths preserve exact output |
| 2P / `e78f9a78` | Remove missing-path forwarder and marker no-op branch; +1/-22/net -21 | 59 -> real FIF annotation/stim characterization61 before/after; upstream MNE warning |
| 2Q / `5155f913` | Coordinator failed-refresh -> pending -> retry -> no duplicate publication; tests only | Native18; missing-retention in-memory fault detected; not service-level dispatch evidence |
| 2R / `aaf64d41` | Actual duration evidence and mapped label owner replace test/single-call forwards; +8/-35/net -27 | Same101 original/migrated/after; per-run/time/atomic behavior intact |
| 2S / `5b97abfd` | Unread filename dependency across three constructors; production -8 | Native126 plus selected actual ApplicationService30 before/after; live snapshot filename retained |
| 2T baseline / `b67d24f8` | Correct two geometry bounds for intended minimum-height surplus; tests only | Original44 pass/2 fail -> strengthened46 pass; explicit150px floor, no layout edit |
| 2T / `92a7cc38` | Unused montage smart_match and three exclusive tests; +2/-50/net -48 | Retained native43; safe/reviewed mapping and all current lifecycle cases unchanged |
| 2U / `20c139b3` | Dead label admission/receipt/specs chain; production -258 | Native289 original ->290 migrated ->289 after one obsolete case; seven actual receipt/SHA neighbors; all safety gates retained |
| 2V / `1e28068c` | Discarded full label payload hash/state; +4/-119/net -115 | Real1MiB admission stream1,048,576 ->0 bytes; actual524,288 labels unchanged;64 safety cases before/65 after; identity probes/early descriptor/final SHA intact |
| 2W / `bb5a27e0` | Unused wizard legacy review fallbacks/target/clear_skip; production -172 | Native28 ->27; full target/empty metadata assertions preserved, main focused1; main nonauthor review; no separately strengthened pre-delete run |
| 2X / `bf1a14e6` | Wait for real cancelled-review terminal delivery; tests only | Same native5 before/after, Ruff; in-memory late delivery detected1!=0; finally releases on assertion failure |
| 2Y / `26b8c054` | Remove16 unused wizard-private helpers acrossfourfiles; production -224 | Native130 ->128, exactlytwoexclusivecases removed; real sidecar field retained; independentreview and Ruff |
| 2Z / `4e317328` | Removeignored tree-sizing inputs and equivalent row-count aliases; +4/-21/net-17 | Native10 geometry/rescan cases, Ruff; independent arithmetic/caller review; no visible geometry change |
| 2AA / `11125166` | Merge duplicate rescan case while preserving all assertions; tests net-34 | Strengthened3before ->retained2after, Ruff; main nonauthorreview |
| 2AB / `fca0ac35` | Deleteunused fuzzy montage chain/module; production -102 | Native59 ->52, nine new no-mock actualnormalizer cases; sevenexclusiveold removed; same18upstreamwarnings; independentreview/Ruff |
| 2AC / `36b2de7e` | TwoOpenNeuro integration roots reuse configured storage; tests only | Isolated red2fail/4pass ->6pass; runpyactualconsumer definitions, no downloads; independentreview/Ruff |
| 2AD / `27c525c6` | Remove four Coordinator payload forwarders; +20/-39/net-19 | Native80 before/after; migrated assertions6focused before deletion; independentreview/Ruff |
| 2AE / `20b05f75` | Remove unused loader lookup/commented rejection; production -17 | Strengthened23 before/after, no-publication fault detected; real Apply neighbors, independentreview/Ruff |
| 2AF / `4df0c36e` | Remove preflight forwards/list copy and unused multiplier aliases; +8/-40/net-32 | Same20 native before/after; receipt/scope/BIDS fallback review and Ruff; policies unchanged |
| 8C / `e8ed6d4b` | Retire duplicate placement capture entrypoint; script +1/-76/net-75 | Canonicalcapture32 before/after, mainnonauthorreview/Ruff; actual factories unchanged |
| 2AG / `528322e7` | Remove empty wizard footer instance and exclusion forward; +1/-9/net-8 | Same13 native rendering/removal/geometry before/after, independentreview/Ruff |
| 8D / `aeb53bf4` | Real Qt persistent-visible timeout evidence; tests+36 | Originalsuccess1 ->success/timeout2pass; in-memory wrong-success fault detected; mainnonauthorreview/Ruff |
| 8E / `b7ed74ab` | Remove unused review-state capture fixture; script-63 | Same32 native before/after, mainnonauthorreview/Ruff; canonical factories/inventory unchanged |
| 3B / `7fb9fcc9` | Retire unused MAT Export/module/export tests; production-57/tests-98 | Native78 ->73, exactlyfive obsoletecases; same17upstreamwarnings; independentreview/Ruff |
| 3A / `07881c8d` | Two unused DrawRegion APIs removed; production-23/testsnet-16 | Original22 ->stronger23 ->retained18; wrongoverlapfaultdetected; actualcanvas/strategycases and mainnonauthorreview/Ruff |
| 3C / `c628be38` | Remove unreachable ordinary preprocess handler branches/helpers; production-76/testsnet+37 | Real ordinary/admission characterization before deletion, retained42pass; cancellation/stale/rollback/epoch safety retained, independentreview/Ruff |
| 3D / `036cb1cc` | Remove unused split to_thread no-op; production-3/tests+87 | Native direct16 before/after; both omitted-guard faults detected; independentreview/Ruff; distinct offscreen font/native-center limitations remain tracked |
| 3E / `63f691b2` | Real epoch boundary workflow replaces two summary mocks; testsnet+43 | Exact1%, above1%, multirecord counts/atomicity; threshold fault detected; combined3E/3G291pass, independentreview/Ruff |
| 3F / `f234a5ea` | Synchronous plotter/fallback/alias cleanup; productionnet-29/testsnet-1 | Real curves/current+overlay/time+PSD; direct25pass and native8cycle stress; wrong-frequency fault, independentreview/Ruff |
| 3G / `d86efa15` | Retire unused Epochs picker chain; production-538 | 307 obsolete collected cases removed (corrected actual parametrization count), actual manual Generator retained; combined291pass, independentreview/Ruff |
| 3H / `3e556a98` | Actual RAM-before-deepcopy test replaces exclusive fake; testsnet-7 | Direct/adjacent37 retained; strengthened actual-copy node1pass and omitted-check fault caught; independentreview/Ruff |
| 3I / `db4670d7` | Normalize/validate split command once; productionnet-10/testsnet+30 | Real defaultNone vs explicitempty replacement; retained47pass; exact public message, independentreview/Ruff |
| 3J / `e77e389c` | Dialogs reuse inherited geometry owner; dead reference aliases removed; productionnet-22 | Same24 Windows QPA windows cases before/after, no visible change; main nonauthorreview/Ruff |
| 3K / `0b7d77ef` | Retire test-only dataset metadata conveniences; production-49/testsnet-11 | Missing mask assertion restored;113before112retained, exactlyone duplicate removed; independentreview/Ruff |

### Evidence qualifications that remain relevant

- Use a fresh unique PYTHONPYCACHEPREFIX plus -B for Windows tests of WSL-edited source: -B alone
  prevents writes, not stale reads. The earlier ambiguous 1B run was superseded by fresh-cache 84.
  That earlier lookup was abandoned. During2X a worker mistakenly invoked Poetry and created a
  separate empty Windows environment. Main verified its exact newly-created path,7,235,691 bytes,
  no using process and sole internal file symlink, then removed only that accidental environment
  xbrainlab-urV89cf7-py3.12 from the Windows Poetry cache. Original Windows Python remains present;
  the invalid attempt supplied no test evidence. Further runs use the explicit existing interpreter.
- 2G had no original unedited chronological two-file baseline. Migrated tests before production
  deletion passed 81, but an environment-assignment warning invalidated its cache-isolation claim.
  Fresh-cache current runs passed 81; nested isolation was strengthened to mutate actual nested input.
  Final strengthened tests then passed 82 against exact historical `1247cf7c` state source loaded only
  in memory and 82 against current source. The first historical harness needed correct inspect
  linecache registration; that was a harness fix, not a product failure.
- 2G actual post-publication retirement failure now includes prior real apply/save and verifies
  interpretation identity, recipe ID/path/full content and pipeline/trainer/history restoration.
  It intentionally isolates internal transaction rollback with admission bypasses; normal policy
  blocks replacing data after training. A manually injected trainer fixture first caused stale
  Scan admission (combined 130 pass / 13 skip / 1 fail); publishing that injection through get_state
  fixed the fixture, and the corrected case plus full 82-case selection passed. Recipe carried into
  prepared state means recipe assertions alone do not prove rollback; restored interpretation ID does.
- 2H same retained Raw/loader/preprocess selection is 116 passed: one no-op case removed, four extra
  event-wipe parameter cases added. All passed within the combined run above. Thirteen skips are
  unconfigured external public fixtures, not checked-in GDF/multiformat cases; the final canonical
  source-diverse gate is still required. Replacing wipe with set_mne in memory caused all four
  imported-event cases to fail; no faulty source persisted. Existing MNE/NumPy warnings are not
  evidence of final whole-platform readiness.
- 2K's list/ndarray real Raw cases cover filtered interleaving, nonzero first sample, previous-value
  column, exact code/order and no source mutation before apply. Mismatch covers both directions.
  The isolated reversed-row probe failed both cases on timestamps/prior values; no faulty source
  persisted. The first argv probe had only a Windows quoting SyntaxError. One existing MNE warning
  in normal suites is expected all-epochs-dropped safety behavior, not a new failure.
- 2J's force_import field belonged to the explicitly internal LabelImportPlan recipe DTO; current
  construction/serialization never used it. Actual DatasetStateService.apply_labels_batch and
  checked atomic ownership remain. 2M's limit=20 belonged only to its discarded test-only convenience,
  not the current preview/public class-map policy. No formal contract changes are implied.
- Lower-mock internal paths retain external MNE/resource isolation where necessary. No reduced test
  count or path-only inventory establishes stronger workflow coverage by itself.

### Inventory and separate infrastructure recovery

The ignored static inventory is `build/dev-artifacts/module-quality-audit/tracked-files.md`,
initially 1,292 tracked files. Update disposition from actual source/caller/test reading; pending
remains unknown. Reconcile newly added/deleted files and domain-owned ranges before final closure.
Do not create a second planning platform or treat generated files as inspected production.

Authorized storage cleanup is complete locally: removed only abandoned backup
`E:\XBrainLabBackups\XBrainLab-WslCompaction-20260909-232646-9134c3e5810d4399b274695a2b546bce\Ubuntu-24.04-ext4.vhdx.bak`
and its empty parent, plus verified empty runs ending
`20260910-011228-93f0770cd28e49afb965485b587f3763` and
`20260910-014659-d5c3910b070c4a3ba2b6877f5734369d`.
E free bytes increased 712835555328 -> 927430828032 (214595272704 bytes, about 199.86 GiB).
Deletion is not recycle-bin recoverable. Both registered C WSL VHDXs, Windows Python, model/RAG caches
and central datasets remain. No C shrink, compaction, shutdown or deregistration ran.

Compaction-only source tooling withdrawal is separately committed `acf7c56d` on
`chore/manual-environment` in the infrastructure worktree; 84 retained native scripts tests passed.
An initial MAXPATH failure was resolved by the existing short cache temp path. Exact deployed
`D:\XBrainLabCache\tools\compact_wsl.ps1` matched retired source SHA-256
`6675b7debb8f02fc163ba1efed2eaff0d89afa632cd388329bff3935af73d0f5` and was removed.
Both manual launch tools remain. Source is recoverable from Git. No push/merge or manual-checkout
update is implied; inspect current Git/PR state before eventual integration.

### Recovery after context compaction

Read this whole active plan, Git status/diff/worktrees and current worker/session state first. Continue
the next unfinished authorized step immediately; a recovery summary is not an endpoint. Preserve the
module table, current slice, exact evidence and outstanding reviewer findings here before context loss.
Do not dispatch from older completed PRs, recreate environments, discard active work or stop because a
single slice has passed. Keep this file the sole active plan until the stage is actually complete.
