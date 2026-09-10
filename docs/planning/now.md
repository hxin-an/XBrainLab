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
| 2 Import/interpretation | Loaders, BIDS, labels/classes, channel/montage, metadata, recipes, related UI | 2A–2T reviewed; remaining resource/domain/UI audit open |
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

Recovery verified product branch `cleanup/module-quality` clean at `92a7cc38` (41 commits after
baseline `4770b049`). The original checkout's UI/test/settings changes remain intact. Recheck Git
after reboot; old session IDs are not running-work evidence. Completed slices are recorded below.

**Completed 2U — remove unused label admission/receipt chain.** Main and independent full caller,
dynamic/config/script/doc audit found LabelResourceAdmissionService, its exclusive
LabelResourceReceiptAuthority module and specs_from_paths reachable only from tests. Actual commands
already authorize through DataInterpretationResourceReceiptAuthority and create explicit specs via
session_from_resource_preflight. Remove only the unused chain and imports; keep actual session,
bounded reader, parser config/path checks, progress/cancellation, full hashes and final review SHA.
Two production files, estimated -250 LOC, two unreachable authority classes removed, no new owner,
formal contract or visible UI change. This is not deletion of actual confirmation/publication safety.

First run four direct suites and architecture guard tests unchanged. Migrate five real apply fixtures
to session_from_resource_preflight with real preflight, preserving assertions; migrate the checkpoint
fixture to explicit specs. Remove only the specs helper's exclusive case. Update architecture negative
fixtures and session detection to actual named/aliased session factory imports; keep public-command
allow cases and rejection of UI parsers/cached payloads. The existing generic admission-import guard
remains. Run migrated behavior tests before production deletion, then identical after, actual service
receipt/content-change neighbors, Ruff and independent actual-diff review; commit reversibly.
Original selection289 passed38.37s. First migrated run287 passed/2 failed only because tests demanded
the obsolete session.load diagnostic: actual imports were already rejected by the generic rule.
This was not a product safety bypass. Independent review suggested removing redundant specific checks,
but automated safety review rejected that removal. Keep every existing check and extend session
detection using the existing import-binding resolver for actual factory and constructor calls; test
direct factory, symbol alias and module alias. No gate rule or session.load assertion is removed.
With updated checks and unchanged production290 passed37.04s. After deleting the chain and one
exclusive helper case, retained289 passed38.63s; seven actual receipt/content-change neighbors
passed9.09s. Ruff/format and independent actual-diff review pass. Production -258 across two files;
the removed module is recoverable from Git. No actual confirmation authority or parser/hash changed.

**Active 2W — unused wizard review fallbacks/conveniences.** Independent full audit and main source/test
reads found no production/dynamic/config/doc callers for review_presenter.build_review_rows,
build_primary_review_rows and exclusive legacy text-routing/action-row helpers, required-metadata
helper, ValidationReviewContract.action_targets or LabelSourceState.clear_skip. Actual ReviewImportStep
uses typed backend action_items, current row grouping and shared submission projection. Remove only
these unused helpers and exclusive test fragments; retain and relocate the live empty metadata_summary
assertion embedded inside the obsolete primary-row test. Keep optional-metadata, typed targets,
fail-closed malformed decisions, grouping/warning/blocked actions and remap/submission behavior.
Three UI production files, estimated -160 LOC, no owner/layout/text/interaction/state change.
Existing user UI-internal authorization applies; no new public interface or visible design change.
Observer owns only those three source files and direct presenter test after main signals 2U committed.
First native presenter suite plus eight existing typed-widget behavior nodes; preserve/migrate live
assertions before deletion if needed, same remaining selection after, Ruff and independent actual-diff
review. Main owns plan/inventory and integration. One reversible commit; continue resource and wizard
audit then remaining module order, not a final handoff.

**Completed 2V — measured discarded label payload hash.** Main and independent security/caller review
confirm session full hashes have no consumer: session.assert_current is never called. Actual parser
descriptor/probe guard and prepared reviewed-content SHA remain authoritative. First measure payload
bytes using a real1MiB TXT session plus actual load, and characterize same-size changes during
admission and before load rejecting before parser materialization. No production edit before this
baseline and meaningful resource regression evidence.

