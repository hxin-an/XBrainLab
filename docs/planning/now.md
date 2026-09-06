# XBrainLab Now

最後更新：`2026-09-07`

## Active repair — sealed saliency reads and completed-result presentation (#113)

- USER-APPROVED RESUME (2026-09-07): finish #113 handoff, then immediately implement the approved
  test cleanup, Filter section-state clarity and Astra-only harness streams without waiting for
  saliency manual acceptance. Keep separate worktrees/PRs; no product merge without acceptance.
  Root branch
  fix/saliency-result-refresh and isolated /tmp/xbrainlab-sealed-results-handoff remain at d9e59dd9
  with scoped uncommitted changes. All delegated workers and coordinator test/capture processes have
  finished. Preserve the open native Windows d9 process and its in-memory results; do not restart it.
  Implemented: all-finished Compute/Recompute, selected-compute plumbing deletion, atomic complete
  batch validation and busy-until-matching-render handling. Integrated focused suite in the isolated
  worktree: 552 passed, exit 0. Its real train/compute/render walkthrough: passed, exit 0, artifacts
  under build/dev-artifacts/global-saliency-render. These are dirty-source development evidence only.
  Root's final integration-test rename to all_finished is not yet synced to the isolated worktree;
  root's plan note is also newer. Resume by comparing scoped file contents, reviewing final busy/render
  artifacts and syncing these deltas; then freeze an exact commit and run the canonical desktop-source
  manifest/CI before updating PR #113/manual instructions. No new-source handoff or Windows acceptance
  claimed. Protected settings.json and unrelated split dialog/test edits remain excluded.

- Queued approved streams after #113 candidate delivery: two Astra workers own tests-only cleanup
  and Filter UI respectively; coordinator owns harness/validation workflow redesign and integration.
  Tests: remove obsolete/duplicate/mock-only assertions, preserve real behavior and failure protection,
  remove unused fixtures/references, report counts and measured time without a deletion quota.
  Filter: separate bordered Band-pass/Notch sections, Epoch-like off dimming with operative On/Off
  toggles, preserve entered values/backend semantics; four combinations/keyboard/screenshots.
  Harness: revise #114 to Astra-only development agents, not the product Assistant; remove mixed-model
  routing, contradictory instructions and duplicate local/CI checks; deterministic checks own
  machine-verifiable evidence, model review handles meaning/design/anomalies. Retain exact-source,
  failed-check and manual-merge boundaries, no new control plane. Each stream updates this active plan
  in its isolated branch before editing, validates the changed contract and opens/updates its own PR.

- Approved scope correction (2026-09-07): user explicitly expects Recompute to calculate everything
  together. Compute/Recompute must cover all finished runs/folds across every subject in current
  training history; current Fold/Run selection controls display only. Interrupted/unfinished runs
  remain excluded. Reuse existing all-finished command/job path if present; do not create another
  batch owner. Pin/admit the existing current training result origin, preserve visible selection, and
  keep busy from acceptance through all-member publication and selected-view settlement. New regression
  must invoke the actual panel action while one subject/fold is selected and observe complete coverage
  for other subjects/folds, including cancelled history and repeated computation. This replaces the
  previous selected-only action expectation, not training outcome eligibility or saliency integrity.
- User additionally requests deletion of now-redundant backend code. Before deleting, trace real
  production callers of selected-compute command/target plumbing separately from indispensable
  selected-read identities. Remove dead single-fold compute branches if no real caller remains,
  together with obsolete tests; preserve all-finished admission, atomic publication, cancellation,
  resource preflight and renderer identity. Characterize existing global path before deletion.
  No broad unrelated backend cleanup or new compatibility path. Complexity review before crossing
  file/owner thresholds; root reviews exact API/caller delta and keeps existing owner count.
- Cleanup review before implementation: actual production callers now all omit selected compute
  target (UI passes None; Assistant and scripts omit it). Approved deletion spans commands, service,
  training_manager, analysis_service and saliency_resource: remove command target, selected member
  plumbing, target-only admission/filter and resource fingerprint metadata (estimated backend net
  -115 to -150 LOC). UI removes its now-dead forwarding; render selection identities remain.
  Owners before/after unchanged: ApplicationService / TrainingManager / existing UI presenter.
  Extend the existing prepared-versus-expected comparison to the global scheduled finished set;
  first reproduce a missing prepared member being wrongly accepted, then require atomic all-member
  publication. Retain prior output on failure, cancellation, resource checks and append lifecycle.
  This is the direct global-compute contract, not a new owner/state machine/receipt. Cumulative
  PR already exceeds eight production files; this continuation is deletion-first in six existing
  files, no new production module/class. Direct call-site sweep also removes the now-unused
  SaliencySelectionIdentity schema import in automation (seventh existing production file).
  Recheck exact +/- and stop/split if total crosses 1500 LOC.
  Reviewed continuation is currently seven existing production files, +96/-254 (net -158);
  against actual PR base a963405a, cumulative fifteen files, +811/-577 (1388 changed lines).
  These figures exclude the user's unrelated split UI edit; existing owners remain unchanged.

- Current native evidence: on verified d9e59dd9, one explicitly requested Compute on selected
  Subject-1-5 produces the actual four-class plot. This establishes that this selected record can
  compute; it does not compute Fold 1–4 and therefore does not meet the newly clarified global
  contract. Preserve the open native process and in-memory results; it remains old candidate source.
  The observed busy-to-render gap is about 0.4 seconds after an approximately 18-second compute/read.
- Current test-first evidence: the existing global job accepted a prepared batch missing one finished
  record and reported SUCCEEDED. A two-record regression fails on that exact result. Extend the
  existing expected/prepared identity comparison to global jobs, preserving previous output until
  the complete batch can publish. Independent workers remove selected-only backend plumbing and
  keep the button busy through the matching selected render; coordinator reviews integration,
  obsolete-test deletion and exact-source handoff. No new retry or publication owner.

- Confirmed-current native failure after coordinator switched and launched d9e59dd9: subject 1
  Individual still says not computed yet while subject 2 renders; Compute becomes blue/enabled
  before the result appears and invites duplicate activation. The earlier old-checkout explanation
  does not resolve this confirmed-current report. Preserve the live Windows process and its state.
- Current slice: inspect visible selection and non-mutating diagnostics; trace selected subject/run
  from UI command construction through member computation and coverage publication. Independently
  trace busy state from command acceptance through computation, publication, summary and render.
  Add real UI/public-command regressions for subject 1 vs 2 and the premature button-ready interval
  before minimal fixes. Reuse existing owners/presenters; no generic state machine or automatic retry.
  User requests correction of busy-button interaction; preserve layout/colors and use existing busy
  presentation. Two bounded workers own backend selected-target coverage and UI lifecycle respectively;
  coordinator owns native evidence, test-fidelity integration and exact-source delivery. Do not merge.

- Reopened after reported native failure on 2026-09-07 00:04: completed Evaluation sets repeatedly
  reject at publisher line 574 and subject-1 Individual saliency remains unavailable. Read-only
  provenance checks then establish the folder named xbrainlab-pr113-d9e59dd9 was created at
  cac5736c (worktree HEAD/reflog); Evaluation publisher and both result panels exactly match old
  cac5736c blobs. Its editable environment also points to that same old-source directory. Thus
  this report cannot yet establish a regression of d9e59dd9; it reproduces the old global guard.
  No merge. Verify the current production ports and deliver fail-closed source-checked launch steps,
  without manufacturing product patches or blaming the user for a version-identification gap.
- Immediate plan: trace exact selected-target identity and runtime adapters (including repeated
  reads without any mutation), then all individual/cohort saliency compute-to-read ports. Two
  nonoverlapping workers investigate Evaluation and saliency; coordinator audits actual Windows
  checkout evidence and test fidelity. Reproduce through real projection ports/ApplicationService,
  not only stable object-returning mocks. Fix only proven causes using existing owners; no retry,
  swallowed failure, guessed electrode mapping, or new compatibility state. Preserve UI presentation
  under existing authorization and all three unrelated local edits. Update progress with red/green
  evidence; run full exact-source delivery only after both reported read paths are explained and
  protected. Missing real-session state must remain explicit, not replaced by claims from toy data.
- Current audit outcome: no new product defect demonstrated on d9e59dd9. Current-source real
  ApplicationService import/epoch/saved-split/train followed by three Evaluation renders passes;
  actual Zhou EDF plus safe subject-1 checkpoint yields complete four-class Gradient and successful
  selected-member manager publication. This is not the lost native GUI state or active-other-fold
  end-to-end evidence. Native saved test/validation cover all four classes with finite outputs;
  saliency compute state was memory-only. Next: close old native process, switch its existing checkout
  to exact d9e59dd9 without force, verify HEAD and relevant source cleanliness, then launch its local
  interpreter. Keep d9e59dd9 as the unchanged PR candidate; retain failed native report as old-source
  evidence, not new-source acceptance or proof that every saliency failure is solved. No speculative
  product patch, test-count inflation, or rerun of the full unchanged manifest for this diagnosis.

- Reopened after failed Windows acceptance (2026-09-06 22:00, Zhou2020): selecting an already completed
  Evaluation fold while other training continues repeatedly raises the global training-boundary stale
  error; Evaluation remains slow; every subject-1 saliency view reports incomplete/recompute. The prior
  cac5736c desktop-source dossier is engineering history, not a passed Windows acceptance. Do not merge.
- New evidence: Evaluation still ties a completed member to the entire trainer token; an unrelated
  fold mutation invalidates its read. The panel contains an eight-attempt retry path. A same-source
  synthetic 2x5-fold profile measures catalog ~0.7 ms but each member materialization repeats one full
  EEG hash (~46 ms at 1720x16x1000 float32). This proves redundant read cost, not the whole reported stall.
  The actual local Zhou2020 BIDS tree has no electrodes.tsv/coordsystem.json, and returns settled
  unavailable before coordinate parsing; cold index ~8.9 s vs warm ~0.2 s. Missing geometry is not proof
  of a saliency payload failure and must not be silently replaced by a guessed channel mapping.
