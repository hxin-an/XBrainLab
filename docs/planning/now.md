# XBrainLab Now

最後更新：`2026-09-09`

## Active — architecture and test-quality hardening

### Delivery protocol — one long-lived Draft, one final manual acceptance

- `#130` completed the prior comprehensive cleanup and was manually accepted and merged at
  `8306a649`. This active stage begins from that exact `main` baseline.
- This stage uses one long-lived Draft PR. Small commits and focused validation are construction
  evidence only; they never request intermediate review, manual testing, or merge.
- The user explicitly authorizes a large-PR exception to the normal production-LOC slice limit,
  while every slice remains independently reviewable and reversible. Do not use that exception
  to combine unrelated behavior changes or create a second control plane.
- The only manual handoff is permitted after every row below is closed, final exact-head checks
  succeed, and the final isolated build is live. Only explicit acceptance of that final SHA permits
  merge.
- UI work is authorized only when it preserves visible presentation, copy, interaction, state and
  workflow. Stop for a visible UI decision. Preserve EEG semantics, result reading, and Assistant
  behavior.

### Outcome

Make the product path and its tests materially easier to trust and maintain:

1. Replace product-path mock/compatibility tests with lower-mock command/publication/workflow
   evidence, retaining mocks only for genuine nondeterministic or external seams.
2. Delete UI/controller compatibility fallback, observer, constructor, and test residue only after
   the production caller and its stronger replacement test are gone.
3. Migrate formal legacy data/automation aliases to the canonical Data Interpretation flow, then
   remove each obsolete alias, handler, schema opt-in, test, docs/configuration entry and persisted
   representation that has a real migration. Never silently break a supported recipe/result reader.
4. Reduce measured overdesign in existing owners. Prefer deletion/reuse; split an owner only where
   the extracted responsibility has two real production callers and removes duplicate policy. No
   new authoritative owner, state machine, permanent compatibility path or general quality platform.
5. Raise the global coverage floor to 85% line coverage and start collecting branch coverage as a
   baseline. Coverage remains secondary to real workflow evidence.

### Inventory and closure criteria

| Area | Status | Closure evidence |
| --- | --- | --- |
| Test quality and coverage | Active | Each critical workflow has a lower-mock product path; external/native mocks have a stated seam; 85% line coverage and branch baseline pass. |
| UI/controller compatibility | Pending | Real `Study` product path has no controller fallback for action/readiness/render; migrated tests no longer need the helper/constructor before it is removed. |
| Formal legacy data/automation | Pending | Canonical replacement, dynamic/config/docs/persisted-input sweep, migration evidence, then physical removal of eligible aliases. |
| ApplicationService ownership | Pending | Command admission/publication/owned-work remain its only authority; forwarding/duplicate policy moves to existing owning services or is deleted. |
| Assistant and MainWindow ownership | Pending | Turn/lifecycle and shell/navigation owners remain explicit; only independently owned pure/duplicated responsibilities move or disappear. |
| Scripts, docs, CI and fixtures | Pending | Gates/documentation reflect the canonical flow; no obsolete compatibility contract or exclusive low-value evidence remains. |

### First bounded slice — test evidence map and compatibility baseline

**Problem and evidence.** Final `#130` CI ran 10,658 tests with 86.68% aggregate line coverage,
but the configured floor is 50%, branch coverage is not measured, and mock-heavy tests are
concentrated in UI presentation and compatibility contexts. Product/native/public-data gates exist,
but their relationship to individual compatibility helpers is not yet mapped.

**Scope.** Build a source-backed map for import→epoch, split→training→stop/retry/reopen,
evaluation/saliency, Assistant confirmation/handoff, and startup/close. For each test family,
record the product entry point, state/side effect protected, mock category, lower-mock replacement
if needed, and deletion candidate. Establish the branch-coverage configuration and 85% line floor
only after the map identifies the required focused protections. Do not delete behavior or formal
contracts in this slice.

**Owners.** ApplicationService remains command admission/publication owner; workflow services own
domain mutation; MainWindow owns product shell/navigation; LLMController owns turn/lifecycle;
native/external adapters retain their isolation seam. Owner count must not increase.

**Validation.** Characterize the current aggregate coverage artifact and relevant focused test
families; run coverage configuration checks, Ruff, architecture compliance, and the selected test
families. The final stage still requires the complete exact-head CI matrix and one manual handoff.

