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

Git recovery: product branch `cleanup/module-quality`, HEAD `b1c0b902`, 79 commits after baseline
`4770b049`. Original checkout UI/test/settings dirt remains protected. Recheck Git after reboot;
old session IDs and plan text do not prove a process is running. No manual candidate or merge request.

**Current work — module3 closure gaps and module4 training; module2 visible decisions remain open.**

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

**Module3 progress and remaining boundaries.** Completed3A–3O/3Q are indexed below; full
chronology, baselines, correction details and reversible changes remain in their Git commits.
The actual prepared command spine now has real ordinary preprocessing, boundary ratio/multirecord,
RAM-before-deepcopy, BIDS receipt/reimport and display-alias materialization protection. Data/render
publication, immutable buffer copies, cancellation and SET_MONTAGE confirmation stay live; generic
callback-only epoch tests do not define a second public snapshot contract.

Module3 is not closed. Remaining obligations:

- Complete caller/test/script inventory reconciliation and independent closure review, including
  current dataset UI adapters and real-data/native lifecycle entries; zero pending rows is not
  a substitute for evidence or resolution of confirmed findings.
- Decide the documented split-artifact chain below; actual Generator/provenance/audit and receipt/
  rollback state remain intact. No restoration of retired picker-expanded indices.
- Shared-runtime module7 owns the native split-dialog center investigation: Windows QPA windows
  compact752/760 cases both pass (horizontal range0); offscreen30/22px overflow was a font/platform
  artifact. Native full layout26pass/1fail shows client center31px below screen center. Inspect actual
  frame/client geometry before requesting visible change; do not weaken assertions.
- Existing UI RAM presentation test spies Raw.copy, which is not the live preprocessing allocation
  seam. Actual no-allocation evidence is3H's deepcopy witness and omitted-guard fault, not that spy.
- Real-GDF training smoke currently patches persistence calls (torch.save/numpy.savetxt/os.makedirs/
  pyplot.savefig). Its observed learning flow is not result-reopen/checkpoint evidence; resolve the
  persistence test-quality boundary in module4, retaining actual output only under test tmp paths.

Evidence qualifications: 3G removed307 collected obsolete cases, not the earlier mistaken309
(actual108 trial-list entries times2, not109). 3E/F terminal output lost during context recovery was
rerun:291combined/25plotter passed. 3I's alleged third enum argument was a reviewer misread, retracted
without product edits. 3O fixture default class maps were corrected before the passing baseline.
3Q proves control synchronization/coalescing/real signal/shutdown, not precise restart latency.
No measured end-user speed gain, whole-module approval or final Windows manual acceptance is claimed.

**Completed bounded 3P — retire unused synchronous epoch handler after real migration.** 3O and its real
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
Integrated3P/3R and actual BIDS/context/cancel/stale/public read-failure protection89passed11.50s.
First attempted collection caught a still-used cast import removed with legacy fixtures; restored
only that import before green. Main nonauthor review/Ruff approved; production+1/-123/net-122,
tests+13/-515/net-502. Exactly17 obsolete direct cases removed; twelve actual operation/invalid/montage
cases remain. No weakening of captured-state validation or actual two-phase publication.

**Module3 unresolved artifact decision.** Independent full validator123/direct45/schema134/split_audit1085
and thesis protocol285–375 audit found artifact writers have no product producer, but the documented
CLI/schema remain a public thesis evidence entry. Validator only checks reported audit and cross-split
overlap, not the full claimed schema/provenance. User asked asynchronously to retire the unused entry
or retain-and-align its contract. No deletion, acceptance-strengthening or scientific claim until choice.
Unused build_training_ready_state test helper is separately removable; actual saved split/receipt seam
helpers retain live integration callers. Continue independent cleanup; module3 not closed.