- User-authorized cleanup: delete unnecessary overdesign in these result-read paths even when its
  measured timing impact is small. Scope remains completed-result admission, read/publication,
  incomplete/recompute classification and directly related latency. No whole-repo SHA cleanup,
  Assistant/harness work, split changes, model changes or invented montage fallback.
- Outcome/assumptions: finished Fold A remains readable while unrelated Fold B trains; actual selected
  result replacement, reset, retraining and cancellation still cannot publish stale output. Diagnose
  subject-1 incomplete down to concrete coverage/producer/publication evidence; do not declare it fixed
  from the earlier balanced synthetic probe. Actual latest Windows in-memory payload may be unavailable;
  saved metrics alone cannot establish what saliency was published.
- Steps now: (1) two nonoverlapping read-only audits: lifecycle/read correctness and real BIDS/artifact
  evidence; coordinator measures costs; (2) converge on reproducible defects and deletion candidates;
  (3) add reachable public regressions before each authorized repair, using existing owners; (4) replay
  completed-A/active-B, selected replacement/cancel, interrupted/retrained multi-subject incomplete and
  repeated reads; (5) freeze a new scoped candidate and run the unchanged desktop-source/CI handoff
  workflow only after these failures are explained. No automatic retry increase or weakened assertions.
- UI authority: existing explicit permission covers internal UI-file fixes preserving presentation;
  no new layout/colors/copy or BIDS workflow change is planned. Stop for new visible design decisions.
  Complexity review precedes new owner/module/class or threshold crossing; prefer deleting global
  read coupling/redundant work rather than new cache, receipt or state machine. Root settings.json and
  the two unrelated Atomic trial group UI/test edits remain untouched. Rollback is a focused PR, not reset.
- Bounded Evaluation cleanup design: existing publisher/work controller/UI remain the owners. Remove
  Evaluation's saliency producer SHA metadata (only exposed as Qt properties, not used to protect its
  read), the trainer-wide activity veto and timer retry scaffold. Retain dataset epoch/split and trainer
  identity, exact selected plan/run/record admission, detached finite predictions, and selected-target
  replacement/cancel/worker cleanup checks before accepting a result. Unrelated progress must not
  invalidate an otherwise identical selected result in either publisher or UI callback.
  Also reuse admitted/committed state for Evaluation's training_active diagnostic instead of another
  whole get_state call; do not generalize into a new cached-state owner or change other workflows.
- Complexity review before continuation: cumulative #113 already touched nine production files/net412;
  this continuation is deletion/reuse-first in existing Evaluation/service/UI owners, with no new
  production module/class/receipt/state machine. Expected additional production net negative, exact
  +/- and file count must be checked before freeze. Keep saliency provenance intact until its separate
  actual incomplete cause is known. Split if >1500 production LOC or ownership must expand.
- Current next step: freeze the integrated follow-up and run the complete exact-source desktop-source
  manifest and CI. Focused coordinator rerun passes 320 tests across ten directly related modules.
  Evaluation now copies captured selected objects, allows unrelated unstable progress, rejects actual
  origin/target replacement and routes late callbacks by semantic origin. Its producer metadata,
  data-only wrapper, redundant selection pass and timer retry scaffold are deleted.
  The real-owner interrupted-round -> two five-fold Early Stop cohorts -> Compute B/A/A integration
  verifies all ten members and pooled/member reads, including replacing five incompatible A records
  without changing B. UI regressions distinguish never-computed,
  partial and all-invalid stored output. This is not proof of the unavailable Windows in-memory
  failure; no claim that the cross-selection SUCCEEDED bug explains every earlier recompute failure.
  No BIDS production change: this Zhou tree genuinely lacks the coordinate sidecars.
- Exact-source 0258da69 handoff stopped at complete-regression: the MOABB evidence journey's dynamic
  EvaluationRenderRequest constructor was missed by the initial call-site search and omits the new
  origin fields (same failure in CI). Migrate that one script caller and its recording fixture to
  source trainer/split origin from the actual publication; retain all journey/quality assertions.
  Scope is the direct API caller, not MOABB product behavior. Re-run its full test module, commit the
  correction and repeat the complete canonical manifest on the new SHA; no combining failed dossiers.
- Exact-source 73cefebd complete regression passes 10,842 tests (eight declared optional skips) and
  CI passes all 23 non-skipped checks. The subsequent visualization capture fails with its canvas
  hidden behind `Loading saliency visualization...`, despite recording render_settled=true and complete
  backend coverage. The capture wait recognizes only `Rendering saliency...` as nonterminal and can
  accept backend loading as a terminal error. Add a controlled loading-to-visible-canvas regression,
  fix only this capture readiness predicate (and recheck after draw/event delivery if necessary), and
  rerun the real capture without increasing timeouts or weakening geometry/result assertions.
  Independently audit the panel's queued summary/render callbacks before attributing the entire failure
  to the script; change production only if a real stale/loading overwrite is demonstrated.
  Capture-only repair: classify all three existing loading messages as nonterminal. Replaying the old
  predicate after an initial collection-path failure reproduces both new regressions; the repaired
  full module passes 72 tests. A real tiny-train/explicit-compute capture then passes all three 2D tabs
  and expected headless 3D blocking. The independent audit found no demonstrated product overwrite
  in this artifact. Freeze this script/test correction and repeat the full exact-source dossier.
- Follow-up complexity outcome: five existing production files, +271/-291 (net -20); cumulative
  against main, twelve existing files, +729/-337 (net +392). Existing owners unchanged; no new module,
  public class, cache, receipt or compatibility path. The additional files remove Evaluation-only
  bookkeeping and reuse the runtime boolean rather than build a second state snapshot.
- Measured working-tree evidence: the same Evaluation member workload now takes 0.34-0.64 ms with
  zero EEG/model SHA calls (previously ~46 ms with one each). Full ApplicationService Evaluate takes
  47-147 ms on that synthetic workload; the catalog helper alone is not the whole command. Actual
  saved Zhou EEGNet model fingerprints take ~2.2 ms for ten; these retained saliency checks detect
  changed models and are not deleted merely because Evaluation no longer needs them. Neither timing
  proves native Windows responsiveness. Full handoff must use the new source, not the old dossier.
- Latest subject-1 evidence: actual 22:00 manual-checkout test/validation records cover all four
  classes; safe selected early-stop checkpoint is finite. Replaying that checkpoint with real Zhou EDF
  event windows (four examples, not the unavailable exact saved heldout masks) produces sealed complete
  Gradient coverage. Next exercise the manager/terminal/publication/UI seam. Separately, the UI treats
  any same-method global SUCCEEDED job as evidence an uncomputed selected run is incomplete. Remove
  this cross-selection inference using existing per-run coverage/current-operation state; no new status
  owner or receipt. Red: compute Subject B, then choose never-computed Subject A: offer ordinary Compute,
  not incomplete/Recompute; compute A explicitly and verify its published coverage and member views.
  This is a correction of existing status semantics, not a layout/color/control redesign. Do not claim it
  explains all reported recompute failures without the full selected-job path evidence.
  Dispatch: coordinator owns scope/plan/integration; Evaluation and saliency workers plus a temporary
  independent two-file catalog-diagnostic cleanup worker under the user's multi-agent authorization;
  no model escalation/Fast.

### Previous candidate evidence (superseded by failed native acceptance above)

- Approval: user approved the complete cleanup plan and requested implementation on 2026-09-06.
  This section supersedes the earlier saliency investigation steps below. User subsequently confirmed
  #112 data-split manual acceptance and explicitly approved merging its f7ff0658 candidate. Complete
  #113 as a Desktop manual-test candidate; no #113 merge authorization. Leave #114 untouched.
- Evidence: synthetic real-owner 2x5-fold summary takes 1.102s cold / 1.141s warm, including 20 full
  EEG fingerprints (~95% hashing). Windows completed results now work but remain slow. Read-only
  review also found summary dispatch returning False can overwrite its settled failure dirty state;
  current private-helper tests do not cover the public UI update path.
- Outcome: validate and seal completed saliency once; display without full EEG or payload hashing;
  keep exact model/mask and semantic metadata checks. Both result pages show completed runs only,
  count valid Early Stop as completed, preserve original identities, and retain Compute for completed
  training without saliency. Fold Set admission still requires its complete valid cohort.
- Scope/non-goals: existing EvalRecord, provenance, TrainingPlan, saliency publisher, two result panels
  and shared display labels. No global EEG immutability, generic cache/revision owner, artifact schema
  change, dataset-specific behavior, whole-repo SHA removal, split changes or unrelated cleanup.
- Snapshot contract: detach arrays into immutable bytes, validate the detached candidate, then seal.
  Public array access creates lightweight views directly over bytes (not views exposing the canonical
  ndarray through .base); caller shape/dtype changes cannot alter the snapshot. Keep canonical metadata
  private, expose defensive copies preserving dict/list/tuple types, and reject sealed field replacement.
  Recompute creates and atomically publishes new records.
  Compute/load retain full verification; unsealed/incompatible records cannot take the fast read path.
  Post-seal unsupported direct numeric EEG mutation is not detected on every display; normal model,
  split and semantic metadata changes remain checked. Normalization produces separate display arrays.
- UI approval: hide incomplete runs/folds in Evaluation and Visualization; remove Run's (Finished)
  suffix; display generated Subject-1_0 as Subject-1-1, one-based, without renaming stored identities.
  Preserve all other layout/colors/copy. Fix summary failure settlement without automatic retry loops;
  retain generation fences, cancellation and equivalent-render coalescing.
- Complexity review: existing #113 production +171/-18 (net153), three files. Estimated cumulative
  nine files / net360-500 triggers review before implementation. Existing owners unchanged; no new
  module/class/control plane. Delete hot EEG/payload checks, redundant sealed-store finite scans and
  misleading async return-value assignments. Keep normalization/pooling checks. Two bounded workers
  own backend snapshot/read changes and UI lifecycle/labels; coordinator integrates and verifies actual
  +/-/net before handoff. Split further if >1500 production LOC or ownership must expand.