**Stop condition.** The test/evidence map identifies the next concrete compatibility family and
its stronger replacement. Persist a new bounded record before changing that family.

### Sequenced implementation

Parallel bounded work — legacy backend data entry retirement: Assistant aliases are absent from
the approved registry; its stale intent/verifier references and real-workflow import fixtures have
now migrated. Retire `LoadDataCommand`, `AttachLabelsCommand`, `PreviewLabelImportCommand` and
`ImportLabelsCommand`, their compatibility service/receipt, headless legacy opt-in and hidden
Dataset Add labels route. Canonical scan/review/apply owns import semantics; saved historical
`label_imports` recipes retain reload/review/apply support. The new fixed historical JSON test
already verifies four-class GDF/MAT replay without any retiring command. `LabelImportPlan` still
has a canonical apply caller and must not be blindly removed with its public command: trace and
preserve any required internal record representation. Migrate remaining generic command/error/
confirmation tests, remove only retired-exclusive tests, and preserve equivalent current resource,
atomic rollback, cancellation and state publication evidence. No visible UI or 18-tool membership
change, no new authoritative owner; expected owner delta is minus one compatibility service.
Independent review must examine the actual data/recipe/lifecycle diff before integration.

Direct dependency closure: `EventFilterDialog` and `LabelMappingDialog` have no current production,
script, or canonical Data Interpretation caller; only their lazy package exports and exclusive dialog
tests remain. Data Interpretation review/apply retains reviewed carrier mapping and event choices.
Remove those orphan dialogs, exports, and exclusive tests; retain canonical preview mapping and
event-choice evidence. Validate focused Data Interpretation/UI suites and import boundaries.

Direct retirement dependency — the old `label_import_preview` cache has no remaining production,
registration, script or recipe reader caller after those commands are removed. Delete that cache
and its preview-only `label_import_policy` dependency, plus unused service forwarding methods for post-load
recipe recording. Keep `DataInterpretationState.record_label_import_for_recipe`, the internal
`LabelImportPlan` representation. The old mapping-cardinality policy has no canonical caller;
its only callers were the retired compatibility service and preview cache. Current reviewed
carrier validation and admitted parser/resource boundaries remain unchanged.
Validate canonical label apply, resource admission, recipe round-trip and historical JSON replay;
remove only source guards/tests exclusive to the retired preview cache. This reduces owners and
does not weaken current resource/atomicity checks or change visible UI.

Current bounded work — Training publication and query boundary: MainWindow constructs Training
with application publication/query ports; its remaining controller constructors, observer branch,
history/readiness/preflight fallbacks serve test-only contexts. First remove ModelSelectionDialog's
controller argument, using its existing explicit TrainingQueryPort and preserving catalog,
provider loading, recovery, weight loading and current model identity. Then migrate panel/sidebar
tests to publication/query state and remove the redundant controller branch. Preserve transient
training progress, terminal publication ordering, stop/retry, confirmation, stale generation and
result reopening. No new owner or visible UI change. Validate model dialog/catalog tests and real
training refresh/runtime tests before/after each coherent change; verify actual event callers
before deleting callbacks. Finish when the production path and retained tests use only the
application ports, with equivalent lifecycle/state evidence passing.

Shared UI dependency — after the last Training fallback caller is removed, delete the two
uncalled controller compatibility lookup/execution helpers in `application_capabilities` and
their four exclusive tests. Retain the unavailable-context error/message used by current Data
Interpretation review and all runtime resolution/async lifecycle protections. Confirm no dynamic,
script or production caller remains; validate application-capability and Data Interpretation UI
tests. This is deletion of an unused convenience API, not a new UI behavior or owner.

Next bounded shared-UI slice — BasePanel/BaseDialog controller storage and DatasetPanel's ignored
controller argument have no product reader. Remove these empty constructor slots and the two
BasePanel observer-refresh convenience methods whose only callers are tests. Migrate callers to
explicit parent/publication ports; retain `_create_bridge`, publication/transient delivery, busy
state and native cleanup. The current core/Dataset/context/constructor baseline passes 131 tests.
Add real Observable delivery/unsubscribe evidence rather than retaining helper-call choreography.
Validate those same families plus Dataset integration and publication refresh. This reduces unused
API, adds no owner, and does not alter widget construction order, layout or visible behavior.

