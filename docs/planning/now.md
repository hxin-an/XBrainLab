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
| 2 Import/interpretation | Loaders, BIDS, labels/classes, channel/montage, metadata, recipes, related UI | 2A–2H reviewed; loader consolidation active, remaining domain audit open |
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

Recovery verified product branch `cleanup/module-quality`, clean source `7c89b532` before 2I edits
(27 commits after baseline `4770b049`). The original checkout's UI/test/settings edits remain intact.
Read Git again after a reboot; old session IDs are not evidence of running work.

**Completed 2I — test-only loader consolidation, `73002524`.**
Remove test_loaders.py (six redundant mock cases) and test_lazy_loading.py (two cases). Four wrapping
cases map to the retained parameterized wrapping test; EDF maps to richer inference/reader-close
coverage; FIF failure maps to retained raw/epochs error cases; GDF preload already has exact arguments.
Strengthen retained SET success to exact codec/preload arguments before deletion. Original Windows
baseline: 39 passed. Run strengthened characterization, then retained suite after deletion, Ruff and
independent actual-diff review. No production changes; exactly eight duplicate cases removed. Keep
actual FIF/epochs, factory/registration and checked-in multi-format integration protection. One
reversible test-only commit. Whole-tree script/config/doc lookup found no references to deleted paths.

2I strengthened characterization also passed 39; after deletion 31 passed, exactly eight fewer.
Ruff/format pass. Independent actual-diff review approved; no production edits in this slice.

**Completed 2J — retire unreachable label sequence/force chain, `daaf1a59`.** Independent full service/test
audit and main caller review establish actual reviewed sequence imports use mapped checked atomic
batches, not the flat distribution API. Delete LabelImportService.apply_labels_sequence,
_force_apply_single, its fallback count/operation flag, DatasetStateService.apply_labels_sequence,
and the catch-to-zero LabelImportService.apply_labels_batch convenience. Remove the unread
LabelImportPlan.force_import field: architecture/backend.md explicitly defines this as an internal
recipe-record DTO, not a public command; current construction and recipe serialization never read it.
Preserve actual DatasetStateService.apply_labels_batch, checked atomic/timestamp entry points,
explicit event selection, rollback/unknown-state errors and get_epoch_count_for_file.

Worker owns the three production files plus test_label_import_service.py and the event-value test's
single fake adapter call. Main owns atomic architecture guard/tests and plan. First run original
service/event-value/timestamp/state/atomic-guard baseline. Migrate meaningful batch tests to checked
entry, explicit AtomicLabelApplyError assertions and unchanged real Raw outcomes before deletion;
retarget the existing atomic guard to checked owner and retain unsafe-write detection. Remove only
11 sequence/force-exclusive cases after mapping their live-behavior protection. Retain actual
prepared command sequence/recipe/rollback neighbors. No owner addition, UI/public contract or EEG
semantics change; production decreases, one reversible commit after characterization/after tests,
changed-file lint and independent lifecycle/test review. No new guard framework.

2J original five-file native baseline: 79 passed before any label source/test changes.
Migrated checked-entry/guard characterization: identical 79 passed before production deletion;
25 callable-origin guard cases also passed before/after guard-only removal of legacy requirements.
Worker's interop process failed before launch; only main's successful native runs count.
After deletion: 68 passed on the same five-file selection (exactly 11 legacy cases removed),
18 actual reviewed sequence/recipe consumers passed. Nine retained checked-batch cases (not ten)
preserve real Raw no-mutation/rollback and explicit failure phase/cause. Ruff/format/diff check pass;
independent final review approved after correcting the stale force-mode class docstring.
Production +9/-223/net -214 across three files; no owner/public contract addition.

