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
| 3 Preprocess/epoch/split | Processing, copies, invalidation, preview/materialization, related UI/tools | 3A–3U reviewed; documented split-artifact decision and final inventory/closure review remain open |
| 4 Models/training | Catalog, resource preflight, settings, stop/rerun, history/checkpoints | Core/model/resource/record/UI audit substantially complete; final inventory, convenience retirement and two visible decisions remain open |
| 5 Evaluation/saliency/views | Read/publication, SmoothGrad/recompute, four views, stale work/render lifecycle | Core/attribution/3D/publication integration fully read; script/inventory reconciliation and two explicit retirement decisions remain open |
| 6 Assistant/chat | Tool adapters, turns/confirmation/execution, model/RAG lifecycle and shutdown | Controller/confirmation/execution ownership audit started; not closed |
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

Git recovery: product branch `cleanup/module-quality`, HEAD `3d498c51`, 104 commits after baseline
`4770b049`. Original checkout UI/test/settings dirt remains protected. Recheck Git after reboot;
old session IDs and plan text do not prove a process is running. No manual candidate or merge request.

**Current work — module5 render/resource/lifecycle and module2–4 closure gaps; visible/API decisions remain open.**

**Completed bounded8G — preserve caller-owned walkthrough output directory.** Main fully read visualization
capture2857; main() recursively deletes the arbitrary --training-output-dir before capture. Its
registered handoff caller supplies an evidence runtime directory; no contract requires erasing its
contents. Existing training output owner creates exclusive per-record directories. Remove the two-line
rmtree branch and now-unused shutil import, retain directory creation and unchanged configured output
path. No production/UI/Command/schema change, script-3LOC, owner delta0. Do not add a cleanup framework
or run the unsafe script against real directories. Test main with real pytest filesystem, spaces/non-ASCII
path, preexisting nested sentinel and two runs; isolate only QApplication/walkthrough (not filesystem).
Cover new/existing roots and passed/failed capture exit/artifact status. Red before fix, same green plus
full direct script tests, Ruff and independent actualdiff review. This does not certify native render
or delete retained test weights; explicit target-verified cleanup remains separate. Stop this slice
when rerun preservation and honest output/exit are proven, then continue remaining module audits.
Actual red4failed5.83s on deleted sentinel/prior-output reads; corrected full direct suite76passed8.18s.
Ruffcheck/formatpassed and independent actualdiff review approved. Script-3/test+61LOC; all prior
cases retained. Test sys.excepthook registration intentionally restores main's replacement at teardown.

**Module6 initial full owner audit (not closure).** Independent full controller2949/attempt898/
execution342/confirmation314/pending443 and respective direct confirmation154/pending560/execution151/
closure91 plus controller4625–4805 retain one host-turn/Qt orchestration, deterministic admission,
one pending correlation owner and authoritative ApplicationService expected-generation execution.
Real tiny-FIF product-flow528 proves a current direct-input receipt makes one resample without model/
RAG and stale receipt makes none; it does not prove confirmation-card approval through real mutation.
No controller split merely for LOC: lifecycle/presentation delegation already exists, with no proven
competing owner. Remaining helpers/direct suites/model/RAG/UI/scripts still require full audit.

**Completed bounded6A — retire orphan Assistant command-to-panel route chain.** Independent full presentation285/
direct209 and controller audit show unused private wrapper is the sole production consumer of the
presentation helper, which solely owns command maps/canonicalizer/action-contract import. Remove
that whole test-only chain and controller's write-only _max_tool_failures, not a replacement shell.
Keep typed AssistantPanelNavigationRequest/target/view modes, actual UiRequest→AgentManager routing,
_command_identifier and CommandName for live interaction copy, _max_loop_breaks and all pending/
confirmation/publication policy. No dynamic/config/docs/export caller; no visible UI/public tool/model/
prompt/RAG change. Two production files roughly-60LOC, owner delta0, no new abstraction. Establish
passing response/controller/UI-handoff/actual navigation tests before deletion; remove only two
exclusive routing test functions (three collected cases) after baseline, preserving negative handoff
guard. Same retained tests, Ruff and main nonauthor actualdiff review before commit. User-authorized
unused convenience retirement applies; stop at that bounded verified deletion then continue module6.
Original full response/controller/UIhandoff +real navigation/product-flow342passed15.18s, three MNE
deprecation warnings. Worker owns exactly controller/presentation/direct presentation test; main
owns after verification and plan. No concurrent source writes during hooks.
Retained339passed15.51s with the same three MNE warnings; exactly three exclusive route cases removed.
Production-80 across2files, tests-18; main nonauthor actualdiff approved, Ruffcheck/formatpassed.