- Steps: (1) public failure and snapshot/selection red tests plus passing artifact characterization;
  (2) backend sealing/read changes and independent UI correction; (3) focused regression, alias/tamper,
  stale/cancel/repeat and mixed completion coverage; (4) measure same-size cold/warm/A-B-A/Fold Set
  timings, hash calls and sealing memory; (5) exact-source UI/source-diverse/static/canonical gates,
  focused commit/push and update existing draft PR. The approved handoff continuation now permits
  merging #112 after exact-source CI/acceptance checks, then retargeting #113 to main without mixing
  either #114 or local settings/split edits into the candidate.
- Validation floor: zero full EEG/payload hashes after sealing in summary/single/cross-fold reads;
  disk tampering and model/mask changes reject; shape/dtype/source-alias/metadata mutation cannot
  corrupt sealed results; values/shapes/classes unchanged; public worker failure settles once.
  Keep P1/P2 recovery, cleanup/heartbeat and interrupted/retrained cohort tests. Replace private-only
  failure tests and live-payload-mutation expectations, not artifact tamper coverage.
- Stop condition: use the existing desktop-source profile and its accepted bounded Assistant baseline,
  not the stricter Stable promotion profile. Missing exact-source/canonical/CI evidence remains a
  checkpoint; Windows manual acceptance for #113 remains a later user gate.
  Prior four-file Assistant shard timeout must be investigated without reducing the denominator.
  Preserve settings.json and unrelated Atomic trial groups UI/test edits. Rollback only this slice's
  focused commits through a PR; do not revert user changes or rewrite persisted results.
- Dispatch: coordinator supervises; two existing-owner workers; no model escalation; Fast off.
- Progress: snapshot source-alias/header test reproduced corruption; four public summary-failure tests
  reproduced dirty-state overwrite. Full prior four-file Assistant timeout selector replay passed 23/23
  with coverage in 8.73s; this does not explain the earlier timeout or replace final canonical evidence.
  Same exact baseline synthetic benchmark: summary warm 1.173s (20 EEG/40 payload descriptor calls),
  single warm 0.126s (2/4), pooled warm 0.598s (10/20). Working-tree candidate summary/single/pool
  warm reads measured 0.004/0.006/0.024s with zero full EEG/payload hashes and equal arrays/shapes;
  setup peak RSS rose about 22 MiB for ~21 MiB per-record payload detachment. Final SHA rerun pending.
- Simplification during implementation: recursive metadata freeze/thaw changed tuple/list identity in
  artifact verification. Replace that conversion with private canonical copies + defensive getters,
  preserving the existing strict serialized types; no frozen-list type or compatibility adapter.
- Final bounded implementation: fresh dict/read-only-array views preserve existing coverage admission;
  no MappingProxy compatibility branch. Exact model/mask/sfreq mutation rejects with the existing
  SaliencyContextError semantics. Reuse the original context builder with a sealed fingerprint rather
  than adding a second metadata parser. Private async refresh returns None; both result pages use the
  same name formatter without an ordinary-name exception.
- Focused checkpoint: six full related backend files 210 passed; related UI plus training-refresh
  integration 170 passed; four real lifecycle/UI/workflow integration files 40 passed. Real MNE/EEGNet
  five-fold probe computes and renders Fold Set 3 after two incomplete historical cohorts, including
  Early Stop completion. These overlapping working-tree runs are not a summed final dossier.
  Basedpyright reports zero new diagnostics; architecture and Ruff checks pass. Coordinator inspected
  populated/empty selector captures; these fixture captures do not prove native Windows rendering.
- Complexity outcome before freeze: cumulative #113 production +458/-46 (net412), nine existing files,
  no new owner/module/public class. Additional LOC closes mutable-alias boundaries in the existing
  result API; display no longer repeatedly hashes the data. No global input immutability or new cache.
- Exact-source checkpoint: source commit 4c08f35 passes static/type/docs/architecture checks. Canonical
  regression phase 1 found six stale expectations (five exported-container identities and one empty
  Evaluation catalog); update their observable content/isolation and public-read assertions. No new
  production repair is needed for these failures. Focused export/artifact tests pass 64; the Evaluation
  publication module passes 22. Later canonical phases remain unexecuted, not passed.
- Second canonical pass: all five unit groups pass on e0b8f104. Integration identifies one stale
  semantic-workflow producer double and the old Run Finished walkthrough assertion; both are corrected
  without production changes (focused 18 and 10 passed). Six public-fixture failures came from this
  validation checkout's symlink paths; replacing only its fixture links with local copies makes all
  four affected integration modules pass (13 tests). No import behavior/test expectation was weakened.
  Repeat the complete exact-source manifest after these test corrections; do not combine old runs.
- Third canonical pass: eaab6990 complete regression passes 10,829 tests with eight explicitly optional
  fixture skips. Source-diverse training also passes. Visualization capture renders a valid settled
  Saliency Map but its old provenance parser rejects the approved parenthesized fold descriptor;
  it then misleadingly reports missing Spectrogram evidence. Update only the capture parser and its
  characterization test, preserving nonempty dataset/run and positive fold identity checks. No product
  rendering change is needed. Xvfb and strict model gates also need a native-environment retry:
  the existing Xvfb helper and a CUDA allocation probe both pass outside the restricted sandbox.
- Final candidate checkpoint: pushed 143aace647e35052600414511391fe66da968936. The native-environment
  full manifest passes complete regression (10,829 passed, eight declared optional-fixture skips),
  static/type/docs/architecture, wizard capture/validation, baseline/startup, three 2D visualization
  tabs plus expected headless 3D blocking, lifecycle/stress and required data/import/training checks.
  Source-diverse evidence covers class-grounded PhysioNet EDF/BBCI GDF training plus SCCN EEGLAB/MNE
  CNT import and missing-label admission boundaries. The exact five-fold MNE/EEGNet probe renders
  Fold Set 3 after incomplete historical cohorts. Display hash calls remain zero in the measured
  summary/member/pooled paths; timings are backend synthetic evidence, not Windows latency acceptance.
- Correction: selecting the default strict promotion gate was an execution error. The complete 143aace6
  report matches the already accepted baseline: 36/36 positive, 10/10 explicit-origin and 5/5 missing-origin
  guards, 22/24 precision and 6/7 clarification. Exact model revision, frozen case files and 81-case
  inventory match; observed failure IDs are precisely the three approved baseline cases. The existing
  bounded-baseline checker returns passed. Do not open a new Assistant repair or raise the threshold.
- Next: record the user's #112 manual acceptance and merge approval, recheck exact head/base/CI and merge
  with a merge commit. Retarget #113 to main, correct PR evidence claims, freeze scoped docs/source and
  run the complete canonical desktop-source manifest in the clean handoff worktree. Use native Xvfb/GPU
  access, local copied fixtures and PATH including WSL NVIDIA utilities; keep all registered gates,
  including RAG, resource calibration and the desktop-source dashboard. Require exact-head CI success,
  coordinator artifact inspection and final narrow review before delivering SHA, Windows commands and
  the interrupted/retrained Fold Set 3 checklist. Keep #113 unmerged and #114 unchanged.
- Dispatch for handoff continuation: coordinator owns Git/PR/CI and inspects final artifacts; one worker
  runs the canonical manifest, another performs bounded read-only diff review. No production changes
  are planned, no new UI/API behavior, no new owner/cache/compatibility layer. Preserve settings.json
  and unrelated Atomic trial groups UI/test edits. Rollback, if needed, is a focused PR, never a reset.

## Prior saliency investigation evidence — interrupted retraining and warm-view latency

- Evidence: Windows Zhou2020, two subjects/85 recordings, Individual five-fold CV; stop first
  training midway, enable Early Stop and finish a second training. Compute Saliency appears to
  freeze the GUI; Fold Set 3 (subject 1) and its member results request Recompute while Fold Set 2
  can render slowly. The application has been closed and no runtime saliency error was logged.
  Saved second-round Test/Validation evaluations cover all four classes in all ten folds; saved
  metrics do not preserve the later in-memory saliency update, so they cannot prove compute failure.
- Outcome: identify and repair demonstrated saliency lifecycle/read-path defects, including repeated
  opening of already-computed output; preserve mathematical output, exact fold/run/model provenance,
  integrity rejection and the current visual design. Separate genuine missing output from an
  unrelated completed job's UI status. Do not attribute the report to split coverage without evidence.
- Priority clarified by user: Fold Set 3 being unusable is the primary blocking defect; performance
  is secondary. Acceptance requires interrupted training -> completed retraining -> explicit Compute
  for the affected cohort -> renderable cohort and member runs. Correct copy or improved latency
  alone cannot close this slice.
- Further user evidence: explicitly selecting the affected Fold Set and using Recompute still leaves
  no viewable output. A never-targeted cohort with misleading global status is not an adequate root
  cause. Audit non-deterministic read/publication races with controlled interleavings; a passing
  sequential synthetic run must not be used to rule out the reported defect.
- Scope/non-goals: audit compute selection, cancellation/retraining, publication, summary validation,
  render preparation and warm reuse. No split policy, model, import, dataset-specific behavior,
  new cache owner/control plane, arbitrary performance rewrite, or unrelated cleanup.
- Assumptions: current runtime artifacts were lost on application close; bounded synthetic scaling
  and real persisted evaluation metadata supplement, not replace, exact Windows reproduction.
  Previously measured five context validations on 207 MiB synthetic EEG plus 21 MiB saliency cost
  0.506–0.519 seconds; this alone does not establish the long freeze's cause.
- UI confirmation: user explicitly authorizes internal UI file/read/event/async corrections without
  asking per file (2026-09-06: do not ask for each UI file edit; preserve UI presentation). Existing
  layout, colors, buttons and copy stay unchanged; no redesign or new visible workflow is authorized.
