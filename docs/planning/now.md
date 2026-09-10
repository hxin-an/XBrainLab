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
| 1 Command/state spine | Admission, capabilities, confirmation, publication, owned work, shared domain ports | 1A–1M reviewed; Study conveniences and final shared-spine evidence audit open |
| 2 Import/interpretation | Loaders, BIDS, labels/classes, channel/montage, metadata, recipes, related UI | 2A–2E reviewed; remaining domain implementation/tests audit open |
| 3 Preprocess/epoch/split | Processing, copies, invalidation, preview/materialization, related UI/tools | Pending |
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

- Recovery reverified: product branch `cleanup/module-quality` is clean at `7b4fc8a0` (22 commits
  after baseline); original dirty UI/test/settings remain intact. Earlier reboot checks verified the
  existing Windows Python and retained caches. Resume from committed source, not ended tool sessions.
- Active next: finish module 1 Study convenience caller/test audit, reconcile shared-spine inventory
  and run directly relevant confirmation/publication/owned-work/shutdown closure evidence. Independent
  full state-service test audit read 2,063 lines / 49 functions and found no safe deletion: failure,
  detachment and retry tests protect distinct read-port contracts. Verify existing actual data_lists
  stale-generation/lock tests before treating a file-local coverage gap as a product evidence gap.
  Module 2 prepared-path cleanup 2C/2D and native recipe repair 2E are committed; remaining module 2
  domain review and modules 3–9 remain open. No whole-module closure or manual candidate claim.
- Bounded 1N caller audit (read-only until its evidence map is complete): Study loader/export/read
  conveniences and their exclusive manager forwarding paths. Check dynamic/config/doc consumers;
  retain actual Command/query/result export and saliency propagation owners. Do not remove methods
  just because they forward. Independent worker owns the audit, not source edits.
- Bounded 1O test consolidation: runtime tests repeat direct construction's cache identity checks.
  Merge the explicit-construction-then-runtime-lookup case into the existing two-explicit-instances
  test, retaining all distinct identity/cache assertions and the separate opposite creation-order
  case. Preserve failure/retry and actual concurrent close/lookup tests. Production unchanged;
  same native runtime suite before/after, Ruff and independent diff review. One rollback commit.
  Existing data_lists tests already exercise nonwaiting lock rejection, pre-read stale-generation
  rejection and use of committed state without refresh; retain these as shared-spine evidence,
  while row/EEG domain semantics remain module 2, not an invented new concurrency owner.
- 1N implementation declared after independent caller audit: delete Study.get_raw_data_loader and
  DataManager.get_raw_data_loader, Study.export_output_csv and TrainingManager.export_output_csv,
  and Study-only get_saliency_params/unlock_dataset/has_raw_data/has_datasets/has_trainer wrappers.
  Whole tracked source/config/scripts/docs checks found no runtime/dynamic consumers. Preserve real
  RawDataLoader, result-record CSV export, manager predicates/unlock, manager saliency getter and
  formal visualization/analysis consumers. Remove exactly their loader/export-exclusive tests and
  fake export helpers; migrate the two Study saliency read assertions to its retained manager while
  preserving setter/trainer propagation checks. No new owner, fallback or visible/public contract
  change. Worker owns the three backend classes and four directly affected test files, main owns
  plan/inventory/runtime tests. Native baseline/after on those test files plus actual analysis/
  visualization getter consumers; unchanged retained assertions, Ruff and independent actual diff
  review before a separate rollback commit. Do not expand to other training/data methods.
- 1O completed focused evidence: native runtime baseline 10 passed; consolidated suite 9 passed,
  with all distinct prior cache/identity assertions retained and explicit-close isolation added.
  Production unchanged, Ruff/format passed; independent reviewer approved actual diff/ownership.
- Next bounded 2F import verification simplification: full content-identity source (1,010 lines)
  and its two test files (945 lines) were read. Preserve streaming SHA, canonical path scope,
  admitted digest reuse, bounded workers and explicit owned-context/cancellation/progress behavior.
  Remove only a consecutive duplicate session-current check in prepared apply, its single-use
  `_ensure_reviewed_label_content_is_current` forwarding wrapper, and the one-use nested `_build`
  wrapper inside hash dispatch by inlining under the existing context bindings. No cache, identity
  schema, extra owner, I/O or lifecycle redesign; no performance claim. Native content identity/hash
  cancellation and actual prepared apply stale/content/rollback tests before/after; unchanged tests,
  Ruff and independent data/lifecycle review. Main owns these two production files, separate from 1N.