**Completed bounded6C — retire orphan Assistant backend class registry.** Main fully read backend_resolver101,
actual real adapters249/package registration288 and mixed tools/debug tests423. BackendClassRegistry
is imported only by three exclusive direct tests; real tools now use ApplicationService/GUI owners.
No dynamic registration/config/script/doc/export caller. Delete that source module and only its three
exclusive tests, updating the mixed suite's introductory description. Preserve actual backend model
catalog, optimizer map, preprocess owner and exact18 real/mock registration. Production-101, no new
or replacement owner; no public tool/schema/model/UI behavior change. Baseline mixed suite +real-tools
ownership/registry tests, same retained after, Ruff and independent source/diff review. No artificial
compatibility shell or per-model tests removed. Other mixed-suite visualizer/seed/logger overlap is a
separate module9 quality question, not part of this deletion.
Original74passed6.36s, retained71passed6.23s; only three exclusive resolver cases removed. Independent
actualdiff/registration/owner review approved and changed-file Ruffpassed. Production-101, testsnet-36.

**Completed bounded6B — real confirmation approval/replay/stale mutation evidence.** Full product-flow528,
resource-receipt302 and strict-recovery273 do not connect actual confirmation to a real mutation;
independent long-session1151 and AgentManager product-chat3503–3769 show no-action model responses
or fake controller confirmation. Reuse the existing real-controller/AgentManager long-session test
host, adding only the necessary deterministic worker proposal and confirmation transport seam. Send
a real strict reset_preprocessing proposal from current preprocessed publication, receive the actual
pending request/card, click its real approve/cancel control, and observe actual ApplicationService
derived-state reset/raw retention. Replayed exact approval must not mutate twice; after a legitimate
external preprocess changes generation, old approval must not reset new data. Do not fabricate pending
decisions/receipts or mock execute, confirmation/capability policy, application state or filesystem.
Inference/RAG and existing runtime transport host remain explicit test seams; this is not real-model,
native desktop/production dispatcher acceptance. Test-only, one existing integration file, no new
production owner/UI/contract. Establish its existing baseline, add focused cases, same retained checks,
bounded in-memory omitted/duplicate reset fault where practical, Ruff and main nonauthor diff review.
Keep long-session no-action/heartbeat limits unchanged; do not loosen them to make new evidence pass.
Existing full host/soak suite21passed46.35s before edits. Worker waits for6A/6C commit hooks before
writing this one test file; main owns focused after/fault/lint and review.
First focused run exposed three new-fixture mistakes (missing host navigation, zero-argument started
signal collector, and expecting reset to remove rather than restore loaded data); corrected without
product edits. Retained full suite24passed47.20s, six MNE NumPy deprecation warnings. In-memory handler
that reports success without resetting data fails the real256Hz assertion in9.06s. Main nonauthor
actualdiff review approves real command/publication/raw identity/file-byte/replay evidence; model,
RAG and minimal in-process runtime/navigation host remain isolated, not native/manual acceptance.
Test-only net291LOC; no existing cases removed. The fault runner preimport also exposed cp950 console
encoding failure for metrics' approximately sign; shared logger/launcher audit owns investigation,
not a reason to alter this test's success criteria or claim product logs validated.