If confirmed, preserve the exact per-path owned-work stages, progress/cancellation and early
open_binary context including descriptor and before/after identity checks, but do not read payload
inside that context. Remove discarded hash field/helpers and unused session/reader.assert_current
methods. This deliberately retains early checking; it is not removal of admission or final SHA.
Two production files, estimated -125 LOC, unchanged owners and no visible stage/schema change.
Main owns these files and direct label-admission tests; observer's2W files are disjoint.
Run existing reader race/probe tests, actual before/during-detached-apply no-publication cases and
five migrated apply fixtures along with new characterization before/after, Ruff and independent
security/actual-diff review. Metric is admission full-payload bytes, not total OS/probe IO or wall-time
speed promise. One reversible commit; continue the module audit rather than handing off this slice.
Measured Windows baseline: real1MiB TXT session consumed exactly1,048,576 bounded payload bytes before
actual load; the new zero-admission-payload check failed on that count as intended. All64 correctness,
same-size pre-parser rejection, reader race/probe and apply no-publication neighbors passed10.41s.
The actual TXT load already produced every expected alternating label before the budget assertion.
This confirms one discarded full-stream read, not an OS-IO or whole-application speed estimate.
After retaining the exact context/guard and deleting the discarded hash chain, identical native65
passed10.10s: admission payload bytes0, actual parsed labels unchanged. Ruff/format and independent
security/resource actual-diff review pass. Production +4/-119/net -115 across two files; owner count,
formal diagnostics, checkpoint text/order and final full reviewed-content SHA remain unchanged.

**Completed 2N — unused metadata readers/projection alias.** Main fully read metadata.py (735 lines),
direct metadata tests and actual scan/cache consumers. Independent caller/dynamic/config/serializer
audit confirms BidsMetadataReadBudget.read and _read_json_object have no callers; the
DATASET_DESCRIPTION_MAX_BYTES alias has only one test caller. Actual materialization uses
_read_bids_dataset_description -> parsed_json_value with admitted guards and the retained budget
fields, remaining_bytes and to_diagnostics. Delete only those unused methods/alias; migrate the
existing bounded-read test to BIDS_METADATA_READ_BUDGET_BYTES without weakening its assertions.

Preserve current byte caps/accounting, parsed-content freshness, containment, callbacks and
metadata/recipe field serialization. MetadataFieldResolution.to_dict remains: actual review calls
item.subject.to_dict. Main owns metadata.py/direct test only. Original metadata+parsed-cache suites
and selected actual scan admission/budget cases, migrated characterization before deletion, identical
after, Ruff and independent review; no new owner/API, visible UI or EEG/public schema changes.
Native original, migrated characterization and after selection each passed 27 cases (2.85/2.84/2.87s).
Ruff/format and independent actual-diff review passed; production -30 lines, no owner change.
Committed as `2a61245b`; continue module-2 review/candidate consolidation audit.

**Completed 2O — review projection helper consolidation.** Main read all review source (842 lines)
and direct tests (499 lines), plus searched actual public preview/service/UI consumers. `_raw_paths`
and `_path_values` implement identical ordered nonempty stripped path deduplication; use `_raw_paths`
for recipe diff rows as well as remap options and remove `_path_values`. Remove the private
`_target_step_for_text` forwarding alias and call the existing shared public routing function at
its three internal callers. Keep all visible wording, decision/identity validation and projections.
No UI file edit, new owner, schema or public-contract change; pure deletion/reuse in one source file.
Before deletion strengthen the existing recipe-preview characterization with duplicate/blank/None
path inputs for both EEG and labels, proving unchanged public diff/remap output. Run direct review,
candidate and recipe suites before and after, Ruff and independent actual-diff review; reversible
commit then continue remaining module2. Candidate one-use forwarder remains a separate next slice.
Original/strengthened-before-production/after native review+candidate+recipe selection each passed
80 cases (3.41/3.32/3.27s); Ruff/format and independent actual-diff review pass.
Production +8/-23/net -15, unchanged owners.

Placement source/direct tests were independently read (972/429 lines). Retain trial-order, time,
interval, event-code and committed-scope admission rules. Follow up event-code/interval branch evidence:
reviewer is checking existing downstream tests before declaring a gap. Main noticed interval may
overwrite a time-field `needs_review` with `ready` when duration count matches but onset count does not.
Reviewer traced real TSV plan -> wrong ready -> atomic apply fails nonnumeric onset without mutation.
Existing candidate tests cover normal interval and event-code ready/repeated/conflict; they do not
cover partial onset. User confirmation requested asynchronously because correcting ready changes
visible state. Do not change this product behavior until approved; other authorized work continues.

**Remaining read-only audits / next scope decisions.**

- Candidate/choice-schema source (1348/303 lines), all candidate tests (2518 lines, 56 cases) and
  event-value candidate/schema tests (342 lines) were fully read independently. Retain real temporary
  filesystem/format tests and external event-reader isolation. A one-use missing-files forwarder
  is a candidate only; underlying path resolver has two real consumers and must remain.
- Scan source (1493 lines) and all direct tests (1245 lines, 38 cases) were independently read.
  Preserve explicit-vs-recursive source selection, no-payload discovery then admitted materialization,
  shared budgets, identity/link guards and BIDS index traversal interfaces. No confirmed deletion.