- 1N native before/after: 158 / 146 passed on identical four-file selection. Exactly 12 loader/export
  exclusive cases removed; real plan, saliency propagation and manager mutation assertions retained.
  Production +2/-63/net -61, tests +8/-112/net -104; Ruff/format/diff pass. Independent final review
  approved. Retained visualization/analysis readback neighbors: 7 passed (33 deselected).
  EvalRecord.export_csv itself remains for module 5 caller/disposition review; this slice
  does not assert a currently reachable CSV-export product feature.
- Recipe audit: independent full source/test/caller read retains persistence, replay conversion,
  legacy class-map migration and current label-audit reconstruction. Their real save/reload and
  state roundtrip cases protect current behavior. Target-level extra provenance/schema fields are
  not current guarantees or authorized schema work. 2F baseline: 49 content/prepared cases plus
  6 actual stale-session/cancel/commit/content-boundary cases pass before edits.
- 1O committed as `6c0ee806`; 1N commit next. 2F source edited only after its baseline; after evidence
  and independent review remain. No module closure or manual acceptance is implied by these commits.
- Planned 1L observer cleanup: remove the unread QtObserverBridge._observer_callback member (two
  assignments) while retaining Observable/_ObserverSubscription callback ownership, QObject destroyed
  cleanup and finalizer. Replace the test-only empty MockObservable subclass with Observable itself.
  UI-internal changes authorized; no visible behavior change. Native bridge suite before/after plus
  observer lifetime checks, unchanged assertions, independent review and one rollback commit.
- 1L baseline/after native selection: 34 passed both times (513 deselected), including real Qt
  handoff/ack/teardown and reboot smoke. Independent reviewer approved callback retention and
  unchanged test assertions. Infrastructure withdrawal is committed separately as `acf7c56d`;
  no PR merge or product handoff was inferred. 1L is committed as `3a35efee` (production -2 LOC).
- 2C authorized next data slice: first migrate legacy-only selected-file, partial-load failure,
  reviewed resource mutation and essential confirmation-receipt cases onto the real prepared
  ApplicationService path, using existing real Study fixtures and only external loader/resource
  isolation. Preserve before/during content-change coverage for EEG, BrainVision dependencies and
  EEGLAB sidecars where feasible; keep label-byte mutation and recipe assertions. Do not teach the
  legacy fake controller to imitate two-phase mutation. Obtain passing characterization before
  deleting handle_apply_interpretation and its four exclusive raw-replacement/snapshot helpers.
  Migrate the private rollback test to the existing PipelineStateTransaction owner and retarget the
  owned-work materialization guard at prepare/load/commit owners. Existing equivalent real tests stay.
  Deletion requires a per-group evidence map; unresolved groups block this slice, not disappear.
  No formal Command/UI/EEG change/new owner. Separate test migration and production deletion commits
  are allowed within this coherent reviewed slice; focused import/content/receipt/rollback/recipe
  tests before/after, meaningful fault probe and independent data/lifecycle review before closure.
- 2C characterization before production deletion: 22 new real ApplicationService cases passed
  natively; six existing selected apply cases also passed. Independent review approved the actual
  test diff and bounded loader/preflight fault isolation. The materialization guard now inspects
  real detached prepare/load and guarded commit, not the unused handler; all 29 owned-work tests
  passed. Remaining receipt permutations and label/recipe legacy cases still require an exact
  retained-evidence map. No production deletion has occurred and 2C is not complete.
- 2C deeper map found pending-token, warning-to-blocking, external-label preflight scope and
  label-before-apply gaps; extend actual command cases before deleting those old tests. Add exact
  candidate binding where not already protected. TTL/eviction primitives remain protected by the
  actual ResourceReceiptAuthority tests, not by unrelated preview-wrapper claims. Manual recipe
  state mutation is superseded by real apply/save/metadata/label flows and retained state-owner tests.
- Before-delete full legacy service plus receipt-owner baseline: 101 passed / 3 failed on native
  Windows. The three recipe reload failures precede production edits and report fingerprint/diagnostic
  mismatches; independent diagnosis is checking real stat/fstat evidence. Do not waive or count them
  as green. Separate recipe repair scope if a real platform defect is confirmed. The 23-case actual
  prepared apply plus transaction rollback selection passed; guard formatting was corrected by Ruff.