**Completed bounded6D — remove unreachable empty-schema override.** Main full assembler835/schema72 and
independent context1791/stage283 tests confirm no caller supplies backend_default_tools or
use_backend_defaults. The real formatter always uses strict_prompt_parameters; alternate forced-empty
schema cannot run. Strengthen existing two-action catalog test to parse emitted configure_training/
bandpass schemas and assert their exact properties/required/additionalProperties before deletion.
Run full assembler/stage baseline, then delete only unused parameter/forward/conditional in two source
files. Keep prompt strings, actual schemas, current publication/tool membership, history/RAG/model
policy byte-for-byte unchanged. No experiment or new owner; roughly-13productionLOC. Same retained
tests, in-memory empty-schema fault, Ruff and independent actualdiff review before commit. No existing
case removed. Other unreachable history options/stage prose are separately audited candidates, not
part of this slice.
Strengthened baseline72passed6.58s; recovered after72passed6.07s (earlier after output unavailable,
not counted). In-memory forced-empty schema fault fails the exact bandpass properties assertion
in0.45s. Ruffcheck/formatpassed; independent actualdiff review approved. Production+2/-17/net-15LOC,
tests+23; no existing cases removed.

**Next bounded6E — retire unused stage prose and unreachable history suppression.** Full pipeline190/
direct298 and assembler835 audit, plus independent exact caller search, find STAGE_CONFIG's seven
system_prompt values unused by runtime: assembler and evaluator consume only tools. Preserve that
live stage/tool ledger, public membership and all actual generated prompt bytes. Before deletion,
compare full prompts for all seven fixed-publication stages with unique sentinel prose substituted;
also record exact before/after prompt digests. Remove only prose builder/values, unused fallback
prose/docs and exclusive prose tests; retain tool-stage and label assertions. Separately remove
receipt_question whose sole caller always passes None, retaining selected/sanitized bounded history.
No model/prompt experiment, new owner or compatibility shell; approximately-120productionLOC across
two files, owner delta0. Full stage/config/context baseline and retained after, exact output comparison,
Ruff and independent actualdiff review are required. No UI behavior change or confirmation-policy edit.
Stop this slice at verified output-preserving deletion, then continue module6 lifecycle/tool/UI audit.

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
- 4E removed suppressed persistence from real-GDF training and successful OOM retry; actual safe
  checkpoint/EvalRecord reads now verify artifacts under pytest tmp paths. This is not GUI restart/reopen.

Evidence qualifications: 3G removed307 collected obsolete cases, not the earlier mistaken309
(actual108 trial-list entries times2, not109). 3E/F terminal output lost during context recovery was
rerun:291combined/25plotter passed. 3I's alleged third enum argument was a reviewer misread, retracted
without product edits. 3O fixture default class maps were corrected before the passing baseline.
3Q proves control synchronization/coalescing/real signal/shutdown, not precise restart latency.
No measured end-user speed gain, whole-module approval or final Windows manual acceptance is claimed.

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
catalog662/model_holder114/option450direct tests. Subsequent full resource/runtime audits below
supersede the initial partial reads; whole training closure remains pending. Retain static
catalog browsing (no provider import), stable identity/provider admission, numeric/device/class-weight
validation, conditional model context and single configure/build/preflight/receipt owner. Actual
preflight differs intentionally from advisory preview. Catalog command-name helper/input aliases and
optimizer repr duplicate have no consumers; TestOnlyOption and its export are used only by exclusive
tests, while actual manager accepts base TrainingOption. Declare separate baseline slices before
removing these. Subsequent independent full TrainingManager2413/direct1122/training_runtime587 audit
retains real config/start-stop/wait/CAS/lease/rollback ownership; saliency724–2115 is module5's obligation.
Study110–360/shutdown180–245/pipeline tests1–230/integration1–250 remain partial, not full audits.
4B closes the real-manager startup restore evidence gap with a completed actual Trainer, retirement,
snapshot restore and an omitted-restore fault. Keep useful Thread/Event/identity tests.

**Module4 resource admission audit.** Independent full resource_guard2341/resource_preflight563/
resource_receipt322/training_resource_receipt517 and3371direct/integration test lines reviewed.
Retain advisory draft preview versus current authoritative start admission and distinct receipts;
exact scope/TTL/capacity/consume-before-start and actual Agent/Application/Qt paths remain protected.
OS/GPU/MNE isolation is justified, not a deletion target. 4C measured and removed the duplicate GPU
estimate (two model constructions/data reads become one), preserving the cancellation observation
between RAM and GPU queries. No draft-preview reuse or persistent cache was introduced.