- Steps: (1) parallel read-only lifecycle and render audits; (2) measure cold/warm summary and render
  stages with production objects, including dataset-size scaling; (3) converge on smallest proven
  repairs in existing owners, with red reproductions before implementation; (4) focused integrity,
  target identity, cancel/retrain, numerical parity and repeat-load verification.
- Validation: distinguish empty log, missing runtime artifacts, no output, rejected provenance,
  expensive validation, and actual compute/render work; record timings and environment. No claim of
  Windows acceptance or handoff-ready without the canonical applicable handoff gates.
- Stop: report any required UI/public-contract decision before implementing it. Complexity review
  before new owner/module/public class, >8 production files or >300 net production LOC. Preserve
  settings.json and the completed uncommitted Atomic trial groups row removal. No merge.
- Dispatch: coordinator integrates evidence; two non-overlapping agents audit lifecycle and render
  performance. Existing-owner investigations need no model escalation; Fast off.
- Active repair: tag successful `VisualizeCommand` summaries with the exact verified committed
  publication generation, matching `EvaluateCommand`. This is an internal async-read coherence
  repair only: no visual change, saliency computation change, new owner, state or public class.
  First add a red service-level assertion that the tag equals the committed publication and retain
  the existing crossing-training-read rejection; then make the smallest existing-owner change and
  run the focused service/race checks. Stop if the tag cannot be bound to the same verified
  publication without changing the command contract more broadly.
- Baseline: directly related saliency render, post-training lifecycle and artifact-integrity suites
  pass unchanged (93 tests, 5.23 seconds). They do not yet reproduce the reported Windows blocker;
  do not treat existing green tests as evidence that Fold Set 3 works in the reported workflow.
- Sequential characterization: real MNE epochs/EEGNet, four classes, five new early-stop-enabled
  folds and two unfinished historical cohorts compute and render exact Fold Set 3 successfully.
  This narrow backend happy path excludes UI timing and actual Zhou arrays. Investigation now
  prioritizes replaced records vs accepted publication, stale summary/coverage and late render
  results around recomputation, including injected callback ordering.
- Candidate read defect: saliency summary query can retain older cross-fold choices while accepting
  a newer recompute publication; callers unconditionally clear the dirty flag after the query. Unlike
  the existing Evaluation query path, the summary has no publication-generation coherence check.
  Prove the interleaving with a focused regression, then reuse the existing Evaluation boundary
  pattern without changing presentation or weakening saliency provenance/integrity validation.
- Bounded repair assignment: backend worker owns VisualizeCommand's verified publication-generation
  diagnostic in the existing ApplicationService plus public-service red/green coverage. UI worker
  owns VisualizationPanel summary/result coherence, preserving invalidations during queries and
  automatically retrying the latest accepted generation, plus controlled-interleaving UI tests.
  Two existing production files expected; owner count unchanged, no durable cache or weakened hash
  checks. Keep old copy/layout intact. Partial-success and numeric-summary optimization stay deferred
  until the primary read defect is tested; do not broaden the diff merely because audit found them.
- Backend repair evidence: missing Visualize generation tag fails the added assertion before repair;
  post-repair Evaluate/Visualize generation and crossed-read selectors pass (4 tests). Entire
  ApplicationService test file passes (282 tests, 17.79 seconds); warnings are existing short-signal
  filter and upstream NumPy/MNE deprecations, not saliency failures.
- UI red evidence: a controlled runtime returns P1's successful summary then exposes P2's newer
  publication before UI acceptance; old code accepts the mismatched pair. Follow-up regression must
  prove automatic recovery of the selected cohort, not merely rejection or manual second query.
- Performance baseline: real holder/provenance/EvalRecord types, synthetic 2x5 folds with 16x1000
  float32 inputs and 344 held-out trials/fold: computed cross-fold summary 1.102s cold / 1.141s warm;
  approximately 95% is hashing, with 20 full EEG fingerprints per query. No-saliency query 0.100s;
  pooled render arrays about 0.04s. These are Linux synthetic measurements, not Windows timings.
  Any responsiveness repair must retain full integrity checks and reuse existing owned async work.
- Primary controlled-interleaving repair now protects both on_update and whole update_panel entry:
  retain selected controls while a summary is dirty, queue the accepted newer publication through
  the existing ledger, and defer recording it as rendered until coherent choices are rebuilt.
  The whole-panel regression caught an additional lost-recovery path in the initial narrow fix.
- Next bounded performance step: execute the same VisualizeCommand through the existing owned
  execute_application_command_async runner. One panel-local active callback token and the existing
  dirty flag coalesce updates; callback acceptance keeps the new generation check and existing ledger.
  No synchronous product fallback, new worker owner, state machine or durable validation cache.
  Preserve controls/selection while loading, use only existing copy, and fence late callbacks on
  cleanup. Estimated additional production +55/-15 LOC. First red test must prove Qt heartbeat and
  selector responsiveness during an intentionally blocked summary; then verify stale replacement,
  successful latest-generation rendering and close/deletion suppression. Total scope remains the
  same two production owners; review actual size before exceeding the existing complexity limits.
- Direct same-outcome backend guard: audit also found an explicit multi-member compute can silently
  skip a member with unavailable evaluation and publish the other updates as SUCCEEDED. This yields
  an unrenderable cohort despite a successful job, matching the failure class under repair (not
  established as the exact Zhou cause). Add a red scheduler regression and require every explicitly
  selected member to produce an update before any publication; otherwise reuse existing
  evaluation_unavailable failure and preserve previous results. Do not change class/split fallback
  policy, automatic batch semantics, UI copy or add another owner. One additional existing production
  file (TrainingManager), expected <=20 net LOC; root reviews exact member identity, not just counts.
- Current checkpoint: generation-paired async summaries and explicit-member all-or-nothing
  publication are implemented in three existing production files, without a new owner, visual
  design change or weakened artifact checks. Controlled P1/P2 tests cover automatic selected-cohort
  recovery; a held worker leaves Qt responsive and cleanup suppresses its late callback. For the
  heartbeat case, the old-source failing test was replayed after implementation, not a clean
  test-first sequence. Do not overstate that ordering or claim exact Windows reproduction.
- Focused evidence: backend saliency/integrity/context checks (134), related integration checks (38),
  and Visualization regression checks (198) pass on the working tree. Basedpyright reports zero new
  diagnostics. Seven offscreen main-window captures match approved references; the coordinator
  inspected Visualization. This empty-state capture does not establish affected Fold Set usability.
- Architecture scan passes after migrating only the exact detached CommandResult storage exception
  to its async acceptance method; no checker rule or domain-object permission was broadened.
- Authorization/delivery: user explicitly authorized commit, push and a separate PR on 2026-09-06;
  no merge is authorized. Deliver only the three existing saliency owners, their direct tests and
  exact architecture exception migration. This branch is stacked on open PR #112; document that
  dependency and retarget/rebase requirement rather than claiming an intended-main handoff.
- Next evidence state: exact-commit PR CI, source-diverse handoff evidence and Windows native
  acceptance remain outstanding. Preserve the user's settings and earlier Atomic trial groups
  removal; do not merge.
- Regression follow-up: the full canonical UI shard exposed one existing synchronous assertion in
  `test_training_result_presentation`: `update_panel()` now dispatches a background summary read,
  so the test must wait for the accepted Qt callback before asserting the same blocked Command API
  result. Migrate that direct test only; do not add a synchronous fallback or alter product/UI copy.
- Follow-up validation on the exact PR head must similarly distinguish one published saliency
  revision from the two internal UI phases (summary dispatch, then accepted render). Preserve the
  exact one-publication/event assertions while waiting for the accepted result in stale synchronous
  integration tests. The native-render stress runtime must return the same generation diagnostic
  required of the real `VisualizeCommand`; this is fixture-contract parity, not a render timeout
  increase or production behavior change.
- Direct slow-open defect: `_SaliencyRenderTask` currently compares its owner-only `operation_id`,
  so a fresh UI task for the active request is falsely different after the owner assigns its ID.
  Coalesce that exact request, retain different normalized variants and discarded-result requeue,
  and verify both duplicate-request and current-error behavior with a nonempty operation ID.

## Historical #112 repair — import capacity and split/epoch feedback

以下為已合併 #112 的施工紀錄，不是 active dispatch；其舊的 pending／next 不再生效。

- Evidence: Zhou2020 subjects 1+2 select 85 event files and hit the application-only 64-file
  mapping limit. Windows manual preview with 1,719 atomic trials, Full Data, Trial validation/test
  0.2/0.2 stays Calculating; repeated edits are slow. User also reports suspicious 0.2/0.3 counts.
- Outcome: all selected labels reviewed/importable subject to existing resource admission; responsive,
  deterministic split preview with original-scope ratios; continuously available gray Back matching
  Confirm; expected invalid settings recover without ERROR tracebacks; concise epoch and result UI.
- Explicit UI approval: user requests removing Suggested by, shortening duration-variability warning/
  checkbox, removing Hover/Showing/totals duplication, and always-available Back (2026-09-06).
  Preserve five-stage import and existing split table/colors; keep safety acknowledgement semantics.
  Follow-up approval: remove the 50-row split-result cap entirely; show all rows with the existing
  scrollbar, no pagination, external summaries, or truncation notice (2026-09-06).
- Scope: existing label admission/preview, allocator hot path, split preview lifecycle/error projection,
  epoch presentation, directly related regression tests and UI artifacts. No new owners, solver,
  dataset adapters, silent partial imports, settings edits, or unrelated cleanup.
- Assumptions: ratio targets count original atomic groups; unequal group row sizes need not yield exact
  row percentages. Integer rounding and preview/Train parity must be verified, not inferred from UI.
- Steps: (1) red tests and timing for 1,719 groups at 0.2/0.2 and 0.2/0.3; (2) preserve selection
  objective while eliminating repeated row-mask scoring; (3) lift label file-count cap with existing
  resource checks; (4) simplify UI and route expected validation outcomes without generic failures;
  (5) focused regression, cancel/repeat checks, screenshot inspection and canonical handoff gates.
