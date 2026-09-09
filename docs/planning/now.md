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