**Documentation evidence limitation.** Consolidated plan passed audit_agent_guidance check (ok=true,
no errors). Strict MkDocs build could not start in the existing Windows interpreter: No module named
mkdocs. No environment/dependency installed. Final exact-source docs CI remains required; current
source-only consolidation is not a successful docs-site build or final handoff.

**Module4 main presentation audit (not closure).** Full MetricTab332/history497/modeldialog702/
optimizerdialog212/devicedialog94, metric tests155/history412 read. 4G retired test-only update_plot
and the history forwarder after protecting the actual set_series/reset/repopulate path.
Model dialog async provider, stable recovery identity and pretrained-weight handoff remain live;
Direct modelselection429, training setting1242/direct1321 and full panel/sidebar source/direct tests
are reviewed. 4H removed inert settings remnants, retaining actual saved-split recommendation evidence.
Model settings/identity and cross-module main-window obligations remain pending, not whole UI closure.

**Pending visible-state decision — zero validation metrics.** Actual offscreen TrainingHistoryTable
fed validationloss0.0/accuracy0.0 renders both cells N/A. Zero is a valid result, distinct from missing.
User asynchronously asked to authorize0.0000/0.00% with N/A only for absent metrics; no reply yet.
No product edit made. Continue internal cleanup; do not silently treat this visible issue as fixed.

**Pending visible-state decision — device recommendation adapter.** Independent recommendation owner604/
direct314 audit retained metadata-only formula/cache/provenance and all scope keys. Unused
cached_for_context is a separate deletion candidate. Real Sidebar device recommendation passes
prospective_device, while concrete _StudyApplicationUiRuntime/TrainingQueryPort omit it although
backend supports it. Real application_ui_runtime over Study reproduced the TypeError in Windows;
no signature mock or product file change. User asynchronously asked to authorize the visible device
workflow repair; no reply yet. ApplicationUiRuntime itself is the Protocol, not the concrete adapter.

Completed4I–4N and5A–5D/5G are indexed below; actual source, review and focused evidence
remain traceable in their small commits. Remaining decisions/audit gaps follow.




**Module5 entry audit / next declaration.** Independent full evaluator477/EvalRecord1344 and direct
evaluator173/eval352/metrics155/context532/integrity608/safe-store889 reviewed. Retain real torch
metrics/final evaluation/recompute and safe JSON+NPZ, identity/context/integrity/sealed publication;
real tampered artifact and MNE montage tests are necessary. Coupled renderer/visualizer/TrainingPlan
saliency paths were only sampled, so whole module5 remains open. Concrete candidates are unused
export_csv, standalone export_saliency and five saliency getter conveniences; each requires its
own plan/baseline and exact exclusive test disposition before deletion. Existing canonical EvalRecord
export/load and dynamic figures stay. No unknown-script compatibility or new artifact format.



**Module4 additional completed audits.** Independent full training_history417/direct159 retained as
sole detached JSON-safe projection. Full first-party model/requirements/holder plus direct tests
retain supported catalog/identity/minimum-input/real forward+optimizer boundaries. Full
training_contract9/reset30/submission65/synchronous_lifecycle365/publication_lifecycle582 and direct
reset60/contract32/synchronous574/publication597 retain exact reset ordering, typed host submission,
unlocked waits/locked final verification, retry/dedupe/supersession/close. Secure output paths518 and
safe-store889 were already fully reviewed; don't repeat reads as new coverage. Preview coordinator,
remaining training integration/script entries and final inventory still require completion.

**Module5 render owner audit (not closure).** Independent full evaluation_render1369/work139,
direct1267/205 and UI publication_refresh935 retain immutable DTO copies, exact selected identity
fences and shared owned-work claim/cancel/retry. Copies have a concrete isolation purpose; no new
cache or measured redundant allocation established. UI timer/worker tests use mock ports and do not
prove full native GUI acceptance. Two separate future candidates: unused _final_unavailable_error,
and legacy build_evaluation_model_summary string forward (migrate three test/helper calls to typed
result.text before deleting). Actual typed model-summary preparation/result stays. Full Evaluation/
Visualization UI audit is ongoing; sampled main-window/renderer paths remain incomplete.