- Validation: real selected label scopes >64, ratio/atomicity/classes/determinism, preview vs materialized
  counts, repeated edits/cancel/Back, retained true-error diagnostics, epoch acknowledgement, complete
  table access, source-diverse data and exact-source UI/static/CI evidence for handoff claim.
- Stop: no new owner/public state machine or broad solver; review complexity before >8 production
  files or >300 net production LOC. Missing native/exact-source gates remain checkpoint, never handoff.
- Dispatch: bounded workers own allocator, UI and label capacity; coordinator reviews integration/
  evidence only. Preserve user's modified settings.json. No merge authorization for new source.
- Progress: file64 and row50 caps removed; UI uses gray Back, preserves Step2 draft and cancels obsolete
  work immediately on edits; expected preview preconditions are distinct from unexpected exceptions.
  Allocator scores fixed group-label counts instead of repeatedly materializing row masks, with no new
  owner or changed greedy objective. Ten production files after the bounded import dependencies below,
  currently net deletion overall.
- Measured checkpoint: baseline 1,719-group .2/.2 timed out after 30 seconds; new sequential .2/.2,
  .2/.3, .2/.2 core allocations measured 0.085/0.112/0.098 seconds. Uneven/mixed/rotated small cases
  matched baseline full masks and infeasibility outcomes. This is not yet Windows repeat-UI evidence.
- Real label checkpoint: Zhou2020 actual 85 TSVs reviewed through resource admission, 3,398 timestamp
  labels, four classes, safe resource preflight; EEG materialization still being verified separately.
- Real-service offscreen checkpoint: actual ApplicationService + preview dialog with 1,719 verified
  nonoverlap atomic trials, one subject/seven sessions/four classes: initial .2/.2 0.097s; QLineEdit
  validation edit to .3 0.378s; back to .2 0.352s (edits include 250ms debounce). Counts match the
  original-scope contract; reject leaves no live worker and service closes, no ERROR observed.
- Focused final-tree checkpoint: Dataset/split application 623 passed; UI/epoch 165 passed; labels
  61 passed; real-source workflow/duration/training 14 passed. Basedpyright reports zero diagnostics,
  architecture compliance and production Ruff pass. One initial output-directory sandbox failure
  passed on the complete 623-test rerun with appropriate test-output permission. These are dirty-tree
  engineering runs, not an exact-source handoff dossier.
- Coordinator inspected actual-dialog offscreen captures in `/tmp/xbrainlab-split-epoch-repair/`:
  Calculating+Back, expected failure+Back, scrolled Fold51 and concise epoch acknowledgement.
  Captures use synthetic data; Windows native acceptance remains outstanding.
- Pending full-scope evidence: actual 85 EDFs (1.37 GB) have normal Safe preflight (8.7 GiB estimated
  RAM, 29.5 GiB available, no confirmation/refusal). The initial composite probe included an extra full
  Scan before Review and did not complete within 600s; its exact owned session was interrupted. This
  does not demonstrate the BIDS UI path timing (UI uses catalog-only Scan). Corrected stage-timed
  probe completes catalog Scan in 9.106s; Review stack samples advance through resource preflight and
  admitted BIDS resources in Path.resolve on the WSL-mounted dataset. No deadlock/resource refusal
  established. Keep identity guards; no speculative path caching/extra production scope. Complete the
  bounded UI-equivalent probe before any full85 EEG materialization claim.
- User continuation (2026-09-06): proceed through a manual-test candidate, including commit, push and
  PR #112 update/CI verification; do not merge. Commit only task-owned paths; preserve settings.json.
- Remaining: read-only/measurement classification of post-import montage-close warning, freeze source,
  commit/push the scoped repairs, run canonical exact-source handoff and inspect required UI/CI evidence.
  Coordinator supervises; existing label worker investigates montage, UI worker checks Windows artifact
  capability, allocator worker reviews split repeat/lifecycle protection. Do not broaden production scope
  without a reproduced directly coupled defect and plan/complexity update.
  Canonical full handoff runner correctly rejects dirty source; no exact-source handoff claim yet.
- Direct dependency repair / complexity review: corrected user-like Apply also exceeded 600s after
  applying all85 labels, in recipe transaction path identity recording. `_label_import_carrier_plan`
  previously resolved each mapping's carrier and current carrier inside the 85x85 loop (14,450
  resolutions before further recipe work). Replace that comparison with one invocation-local carrier
  index. Keep the same resolver, identity/freshness guards, recipe data and existing session owner;
  no persistent cache/new owner/public class/module. This adds a ninth production file, triggering
  explicit review: prior eight-file production diff +142/-179/net-37; allow a <=30-line net local
  indexing repair, otherwise stop/split before expanding. Deletion candidate is the nested rescan;
  no resource/preflight optimization elsewhere. Red cost+recipe equivalence test precedes the fix,
  then existing recipe/symlink/label regressions and one bounded full85 UI-equivalent rerun.
- Dependency repair implemented: nine production files, total +151/-184/net-33; same recipe resolver
  indexed locally, no owner/cache/guard change. 85-case actual resolver calls fall from 14,620 to340
  while exact pairing (including portable path alias) remains equal; many-to-one recipe roundtrip
  remains protected. Combined state/labels/real-source regression 101 passed, no skips. The one final
  full85 real Apply run exceeded its 600s bound in BIDS channel matching; all EDF headers were read,
  but authoritative Apply completion is not proven. No unbounded retries.
- Second measured dependency / complexity review: `_prepare_channel_apply_plan` repeats canonical
  loaded-file and reviewed-file resolution inside another 85x85 matching loop. Delete this nested
  rescan using invocation-local canonical-path and basename indexes in the existing channel apply
  function. Preserve exact-path preference, ambiguous-match rejection, prepare-all-before-mutation
  and rollback; no persistent cache, new owner, public class, module, or weakened identity guards.
  Current nine-file production +151/-184/net-33; tenth existing file is a bounded <=30-net-line
  exception for the directly blocked 85-file import, not general resource/path optimization.
  Require red 85-run resolver-cost test plus real channel mutation/equivalence/ambiguity/rollback
  checks, focused regressions and one final stage-timed 600s UI-equivalent Apply probe.
  Stop and report a checkpoint if that still cannot complete; do not expand to other I/O owners.
- Channel dependency implemented: tenth file +12/-12/net0; total production +163/-196/net-33.
  The 85-run cost test failed at 14,620 resolver calls before repair and passes below500 afterwards,
  with actual MNE bad-channel mutation. Exact preference, unique/ambiguous basename, duplicate
  canonical aliases, and rollback are covered. Combined final-tree import/state/channel/source-diverse
  regression: 114 passed, no skips; architecture compliance, zero-diagnostic Basedpyright and all
  changed Python Ruff lint/format pass. These remain workspace engineering evidence, not exact-commit
  handoff gates. No further production edits planned. Final bounded full85 run exits0: Scan10.524s,
  Review133.196s, Validate3.899s and Apply255.295s all succeed. Authoritative state assertions verify
  85 raws, subjects1/2, 85 carrier plans, 3,398 labels and feet/left_hand/rest/right_hand classes.
  Evidence: `/tmp/zhou2020_two_subject_final.log`. Do not infer Windows timings or all-MOABB support.
  Closing the probe additionally logs a BIDS montage preparation quiescence timeout warning; this is
  not an Apply rejection but remains a separately disclosed background-close observation. No new
  montage/lifecycle implementation is included in this bounded slice. No commit/push/merge yet;
  settings.json remains untouched. Status stays checkpoint pending exact-source PR/CI handoff gates.
- Handoff continuation: 85-path montage-only measurement completes in53.185s; after a30s warm wait,
  close fences publication immediately but its2s join expires, then the worker drains18.352s later.
  Existing cancellation tests protect discarded results/no callback. Optional pending geometry limits
  automatic electrode/topographic presentation, not import/epoch/supervised training/evaluation or
  saliency computation. Keep this platform timing limitation disclosed; no montage production edit.
  Fix the validation environment's stale editable-install path using `poetry install --only-root`;
  dependencies and product source remain unchanged. Freeze and commit the task-owned repair paths,
  then fast-forward PR #112 head and run same-SHA local/CI evidence. Windows DPI automated evidence
  will come from its native CI job because this WSL session cannot start Windows executables.
- Exact-head CI repair: Linux UI integration still asserted the old verbose duration-warning and
  checkbox strings in `test_dialog_acceptance.py`. User explicitly approved shorter copy; the retained
  backend requirement/modal/receipt and invalidation assertions remain authoritative. Scope is that
  integration test plus `tests/unit/ui/test_dialogs_extra.py`, which also asserts the retired long
  phrase: assert the approved concise visible text while retaining all confirmation safety
  assertions, reproduce the CI failure locally, then run the whole file and directly coupled UI tests.
  No production change. Commit/push this test-only correction and refresh final exact-source evidence;
  fa3e65a2 evidence/CI cannot certify the newer head. Keep settings.json out of hooks/staging.
- Test-only CI correction validated: the two affected files plus epoch layout tests pass74 cases;
  backend confirmation message, checkbox-gated admission and receipt invalidation are unchanged.
  Exact fa3e65a2 real85 Apply also succeeds (Scan9.902s/Review137.054s/Validate4.666s/Apply299.925s),
  and its native Windows100/125/150 artifacts were validated and visually inspected. These are
  production-identical predecessor evidence only; final CI/manifest must bind the corrective head.

## Current baseline

產品基線只由 Git 的 `main` 決定，不在計畫保存第二份 current SHA。#112 已依使用者手測通過與
merge 批准合併；#113 的新 source 尚待重新手測，#114 不在本次修理範圍。Repo-root
`settings.json` 的本機修改由使用者擁有，絕不可 stage、commit、revert、覆寫或隱藏。