**Declared independent 2K — remove identity alignment work.** Full EventLoader (908 lines) and
five related test files (1,041 lines) read. Its sole align_sequence caller is after strict equal-count
validation; both generated index lists are always identity ranges. Remove the 95-line speculative
alignment helper, impossible truncation warning and identity advanced-index copies. Use already
validated event rows and labels in order; keep integer event-code allocation, prior event values,
timestamps, input isolation, count rejection and all timestamp annotation/lifecycle code unchanged.
No external/dynamic/config/script caller exists; smart_filter stays for actual query/row projection.
Main owns event_loader.py and directly related tests, separate from worker 2J. Native original
event/strict/semantic/label suites, then stronger real Raw sequence characterization before edits:
filtered interleaved triggers, nonzero first sample/prior values, exact order/code mapping, source
unchanged until apply and mismatch both directions. Replace mock sequence success/mismatch tests
only after the real equivalent passes. Characterize existing Nx3/epoch behavior without changing
it; no new public semantics. Same after suites plus actual reviewed sequence consumers, Ruff,
independent review and one reversible commit. This removes demonstrably redundant work, not a
measured user-visible speedup or a timestamp redesign.
2K original native selection: 36 passed; strengthened real Raw characterization: 39 passed before
EventLoader changes. One existing expected MNE warning comes from the safety test dropping all epochs.
After deleting two replaced mock cases: 37 passed; identical actual reviewed sequence/recipe
consumer selection 18 passed. Independent actual-diff approval, Ruff/format/diff check pass.
An isolated reversed-row fault makes both new real Raw cases fail on timestamps/prior values;
no faulty file persisted (first argv-based probe had a quoting SyntaxError, not test evidence).
Production +5/-126/net -121; the helper alone is about 94 lines, not the total reduction.
2K committed `0e1c096c`; continue remaining import domain audits, not manual handoff.

**Next bounded 2L — remove unused BIDS size-only view.** Independent full channels/resources and
main caller/property audit found BidsEventsJsonReader.admitted_file_bytes has no production, test,
dynamic/config/script/doc consumers. Delete only this seven-line compatibility projection; retain
actual content_identities, admitted content binding, per-command freshness/budget and parsed cache.
Main owns this one file/plan; baseline and after direct BIDS events-resource suite, unchanged tests,
Ruff and independent diff review. No replacement API/owner, UI/public/recipe semantics or performance
claim. If baseline exposes a real defect, separate its diagnosis before this deletion.
2L complete focused evidence: identical native 28 passed before/after, no test changes or skips;
Ruff/format/diff check and independent review approved. Production -7 LOC; commit next.

Read-only audits continue: worker fully reviews label carrier/field/format boundaries and tests;
shared BIDS index/cache audits retain distinct registry/command ownership and byte freshness checks.
The tiny subject-catalog wrapper is not deleted merely to reduce module count: its optional index
freshness/rebuild and error normalization need preservation; no blocking redundancy established.

**Next bounded 2M — unused label-carrier projections.** Independent complete label-carrier source
audit plus main helper/caller/semantic-owner read found _sidecar_reader_for_plan and
observed_class_map_for_label_carrier unused everywhere; infer_class_map_from_label_carrier_plan has
only four test callers. Delete these three conveniences and resulting unused imports after migrating
the four assertions to actual derive_class_views(plan)[0]. They check resolved/unresolved names,
not the retired helper's arbitrary display cap. Preserve full expected maps and all actual value
decision, admitted reader, cache-vs-streaming and BIDS recommendation semantics. Worker owns
data_interpretation_label_carriers.py and its direct test file only; main owns plan/native validation.
Native original direct suite, migrated same suite before production deletion, identical after,
actual event-value/recipe neighbors, Ruff and independent review; no new owner/UI/public schema.
2M original direct suite: native 35 passed before any test or production edits.

Module-8 entry audit read current Windows bootstrap and separately supported WSL launcher routes.
Retain distinct cmd/PowerShell bootstrap/exit wrappers and bounded input-method readiness waits;
no measured redundant waiting established. One false WSL log message remains: child output goes
only to terminal by privacy design, while text claims launcher-log mirroring. Correct only after
declaring a bounded truth-sync slice and reading its existing privacy tests; no Windows GUI relaunch
or environment change is part of that audit.

**Remaining module-2 work.**
Continue event/label semantics, BIDS, channel/montage and related UI review. Modules 3–9 remain open.
There is no current handoff candidate or merge request.

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