**Pending explicit import-risk decision5E — provenance compatibility re-exports.** Independent full provenance925/
integrity872 plus exact-hash270/ownership138/integrity81/contextconsumer190 retain bounded exact
logical-C hashes, immutable sealing, schema/producer validation and surrounding cancellation fences.
No redundant SHA claim. Eight eval.py noqa-F401 aliases have no real caller; only architecture
compatibility tests and a guard requirement demand them. Remove those eight imports, exclusive
re-export identity test and the guard's must-re-export block only. Preserve actual three context/
producer class imports, domain owner's required definitions, forbidden record-local definitions and
mandatory direct-owner production imports. Rename misleading compatibility fixture/local constant
to record terminology and model minimal actual three imports in its fixture. Main reviewed exact
guard body; worker may own eval.py/tests architecture helper/directtest only after baseline.
Baseline ownership/exact-hash and actual record context before, same retained after with all negative
ownership tests intact, Ruff and independent actualdiff review. No runtime schema/cancellation/
publication behavior change; production-8, zero new owner/compatibility shell or new source guard.
Baseline39passed8.09s (ownership/exact-hash/current context). Edit safety review rejected both initial
attempt and one retry supplying the user's approved no-unknown-external-convenience policy; no files
changed. Gate requires a fresh explicit decision after disclosure that external imports from eval.py
would fail. User asked asynchronously; no reply yet. Preserve aliases and matching guard until then.
Do not bypass the gate with a different editing tool. Continue independent authorized module work.


**Pending explicit lifecycle-risk decision5F — dormant automatic saliency scheduler.** Main and independent caller audit
prove PostTrainingSaliencyAutomation is instantiated but never armed by production; its only active
arm calls are exclusive compatibility tests. Remove the220line class, exclusive imports/service
construction/callback/cancel/wait wiring and shutdown cancellation port; remove the dev native-stress
script's dormant idle probe, retaining actual job/terminal-delivery waits. Owner delta is one legacy
scheduler removed, zero new owner; no replacement shell. Preserve PostCommandSaliencyNotificationBoundary,
explicit SaliencyCommand, PostTrainingSaliencyTarget and scoped target context, runtime cancellation,
terminal publication/ack/retry/discard and timeout budgeting. Existing architecture already requires
explicit Compute Saliency as sole product admission; no UI/public command/schema change is intended.
First complete affected test reads and passing baseline. Remove only13 exclusive scheduler unit cases,
armed-only observer case, submission-only timeout case and automatic-thread-start failure integration
case. Migrate shared shutdown failure test to a live runtime cancellation failure and shared wait
assertions to remaining real runtime/delivery owners; preserve explicit-command startup/cancel/stale
and normal observer lifetime coverage. Approximate production-260, three production files plus one
script; main final diff/LOC and independent non-author lifecycle review before commit. Focused same
retained notification/observer/service/background/publication integration plus script evidence, Ruff
and source call-site sweep are required. No automatic closure of module5 or handoff claim.

5F original baseline448passed34.01s; migrated retained429passed33.60s against unchanged production.
The19 removed collected cases are15 scheduler-only parametrizations, one armed observer, one
submission-only wait and two automatic-thread failure cases. Live runtime cancellation failure now
proved close still discards delivery. Source deletion was rejected by edit safety review before
mutation: explicit approval is required after disclosing that external/manual service.post_training_saliency.arm
calls would fail. User asked asynchronously; no reply. Main restored all five worker-owned test/script
changes to HEAD so retained source keeps its protection. No source deletion or dummy replacement;
do not bypass the gate. Resume the tested migration only after approval. The now-exclusive runtime
submission-failure forwarding chain and manager helper are additional retirement dependencies for that
same decision, not grounds to silently delete the underlying live target/publication contracts.