**Completed bounded 3R — remove unused direct-apply preprocess conveniences.** Main full state-service524 and
tests526 read; after3P, all six apply_filter/resample/rereference/normalization/standard_pipeline/epoching
methods and matching ProductPort declarations have no production caller. Test-only uses combine
prepare/commit and duplicate that spelling; migrate those tests to actual prepare plus commit,
preserving late failure/no publication, one notification, cancellation before commit/retry and rejection
of cancellation after admission. Keep apply_montage, reset/read/notify and every prepared method.
Main owns service/test changes after baseline; no provider/EEG/transaction policy or owner change.
Remove obsolete controller.apply_filter example from observer docstring by showing actual notify
batching, without changing observer code. Native state-service direct cases before/after plus3P actual
prepared paths, Ruff and independent review. No mock-count reduction claimed from spelling migration.
Direct10passed3.90s; migrated same10passed3.83s before deletion; integrated89above after. Independent
actualdiff review approved; production-93 (observer example+4/-4), tests+10/-6/net+4; seven-file Ruff
passed. No live apply_* callers remain; architecture fixture strings deliberately model forbidden UI.

**Completed bounded 8F — retire orphan synthetic epoch dialog capture.** Independent full726 script/direct96
audit plus main whole-tree references confirms no CI/handoff/current-doc consumer. Remove only
capture_epoching_dialog.py, its exclusive test and optional now-dead capture path in architecture
guard. Retain actual epoch dialog tests, current capture_ui_polish_surfaces and all real data/native
gates. First run direct capture test plus two epoch boundary guards and live narrow/public CI script
tests; then same retained gates after deletion, Ruff/affected collection and main nonauthor actual
diff review. Zero production/UI changes; historical synthetic artifact entry recoverable from Git.
Worker owns these script/test/guard files after baseline, independently from3P/main3R files.
Main fully read the script/test and nonauthor deletion diff; baseline7passed3.45s, retained6passed2.83s
after exactlyone exclusive test was removed. Script-726/tests-96/guard+1/-4, net-825; current polish
capture and public data/handoff gates unchanged. Ruff passed, deleted files remain recoverable in Git.

**Completed bounded 3S — dataset adapter test duplication and unused split fixture.** Independent full sidebar963,
panel1166/minimal51/rowidentity321 tests and main relevant replacement paths confirm an unused fake
action class, two panel tests directly calling ActionHandler's already-covered blocked paths, and
one weak duplicate init/style case. Remove those only; preserve actual empty-state button wiring,
headless/no-bridges, real metadata mutation, row identity/generation, geometry and all action cases.
Retire definition-only build_training_ready_state and its exclusive imports from deferred_split_support;
retain live saved-split/materialized-candidate helpers used by resource receipt integration. Main owns
three UI test files plus that helper; no production/visible behavior change. Baseline exact candidates
and richer retained action/row/sidebar/publication/receipt cases, same retained after, exact removed
count, Ruff and independent actualdiff review. Do not manufacture new mock alternatives.
Native43passed8.54s before/40passed8.44s after, exactlythree duplicate cases removed. Independent
actualdiff review approved; no-parent widget now explicitly qtbot-owned, assertions retained.

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
removing these. Subsequent independent full TrainingManager2413/direct1122/training_runtime587 audit
retains real config/start-stop/wait/CAS/lease/rollback ownership; saliency724–2115 is module5's obligation.
Study110–360/shutdown180–245/pipeline tests1–230/integration1–250 remain partial, not full audits.
Missing real-manager startup snapshot restore evidence is a module4 test-quality obligation; existing
transaction tests only fake the runtime delegation. Keep useful Thread/Event/identity tests.

**Completed bounded 4A — retire unused inference-only TrainingOption subclass.** Whole hidden source/test/
script/doc/config references confirm TestOnlyOption has no product consumer: only package exports,
21 exclusive option parametrizations and one manager subclass case. Remove class191lines and two
export entries plus22 obsolete tests/imports, keeping base TrainingOption, all its validation helpers,
manager defensive-copy/invalid-mutation protection and result reading unchanged. Worker owns
option.py/training.__init__/test_option.py/test_training_manager.py after native baseline. No new owner,
public Command/visible UI/model behavior change; roughly-193production, no replacement compatibility.
Use direct option/manager cases plus actual TrainingService configuration consumers before/retained
after, Ruff and main nonauthor review; separate reversible commit then next training audit.
Baseline162passed9.85s; retained140passed9.73s, exactly22 exclusive obsolete cases removed.
Actual production-195/tests-99 after formatting; base validation untouched. Main nonauthor actual
diff/caller review approved and eight-file combined3U/4A Ruff passed. No native/manual claim.