- Metadata/pairing: retain the single shared pairing policy used by candidate, apply and UI.
  Subject-catalog wrapper is not deleted for module count: optional-index freshness/rebuild and
  error normalization remain useful. Label-carrier cache vs streaming fallback and BIDS multi-run
  suggestions have distinct evidence contracts, not duplicate class policy.
- BIDS index/parsed cache/channels/events-reader full source audits preserve distinct registry,
  command freshness, admitted-byte/provenance and atomic MNE mutation responsibilities. Inventory
  records exact full/partial test reads; no dataset-certification claim.
- Module 8 actual aggregation is already slim: it installs only lock-derived coverage, not the full
  product environment. Shards/platform/data/UI lanes provide non-equivalent evidence; retain gates.
  No measured unnecessary wait was established. Launcher/Poe/CI routing audit is only partial
  module coverage: workflow, run_tests, Windows bootstrap and their test bodies still need complete
  reading where inventory says partial. Do not claim all scripts reviewed.
- Continue import event/value/placement, BIDS/montage, metadata and related UI audit. Modules 3–9
  still require their complete per-module closure and final integration evidence.

There is no manual candidate or merge request. Completed slices, context recovery and pending gates
are not an endpoint; continue the next unfinished authorized step.

**Completed 2P — remove import-event identity-only branches.** Independent full candidate/internal-event
audits and main inspected changed caller graphs confirm two no-op layers: candidate's one-call
`_selected_files_missing_from_scan` forwards unchanged to the already-shared `_paths_missing_from_scan`;
internal `_looks_like_prefixed_marker` only returns the same nonempty string as the following branch.
Main removes only these no-ops after passing candidate/lifecycle characterization. Preserve both
the shared missing-path policy and all marker text/spacing/numeric normalization/semantic rules.
One reversible import-event simplification commit, no owners/schema/visible behavior change.

Before source edits, an independent worker owns only test_data_interpretation_reader_lifecycle.py
to add a tiny real saved FIF annotation+stim fixture through build_internal_event_preview, checking
marker spacing/numeric normalization and annotation priority, plus stim-only fallback if coherent.
Existing candidate tests do exercise description normalization after their mocked reader payload;
they do not exercise actual MNE dispatch/priority. Keep their assertions and the reader-failure-close
case. Main runs added characterization against unchanged production, then identical after plus native
Ruff/format and non-author review. No new environment, downloaded fixture or production test seam.
Native original 59 passed3.30s; added characterization before deletion61 passed3.50s; identical after
61 passed3.54s. The real stim reader emits an upstream MNE/NumPy deprecation warning (not failure).
Main reviewed actual test/diff; independent non-author review and Ruff/format passed.
Production +1/-22/net -21, unchanged owners. Commit separately from 2Q.

**Completed 2Q — montage promotion retry characterization, tests only.** Independent audit read all
preparation/coordinator/lifecycle sources (1282/460/355 lines), direct tests (809/630 lines) and real
fixture integration test (130 lines). Keep distinct geometry/resource admission, generation/manual
precedence, and worker/publication responsibilities. Existing real geometry tests and deterministic
async seam isolation are useful. Confirmed uncovered transition: refresh_candidate failure retains
_retry_candidate; a later ApplicationService command calls retry_promotion. Worker owns only
test_bids_montage_coordinator.py: add a deterministic failed-refresh -> retained pending -> successful
retry -> no duplicate publication test using actual coordinator/lifecycle and existing parser seam.
No source changes or new control owner. Main reads patch and runs focused native suite and reviews
whether the assertion actually protects publication/retry, then independent review and separate commit.
This is added behavior evidence, not a claim real-fixture/Windows UI handoff has passed.
Native coordinator suite18 passed1.79s; Ruff/format and independent review passed. This directly
protects coordinator retention/promotion, not separate service-level stale-publication recovery dispatch.
An isolated in-memory missing-retention fault made the new regression fail at pending-candidate
assertion; expected fault detected, no production source mutation was saved.

**Completed 2R — apply helper contraction.** Main fully read apply.py (1479 lines); independent caller
audit confirms `_duration_stats_from_bids_review` is test-only while actual epoch hints already use
the richer `_bids_duration_epoch_evidence`. Migrate its single assertion into the existing complete
duration-evidence assertion (same class-only stats and unknown/count fields), then remove the wrapper.
The one-use `_apply_reviewed_sequence_label_map` forwards unchanged into `_apply_reviewed_mapped_label_map`;
call the actual owner directly with named arguments and remove only the forwarder. Retain actual
mapped batching/per-run decisions, selection, atomic timestamp staging, SHA, rollback and hints.
One production file, no owner/public/visible behavior change. Native event-value apply, timestamp
atomicity, BIDS and service suites original/characterized before deletion/identical after, Ruff and
independent review before a reversible commit. Unused data_filename chain is separate next candidate,
not mixed here; broad remaining service/UI audits stay open even when these focused checks pass.
Original101 passed8.11s; migrated-before-production101 passed7.36s; identical after101 passed7.42s.
Ruff/format and independent actual-diff review passed; production +8/-35/net -27, no owner change.
Independent full test-body audits now complete for service2464, BIDS1375, event-value apply447 and
timestamp atomicity279 lines. Main completed command-service2309, apply-preparation230,
discovery-preparation142 and public-projection124 source reads, and projection253-line tests.
Retain staged publication/rollback, command-bound one-shot resource receipts, BIDS per-run semantics,
bounded/public-vs-persistent evidence and Windows freshness checks; no whole module/UI closure yet.