**Completed bounded5H — no-op 3D scene internals.** Independent full base1548/head269/3Dview1749 and
direct baseasync896/cache391/time264/worker1273 audit plus main fullhead269 confirms definition-only
CHECKBOX_KWARGS/CHECKBOX_TEXT_KWARGS, empty _setup_scene/sole constructor call and unread self.save/
param[save]. Remove only those internals and the fixture's unused save key; sample_index routing,
actors/orientation/camera/control behavior stay. UI-internal behavior-preserving changes are explicitly
authorized; no visible change, owner addition or native lifecycle rewrite. Worker owns only head.py
and time-slider test after fullthree3D test baseline; main actualdiff/lint/after and independent
nonauthor review. Roughly-25productionLOC, oneUIfile; no screenshot equivalence/native3D acceptance
claim from controlled PyVista tests. Base/3D worker, cache, weakrefs and verified teardown are retained.
Same43passed6.74s before/6.50s after; main nonauthor actualdiff approved and Ruffpassed. Actual one
production file+1/-21/net-20; test+1/-1. No sample-index/control behavior or native ownership changed.

**Completed bounded5I — actual Saliency estimator-to-receipt evidence.** Full resource817/direct244 and
Analysis618/direct1409 audits found receipt tests patch preflight; integration confirmation402 covers
import/training only. Add one case to existing analysis test module: allocated tiny NumPy epoch data,
real torch Linear parameters and actual estimator produce a RAM warning (only OS telemetry isolated),
then exact challenge/confirmed consume/readback/replay. Reuse actual TrainingManager and
VisualizationStateService receiver, asserting no initial mutation, one confirmed notification and no
replay mutation. Prove each attempt rechecks current RAM before receipt authorization. The manager has
no trainer to avoid attribution: this is Analysis estimator/receipt/configuration wiring, not a whole
ApplicationService/GUI/training-compute journey. No production change or additional receipt owner.
Worker owns only test_analysis_service.py after existing analysis/resource baseline; fullsameafter,
bounded in-memory admission-bypass fault, Ruff and main nonauthor actualdiff review before commit.
Original41passed0.48s; new42passed2.70s. Admission-bypass in-memory fault fails at the initial challenge
(DIDNOTRAISE,1fail2.15s), no faulty source persisted. Main made the allocated fixture type explicit,
matched Linear input to32flattened features and asserted264real parameter bytes; final combined42+5J38
passed80in6.00s. Ruffpassed. Main nonauthor review approves real receiver/probe/readback evidence, not
a training job. Test-only+116/-3/net+113; existing receipt isolation tests remain useful and retained.

**Completed bounded5J — reuse owned normalized arrays in direct render query.** Main full SaliencyRenderPublisher1420/
work176 and direct733/317 found single-run normalize=True allocates normalized arrays, then copies
them again in DTO construction. An actual Windows publisher probe measured two extra copies/128bytes
for128bytes of output; raw also copies128bytes, which is required to detach source. Current GUI variant
preparation already uses the owned-array path, so this is direct query cleanup, not measured GUI speedup.
Reuse existing adopt_saliency_store only for newly normalized single-run arrays; raw source remains
copied, cancellation checkpoints/read-only flags/identity fences unchanged. No new cache/owner/buffer
type. Add normal/zero and raw/normalized source-isolation/dtype/value tests, establish passing baseline,
then one-line production reuse +stable copy regression/identical focused render/work/normalization
tests. Repeat probe, independent actualdiff review and Ruff before commit. DTO read-only arrays remain
trusted detached renderer data, distinct from immutable bytes-backed authoritative EvalRecord stores.
Do not claim measured RSS/latency gains or strengthen immutability through unnecessary extra copies.
Four new normal/zero/raw/normalized characterization cases and full render/work/normalization38passed
5.65s before reuse. Sole production+1 passes already-reviewed adopt flag only after fresh normalization;
independent actualdiff review approved. Same38after passed within80combined6.00s; repeated exact
probe shows normalized extra copies2/128bytes→0/0, output stays128bytes; raw remains2/128bytes.
Changed-file Ruffpassed. Production+1/testsnet+50, no owner or visible behavior change.

