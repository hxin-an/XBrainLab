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

Current bounded work — Preprocess publication boundary: MainWindow constructs this panel without
controllers and it resolves the ApplicationUiRuntime. Remove the panel constructor/controller
resolution, legacy observer bridges, and sidebar controller read/mutation fallbacks after real
epoch/preprocess/publication baselines pass. Migrate the coupled mock-only tests to the actual
publication/command path; retain native worker/error/cancel isolation. Scope is the Preprocess panel,
sidebar and directly coupled tests, with no visible UI changes and no new owner. Command admission,
mutation and publication remain ApplicationService-owned. Validate epoch runtime, preprocess async
lifecycle and publication commit/retry, plus affected sidebar tests. Finish this family when no
product or test caller requires its fallback and the same behavior baselines pass.

Parallel bounded work — Assistant historical alias residue: the authoritative
`AGENT_ACTION_CONTRACTS` and validated real/mock registry expose none of `load_data`,
`attach_labels`, or `import_labels`. Remove their unreachable intent/parser/verifier
special cases and migrate tests that protect general parsing/verification to current tools.
Keep current 18-tool membership, confirmation and visible results unchanged. Establish
focused baselines first; no new owner or protocol. Backend/hidden label-route removal
is a subsequent slice and must preserve historical `ImportRecipe.label_imports` replay.

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