- 2C complete replacement characterization: 28 prepared-apply cases passed, including all identified
  missing receipt/label/candidate/placement cases. Retained recipe evidence includes actual
  choices_flow_into_recipe, apply_updates_loaded_metadata, label_carrier_choices_flow_into_recipe,
  failed_replacement_restores_raw_interpretation_and_recipe and state-owner record/roundtrip tests.
  Retain the non-apply validate-after-label-change test, non-BIDS BrainVision scan fixture and all
  resource-cache/admission tests. Only old apply-exclusive tests/helpers are deletion candidates.
- 2E necessary native recipe repair declared before edits: independent measurement found unchanged
  files whose descriptor fstat ctime and path stat ctime differ by milliseconds on Windows; dev/inode,
  size and mtime agree. Recipe fingerprint compares unlike observation channels, causing false stale
  errors. Preserve bounded SHA/size and all admission/receipt guards. Match the existing admitted
  resource-reader approach: compare complete identity within descriptor and within path observations,
  but cross-check descriptor/path object identity without ctime. Add a deterministic skew regression
  plus changed-observation rejection before repair, then rerun native recipe reload cases and resource
  reader protection. No UI/public contract/new owner; separate small commit and independent review.
  This prerequisite does not close or replace the 2C deletion work or the remaining module stage.
- 2C evidence migration committed as `1c7ba6fc`; no production deletion in that commit. The 2E
  worker owns only recipe fingerprint and its regression tests; main preserves those files until
  release. Concurrent bounded 1M closes the observer compatibility-property finding: `_batch_depth`
  and `_pending_events` have only two unit-test callers, no runtime/registry/config consumers.
  Delete those two views of existing ContextVar state and stale attribute docs. Replace the tests'
  implementation-state assertions with public notify/notifications_deferred outcomes, retaining
  batching exception, callback delivery and concurrency assertions. Baseline the same observer/batch
  tests before and after, plus publication-delivery neighbors and independent review. No owner/API
  contract/UI change; one rollback commit. Continue 2C immediately after the prerequisite repair.
- 1M original baseline, public-behavior characterization and after-delete runs each passed 33 native
  cases; Ruff/format passed. Independent reviewer approved no remaining runtime/dynamic callers and
  preserved callback/batch/publication behavior. Production -17 LOC; no owner or visible behavior change.
  Committed as `8d51502e`.
- 2E repair evidence: deterministic skew/path/descriptor cases produced 2 fail / 1 pass before repair,
  then 3 pass. Native selected recipe/resource-reader checks: 18 pass; final complete legacy service
  plus receipt-owner baseline: 107 pass (the original 104 plus 3 new cases), resolving all three
  original native failures. Independent review approved full within-channel identity checks and
  cross-channel object comparisons; bounded SHA, size/admission/receipt protections remain intact.
  Production +16/-4/net +12, no new owner/module/type. Next remains 2C legacy deletion, not handoff.
- 2E committed `722207cc`. 2C deletion now begins against its passing 107-case baseline: remove
  the unreachable direct handler plus four exclusive raw replacement/snapshot helpers and unused
  imports. Worker removes exactly the mapped 21 legacy apply test functions and three exclusive
  integrity helpers, preserving validation/scan/preview/recipe/resource tests and new 2E regressions.
  Replace the now-obsolete dataset/Raw fake classes with existing DatasetStateService(Study()) for
  retained discovery fixtures; no imitation two-phase controller. Verify 28 replacement cases,
  retained coordinator/receipt/state/recipe behavior and actual cancel/stale/rollback neighbors.
- 2C after deletion: actual application import/recipe/label/cancel/stale/rollback selection 79 pass;
  retained coordinator/receipt/state/owned-work/resource-publication selection 134 pass (one existing
  MNE/NumPy deprecation warning). Exactly 21 legacy test functions removed; AST comparison confirms
  every retained test body/decorator is unchanged. Main caught/restored required fixture callbacks
  during editing before the shared run. Production +2/-186/net -184; legacy test file +37/-1283.
  In-memory bypass of reviewed content verification makes the new actual selected-EEG mutation case
  fail because mutated content is incorrectly published; the normal source passes the same case.
- Next bounded 2D follow-on removes now-unreachable DatasetStateService.import_files and its
  interpretation-port declaration plus PipelineStateTransaction.prepare_raw_replacement. These
  have no remaining production callers after 2C. First retarget seven stale no-import assertions
  in actual command tests and the confirmation test to the real factory/prepare entry; they currently
  watch the unused convenience. Migrate the two direct import fixtures to prepare/commit, preserving
  actual unexpected-mutation publication evidence. Remove only the obsolete raw-detach call in the
  snapshot test while preserving explicit restore/training isolation. Keep all cancellation, resource,
  channel and label behavior, no new owner/API/visible UI change. Separate scope baseline/after and
  independent review; do not mix any further preprocess legacy path removal into this slice.