**Completed 2S — unused filename dependency chain.** Whole production/caller search and both owner
reads show `data_filename` is stored and forwarded but never invoked by interpretation CommandService
or ApplyService. Remove it from those two constructors, their detached copy wiring, and the sole
ApplicationService injection; update exact direct test factories and remove their now-unused helper.
Keep live data_filepath injection and StateSnapshotService.data_filename (actual other workflows use
it). Three production files, no new owner or formal Command/query/UI contract change, deletion only.
Baseline same101 apply suites plus BIDS index/catalog constructor callers, then identical after;
also selected actual ApplicationService interpretation apply/recipe/sequence paths for shared wiring.
Ruff/format, independent actual-diff review, small reversible commit. No source wrappers or data/state
policies mixed into this constructor-only slice. Continue full module2UI/state obligations afterward.
Native direct126 passed8.10s before /8.00s after; selected ApplicationService30 passed9.41s before
and9.49s after. Ruff/format9 files and independent exact-diff review passed.
Production -8 across3 files, test factories/helper -20; no owner change. StateSnapshot filename stays.

**Completed 2T — unused montage fuzzy convenience.** User explicitly authorized behavior-preserving
UI internals. Independent full source/direct tests (montage946/1238, channel183/109) and dynamic
sidebar refresh/result caller audit found `PickMontageDialog.smart_match` only in three exclusive tests.
Actual prefill uses `_safe_mapping_for_montage`, which maps unique normalized identities without fuzzy
inference. Remove only smart_match and its three exclusive tests; replace stale coverage-line-count
test module docstring with its actual behavior responsibility. Keep all existing current safe mapping,
BIDS pending/ready refresh, duplicate/incomplete validation, persistence, geometry and large-table
interaction tests. No layout/text/interaction/state change; no new owner or backend rule.
Main native original montage/channel suites first, then worker owns only montage source/direct tests;
after identical remaining cases, Ruff and independent actual-diff review. Native unit Qt evidence is
not final DPI/manual acceptance. Weak/duplicate unrelated UI tests stay a separate next slice.
Original Windows baseline currently2 failed/44 passed: pending BIDS summary and shown refresh tests
require bottom gap14..16px but actual height150/action bottom131 gives19px. No UI source edit has
occurred. Pause2T deletion while reviewing actual150px minimum/layout and whether fixed gap assertions
are invalid on native metrics; do not weaken assertions or silently change visible UI. Continue other
authorized audits while this focused baseline is diagnosed.
Read-only native failure metrics confirm natural dialog/layout hint143, summary max/hint115, explicit
minimum150 and outer margins14/14. The7px floor surplus is distributed by Qt; measured bottom gap19
is legitimate, not a visual regression. Repair only the two test upper bounds to include the derived
`max(0, minimumHeight - sizeHint.height)` surplus, retaining14px lower margin, existing2px rounding
tolerance, visibility/overlap checks and long-content exact bound (zero surplus). Existing shown
short->long->short refresh case provides all states; no new generic test platform or product edit.
Run full original46 cases with this corrected characterization before deleting smart_match; independent
review must check it still rejects excessive footer space and does not mask the geometry regression.
Corrected characterization46 passed10.86s; strengthened with explicit minimumHeight==150 guards,
46 passed10.73s. Independent review approved derived-surplus bound; native offscreen is not screenshot
or Windows window-manager acceptance. Commit this test baseline separately before the dead UI method.
Baseline committed separately as `b67d24f8`. After deleting the unused method and its three exclusive
tests, identical retained native selection43 passed10.81s; Ruff/format passed. Independent actual-diff
review approved deletion subject to correcting two stale smart-match comments; both now describe the
retained safe/reviewed mapping. Production +2/-50/net -48, no owner or visible behavior change.
Continue the unused label-admission chain; final module and integrated handoff obligations remain open.

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

### Evidence qualifications that remain relevant

- Use a fresh unique PYTHONPYCACHEPREFIX plus -B for Windows tests of WSL-edited source: -B alone
  prevents writes, not stale reads. The earlier ambiguous 1B run was superseded by fresh-cache 84.
  No new environment was installed; an attempted Poetry environment lookup was abandoned.
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