**Completed bounded 3U — preprocess query uses the existing shared adapter directly.** Main full data_query83,
panel304/sidebar899 and whole-tree caller trace: panel's _query_preprocess_data_rows only forwards to
the shared function, and sidebar dynamically rediscovers that one private method. Call the same query
with the same panel context directly, remove the panel forward/import and unused dynamic type cast;
remove data_query's redundant if-None-return-None tail. Migrate the one test's patch to the shared
adapter seam, retaining its lowest-rate assertion. Preserve exception/fail-closed/rate parsing and
all visible behavior. Main owns three UI files and one direct test. Native query/sidebar/rate baseline,
same after, Ruff and independent review; zero new owner. Existing UI-internal authorization applies.
Original27passed6.73s, migrated27passed6.69s before production; recovered after27passed6.55s.
Previous process result was unavailable, not presumed green. Independent actualdiff review approved
same context/failed query/lowest-rate behavior; Ruff passed. No visible UI behavior change.

**Module4 resource admission audit.** Independent full resource_guard2341/resource_preflight563/
resource_receipt322/training_resource_receipt517 and3371direct/integration test lines reviewed.
Retain advisory draft preview versus current authoritative start admission and distinct receipts;
exact scope/TTL/capacity/consume-before-start and actual Agent/Application/Qt paths remain protected.
OS/GPU/MNE isolation is justified, not a deletion target. Suspected duplicate training estimate across
RAM and VRAM paths requires measured call counts before declaring a behavior-preserving slice;
do not share draft preview with final admission or introduce a persistent cache.

**Documentation evidence limitation.** Consolidated plan passed audit_agent_guidance check (ok=true,
no errors). Strict MkDocs build could not start in the existing Windows interpreter: No module named
mkdocs. No environment/dependency installed. Final exact-source docs CI remains required; current
source-only consolidation is not a successful docs-site build or final handoff.

**Completed bounded4B — real manager startup rollback evidence.** Existing transaction tests prove only fake
runtime delegation. Actual prepared pipeline rollback can restore a quiescent retired trainer;
capture rejects active work, so do not invent active-worker resurrection. Add one test in
test_training_manager.py with real manager/Trainer and a minimal contract-valid holder/record,
capture then actual clean_trainer then restore. Verify exact trainer/holder/record identities,
queue/outcome and saliency lifecycle sequences/status plus no active work or unreleased lease.
Worker owns this test only; no production changes. Run direct manager and existing Trainer snapshot
neighbors, then a bounded in-memory omitted-restore fault; main nonauthor actualdiff review/Ruff.
If fixture cannot exercise the supported path, repair fixture or report the limitation, not mock
manager restore. Separate commit and continue module4, not stage completion.
Actual Trainer runs two lightweight holder operations synchronously to completion, then capture /
retirement / clear_history / restore verifies full non-default TrainerStartupSnapshot equality and
exact record identities. Included in237pass; in-memory omitted Trainer.restore fails on empty restored
holders (1fail0.31s). Main nonauthor actualdiff review approved; tests+58, no production changes.