**Completed bounded5K — retire unused coverage forwarding shell.** Full main482source/294tests and independent
caller/guard audit find three compatibility functions plus _DEFAULT_PROJECTOR used only by one
direct test. Migrate that case to the actual SaliencyCoverageProjector methods, keeping all label/
method/complete assertions; passing baseline before deleting shell and its three exports. Keep
project_method/project_run/label projection and all coverage/context/integrity policy unchanged.
Architecture guard must require only the actual projector definition while still forbidding retired
names in UI imports/calls and state-service policy: retain COMPATIBILITY_NAMES and union it with
PUBLIC_NAMES for negative import detection. Do not weaken tests or the specialized visualization
guard. One production file roughly-40LOC, zero owner/public Command/query/EEG/visible UI change;
three scoped files only (coverage owner/directtest/architecture helper). Full direct coverage +actual
state architecture +negative architecture tests before/after, Ruff and main nonauthor review.
5E provenance aliases and5F scheduler remain unchanged pending explicit decisions.
Same258passed36.69s before/36.50s after, including full architecture negative tests and actual
state boundaries. Ruffpassed; main nonauthor actualdiff approved. Production-39, zero owner change;
all label/method/complete assertions retained. Retired-name negative UI import/call guards stay active.

**Module5 full source/test audit additions.** Backend visualizers2332source/direct2526 retain exact
class identity, scientific color/time/geometry semantics, actual STFT and cache single-flight/clear/
failure fanout/LRU; native mesh IO isolation is justified. All4602visualization redesign tests read
contiguously to EOF: typed receipt/terminal/request identity and state behavior remain valuable.
TrainingPlan prepared publication1–150/953–1348 +fullEvaluator477 +directtests1516–2399 retain atomic
multi-record replacement, captured identity/stale/cancel fences, selected-method batching and final CPU
release. Captum inner calls remain cooperatively cancellable only between protected boundaries;
no stronger interruption promise or measured end-user speed improvement. Direct tests of successful
temporary-model CPU cleanup need tracing before any cleanup-semantics change.

Independent full manager724–2413/directsaliencylifecycle1882 and actual-method accumulation275
retain explicit command target admission, terminal generation/notification/retry, unlocked callbacks,
stale/CAS fences, atomic recompute and actual safe reload. Full publication integration2773 (not the
earlier approximate2430) includes real MNE/EEGNet multi-fold commands, actual Qt close, render barriers,
live-model/mask/metadata mutation rejection and recovered publication. Narrow compute/thread/queue
fault seams are justified, not mock-only duplicates. Its one manually armed dormant scheduler case
remains protected pending5F; similarly named explicit-command scheduler/target tests must stay.
Seven compact read-side/UI/label/FIF tests1277 were fully source-reviewed, not executed native GUI
acceptance. Capture walkthrough/script test audit and final inventory review remain unfinished.

**Module4 preview coordinator full audit.** Main read439source/341directtests: retain single-flight
same-request sharing, latest queued draft replacement, exact generation/receipt refinement, shared
OwnedWork cancellation, non-daemon worker admission/failure/close/retry and nonblocking diagnostics.
Real threads/Events/registry assertions give direct evidence; model estimate callback is a justified
external seam. Retained cache has one bounded completed result, not a second policy owner. No measured
unnecessary waiting; waits are explicit ticket/lifecycle boundaries. The worker_thread property is
used by actual UI tests to check non-daemon identity and is retained. A possible dead None branch
requires control-flow disposition before closure; do not infer deletion from a text-only search.

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