## Historical #112 contract — Data Splitting materialization and preview

以下是已合併實作的歷史計畫，不是第二個 active slice。現行產品語意以 current／architecture 為準。

### Problem and evidence

- 現有可選的 `Disable`/`*_IND` 與 Train admission 不一致：Test Disable 和 Individual 的 Subject/
  Independent 組合能在 preview 出現，卻不能產生有效 train/evaluation partition；Validation Disable
  也會留下 truthy holder，導致 Train 與 preview 的含義不同。
- 現有 ratio 在 test 後再對剩餘資料切 validation，且對 epoch rows 而非原子 group 計算；KFold 可接受
  `K=1` 或對不足群組產生少於 K folds。preview 只顯示計數、save 與 Train 又各自 materialize，沒有可驗證
  的 allocation identity。
- Session 現況以 subject-session pair 而非跨 subject 的同名 session label 分組；manual empty、字串 bool
  及明確 `{}` split config 亦可能被靜默接受或回退 legacy。這些皆會使使用者的 split 選擇無法可靠解釋。
- SSVEP 的 frequency class 是既有 supervised label，不需要 frequency adapter；MAMEM1 已證明 import/
  epoch/training 路徑可用，但 split contract 必須使 frequency classes 和任何 BIDS/MOABB supervised
  classes 同樣可重現地進入訓練與評估。
- Exact-head audit 所列的 admission、audit parity、cancellation、Validation Disable Ratio nearest-feasible、
  mixed Manual residual 與實際 materialization evidence gaps 均已在既有 owner 關閉；回歸測試覆蓋 strict
  structured payload、pair-scoped provenance、preview/Train 同 audit、cancel linearization、Manual scope/
  duplicate/atomic constraints，以及 CV Validation Number 的 exact cardinality。這仍是 bounded contract，
  不是任意資料集的科學品質或 complete-solver 證明。
- Exact-head supplemental complete regression 發現的兩個 stale UI root-contract tests 已以 observable
  `DataSplittingDialog` kwargs 更新，現在傳遞已批准的 saved split rehydration
  `initial_specification`；production/UI 均未改動。
- Exact-head CI 三平台失敗收斂的兩個 stale integration tests 已完成：(1) product walkthrough 的 12 original
  trial groups、Test/Validation 各 `0.25`，依批准的 original-scope contract 使用 `6/3/3`；(2) training
  recommendation synthetic `Epochs` fixture 已提供真實 shape 的 verified non-overlap epoch-window provenance。
  production audit 未放寬。
- Exact-head CI `linux-integration-rest` 的六個失敗同樣都是 stale sequential-ratio expectations，audit 均
  通過：`application_service_workflow` 的 `7/2/3` 改為 `6/3/3`；checked-in GDF `A01`（total 273）由
  `176/43/54` 改為 `165/54/54`，`A02/A03`（各 total 270）由 `173/43/54` 改為 `162/54/54`，涵蓋三個
  training-smoke cases 與一個 CUDA OOM case；`real_data_command_spine` 的 `A01` 亦為
  `176/43/54` 改為 `165/54/54`。scope 限 tests/docs，不改 production。
- `application_service_workflow` 同一 integration test 另有 direct stale assertion：顯式空
  `split_config` 舊期望成功；批准契約只有 `None` 可走 legacy default，顯式空 rules 必須 fail closed 並保留
  state。scope 限 tests/docs，不得放寬 production。
- 上述七個 stale expectations/assertions（六個 count 與 explicit-empty assertion）均已修。Aggregate old-head
  job 未提供額外測試；它因缺 provenance sidecar 而正確 fail closed，不是 Data Split regression。
- Canonical manifest 在 `origin/main` 已有 direct-script `ModuleNotFoundError`，無法完成；supplemental full
  regression 的 `llm-rag` 缺 `langchain_huggingface` 亦為環境問題。兩者不得混為本 Data Split defect 或
  handoff evidence。

### Outcome and exact contract

- 保留 Data Splitting `Step 1 → Step 2 → Save → Train` workflow 與 Data Import 五個階段。Full 支援 Test
  `Trial|Session|Subject`；Individual 支援 `Trial|Session`。Validation 為 `Disable` 或該 training mode
  可用的任一 unit，且可與 Test 混用；所有
  Independent variants 及 Test Disable 移除，Individual Subject 一律拒絕。
- 非 CV 的 Test/Validation units 支援 `Ratio|Number|Manual`；CV Test 僅 exact `KFold`，CV Validation
  僅 `Disable|Ratio|Number`。Test 一個 rule、Validation 零或一 active rule；舊 invalid payload 必須要求
  reconfigure，不能靜默 rewrite。`None` 才可走 legacy default，明確 `split_config={}` 不是 legacy；JSON
  boolean 必須是實際 bool。
- Trial 為 temporal-overlap atomic group；Session 為所有 subject 共用同名 session label；Subject 為整個
  subject。Test 從 Train+Validation 隔離，Validation 從 Train 隔離；混用策略遵守各自的隔離單位。
- Ratio 以原始 scope 的 atomic group count 算，Number 是精確正 group 數，Manual 必須非空、無重複且在 scope。
  Test/Validation capacities jointly computed，最小化 requested test/validation target 的總絕對偏差；同分時
  優先更多 train、較小 test deviation、stable group key。每個 required split 必須非空，否則 preview 阻擋。
- K 必須 `2 ≤ K ≤ groups` 且每個 scope 有 exact K folds；test groups 不重複且聯集等於 scope。確定性、
  bounded 的 allocation 在固定 capacities 下優先完整 evaluation coverage，再 class×partition coverage/
  imbalance 與 stable ID。train 全 classes 是 hard constraint；不切 atomic group。
- Preview 與 Train 使用同一 canonical materialization/audit；receipt 保存 allocation materialization digest，
  Train 重新算 rows/coverage/digest，任一不符 fail closed。Preview row 顯示原始 group、selected group、row
  counts、missing class display names 與 `saliency_source=test|validation|unavailable`。若 test class 不全但
  validation 完整，沿用 validation saliency fallback；兩者皆不完整時允許訓練/evaluation，但該 fold 不產生
  saliency，其他 eligible fold 仍繼續。
- `preview_receipt=None` 保留既有 unreviewed deterministic command path：Train 仍以同一
  `DatasetGenerator.generate()` 與 audit materialize，但不宣稱或比較 reviewed-preview parity。提供 receipt
  時必須有 canonical SHA-256 digest（`unbound`/手工 placeholder 一律拒絕），Train 必重算並 fail closed。

### Scope, non-goals, ownership, and complexity

- Scope：既有 split domain/application owner 內的 enum/config admission、atomic allocation、audit、preview
  publication、receipt/materialization comparison、training saliency admission，及直接 backend tests。UI worker
  只消費 backend truth，另行處理已批准的 dynamic grid、Step 2 copy、manual chooser、rehydration 與 lifecycle。
- 本次直接相關的舊測試也在 scope：盤點並刪除已退役的 Test Disable／Independent expectation，將 mock-heavy、
  繞過 production command entrypoint 或只複製 helper implementation 的 split tests，以最小且較強的
  domain/command/materialization replacement 取代；不進行全 repo test cleanup，也絕不以刪測使 suite 變綠。
- Non-goals：不加 SSVEP/frequency adapter、CCA/FBCCA、dataset-specific split rule、solver、second allocation
  engine、new owner/state machine/compatibility path；不改 filter、Assistant restart、import wizard 五階段或
  `settings.json`。不宣稱所有 MOABB；本機 15 corpus 僅用於 catalog/availability 檢查，不把它誤稱為
  15/15 materialization 證據。
- Owners before/after 不變：`DatasetGenerationService` owns command admission/save/materialization；
  `DatasetGenerator`/`Epochs` own mask allocation；`SplitAudit` owns partition evidence；`TrainingPlan` owns
  saliency split choice；preview publisher only publishes immutable DTO. Reuse/delete invalid enum dispatch,
  silent clamps, fixed fake split facts, and duplicate admission rather than adding a parallel policy.
- Complexity checkpoint (2026-09-04): the current combined production diff against `origin/main` is 14 files,
  `+1806/-512` (net `+1294`). This exceeds the ordinary 8-file/+300-net trigger but remains below the
  approved 1,500-net one-PR stop. Owners remain unchanged: `Epochs`/`DatasetGenerator` allocate masks,
  `SplitAudit` owns evidence/digest, `DatasetGenerationService` owns save/materialize admission,
  `DatasetSplitPreviewPublisher` publishes detached truth, and the UI projects it. No module, public class,
  authoritative owner, state machine, solver or compatibility path has been introduced. Deletions include retired
  Test Disable/Independent dispatch, sequential split methods, UI-local duplicate admission policy, mock-only
  retired tests and weak count/digest echoes; their replacements exercise real allocation or command materialization.
  The bounded deterministic allocation is deliberately not a complete solver and fails closed when no admissible
  partition is found. Replan if production net reaches 1,500 or a new owner/state machine/solver/compatibility path
  becomes necessary.
- UI approval is explicit: the user approved preserving the five-stage import flow and the existing 5×5-like split
  presentation logic, with real dynamic counts and the stated colors/copy. UI still requires screenshot/walkthrough
  and later native Windows acceptance on exact PR head.
- Audit repair actual: four existing production files, `+348/-138` (net `+210`). It reused `SplitAudit`, preview
  publisher, `DatasetGenerationService`, `DatasetGenerator` and
  config admission code; no module, owner, state machine, solver, receipt, or compatibility path was added.

### TDD repair and validation sequence

1. Add the smallest red public/domain reproductions before production edits: invalid strategy/mode matrix,
   Validation Disable/empty semantics, strict boolean and `{}` admission, global Session grouping, ratio/Number
   group capacity, K bounds/exact folds, and preview receipt mismatch. 同時盤點直接被新 contract 淘汰的
   Disable/Independent tests；每個刪除必須有涵蓋真實 observable contract 的 stronger replacement。