**Completed bounded4C — estimate once within one authoritative training preflight.** A native read-only probe
with actual ModelHolder/tiny PyTorch Linear and fixed external RAM/VRAM observed2 estimator calls,
2 model constructions and2 data reads for a single GPU preflight, both reporting24 parameter bytes.
No wall-time/RSS/user-speed claim. Characterize GPU and CPU counts plus returned RAM/VRAM diagnostics
before changes. Compute once locally in check_training_resource_preflight and pass that estimate to
RAM/VRAM checks, retiring the single-use estimate_training_vram convenience. No cache, new owner,
draft-preview reuse, thresholds/messages/receipt policy or available-memory sampling change. Preserve
CPU/missing settings short-circuit and all fallback/unknown/blocking semantics. Main owns resource_guard
and its direct tests plus recommendation no-work guard (retarget only retired seam). Independent
review specifically checks CPU/unknown/fallback/cancel safety and identical diagnostics; direct
resource tests plus TrainingService/receipt consumers before/after, same measured probe, Ruff.
Estimated production net-negative, no module/public Command class or owner addition. A direct
Python convenience checker may take the already-computed estimate; no unknown-script compatibility.
Characterized baseline131passed9.34s, first refactor plus4B/Trainer neighbors237passed9.84s.
Independent review then identified the removed duplicate pass also removed a cancellation observation
after RAM query. New real OwnedWorkRegistry test reproduced cancelled preflight entering GPU query;
preserve one checkpoint with the existing stage text after RAM/before GPU, not a second estimate.
Revalidate this direct defect and resource/receipt neighbors; earlier237 does not certify this fix.
Final133passed9.27s (baseline131 plus missing-settings/cancellation cases). Same measurement now1
estimator/model/data-read instead of2, identical safe risk and24parameter bytes in RAM/VRAM; CPU
remains1 with no GPU query. Independent finaldiff review approved; production+13/-37/net-24,
tests net+93. Four-file Ruff passed after equivalent context-manager syntax correction. No whole
training/model performance or final native/manual acceptance claim.

**Declared4D — unused training metadata conveniences.** Complete model-family audit retains pinned
catalog/provider/recovery and upstream license/provenance groups; finite gradients cover54selectable
models and actual full workflows6family representatives, not allmodel mathematical correctness.
Exact hidden callers show model_command_names plus its sole TRAINING_MODEL_NAMES import, four unused
input_contract TRAINING_* constants (including the one imported alias), and option.get_optimizer_repr
duplicate have no use. Delete those only; keep canonical model names, DEFAULT_TRAINING_OUTPUT_DIR,
get_optim_name/get_optim_desc_str, actual numeric/schema validation and all model contracts. Main owns
three production files, roughly-25LOC, no new owner or visible/public Command/Assistant changes.
Baseline direct catalog/input/options and actual request parser consumers, same after, Ruff and
independent actualdiff review before separate commit. No tests removed or new compatibility paths.

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
| 3L / `81e0dfb6` | Real BIDS receipt scope and same/changed-context reimport; testsnet+69 |45before40retained; four stale-acceptance faults caught; main nonauthorreview/Ruff |
| 3M / `a7b1ad2c` | Export supported lazy dialog targets only; productionnet-6/tests+13 | Missing-class red,12green; independentreview/Ruff |
| 3N / `96366558` | Remove ignored preprocess error-prefix plumbing; production-6/tests-2 | Same28before/after; main nonauthorreview/Ruff |
| 3O / `9ddb204c` | Actual alias-to-epoch labels/counts and unknown list/dict atomic rejection; testsnet+87 | Real3new plusneighbors40pass before handler retirement; main nonauthorreview/Ruff |
| 3Q / `e8cf3260` | Real Qt controls/signals replace timer-rewired mocks; testsnet-19 | Old2→combined4→retained2+15neighbors17; omitted-signal faults detected; independentreview/Ruff |
| 3P / `7e6007c1` | Retire synchronous epoch duplicate and callback chain; productionnet-122/testsnet-502 |17obsolete nodes retired after real migration; integrated3P/R89pass; main nonauthorreview/Ruff |
| 3R / `8ff29e95` | Six unused state-service apply conveniences/protocol entries removed; productionnet-93 | Same10direct before/migrated,89integrated after; independentreview/Ruff |
| 8F / `161b5a33` | Retire orphan synthetic epoch capture/test/optional scan path; script-726,totalnet-825 |7before6retained, oneexclusivecase removed; main nonauthorreview/Ruff |
| 3S / `731e28d5` | Three duplicate adapter tests and unused helpers retired; testsnet-123 |43before40retained; real metadata/row identity/receipt/wiring preserved; independentreview/Ruff |

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