Context-resolution dependency — after removing controller constructors/getters, `find_study` still
searches `controller` and arbitrary `*_controller` attributes only for a standalone test. Remove
that indirect fallback; keep explicit runtime, context.study, main_window.study and Qt parent-chain
resolution. Retain a real parent-chain test and prove controller-only contexts cannot execute a
command. No product caller, registration or script depends on controller-derived context.

Next bounded refresh slice — real-Study command/observer refresh and suppression entry points
return without action; product commands publish revisioned views and Training progress renders via
its transient port. Remove the compatibility changed-state router, suppression/deferred replay
state and their exclusive tests. Retain navigation's guarded refresh of the selected panel and
native-safe callback containment. Remove the inert `refresh` keyword from UI command helpers and
their callers (sync already discards it; async always passes False). Async busy/handle ownership,
result/error delivery, cancellation and shutdown fences remain unchanged. Characterize runner,
navigation and real Training runtime before edits, then rerun after migration. Review actual
async cleanup diff independently. Owner delta is minus the compatibility refresh router; no new
owner, visible behavior or command contract. Separate this deletion from the base-constructor and
legacy data commits; shared guards must protect publication ownership, not require retired helpers.

Final controller dependency — a complete production/script/reflection sweep now finds no caller
of `Study.get_controller`; its lazy factory is the sole importer/constructor of DatasetController,
PreprocessController and TrainingController. ChatController remains active and excluded. The EEG
adapters delegate to existing Study-owned state services and relay obsolete observer events;
tests alone do not justify retaining the unknown-external convenience API. Characterize the current
controller tests, then delete the registry/factory and these three modules. Migrate substantive
data/metadata/epoch/monitor/cancellation/teardown assertions to their actual state service or command
owner; delete only forwarding/relay-exclusive tests. Keep command/public query contracts, recipe
readers, DataManager/TrainingManager and native lifecycle ownership unchanged. Validate matching
service suites plus real import/preprocess/training workflows and source guards; review the actual
diff independently. No new owner or visible UI change. Retire documentation claiming the unused
registry is an active boundary. Stop this slice when no executable registry consumer remains and
all retained behavioral evidence passes; then finish the already-declared integration gates.

Remaining Dataset UI dependency — the final source sweep found test-only branches still allowing
Data Interpretation's async dispatcher to run synchronously when no product runtime exists,
Dataset row actions to invent an unversioned selection, and table rendering to rebuild event
metadata from a live compatibility object. These are not closed by deleting Study controllers.
After the controller slice is committed, characterize Dataset action/render/async tests; migrate
meaningful cases to revisioned rows and explicit async/publication ports, then remove those
fallbacks and their exclusive tests. Collapse the duplicated startup-disabled branch without
changing its text or enabled state. Keep deferred startup, real unavailable-state handling,
generation/row identity, cancellation, resource confirmation and recipe reopen behavior. No new
owner and no visible UI change. Validate real Dataset wizard/import and row-identity workflows,
then independently review the async/state diff. This dependency must close before final handoff.

1. Complete the evidence map and set coverage/branch reporting without gaming the denominator.
2. Migrate the highest-value UI compatibility tests to typed real-service/publication fixtures;
   delete the now-unused fallback path and its exclusive tests. Repeat through the critical
   workflows rather than converting mocks indiscriminately.
3. Audit and migrate formal legacy commands. Known first candidates are `load_data`,
   `attach_labels`, and `import_labels`; include every real schema, script, documentation,
   configuration and persisted-input consumer in the decision. Remove only when the canonical
   Data Interpretation path preserves the supported workflow.
4. Review the large existing owners after their compatibility consumers are gone. ApplicationService
   is first; Assistant controller and MainWindow follow only when the previous changes show a
   concrete duplicated/forwarding responsibility.
5. Reconcile CI, docs, fixtures and tests with the final canonical surfaces, then perform the
   complete exact-head validation and one final manual test.

### Non-goals and retained boundaries

- Do not use a line count, raw mock count, or coverage percentage as proof of product correctness.
- Do not remove supported model implementations, model catalog choices, settings, recipes or result
  readers unless a verified canonical migration preserves their effective behavior; a model-selection
  UI change requires a separate decision.
- Do not weaken native, public-data, Assistant, security, cancellation, publication, SHA/receipt,
  or data-consistency gates to make cleanup pass.
- Do not add prompt/model/RAG experiments, performance redesign, a legacy archive, or a permanent
  compatibility shim.