2. Implement one canonical allocation/audit path in existing owners; parameterize real `Epochs`/
   `DatasetGenerator` tests for 1/2/3/5/7 groups, unequal group sizes/classes, mixed protocols and determinism.
   Assert allocation atomicity, coverage, cardinality and Train/preview identity rather than helper internals.
3. Add lower-mock preview → receipt → save → materialize → Train admission → evaluation/saliency tests; stub only
   expensive final trainer. Verify complete-test, validation-fallback, and unavailable saliency outcomes without
   turning an expected unavailable fold into a generic worker failure.
4. UI tests cover 1/3/5/15 subject layouts, unavailable choices/reasons, narrow/keyboard/manual cancel, 50+ rows,
   class notices and saved-spec rehydration. Root visually inspects screenshots; offscreen does not replace Windows
   native acceptance.
5. Run focused backend/UI selectors under explicit timeout and `prlimit --core=0` where MNE/Qt/PyTorch is involved,
   then changed-file Ruff and `git diff --check`. Before handoff, run canonical public source-diverse data gates and
   exact-head Windows manual materialization for MAMEM1 EEGLAB Trial/KFold with five frequency classes,
   BNCI2014_009 BrainVision Subject/Session, and PhysionetMI EDF Subject/Trial. The local pinned 15 MOABB corpus is
   catalog evidence only, not a 15/15 materialization requirement or arbitrary-MOABB claim.
6. **Audit-repair TDD (complete):** red/green public-command and real materialization cases closed mixed provenance
   fail-closed behavior, preview-time audit parity, cooperative cancellation with no successful receipt after a
   successful cancel, strict structured payload fields while preserving only `split_config=None` legacy behavior,
   nearest-feasible no-validation Ratio, mixed Manual residual semantics, Manual duplicate/out-of-scope/atomic
   constraints, and CV Validation Number exact cardinality. The repairs stayed in the existing owners; no parallel
   allocator or policy path was introduced.

### Stop condition

- Stop rather than expand if valid contract behavior requires a new owner, second state machine/allocation engine,
  generic solver, compatibility rewrite, dataset-specific frequency semantics, or changes outside split/
  materialization/saliency and the explicitly approved UI surface.

### Implementation progress and evidence checkpoint

- Contract/admission, canonical allocation/audit, receipt parity, saliency fallback, saved-spec UI projection and
  obsolete/mock-heavy split-test cleanup are implemented in the existing owners. The five-stage import workflow is
  unchanged.
- Focused pre-commit candidate-tree evidence: full Application+Dataset `2388 passed`; selected Training `628 passed`;
  UI `178 passed`; selected architecture `285 passed`; whole-repo Ruff check and format check passed; Basedpyright
  regression reported `0` new diagnostics; architecture compliance script passed. These results close the listed
  audit/admission/cancellation/no-validation-ratio/mixed-Manual/evidence-gap checkpoint; they do not certify an
  arbitrary dataset, scientific split quality, or a complete solver.
- Supplemental UI root-contract evidence: `test_sidebars_and_components.py` `102 passed`; the
  `tests/unit/ui/test_*.py` selector `944 passed`, and its root rerun of the single file also `102 passed`.
- Integration-UI green evidence: with the correct `PYTHONPATH`, full `tests/integration/ui` reports `119 passed,
  21 skipped`. The first attempt without that path produced three direct-script `ModuleNotFoundError`s; that is an
  existing runner-entrypoint/environment issue, not a Data Split defect.
- Stale-test green evidence: ApplicationService integration file `21 passed`; checked-in GDF `15/15` passed;
  command spine `1/1` passed. The authoritative `linux-integration-rest` result collected `346`, with `311 passed`,
  `35` optional-public-fixture skipped, and `0 failed`; pipeline reports `121 passed, 6 skipped`. Aggregated evidence
  is `10438 passed, 21 skipped, 0 failed`.
- Remaining work: final tests/docs review and commit/push, exact-head CI, and the specified Windows native manual
  acceptance. The canonical manifest retains its existing runner-entrypoint blocker. Until those gates close, this
  remains a checkpoint, not handoff-ready.
- Stop if deterministic allocation cannot satisfy hard train-class/required-split constraints for a given input:
  publish a recoverable infeasible preview with the cause, never silently clamp, split an atomic group, or mutate
  saved truth. Do not expand into arbitrary MOABB support, UI redesign, or a second allocator.

## Historical record — SSVEP import review routing and EEGLAB preflight sampling rate

### Problem and evidence

- Data Import 的既有五個使用者階段是：`Choose EEG Data`、`Load Labels`、`Review Metadata`、`Match Labels`、
  `Review and Import`。使用者明確滿意這五段，要求不要大改。
- 真實 command lifecycle 是 `scan -> preview -> validate -> confirm -> apply -> recipe`；只有
  `AppliedInterpretation` 才能成為下游 truth。
- 在 `DataInterpretationActionCoordinator._repreview_interpretation_async()`，Match Labels 或 final review
  的 edit 會正確重跑 `PreviewInterpretationCommand` 與 `ValidateInterpretationCommand`，但 validated callback
  無條件以舊 `initial_step` reopen dialog。它沒有使用 fresh `ValidationDecision.action_items` 的
  `target_step`。因此新的 `blocked` class/event mapping candidate 可能回到 `Review and Import`，而不是回到
  backend 指定的 `Match Labels`；使用者看不到清楚的 recovery path。
- 這是 coordinator routing defect，不是 dataset 名稱、raw SSVEP parser、backend validator 或 Apply defect。
  已有 focused tests coverage re-preview、fresh final review 與 no-apply boundary，但尚未刻畫 fresh blocked
  decision 的 target-step routing。
- 使用者的 MAMEM1 BIDS 手測揭露另一個直接阻擋：`sub-1` 的 uncompressed embedded MAT v5 `.set` 把
  `EEG.data` 放在 `EEG.srate` 之前。bounded preflight 一讀到 signal shape 就當作完整 header 回傳，因而
  得到樣本數卻漏掉真實 header 的 `srate=250 Hz`。BIDS event review 無法由 `n_times / sfreq` 建立 recording
  bounds，安全地退回 `Match Labels`。這不是頻率 class、SSVEP adapter 或使用者 choices 的問題；同型 embedded
  EEGLAB `.set` 都可能受影響。

### Outcome and user-visible contract

- Re-preview 後只信任 fresh backend `ValidationDecision`：`blocked` 時以 typed actionable target reopen；本
  slice 的 class/event blocker 必須 reopen `Match Labels`，並保留該 decision/action cards。`safe` 和
  `needs_confirmation` reopen `Review and Import`，讓使用者對新 candidate 作 final confirmation。
- `ApplyInterpretationCommand` 不得對 blocked candidate 執行；既有 fresh-final-review confirmation boundary
  必須保留。
- status bar 顯示 concise backend-truth-aligned recovery outcome（例如 review updated and current task），不以
  前端另造 validation policy。loading、cancel、failed 與 repeat lifecycle 保持現有 owner。
- EEGLAB bounded preflight 必須在不 materialize signal samples 的前提下，繼續讀完同一 bounded MAT struct 所需
  scalar metadata；對 data-before-srate 的 embedded MAT v5 source 保留 `sampling_rate_hz=250.0`。這讓 BIDS
  duration validation 使用真實 recording bounds，而不是為 SSVEP 或 frequency class 增加特殊路徑。

### Scope, non-goals, assumptions, ownership

- Scope 包含 coordinator 的 fresh-decision-to-reopen-step routing、EEGLAB embedded MAT v5 bounded-header completion、
  直接 focused regressions、此 plan，和必要的 offscreen walkthrough artifact。production files 預計只有
  `XBrainLab/ui/panels/dataset/data_interpretation_action_coordinator.py` 與
  `XBrainLab/backend/application/eeglab_set_preflight.py`；tests 預計只有
  `tests/unit/ui/dataset/test_interpretation_async_flow.py` 與
  `tests/unit/backend/application/test_eeglab_preflight_gate.py`。
- 不改五階段、dialog layout、copy hierarchy、backend Data Interpretation policy／payload schema、Apply semantics、
  raw loader、recipe schema、MOABB dependency、dataset download、filter、Assistant fallback 或 data split。
- 不新增 frequency adapter、target-to-frequency/phase/code inference、CCA/FBCCA 或 BIDS special case；不宣稱所有
  MOABB、任意 BIDS/event schema、科學 SSVEP accuracy 或 benchmark quality。MAMEM1 的 accepted contract 僅是使用者可將
  `trial_type` frequency values 明確選成 supervised classes，且 import 後可進入既有 epoch/split/train workflow。
- Owner before/after 不變：`DataInterpretationCommandService` owns scan/preview/validate/apply state and decision;
  `DataInterpretationActionCoordinator` only owns async UI command orchestration; preview dialog renders typed
  result; `eeglab_set_preflight` remains the sole bounded `.set` metadata owner. 不新增 owner、state machine、module或
  compatibility path。
- Deletion/reuse first：reuse existing `_repreview_interpretation_async` and typed `action_items`; do not add a
  parallel wizard/router, frontend inference, or second EEG reader. Routing repair 預估 production net `+20–45 LOC`；
  preflight repair actual `+23/-4 LOC`，兩個既有 production owners，owner delta `0`。
- UI approval 已存在：使用者說「目前 review and import 這五個階段我很滿意不要大改」，並在討論 status bar
  後回覆「我覺得可以」。本 slice 只在該批准下修正 recovery routing/status，仍需 focused screenshot/walkthrough
  與後續 Windows native human acceptance；preflight repair 本身不改可見 UI。

### TDD repair sequence and validation

1. 在 `tests/unit/ui/dataset/test_interpretation_async_flow.py` 先新增最小 red reproduction：從 changed
   Match Labels/final draft re-preview，fresh validation returns `blocked` plus typed `target_step="Match Labels"`;
   assert reopened dialog uses `Match Labels`, preserves fresh review state/action items, shows recovery status, and
   never calls Apply. 它必須在 current code 因 reopen uses stale `initial_step` 而失敗。
