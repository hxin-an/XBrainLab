# XBrainLab Now

最後更新：`2026-09-11`

## Active: complete internal refactor, one integrated acceptance

PR #135 is merged and manually accepted; its narrow result-read/checker/evidence work is finished.
It does not establish whole-project architectural cleanliness. The user approved this complete stage
and requested implementation with one final Windows manual acceptance. Git owns source identity,
branches, dirty state and worktree inventory.

### Outcome, authority and limits

Establish a reliable, understandable baseline across production, UI internals, Assistant wiring,
tests, scripts, development settings and documentation entry points. Eliminate proven unused
capabilities, duplicate policy/state/adapters and unnecessary measured work; preserve needed safety.
Every tracked file must be assigned to a module and disposition. Listed/scanned is not deeply read.
Every module needs actual entry points/callers, owners, evidence and a retain/change/delete decision.

The user approved one integration PR accumulating independently reversible commits, including the
stage-wide PR-size exception; per-slice complexity review remains mandatory. UI internal refactoring
is authorized only with visible behavior unchanged. Preserve Command/query/Assistant public contracts,
EEG semantics, supported settings/recipes/artifact readback, confirmation, cancellation and publication.
No unknown external convenience API preservation is required, but check dynamic registration,
configuration, scripts and docs before deleting. No legacy relocation or empty compatibility shell.

No UI redesign/public contract/schema change, architecture rewrite, model/prompt/RAG experiment,
environment creation/download, WSL compaction or unrelated storage cleanup. Existing original dirty
UI/test edits, root settings, data, Windows manual app and shared environment remain protected.
New public decisions need permission; continue unaffected authorized work if one area is blocked.

### Ordered batches and completion gates

| Batch | Work | Required completion | Status |
| --- | --- | --- | --- |
| 0 Inventory | All tracked source/tests/scripts/CI/hooks/dependencies/docs entries | No unassigned file; module responsibilities/callers/tests/dispositions identified, open investigations explicit | Enumerating |
| 1 Command/runtime | Admission, detached prepare/commit, queries, cancellation, terminal/publication | Unique decision owner; duplicate orchestration removed without weakening stale/nonblocking/failure behavior | Pending |
| 2 Data | Import/review/recipe, classes/channels/montage, preprocess/epoch/split | Real semantics/rollback protection; copies/caches/fingerprints justified or removed | Pending |
| 3 Training/results | Subject/folds, Stop/restart, persistence/reload, Evaluation/Saliency/SmoothGrad/views | Clear lifecycle/storage/publication; no old-work overwrite or partial result publication | Pending |
| 4 Consumers/tools | UI internal refresh/dialogs, Assistant wiring, startup/settings/log/close, scripts/Poe/CI/hooks/deps/docs | No consumer-owned duplicate policy; retained tools have real entry points; obsolete paths/tests removed | Pending |
| 5 Integration | Coverage completeness, cross-boundary independent review, frozen candidate | All batches closed, applicable same-head CI/data/platform/UI/Assistant gates pass; one Windows handoff | Pending |

Tests and related scripts are cleaned alongside each batch, not deferred wholesale to batch 4.
Source inventory and bounded measurement output use ignored build/dev-artifacts, not a new platform.
Keep the module ledger and next step here; retained evidence is indexed here, not duplicated in logs.

### Slice method and review

Trace actual caller/owner -> passing characterization (or real defect red test) -> delete/reuse/refactor
-> identical focused/adjacent verification -> review actual diff -> integrate a small commit.
Before a complexity-triggering change record deletion candidates, owners before/after, production
+/-/net LOC, necessity and reversible split. Large-file size is a risk signal, not a deletion target.
Reuse existing owners; no generic transaction/control/test framework or added authoritative owner.

Use at most two non-overlapping workers; main owns integration, shared boundaries and this plan.
Independent nonauthor review is required for high-risk data/lifecycle/publication and final closure.
Reviewers inspect actual source/diff/evidence: reachable safety/contract/regression gaps block;
speculative hardening and new product abilities do not expand the stage. No duplicate broad reviewers.
Do not call a module finished with unexplained retain items or unresolved in-scope evidence gaps.

### Test and resource strategy

Prefer real domain objects, minimal EEG data and actual save/reload through Command workflows.
Keep mocks for external/native isolation and intentional faults; replace mock-only product-success
claims before deleting tests. Map removed cases to retained stronger behavior protection; don't shrink
the coverage denominator to claim improvement. Reuse existing fixtures/runners, not a second framework.

Required behavior matrix: normal completion; rejected operation preserves prior state; cancellation;
Stop/restart; selection changes; save/reopen; stale callback rejection; atomic saliency publication;
native cleanup. Fault witnesses include wrong split, omitted checkpoint, stale terminal and partial
saliency where applicable. Assistant retains approved capability/confirmation/visible-result behavior;
affected inference paths require applicable real-model evidence, not an assumed Stable promotion.