- 2C committed as `d3ef1ac4` after independent final source/test approval. 2D main baseline and
  prepare/commit fixture characterization each passed 24 native cases. Worker retargeted seven
  blocked import cases plus confirmation/automation: initial selection 10 pass. Main review additionally
  found four original-dataset label mocks cannot see the actual detached label owner; remove those
  ineffective checks in favor of no actual loader entry and no applied truth. The automation case
  tests review-state serialization but silently attempted failing Apply on a placeholder FIF: stop
  at successful Validate and assert its actual result while preserving all review-state assertions.
  Re-characterize before production deletion. Also remove clean_dataset only from the interpretation
  port's obsolete requirements; lifecycle port/implementation still own reset and remain unchanged.
- 2D final: corrected worker selection 10 pass before/after, no placeholder-FIF warnings after
  removing the irrelevant Apply attempt. Main after selection 53 pass (24 direct neighbors plus
  29 owned-work cases; one existing MNE/NumPy warning). Production -81 LOC across two files;
  no executable caller remains, only the intentional architecture forbidden-name guard. Independent
  reviewer approved unchanged prepared mutation/admission/lifecycle boundaries and actual-side-effect
  test replacement. Finish the small commit, then close remaining module 1 full-test audit gaps
  and continue module 2 domain implementation/tests; no whole-module closure or handoff claim yet.

### Earlier slice declarations and evidence

- Baseline: fetched main `4770b049`; original dirty checkout preserved; source-only integration worktree
  created on `cleanup/module-quality`. Existing Windows Python/pytest are available without installation.
- Slice 1A: remove snapshot-to-training-command coupling. StateSnapshotService uses a training command
  object solely to forward three pure serializers already owned by training_snapshot.py. Both the lazy
  adapter and TrainingCommandService duplicate these wrappers. Route callers directly to the existing
  serializers, remove the dependency and wrapper-only fixture construction; keep lazy heavy imports,
  publication/consistency checks and serializer behavior unchanged. No new owner/module/public type.
- Baseline/after: native Windows state-service tests, training-service tests and directly selected real
  application configuration/reset/query tests, plus changed-file lint. Rollback is one slice commit.
- Slice 1A committed as `0d67870f` after independent approval; persistent stage plan `5346a296`.
- Slice 1B: remove unused state-service compatibility reexports and their alias-identity-only test,
  unused optional duplicate training/evaluation read-port constructor aliases, and lazy adapter methods
  proven absent from dispatch/callers (handle_train and active_split_summary only; handle_evaluate is
  retained because the handler registry binds it). Keep formal query/coverage behavior and lazy imports.
  Add serializer model-name fallback/detachment characterization through a real snapshot build.
  Baseline/after: state-service, saliency coverage, import boundaries, application-state architecture,
  application lazy configure/reset/empty state tests; compare exact retained behavior denominator.
  No new owner/type/module; rollback one slice commit. Main owns production/state tests; worker 8A owns
  CI routing and its tests without overlap. Independent core lifecycle audit is read-only.
- Inventory: 1,292 tracked files initially routed in ignored
  `build/dev-artifacts/module-quality-audit/tracked-files.md`; pending means not deeply inspected.
  Correct path-based initial routing from actual responsibility as each module is read.
- Blockers: none established. No module is complete and no manual candidate is being offered.

### Reviewed slices and concurrent work

- 1A snapshot/training-command decoupling: before/after 139 native Windows focused cases passed;
  changed-file Ruff and format checks passed. Independent `snapshot_review` approved actual diff and
  caller/lazy-import evidence, no blocking findings. Production +16/-50/net -34, no new owner. This is
  slice evidence, not module closure or measured speedup. Retain model-name fallback/detachment
  characterization as a next test-quality check within the snapshot audit.
- Script inventory: 106 tracked files on main, 66,204 physical lines. Earlier stale-branch candidate
  names were discarded after exact checkout verification. Registry/CI/evidence scripts are not dead
  solely because they lack product callers. Full domain semantics and actual deletion still pending.