2. 加 direct adjacent cases: fresh `safe` and `needs_confirmation` reopen `Review and Import` and preserve the
   required fresh confirmation boundary; cancellation/error remains owned by existing lifecycle.
3. 只在 coordinator 加最小 resolver using fresh typed decision/action items; unsupported/missing target fails
   closed to the conservative review path, never guessed from SSVEP names or UI labels. 不改 backend or dialog policy.
4. Run the red selector, then the same selector green and directly coupled async-flow file under Qt-safe timeout /
   `prlimit --core=0`; run changed-file Ruff and `git diff --check`.
5. Produce the existing data-import offscreen capture plus a user-like blocked-to-Match-Labels walkthrough artifact;
   inspect the screenshot for five-step preservation, readable status, no clipping/overlap. Offscreen evidence does
   not replace Windows native acceptance.
6. 先在 `tests/unit/backend/application/test_eeglab_preflight_gate.py` 新增最小 red reproductions：uncompressed
   embedded MAT v5 `EEG` struct 的 `data` 在 `srate` 前，以及 top-level `data` 後仍有 ignored metadata、再有
   `srate` 的 continuation；兩者 assert bounded inspection retains shape/dtype and `sampling_rate_hz == 250.0`
   while physical reads remain bounded and no signal materializes。另以既有最多 256 個 post-data outer metadata
   elements 的 cap，證明 255 個 ignored elements 後的 `srate` 仍可讀到、256 個後的 late `srate` 則 fail closed
   as an embedded bound with `sampling_rate_hz is None`，不得為找 rate 讀取 signal。
   current code 必須因 early return 令 sampling rate 為 `None` 而失敗；不先修改 production。修理後 rerun exact
   selectors and the coupled EEGLAB preflight file under `prlimit --core=0` and timeout.
7. Windows native acceptance on the exact PR head: select MAMEM1 `sub-1` runs 0–2, map `trial_type`
   `6.66/7.50/8.57/10.00/12.00` to five explicit `Hz` classes, continue to Review and Import without a missing
   sampling-rate blocker, Apply, epoch `0–3 s`, save `Individual/Trial` split, and complete one CPU EEGNet epoch.
   Record five imported classes and completed training; this is MAMEM1-specific acceptance, not a broad MOABB claim.

### Implementation progress and focused evidence

- Red reproduction completed: the new coordinator async seam dispatched `PreviewInterpretationCommand` then
  `ValidateInterpretationCommand`; a fresh `blocked` decision with typed `target_step="Match Labels"` actually
  reopened stale `Review and Import`, exactly proving the reported defect. No Apply was invoked.
- Minimal repair completed: coordinator reuses `adapt_serialized_validation_decision()` from the existing review
  presenter. A valid fresh blocked decision takes its first typed blocked action target; `safe`,
  `needs_confirmation`, invalid, or incomplete decisions reopen conservative `Review and Import`. The sole new
  status copy is `Import review updated · Continue in <task>`.
- Green focused evidence: red selector then passed; blocked/safe/needs-confirmation routing selectors were `3 passed`
  (2.32s); full `tests/unit/ui/dataset/test_interpretation_async_flow.py` was `85 passed` (12.42s); directly coupled
  review presenter/loading Qt tests were `23 passed` (1.25s). Changed-file Ruff and `git diff --check` passed.
- TCP-only Xvfb focused capture completed with exit `0`: the existing canonical generator wrote
  `build/dev-artifacts/ssvep-repreview-ui-evidence/04-match-labels-final-loaded-label-files.png` and its root
  manifest. PNG SHA-256 is `efc535fdd7aaa1479bc72047f8f800bbbd89ccca2141c82d98ffa50644ee7b04`; it is a readable
  1220×1320 xcb-native-window screenshot. Visual inspection confirms all five named stages remain visible, Match
  Labels is active, the class-event choices and footer are readable, and there is no observed clipping/overlap.
  This focused capture proves only the pre-existing five-stage Match Labels surface; it does not exercise the new
  asynchronous re-preview route or status bar, is dirty-source evidence, and is not Windows human acceptance. The
  exact-source Windows human walkthrough remains required before any merge claim.

### PR #110 direct product dependency — EEGLAB embedded sampling-rate preflight

- Exact red evidence: the new uncompressed embedded MAT v5 data-before-srate selector failed on the unmodified
  parser with `1 failed in 0.56s`; inspection had `bound_known=True`, embedded `(4, 100000)` float32 data and
  `sampling_rate_hz=None`. This isolates the early header completion defect without loading EEG samples.
- Minimal parser repair is complete in the existing `eeglab_set_preflight` owner: after embedded data is bounded,
  uncompressed top-level scalar metadata may continue through the existing cap; compressed, v7.3, payload and
  unsafe-reference boundaries retain their existing fail-closed behavior. Actual production delta is `+23/-4 LOC`,
  owner delta `0`; no loader, BIDS policy, frequency adapter, UI, or compatibility path was added.
- Green regression inventory: one nested data-before-srate regression, one ordinary top-level continuation regression,
  and two real top-level cap boundaries (255 ignored post-data elements then `srate=250`; 256 then late `srate=None`)
  are included in the full EEGLAB preflight suite. Independent review found no lifecycle, ownership, payload-read,
  cap, or class-carrier blocker after the 255/256 boundary correction.
- Actual MAMEM1 bounded probe on `sub-1/ses-0/eeg/sub-1_ses-0_task-ssvep_run-0_eeg.set` reports `bound_known=True`,
  `storage_mode=embedded`, `sampling_rate_hz=250.0`, `header_bytes_read=512`, shape `(256, 117917)`, and `float32`.
  This proves the exact cached run's header admission only; it is not an Apply/epoch/train or scientific claim.
- Focused Windows evidence on the current dirty source: EEGLAB preflight `19 passed` (0.72s), resource guard
  `48 passed` (2.37s), interpretation resource reader `14 passed` (1.80s), and async import routing `85 passed`
  (10.27s), each under `prlimit --core=0`, explicit timeout, `MNE_DONTWRITE_HOME=true`, and offscreen Qt where
  applicable. Changed production/test/UI Ruff and `git diff --check` passed.
- Next step: commit and push this exact source, wait for non-skipped CI on that exact PR head, then repeat the full
  native Windows MAMEM1 acceptance (three sub-1 runs, five `trial_type` frequency classes, Apply, `0–3 s` epoch,
  Individual/Trial split, CPU EEGNet one epoch) before any merge claim.

### PR #110 direct CI blocker — restore Dataset startup lazy import

- Exact `6b9f1fe09425ea2274333538975a5eeb59bfd330` has four direct Linux CI failures in the Dataset import-latency
  boundary. Their common root is this slice's new top-level coordinator import of
  `XBrainLab.ui.dialogs.dataset.review_import_presenter`: importing Dataset actions now imports the Dataset dialog
  package during first-open, violating its explicit lazy-import contract. This is an eager-import regression, not a
  routing, validation, raw-SSVEP, or behavior failure.
- Repair scope is only to restore the existing lazy seam: remove the coordinator top-level presenter import and
  import the existing adapter only at fresh decision resolution. Do not add a parser, module, owner, cache, schema,
  dialog/layout change, or fallback policy. The same typed adapter and routing outcome remain authoritative.
- TDD evidence is the existing four import-latency selectors, run directly in the external Linux environment: they
  must fail current source because the dialog package is eager. After the smallest lazy import repair, rerun those
  selectors, the routing triplet, full async-flow file, a relevant MainWindow startup probe if environment permits,
  changed-file Ruff and `git diff --check`.
- Stop if lazy resolution changes the typed decision contract, delays/loses routing behavior, causes a new startup
  import root, or needs a broader dialog/package redesign. This repair restores no user-visible behavior beyond
  startup import latency and does not change the five stages or SSVEP claim boundary.
- Red evidence completed in the external Linux environment: the direct import-latency probes found
  `XBrainLab.ui.dialogs.dataset.review_import_presenter` after Dataset panel/actions import. The selected CI boundary
  set was `2 failed, 2 passed`; both failures have the stated common eager-import root. The remaining two reported CI
  failures are the same package-startup boundary on their own CI paths, not an additional routing defect.
- Minimal repair completed: the adapter import now occurs inside `_repreview_step_for_decision()` only. It preserves
  the existing adapter, typed decision semantics and routing outcome; no new parser/module/owner/cache was added.
- Green evidence: the same four direct import-latency selectors plus default MainWindow startup probe and the routing
  triplet were `8 passed` (5.46s). Full async-flow was `85 passed` (12.26s); changed-file Ruff and `git diff --check`
  passed. These are dirty-source focused results only and do not replace PR CI or Windows acceptance.
- Independent review passed: the repair preserves the existing lazy dialog boundary and routes through the same
  adapter only after a fresh decision exists; it found no lifecycle, policy, owner, or visible-flow blocker. Combined
  focused evidence is `91 passed` across the import-latency/startup boundary and complete async-flow protection.
  Next step is commit/push this exact lazy-import repair, then wait for PR CI on that exact head; do not treat this
  local evidence as CI completion or Windows acceptance.

### Stop condition

- Stop rather than expand scope if fresh backend output lacks typed action items/target, targets a stage outside the
  existing five, requires backend policy/schema changes, makes Apply reachable for blocked input, changes more than
  the stated two production files, or cannot be observed by the focused test.
- Stop rather than broaden the preflight fix if a correct scalar requires reading numeric signal payload, compressed
  header decoding exceeds its existing budget, a MAT v7.3 file is involved, or the repair needs a loader/BIDS policy
  change. Do not proceed into raw SSVEP adapters, target-frequency/phase semantics, data download, classifier work,
  filter, Assistant fallback or splitting cleanup. After this slice, claim only typed review routing plus the exact
  embedded EEGLAB sampling-rate repair; MAMEM1 supervised training remains subject to the listed Windows acceptance.