Retain the 85% line gate and branch evidence; review high-risk missing branches rather than setting
an arbitrary percentage. Measure suspected redundant queries/SHA/copies/waits and existing test/CI
timings before optimizing. No speculative caches or speedup claims.

L0/L1 focused feedback per slice; early adjacent integration for shared boundaries. Final same-head
CI owns full regression, source-diverse/platform/applicable UI evidence. Reuse equivalent successful
CI artifacts; fill only missing necessary native/Assistant evidence locally. Commands/contracts remain
in docs/validation/README.md and scripts/dev/handoff_gate_spec.py, not a copied gate list.
Serialize heavy native/GPU work in the existing environment. Enforce bounded native process safety.

### Persistence, endpoint and delivery

Update batch status, next step, exact evidence pointers, ownership and blockers while working. On
compaction/restart inspect this plan, Git/PR and owned sessions, then continue the unfinished step.
Commits, worker reports, CI pending and compaction are checkpoints, not endpoints or requests for the
user to say continue. Don't ask for per-batch manual tests or merges. Report progress by completed
criteria and open evidence, with production/tests/scripts +/-/net counts, never invented percentages.

After all batches and independent completeness/cross-boundary review, freeze one candidate. Require
all applicable exact-source checks; never relabel old PR evidence as this candidate's pass. Deliver
outcomes, retain reasons/limits and one flow-organized checklist. Open native Windows GUI with one
PowerShell live-log console, verify responsiveness, provide the exact restart command, then hand over
without continued monitoring. Manual defects get affected/adjacent checks and a new accepted source,
not automatic whole-suite human retesting. Merge only after new explicit acceptance and permission.
After authorized merge preserve required evidence and safely remove only this stage's disposable work.

Completion means the agreed internal refactor and direct protections are complete, not universal
absence of defects, scientific validity or all-dataset/model support.

### Current step / module ledger

Fresh worktree created from merged main; original checkout is unchanged. Establish tracked-file
inventory and bounded module investigations before production edits. Native test environment remains
the existing Windows venv; confirm invocation and owned-process safety before running characterization.
Tracked inventory:1255 files grouped in ignored complete-audit/inventory.json, all explicitly marked
enumerated-not-yet-reviewed. Workers audit tools/config and data-domain files; no source edits yet.
Main owns command/runtime and integration tests; workers must not edit this plan or run heavy suites.

First bounded core slice: four production command routes duplicate the same successful-mutation
post-state verification/error policy (serialized, discovery, apply, preprocess/epoch). Consolidate only
that policy into a private ApplicationService method, retaining caller-owned mutation/fence timing,
special montage work, read-only behavior, cancellation and stale admission. No new owner/module/class;
one production file, expected net deletion. Baseline existing real FIF Command journey plus new
parameterized real-command successful/unreliable/error post-state evidence for these routes; retain
existing unit publication/cancel/refresh tests. Independent reviewer checks fence/error timing and
behavior evidence. Rollback is the single core source/test commit, not the full stage.

Parallel bounded candidates (baseline first): data worker removes only Study.preprocess ->
DataManager.preprocess and its test-only fake processor cases; current PreprocessStateService and
dynamic processor registry remain. No in-project caller beyond delegation/tests was found; verify
all dynamic/script/doc entrypoints before removal. Two production files, no new owner, net deletion.
Tools worker removes orphan PyVista sphere probe and historical hardcoded Windows-to-WSL launcher
walkthrough plus their dedicated tests/routing entries only after confirming retained native startup,
render and launcher contracts cover current behavior. Do not remove current launchers/gates. No
production change/new owner. Focused baseline covers both old helpers, artifact policy, runner,
Study/DataManager and actual retained preprocess/launcher/native contracts. Independent commits.

Core progress: real post-state characterization15passed before source edits (initial normalization
label expectation was corrected, not counted as a defect). Shared verifier is independently reviewed,
production+45/-64/net-19, no owner delta. Together with direct-preprocess deletion, native Command
journeys/ApplicationService/Study/DataManager386passed27.84s. Data convenience deletion net-30
production (actual net-29 after import replacement) and-30 tests; formal prepared path retained. Tools first baseline124passed/1failed:
Windows Git could not resolve WSL absolute worktree gitdir. Converted only this new worktree's .git
pointer to relative form; both Git implementations resolve the same SHA. No source workaround or
test waiver. Original failure retained; tool postchecks plus import-boundary baseline86passed7.22s.