- 8A authorized concurrent slice: inspect and reproduce missing UI-evidence script routing in
  ci_change_scope.py; ensure changed visual evidence producers trigger existing visual lanes. Add
  precise path-classification regression before the smallest policy fix; preserve non-visual routing,
  gate requirements and CI cost boundaries. Worker owns that script and its existing test file only.
  Baseline/after: focused CI scope tests and changed-file lint; rollback one commit. No public/UI change.
  Independent main review rejected the first five-path proposal: the current visual CI lanes do not
  execute those separate handoff captures, so that routing could add irrelevant waits without proving
  their output. Worker must trace actual visual-lane helper dependencies before proposing a replacement;
  a red test for an unsupported routing expectation is not evidence of a product defect.
  Corrected 8A now covers only the three actual visual CI dependencies artifact_integrity.py,
  human_like_walkthrough/readiness.py and ui_navigation.py; all five unrelated producer additions were
  withdrawn. Worker evidence: baseline 10 pass, helper regression 1 fail/10 pass, corrected 11 pass,
  Ruff pass. Main is verifying actual imports and diff before approval/commit.
- 1C authorized concurrent slice: remove OwnedWorkRegistry.start(), a forwarding convenience with
  only low-level test callers, in favor of existing claim_start(). Inspect dynamic callers and update
  tests to exercise the authoritative claim API without changing assertions or Thread.start calls.
  Preserve binding, replay rejection, cancellation/commit fence and retention. No new owner/type;
  focused owned-work registry tests before/after plus lint. Independent worker owns owned_work.py and
  its directly affected tests only, main reviews actual diff/evidence before integration.
  Worker finished: before/after registry 29 pass; all seven migrated caller files 112 pass. Main
  verified the full diff: only the four-line alias and 20 exact test-call replacements; no assertions,
  Thread.start calls, claim/cancel/commit/replay or state semantics changed. Approved for slice commit.
- 1B evidence: baseline 92 pass; retained behavior after cleanup 94 pass (one alias-identity-only case
  removed, three snapshot behavior cases added). An obsolete guard initially failed while 93 passed;
  only its forced compatibility-export requirements were removed, ownership/cold-import checks retained.
  New detachment cases all fail on the intended live-alias mutation in an isolated in-memory probe;
  normal source passes. A first probe had only a quoting SyntaxError and was not counted as evidence.
  Independent scripts_audit reviewer now examines 1B actual diff. No module-level approval yet.
- 1D next authorized slice: remove unreachable split_runtime_fields/_is_json_contract_value from
  serialization.py after whole-repo source/config/doc/registry caller checks. Formal results already
  use detached diagnostics and explicit internal/public serializers, not this retired runtime split.
  Preserve serialize_json_value behavior; correct its stale runtime-query description. Focused baseline
  results/automation/import tests before/after, no new owner/type; worker owns serialization.py only.
- 1B committed `f498e436` after independent approval. Reviewer additionally ran native Windows
  focused suites: 84 passed; no blocking findings. Correction: -B only prevents bytecode writes,
  not reads, so that run was not cache-isolated. Subsequent native checks use a fresh unique
  PYTHONPYCACHEPREFIX plus -B to avoid stale WSL-edited bytecode; recheck 1B using that isolation.
- 1C committed `25aca4a8`; corrected 8A committed `c0425f43` after main verified actual CI imports.
- 1D committed `1f0329fd` after main independently inspected the complete diff/callers. Results,
  automation and import boundaries: 55 passed before and after. Production +2/-34/net -32;
  no serializer behavior or owner changed.
- 1E authorized next: pipeline_stage.py contains a second Study-shaped stage derivation used only
  by compatibility mocks, while the real Assistant consumes an explicit ApplicationViewPublication.
  Remove the mock discriminator, legacy derivation/run scan and obsolete architecture exemption.
  Simplify compute_pipeline_stage to accept only the existing publication; migrate its sole real
  assembler caller and test callers. Preserve all stage labels, stage priority, STAGE_CONFIG prompt
  bytes/tool membership, fail-closed missing/invalid/unknown publication and unavailable policy.
  Replace mock-return stage filtering with typed publication inputs; remove obsolete mock-business
  cases only after all-stage publication characterization passes. Keep real runtime/policy tests.
  Baseline/after: backend/LLM pipeline tests, assembler stage/context tests, focused training-runtime
  architecture tests and changed-file lint. Independent review checks publication-only admission
  and tests that actually detect a wrong stage. No UI/public contract/owner addition; one rollback
  commit. Worker owns those production/tests plus backend architecture truth paragraph; main retains
  this plan and inventory. Module 1 capability/confirmation audit proceeds read-only separately.