| 4A / `31ca6ed1` | Unused TestOnlyOption/export retirement; production-195/tests-99 |162before140retained;22exclusive obsolete cases; main nonauthorreview/Ruff |
| 3U / `b1c0b902` | Direct shared preprocess query, no panel forward; productionnet-14/testsnet+10 |27before/migrated/recoveredafter; actual panel context/minimum rate retained; independentreview/Ruff |
| 4B / `210ea1f3` | Real completed Trainer retirement/startup restore; tests+58 |237combined; in-memory omitted restore fails; exact record identities/full snapshot; main nonauthorreview |
| 4C / `e19967d6` | Single estimate per preflight; productionnet-24/testsnet+93 |131baseline/133final; measured GPU models/data reads2→1; cancellation before GPU retained after fault; independentreview/Ruff |
| 4D / `12e389be` | Unused model metadata/optimizer conveniences; production-25 |Same125before/after; canonical schemas/dynamic catalog unchanged; independentreview/Ruff |
| 4E / `45aae45d` | Actual training persistence, shared safe-load assertion; testsnet-2 |5before/after; migrated A01T1pass; omitted-save fault fails; A01T100784bytes/retry100750bytes; no GUI restart claim |
| 4F / `893e4ad0` | Unused Trainer name lookup; production-22/tests-21 |Retained Trainer/real rollback/optimizer stop47pass;4obsolete cases; independentreview/Ruff |
| 4G / `eac27aad` | Live bulk metric/history rendering only; productionnet-26/testsnet-46 |35baseline→42final incl7retained presentation neighbors;2obsolete append cases retired after historical9pass; independentreview/Ruff |
| 4H / `05da6d88` | Inert settings fields/note/helper removed; productionnet-22/tests-1 |Same45before/after incl real saved-split recommendation; main nonauthorreview/Ruff; no visible change |
| 4I / `77fc31c2` | Orphan record wrappers/exclusive suite removed; production-82/tests-59 |70before65retained;5obsolete cases; negative architecture boundary retained; independentreview |
| 4J / `4e9deb3a` | Unused TrainRecord summary/append API; production-57/tests-72 |67migrated before;62retained+4K25=87after; actual update gapfill and omitted-gap fault retained |
| 4K / `e90be669` | Unused recommendation cache accessor; production-13 |Same25before/after within87; cache/invalidation/policy unchanged; independentreview |
| 4L / `2ab22913` | Unused ModelHolder description; production-18/tests-2 |Same232 real model/catalog construction+gradient cases; no test case removed; independentreview |
| 5A / `6558bd06` | Unused EvalRecord CSV export; production-21/tests-15 |35before34retained; current JSON/NPZ reading unchanged; independentreview |
| 5B / `5c33337d` | Unread standalone saliency export retired; production-83/tests-76 |101before93retained;8obsolete cases;8POSIX-only skips still CI obligations; main nonauthorreview |
| 4M / `bf24db3f` | Mock-only output uniqueness replaced by real frozen-clock records; testsnet-98 |32before31retained/4POSIXskips; duplicateUUID fails real exclusive output creation; independentreview |
| 5C / `cdeb3175` | Unused saliency getters removed; production-100/testsnet-67 |93migrated before88after;6actual-validator bypass faults fail; invalid/old/producer checks migratednotremoved |
| 5D / `ae7c8d62` | Dead render error/string forwards; production-19/testsnet-10 |Same50before/after incl real trainer typed summary; no cases removed; independentreview |
| 4N / `33a7ad8b` | Real persistence in synthetic training integration; testsnet-41 |Same27before/after;122files/723462bytes; omitted-save exactcase fails safe load; main nonauthorreview/Ruff |
| 5G / `0839dcc2` | Unused policy/holder/render conveniences + duplicate assertion; productionnet-61/testsnet-8 |235migrated before234after; strict invalid-method/default state/vectorized interpolation retained; independentreview/Ruff |
| 5H / `cef27766` | Inert 3D setup/state removed; productionnet-20 |Same43before/after; control/sample identity/lifecycle unchanged; main nonauthorreview/Ruff |
| 5I / `75bd4047` | Real Saliency estimator/receipt/receiver evidence; testsnet+113 |42after within80combined; admission-bypass fault fails; not an attribution journey |
| 5J / `848d3356` | Reuse newly normalized detached arrays; production+1 |Same38before/after; normalized extra copies128→0bytes, raw copy retained; independentreview/Ruff |
| 5K / `e3c57cd9` | Retire unused coverage forwards; production-39 |Same258before/after; all assertions and negative UI boundaries retained; main nonauthorreview/Ruff |

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