Next core slice: remove forwarding-only _LazyAnalysisCommandService (six methods plus constructor)
in favor of one cached real AnalysisCommandService property on the existing application owner.
Three handler entries resolve the property only when invoked; state/query/reset startup must not
import analysis/training stacks. Preserve all six real analysis APIs and resource receipt identity.
Unlike analysis, other lazy wrappers also own cold-state/reset behavior and are not blanket-deleted.
No new owner/public API; service.py net deletion, architecture guard removes only the retired wrapper
specific checks, keeping actual analysis dependency and montage-routing rules with hostile fixtures.
Baseline: import-boundary tests pass, direct application386tests already pass; verify both after and
real FIF/analysis/saliency callers. Roll back this slice independently. Tools worker owns guard/tests.

Next data deletion: remove unreachable EditEventName/EditEventId capability/package exports and
dedicated tests, unused DataType export, and Dataset.intersection_with_subject_by_idx /
discard_remaining_mask. All have no Command/UI/Assistant/script/config entry; processor registry
lookup checked. Preserve current reviewed event editing/import/class semantics and mask mutation
revision. Replace the remaining dataset getter test's obsolete setup with existing set_train rather
than deleting its still-useful array/label assertions. Baseline preprocessor/dataset/load tests plus
prepared-state tests; main runs serial native evidence before worker edits. No new production owner.

Docs consolidation slice: backend.md mixes historical chronology with stale current-gap claims
(old controller adapters and never-completed acceptance wording). Tools worker may consolidate that
existing page against current source, retain necessary state/receipt/persistence/privacy boundaries,
remove historical repetition rather than create a second history page. Do not edit target/contracts,
invent stage acceptance, or claim source-diverse/native automation proves human/scientific acceptance.
Main reviews actual doc diff and validates affected documentation when it joins final candidate.

Lazy analysis source/guard change independently reviewed;620native tests passed57.02s including
import-boundary, Analysis, all ApplicationService, architecture unit and real FIF Command journeys.
Cached construction is protected by existing command serialization, not a claimed general thread-safe
cached_property. Other lazy wrappers keep their distinct cold-state/reset responsibilities.
Data deletion pre-baseline481passed4.16s; worker removed19 dedicated test functions/22cases, preserving
getter assertions via set_remaining_by_subject_idx(2). Post-baseline587passed6.97s, including receipt
characterization before its production edit. Counts are not summed
across overlapping runs and do not establish final-candidate acceptance.

Receipt slice decision (independently reviewed): retain each domain authorize policy and outer lock.
Training and apply-import reuse pending on confirmed/no-token; preview/review/reload and Saliency
issue a fresh challenge in that case. Existing ResourceReceiptAuthority already owns atomic storage.
Change its internal issue return to the just-stored ResourceReceiptRecord and migrate exactly four
production issue-then-peek callers; remove redundant second reads/impossible empty-record checks.
No extra issue_record convenience API, owner or policy framework; public challenge JSON unchanged.
Expired/cleared/mismatched tokens still fail at later peek/consume before effects. This also removes
the artificial immediate-peek expiry/race failure, not authorization expiry. Five production files,
net deletion; independently review actual diff and exact confirmation/TTL/replay/candidate tests.
First establish passing base/wrapper/real-Command resource tests and confirmed/no-token distinctions.

Receipt postchecks and next training baseline:163passed6.84s in ignored
complete-audit/receipts-after-training-baseline. Includes base authority, training/saliency admission,
Analysis, real import/resource-publication/Assistant receipt workflows and the four training deletion
baseline modules. Independent actual-diff receipt review approved; production+13/-47/net-34, no public
authorization policy changed.

Next training deletion: TrainingStateService.get_progress_text/get_formatted_history/
get_missing_requirements have no consumers; ApplicationService injects TrainingStateReadModel into
StateSnapshotService. Delete those three dead projections and two TrainingProductPort declarations,
retaining live resolver, read-model and lifecycle methods. Delete unused backend/evaluation Metric
package and its dedicated two tests after checked exports/dynamic/script/doc references. No new owner;
worker owns only service/contract/package/tests. Baseline passed above; verify remaining three modules
after deletion, then independent integration review of actual diff. This does not change split behavior.
Training deletion actual diff reviewed: production-76/tests-15, no owner added;114tests passed10.29s
across live training service/read-model/snapshot and current primary UI publication baseline.

Next UI slice: five panels duplicate publication type/revision validation. Characterize existing five
validators in current UI tests before sharing a pure helper in existing application_publication_renderer.
Keep each panel's stale/duplicate/relevance/queue/render policy and visible behavior unchanged. No new
state/owner/module. Current publication tests protect lifecycle; add only uncovered scalar-validation
cases rather than replace real callback evidence. UI worker owns tests then scoped panel/helper edits;
main serializes native baseline/postchecks. Roll back independently if publication behavior differs.