- 1F authorized parallel main slice: application/__init__.py duplicates its 114 lazy export names
  in a manually sorted __all__ list. AST baseline confirms identical membership and sorted order.
  Derive __all__ from the existing mapping, retaining all public names, lazy resolver and memoization.
  No new owner/type/module or contract change. Characterize lazy import and unknown-name behavior,
  run existing import-boundary tests before/after, compare exact baseline export list after rewrite,
  and lint. Main owns only initializer/import-boundary tests; independent review before one commit.
- 1G authorized concurrent alias cleanup from capability/confirmation audit: remove the uncalled
  enabled_tool_names/blocked_tool_reasons convenience functions; replace internal/test imports of
  CapabilityPolicyUnavailable and ResourcePreflightReceipt with the actual existing error/receipt
  types, then delete those aliases. Do not change tool membership, confirmation fields, generation/
  fingerprint checks, receipts, prompts or execution. Keep existing behavioral assertions intact.
  Worker owns application_surface.py, tool_attempt_coordinator.py and their affected tests only.
  Focused baseline/after: application surface, attempt policy, selected controller receipt/error cases
  and real resource-receipt integration. No new owner/public tool contract; one rollback commit.
  Capability audit retained confirmation metadata despite apparent duplication because both fields
  are observable contracts. A destructive Assistant confirmation end-to-end coverage gap remains
  for module 6 closure; alias deletion alone does not certify that workflow.
- 1B revalidation: fresh isolated bytecode prefix + no bytecode writes, native state-service,
  saliency coverage and state-read-model suites: 84 passed. This supersedes the ambiguous cache claim,
  but is still focused evidence, not the full stage gate.
- 1F characterization: original import suite 4 passed; strengthened cold-import/unknown-name/
  memoization assertions also 4 passed before deletion. Exact comparison preserves all 114 exports
  and their order. Existing Ruff rejects sorted()/starred-list __all__ forms; use its supported
  explicit list constructor and in-place sort, preserving the rule rather than adding a suppression.
- 1H next main slice after 1F validation: remove unread visualization constructor/member from
  StateSnapshotService and unread study constructor/member from QueryStateCommandService; collapse
  the snapshot's duplicate training/training_state references onto training_state. Migrate all
  constructor callers and the optional progress-failure fixture without weakening its assertions.
  Full source read confirms visualization has no use; data_filepath is retained because it is
  injected into interpretation as a callback (absence of direct calls alone would be misleading).
  Baseline/after: state-service/read-model suites, import/lazy application query/reset tests, lint.
  No public/UI change, owner or module addition. Main owns these read services/callers/tests only;
  independent review before one rollback commit.
- 1F committed `8044302c`, production +2/-116/net -114. 1H committed `f5c7fd77`, production
  +1/-8/net -7. Both independently approved. Main final command ran state-service, saliency coverage,
  state-read-model and import-boundary files: 88 passed (reviewer's 84 omitted the 4 read-model cases).
  Ruff check/format passed; no test-count discrepancy after comparing exact file lists.
- 1G committed `b5d6dc4b` after main inspected the full diff, dynamic caller sweep and exact canonical
  error/receipt identity. Production +2/-49/net -47. Identical baseline/after: application surface,
  attempt policy and real resource-receipt integration 89 passed; selected controller cases 4 passed.
  No policy/confirmation assertion changed. An attempted Poetry lint lookup could not create an env;
  it was abandoned and all actual lint ran in the existing Windows environment, with no installation.
- 1E main review accepts production/guard removal but requests eliminating newly duplicated backend/
  LLM stage mapper tests and using an applicable typed publication policy in assembler fixtures.
  Retain all-stage backend mapping and all-stage actual assembler consumer behavior, not two copies
  of the same reexport test. Exact original/characterized/after counts and a wrong-stage probe remain
  required before approval. STAGE_CONFIG and real runtime-policy tests remain unchanged.
- 1I authorized next worker slice: consolidate the three identical detached-prepare failure envelope
  methods in ApplicationService into one private typed-Command helper. They preserve a concurrent
  winner's publication after discovery/apply/preprocess preparation fails; keep every diagnostic,
  cancellation marker, empty ChangedState and current state/error semantics. No new owner/type/module.
  Whole service source is now read; maintainability issues must be resolved by actual duplication
  removal, not file movement. Baseline/after include real concurrent apply failure/cancel, discovery
  failure-after-reset and preprocess stale/cancel tests. Extend the existing preprocess concurrent
  mutation fixture to characterize failed preparation too before changing production. Worker owns
  service.py and its application-service test only; main independently reviews. Rollback one commit.
  Six repeated publication-fence blocks are retained pending separate lifecycle characterization;
  do not conflate their sequencing refactor with error-envelope reuse.
- 1J next main read-dependency slice: LifecycleCommandService retains unread study/preprocess/training
  members and creates a fallback PipelineStateTransaction only for its unit fixture; real composition
  supplies the existing transaction. Require that injected transaction, remove unused dependencies
  and the two trivial private clear forwarders; retain reset/rollback/invalidation order and results.
  Remove fixture-only preprocess/training controller doubles and their identity/no-call assertions
  once existing rollback/stale trainer/current-state evidence passes. Do not delete real rollback
  tests. Main owns lifecycle_service.py/test_lifecycle_service.py; update its service.py composition
  only after worker 1I releases that file. Baseline/after: lifecycle/pipeline-transaction tests and real
  application reset/new-session/rollback cases, cold-import guard and lint. No new owner/type/module;
  independent review and one rollback commit. UI unchanged.

- 1E committed `3a8143f0` after main review corrections. Production +4/-107/net -103;
  original focused baseline 138 passed, final 127 passed after retiring duplicate legacy/reexport
  cases and retaining typed all-stage mapping plus actual assembler consumer coverage. New typed
  cases were not run against the old signature before implementation; do not claim otherwise.
  Both forced-wrong-stage probes were detected. Callable schema assertions now distinguish enabled
  tools from unavailable reference text. Architecture guard, Ruff and diff checks passed.
- 1I committed `264ef571`: production +6/-79/net -73, three real callers reuse one failure envelope.
  Original focused baseline 5 passed; extended concurrent-preprocess failure characterization 6
  passed before and after production edits. Main approved actual current-publication/cancellation
  semantics; all six publication fence blocks remain untouched.
- 1J baseline lifecycle/pipeline-transaction suites: 10 passed in isolated native Windows run.
  After cleanup, extended real reset/new-session/rollback and cold-import selection: 26 passed,
  268 deselected. Ruff passed. Independent review remains before commit.
- Independent test-quality audit fully read results, automation, pipeline-transaction and workflow-
  projection tests (1,761 lines): retain all four suites. Privacy/public-JSON contracts, real command
  and subprocess flows, explicit mutation-port isolation and fail-closed policy cases protect distinct
  observable failures. Mock count alone is not grounds for deletion. No module closure claim.
- 2A next bounded data-lifecycle repair: DataManager.clean_raw_data clears active lists but retains
  the channel-selection backup. Confirm real Select Channels -> Reset/New Session retains the old
  Raw/array with a native test and a bounded byte/weak-reference witness before adding one reset in
  the existing cleanup owner. Preserve in-session channel undo and transactional rollback; test both
  session commands plus direct raw replacement so a later reset cannot restore an obsolete backup.
  Main/reviewer trace confirms formal two-phase apply calls commit_prepared_import -> loader.apply ->
  set_loaded_data_list; the explicit prepare_raw_replacement safeguard belongs to the older handler,
  not this prepared path. Reproduce the actual reset retention and replacement/undo invariant rather
  than assuming the other handler protects it. No UI change/new owner/module; one rollback commit.
  Main owns data_manager.py, test_data_manager.py and the new real command regression. Independent
  data/lifecycle review required; focused channel-selection/rollback/session and data-manager suites.

- 1J committed `a5101683` after independent lifecycle approval: production +5/-22/net -17;
  extended native 26-case selection passed, no rollback/trainer assertion weakened.
- 2A reproduced three failures before the one-line cleanup fix. After: 59 focused cases passed,
  including channel cancellation/stale/failed commit and raw/session rollback. Two session cases
  were then extended through real FIF scan/preview/validate/apply and Reset Preprocess: both passed.
  An 8,000-byte deterministic backup and its Raw wrapper become unreachable after cleanup; this
  is object-retention evidence, not an immediate OS RSS or allocator-reclamation promise. Independent
  reviewer approved invalidation timing and restoration on transactional failure; Ruff passed.
- Separate authorized storage residual cleanup executed: removed only the abandoned backup
  `E:\XBrainLabBackups\XBrainLab-WslCompaction-20260909-232646-9134c3e5810d4399b274695a2b546bce\Ubuntu-24.04-ext4.vhdx.bak`
  and its now-empty run directory, plus the verified empty runs
  `XBrainLab-WslCompaction-20260910-011228-93f0770cd28e49afb965485b587f3763` and
  `XBrainLab-WslCompaction-20260910-014659-d5c3910b070c4a3ba2b6877f5734369d`.
  E free bytes rose from 712835555328 to 927430828032: exact delta 214595272704 (~199.86 GiB).
  Backup deletion is not recycle-bin recoverable. Both registered C WSL VHDXs, working Windows Python,
  model/RAG caches and central datasets were verified retained. No compaction/shutdown/WSL deregistration
  ran, and no C-drive reclamation is claimed. Source withdrawal of compaction-only tools from separate
  manual-environment branch remains; retain its useful single-environment launcher/config work.

- 2A committed `d1dc62ff`, production +1/-0; no public API/owner addition.
- 1K next declared spine slice: six command/read-publication paths repeat the same fence decrement,
  underflow recovery and invariant error. Reuse one private release helper in ApplicationService;
  keep every increment, lock, mutation flag reset, mark_stale call and finally placement unchanged.
  This intentionally does not introduce a context manager or alter exception sequencing. Six real
  callers justify the helper; no new owner/module/type. Characterize current deferred-publication,
  handler failure/early return and Evaluation-summary behavior before edits; same focused after
  plus changed-file lint. Reviewer checks exact sequencing and a bounded intentional missing-release
  mutation is detected. Worker owns service.py and only directly relevant test additions if needed;
  main reviews actual diff. One rollback commit; module remains open until coverage gaps resolve.

- Module 2 next audit focus: the unused direct handle_apply_interpretation path duplicates normal
  two-phase apply and is still the target of several source guards and mock-heavy tests. Main confirmed
  the product lazy adapter/dispatch does not call it. Before deletion, map every protected label,
  resource receipt, rollback, content-identity and recipe behavior to the actual prepared path; migrate
  meaningful tests/guards first. Do not keep a second mutation implementation solely for those tests,
  and do not delete scientific/security evidence without replacement. This is audit scope, not yet an
  approved code slice; choose the bounded migration after complete caller/test reading.

- 2B first bounded evidence migration: check_label_resource_admission_boundary currently examines
  only the unused direct apply handler, allowing the real prepare_apply_interpretation ordering to
  regress without a guard failure. Add a failing fixture with safe legacy code and unsafe actual
  preparation, then point the existing guard at the actual preparation owner. Keep the rule (resource
  preflight/admission before label materialization), no new guard framework or production change.
  Validate both safe and unsafe actual order, existing label-resource guard cases and current source.
  Main owns tests/architecture_compliance.py and its unit test only; independent review before commit.
  Remaining legacy runtime/test deletion stays open, this guard correction is not its completion.

- 1K main independently approved exact six finally replacements: production +15/-36/net -21.
  Baseline 17 passed plus the existing actual NewSession publication-consumer characterization;
  final 18 passed. Disabling release in memory makes that consumer test fail. No test source or
  lock/flag/exception sequence changed. Ruff and diff checks passed.
- 2B red evidence: after fixing a missing pytest import (collection error, not a regression result),
  actual unsafe preparation with safe legacy handler produced 1 fail/1 pass against the old guard.
  Corrected guard: 15 label-resource cases pass, including current-source check. Independent reviewer
  approved unchanged privacy/admission rule and the fixture's false-green detection; Ruff passed.
- Compaction tooling withdrawal on separate manual-environment branch: 84 retained scripts tests
  passed using a short existing-cache temp path; first attempt hit native Windows path-length errors,
  not a product assertion. Main review caught and removed the leftover host-only shard filter,
  while preserving Linux scripts invocation and manual-environment gate coverage. Deployed
  `D:\XBrainLabCache\tools\compact_wsl.ps1` matched retired source SHA-256
  `6675b7debb8f02fc163ba1efed2eaff0d89afa632cd388329bff3935af73d0f5`; that exact deployed copy
  was removed, with both manual launch tools retained. Source remains recoverable from Git history.

### Recovery after context compaction

Read this whole active plan, Git status/diff/worktrees and current worker/session state first. Continue
the next unfinished authorized step immediately; a recovery summary is not an endpoint. Preserve the
module table, current slice, exact evidence and outstanding reviewer findings here before context loss.
Do not dispatch from older completed PRs, recreate environments, discard active work or stop because a
single slice has passed. Keep this file the sole active plan until the stage is actually complete.
