# XBrainLab Now

最後更新：`2026-09-12`

## Active: known-gap closure and deep core responsibility consolidation

### Approved extension — 2026-09-12

The user approved the complete replacement plan in conversation and requested implementation.
Continue the existing integration branch and its twenty commits; do not restart the inventory.
This extension includes deep consolidation of ApplicationService, LLMController and AgentManager,
not merely closing the previous candidate. Reuse existing responsibility owners, preserve visible UI
and all Command/query/18-tool/data/artifact contracts, and introduce no independent control plane.
Internal UI edits remain expressly authorized with unchanged visible behavior. No model/prompt/RAG
policy experiment, new environment/download, WSL compaction or unrelated storage deletion.

Ordered extension batches (the older ledger below remains evidence for completed initial work):

| Batch | Outcome / implementation boundary | Status |
| --- | --- | --- |
| E1 RAG privacy | Route child initialization/retrieval/cleanup failures through the existing central safe diagnostic; preserve queue, cancellation and timeout semantics; adversarial real-log witnesses plus Process/controller regression | Focused GREEN and independent diff review complete |
| E2 Backend core | Move workflow-specific montage/epoch/data construction and duplicated validation into existing focused services; ApplicationService keeps command admission, lock ordering, result envelope and coherent publication | Focused baseline/post, responsibility-group closure and independent review complete |
| E3 Assistant core | Consolidate request construction/validation in existing tool/handoff modules, turn/confirmation/cancellation decisions in existing owners; keep Qt dispatch and thread shutdown coordination in controller | Focused baseline/post, shared admission and responsibility-group closure independently approved |
| E4 UI core | Consolidate training terminal identity/publication retry decisions in the existing publication coordinator and copy classification in presentation; AgentManager keeps widgets/timers/events/rendering and successful-delivery acknowledgement | Focused post/review and remaining responsibility-group closure complete |
| E5 Tools/history | Integrate useful manual launcher and owned successful-test cleanup from local acf7c56d; retain compaction withdrawal; trace source commits, replace/close #133 after verified integration; classify 57 branches / 18 worktree registrations using actual Git and Windows paths | Native post and safety review complete; history classified; PR replacement and approved post-merge cleanup pending |
| E6 Evidence | Strengthen affected high-mock behavior tests and ten existing guards lacking hostile witnesses; independent responsibility/actual-diff review; final same-source canonical gates and one Windows handoff | Ten witnesses GREEN/reviewed; extension cross-boundary review complete; final candidate not yet frozen |

For E2–E4 map each responsibility group's entry points, readers/writers, failures and destination before
editing. Remove the original decisions/state in the same slice; do not shrink files by mixins, private
proxy access, forwarding shells or passing the entire core object to a new helper. Required coordination
may remain with a concrete cross-boundary rationale. Different detached-work identity fences are not
automatically duplicates. State/publication ownership count must not increase. Each bounded slice records
passing characterization, direct regression, actual production +/-/net, retained reasons and rollback.

Independent nonauthor review is required; at most two non-overlapping workers, main owns shared boundaries,
this plan and integration. No commits while workers/tests are changing source: hooks stash unstaged files.
Use existing bounded native runners and the shared Windows environment. Runtime fault tests isolate only
external retriever/model work, not the real diagnostic/Command/Qt/process/persistence behavior under test.
The ten existing architecture guards receive positive/hostile minimal witnesses, not a new guard platform.

E5 history policy: classify active/manual/merged-retirable/unique-dirty/stale-registration entries; verify
Windows-only worktrees before interpreting WSL prunable markers. Preserve original dirty checkout and
settings, source data, shared model/environment and failure evidence. Before handoff finish classification;
after explicit accepted-source merge only remove clean, unused, integrated disposable worktrees/branches.
Unique/unknown entries remain a named retain list; no blanket prune, archive-branch proliferation or force
deletion. #133 source migration is selective: no abandoned compaction source/tests/docs, no obsolete plan
overwrite. Automatic test cleanup may remove only an owned successful-run directory, never failure evidence
or explicit retained/basetemp paths.

Stop condition: all E1–E6 implementation/review and applicable same-clean-head gates pass, then open exact
Windows source with one PowerShell log and deliver one GUI/Assistant checklist/restart command. No per-batch
manual tests/merge, no stopping at compaction or pending CI. Source acceptance and merge approval are still
required; approved post-merge Git cleanup is the final stage operation. Known failures cannot be relabeled
green. Do not claim ideal architecture or zero defects. Only a genuine new authority/resource blocker or
explicit user pause stops in-scope progress before handoff.

Current next step: repair the evaluator harness defect found by final native inference, then freeze the
corrected integration head and obtain same-head CI/native evidence before one Windows handoff.
PR #136 is open; #133 is closed as selectively superseded, with its unique history retained. No manual
acceptance exists for this candidate. Final gates, not speculative cleanup, are the remaining work.

Candidate 9c4af2f5: clean 27-commit integration pushed; docs/lint CI passed and remaining checks started.
The existing offline Granite runtime is GPU-ready with one 6.82 GB model cache. Its real 81-case model
gate failed on case 1 before a completed score: `_EvaluatorControllerHarness` lacks `_conversation`.
The evaluator delegates real controller methods but still owns an old list/history helper; E3 moved
selection to ConversationHistory. Repair only that script's fixture wiring using the existing history
owner and delete its stale private forwarding method. Preserve frozen cases/scoring/admission/no-side-
effect boundaries; no model/prompt/public contract/UI change. Reproduce with existing actual evaluator
trajectory tests, then run the evaluator script test file and real-model gate after source freeze.
The failed native artifact remains under the old exact SHA. No compatibility shell in production.
Evaluator repair: existing normal-execution and typed/origin-guard trajectory tests reproduced two target
failures. The full evaluator file now passes 73 tests/6.94s with the real controller delegation retained;
independent actual-diff review approved and found no other reference to the removed E3 private methods.
Next: commit the script-only repair, push the corrected candidate and rerun its required native gate.

Latest closure evidence: optional-RAG launcher and adjacent temp cleanup 85 passed/17.30s; corrected
architecture witnesses and existing guard suite 256 passed/38.08s; renderer import and actual revision/
retry tests 41 passed/5.35s. Independent E1–E6 cross-boundary review approved with no blocking finding.
The baseline inventory retains 1,255 distinct dispositions and adds three explicit E5 source/test files
(1,258 baseline-plus-extension paths); full-body reading and related-test inventory remain different.
Git retain classification is recorded in existing ignored tools.md: 22 merged-retirable branches,
one active candidate, one protected unique/dirty root, one retained manual-source branch, 14 remotely
backed unique and 18 local-only unique branches. No branch/worktree has been deleted or pruned.
Corrected whole-project Basedpyright gate passed with zero diagnostics; the immutable baseline was not
changed. Commit integration starts with all workers read-only and no active native validation process.

The detailed entries below are chronological construction evidence, not additional active dispatch.

E1 RED evidence: `complete-audit/rag-child-privacy-red` has six failures across initialize/retrieve/close
and RuntimeError/KeyboardInterrupt. Actual child loop + standalone stream handler leaks synthetic path,
email and token before the patch; queue/close assertions already pass. Replace only its three exception
logging calls with existing safe_unexpected_failure (one production file, no owner/queue changes).
Combined E1 GREEN + E2/E4 pre-change baseline is running in `extension-baseline-rag-green`.

First E2 slice: reuse PreprocessCommandService's epoch setup builder for dialog and execution; coordinator
owns normalization/validation of manual montage selection, removing duplicated service validation.
Three existing production files; command lock/training freeze/publication and epoch geometry projection
remain in ApplicationService. Estimated net deletion, no added owner. Baseline includes actual workflow,
application/preprocess/coordinator/epoch context and dialog-boundary tests.
First E4 slice: move existing stricter host training-run predicate into publication coordinator and remove
host duplication; move terminal copy/classification into existing presentation service. Three production
files, no owner increase; timer/render/successful-delivery acknowledgement remain in Qt host. Baseline
includes coordinator/presentation/AgentManager/native-switch tests. Subsequent responsibility-group review
must distinguish these initial slices from full E2/E4 closure.

E1 GREEN: `extension-baseline-rag-green` 651 passed / 54.31s, including both prior guard failures,
six new real child-loop privacy witnesses and actual Process lifecycle tests. Independent E1 review
approved the exact diff and evidence; no constructor/timeout/cancellation change.

First E3 slice: existing ui_handoff module owns validated tool-to-route request construction and
published interpretation identity projection; controller performs any required publication IO then
dispatches typed requests. Existing ToolAttemptCoordinator owns confirmation-request construction from
its own decision/context, retaining exact risk/generation/params. ConversationHistory owns latest-human
message selection used by both parameter-reply and proposal paths. AssistantTurnOrchestrator owns RAG
result cancellation/id acceptance; remove controller's duplicated id/waiting/cancelled check but retain
processing/Qt close admission. No new modules/classes/authority, no timeout/prompt/public contract change.
Baseline: all unit llm/agent plus controller lifecycle faults and long-session integration; characterize
real controller behavior before editing, then migrate test helper references rather than leave wrappers.

E3 baseline `assistant-core-before`: 947 passed / 66.46s; controller/turn/tool source was unchanged during
this baseline. E2/E4 first diffs independently approved; parent spotted None-vs-empty electrode regression
before post-test and worker corrected it, with a real Command old-layout-preservation witness. E2 also
removes the extra epoch list copy. E4 transfers the effective stricter run-identity rule to its existing
owner; render acknowledgement stays in host. Post-change combined run pending.

E2 second slice: DatasetStateService should own selection of preprocessed-vs-loaded detached summary rows;
extend its existing detached-read port, pass bound method directly to publication coordinator, delete
ApplicationService's selector. No new owner/cache. New real publication characterization covers loaded,
preprocessed, empty and detached prior rows; passing baseline required before this source change.

E5 complexity review before implementation: four script files gain about 350–400 net LOC, including an
existing deployed 334-line manual_environment module and 23-line PowerShell entry imported from acf7c56d.
This is an explicit necessary OS/source/environment lease seam, not a second product command owner.
Its source-owned manual run lease already exists in deployment; runner owns only its generated temp dir.
No new product state machine/receipt, no competing environment/launcher. Deletion candidates are withdrawn
compaction source/tests/docs (already absent here); do not import them. Preserve source commit provenance.
Rollback independently removes manual entry/module and associated temp hooks; split review by launcher
and runner even though both integrate in the one authorized stage PR. Native existing runner/temp tests
form pre-change baseline; absent manual-module tests are imported with their source and verified after
integration, not falsely reported as a current pre-change pass.

E2/E4 first post + E2 summary/E5 runner baseline `core-first-after-and-next-baseline`: 766 passed /47.23s.
Independent review approved E2/E4 actual changes. E3 deeper reachability correction: the canonical frozen
18-action registry has no APPLY_INTERPRETATION UI_REQUEST action, and controller's handoff request builder
had exactly one production caller behind that registry check. Its interpretation-publication IO/identity
branch is therefore unreachable; remove it instead of moving it. Preserve the formal handoff DTO identity
and UI route used directly outside this retired Assistant convenience path. Existing ui_handoff module
now validates/builds registered tool requests directly; no new publication factory or compatibility shell.

E5 review found a direct integration mismatch: legacy manual launch requires embedding cache although
current production RAG explicitly permits disabled/unavailable retrieval. Add a real launch-preflight
RED witness, then require only the selected local LLM cache in launcher; retain offline/no-download
and all independent final RAG/model gates. Do not lower candidate evidence because launch can degrade.
E3 additional same-owner consolidation: typed user/debug turn entrypoints duplicate identical busy/close
admission and rejection envelopes. Share that rejection helper inside LLMController (two real callers),
retaining payload validation, normal-vs-debug binding, error/rollback and Qt signal authority; no added
owner or state. The passing988-case post run is its baseline; repeat affected controller/lifecycle tests.

Summary/tools post `summary-tools-after`:493 passed/30.57s; intentional failing child verifies retained
fake-weight evidence, not a failed parent gate. E3 admission + all architecture guard tests:
`guard-admission-after`526 passed/1failed53.61s. The failing new local-only witness injected into a
nonexistent old backend/config.py; correct target to current application/commands.py, retaining the real
guard and expected diagnostic. Other nine witnesses and all controller/lifecycle tests passed; reviewer
approved shared admission. Montage builder row annotation must describe indexed rows as
Sequence[Sequence[float]], matching its sole ApplyMontageCommand caller; annotation/import-only fix,
no conversion before validation or runtime change.
Manual optional-RAG first test attempt failed before target preflight because synthetic module objects
violated active-checkout provenance. Preserve the real guard, patch only external class attributes on
real modules, and rerun before source repair. This failed harness run is not the target RED evidence.

Corrected optional-RAG RED: one failed/one passed, failing exactly the absent optional embedding with
model present. Minimal launcher repair removes only the embedding prerequisite; postcheck is running.
E6 corrected ten hostile witnesses independently approved; actual guard implementations are unchanged.
Whole-project typing found three revision-field diagnostics in the earlier publication renderer cleanup:
the lazy package export prevents analyzer narrowing. Import the existing dataclass from its concrete
module, preserving runtime identity, boolean/positive revision validation and all owners; no baseline
rewrite. Existing renderer/guard tests plus the same whole-project type gate validate this correction.

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
| 0 Inventory | All tracked source/tests/scripts/CI/hooks/dependencies/docs entries | No unassigned file; module responsibilities/callers/tests/dispositions identified, open investigations explicit | Owner/disposition inventory reconciled |
| 1 Command/runtime | Admission, detached prepare/commit, queries, cancellation, terminal/publication | Unique decision owner; duplicate orchestration removed without weakening stale/nonblocking/failure behavior | Focused implementation/review complete; final integration pending |
| 2 Data | Import/review/recipe, classes/channels/montage, preprocess/epoch/split | Real semantics/rollback protection; copies/caches/fingerprints justified or removed | Focused implementation/review complete; final integration pending |
| 3 Training/results | Subject/folds, Stop/restart, persistence/reload, Evaluation/Saliency/SmoothGrad/views | Clear lifecycle/storage/publication; no old-work overwrite or partial result publication | Focused implementation/review complete; final integration pending |
| 4 Consumers/tools | UI internal refresh/dialogs, Assistant wiring, startup/settings/log/close, scripts/Poe/CI/hooks/deps/docs | No consumer-owned duplicate policy; retained tools have real entry points; obsolete paths/tests removed | Focused implementation/review complete; final integration pending |
| 5 Integration | Coverage completeness, cross-boundary independent review, frozen candidate | All batches closed, applicable same-head CI/data/platform/UI/Assistant gates pass; one Windows handoff | Final independent closure review, then candidate gates |

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

Implementation source is the integration worktree `build/dev-artifacts/complete-baseline`; the original
checkout, protected settings, existing manual app, data and shared environment are unchanged. Git owns
exact commit/branch status. Twenty small product/tool commits are integrated; canonical architecture
docs are being finalized before the single PR candidate. No PR/manual acceptance yet.

Ignored `build/dev-artifacts/complete-audit/inventory.json` reconciles all1,255 baseline paths:
322 full-source body reviews,125 UI section/owner/caller reviews,579 test/fixture behavior inventories,
102 tool/CI owner reviews,91 documentation/config authority inventories,17 asset/provenance reviews,
18 deleted files and1 protected local setting. These categories sum to1,255 and are deliberately not
called1,255 deep reads. Package markers and vendor recovery dependencies retain explicit import/provenance
roles. Test-name/import inventories do not imply every test body or branch was deeply reviewed.

| Module | Implemented cleanup / retained responsibility | Evidence and limits |
| --- | --- | --- |
| Command/runtime | Share successful-mutation post-state result policy across4 routes; remove forwarding-only lazy analysis wrapper; reuse exact newly stored resource receipts rather than issue-then-peek | Real Command/FIF, stale/cancel/publication/import-boundary/receipt tests; independent actual-diff review. Distinct detached discovery/apply/preprocess fences remain. |
| Data/preprocess/split | Remove unused Study/DataManager direct preprocess, edit-event processor and Dataset convenience APIs; pure split protocol mapping shared in existing audit owner; inject canonical config parser | Real import/epoch/rollback/split/audit tests; current UI/Command semantics and recipe readback retained. |
| Training/results | Remove duplicate unused training state projections, dead Metric enum/package and unused preflight delegate | Live read models, trainer/fold/result identity, stop/restart, safe persistence and atomic saliency owners retained after body/caller/test review. |
| UI internals | Share5 identical publication shape predicates; delete hidden standalone Smart Parse route; share existing workspace/tab indices | Reviewed-import Adjust parsing stays. Actual Qt topology/partial3D/cancel/publication tests. No visible layout/text/operation changed; final native evidence remains necessary. |
| Assistant | Remove unreachable legacy converters/file authorization; preserve live training output-dir and direct-value origin guards; remove identity normalizer/feedback wrappers; share switch-panel tool; keep only latest completed metrics; remove test-only thread RAG implementation | Real registries/strict controller/admission/confirmation/lifecycle/Qt/process tests. Production Process RAG, model/prompt/corpus and18-action contract unchanged. Native real-model evidence pending. |
| Scripts/config/docs | Delete orphan PyVista probe and historical launcher capture plus dedicated tests; update actual metrics consumers; consolidate stale architecture chronology/claims into current owner docs | Retained scripts have concrete gate/dev/fixture/private-evidence callers. Linux aggregate already stdlib-only before locked coverage install: no unsupported performance rewrite. Dependency/hook/gates not weakened. |

Detailed owner/caller/retain reasons are in the ignored data, training, application-domain, core-runtime,
llm-runtime, models-utils, UI, Assistant/controller and tools ledgers. Test per-file tables are in
`test-quality.md` and `test-quality-consumers.md`. These are local audit evidence, not another tracked
policy platform or active plan. Reconstruct current state from this plan, Git and retained evidence;
do not restart the audit or stop at compaction.

### Focused evidence already completed

Native focused runs use the existing Windows Python, source-isolated child bootstrap, owned process
groups and explicit timeouts. No environment/model download or shared install alteration occurred.
Overlapping counts are never summed as unique tests. Evidence folders below are all under complete-audit.

- Shared core/data:15 new real-command characterization cases passed before edits; combined core/data386
  passed. Lazy analysis/import-boundary/analysis/application/FIF620passed. Data API baseline481passed,
  post587passed; receipts163passed; training114passed.
- UI/Assistant: combined publication/tool/metrics467passed with3 allowed POSIX-only skips; actual1000-turn
  metrics witness retains1 terminal record instead of1000, reset0. This is object retention, not total
  memory/latency/GPU speedup.
- Security/split:18 current-registry training host-path cases passed before deletion; adjacent1324passed
  plus1 exclusively retired fabricated list_files case removed. Remaining controller296passed.
- Assistant adapters:601passed40.60s in `assistant-adapters-after`, independent diff approved.
- UI topology/RAG baseline:382passed69.50s in `navigation-after-rag-baseline`, including real Qt,
  controller process/thread baseline, lifecycle faults, long-session and product walkthrough.
- RAG removal:335passed in `rag-owner-after`; the new Qt witness failed awaiting startup/result within2s.
  Independent review also identified its possible timeout false-pass. Replaced it with real Process held
  pending, Qt timer progress while generation remains uncalled, and verified owned close;11passed5.28s
  in `rag-qt-pending-witness`. The separate real Process positive/cancel/timeout/init/kill tests remain.
  No product timeout was increased. Typed deterministic harness casts add no runtime owner.

Failed attempts are preserved, not relabeled green: initial characterization mistaken expectations,
Windows Git absolute-worktree pointer, source namespace contamination, accidentally removed QDialog
test import, and the RAG witness above were corrected at their actual boundary. The new worktree uses
a relative Git pointer verified by both Git implementations; original dirty files/settings were not
touched. Linux stdlib-only architecture invocation lacked `packaging`; it is not product regression
evidence, and no environment was installed to rerun a CI-equivalent check.

### Review conclusions and honest limits

Independent reviews approved post-state/receipt/data/split/security/lifecycle and UI topology changes.
Initial integrated review found one stale security-test path to the deleted thread RAG module; focused
reproduction30passed/2failed. E1 migrated the boundary-list entry to the retained production Process module
and fixed its real child diagnostic leakage; both guard checks and the six new runtime witnesses passed.
Current large ApplicationService, LLMController, AgentManager and import/visualization widgets remain
maintenance risk surfaces. Their remaining distinct admission/mutation/publication/Qt/native boundaries
have real callers; moving code alone is not evidence of simpler architecture. Extracting into an existing
proven owner is valid; only introducing another independent authority is the avoided risk.

High-mock tests remain where they isolate external work or inject delivery/native faults, paired with
real Command/Qt/MNE/Torch/process/persistence paths. E6 closed the ten identified missing hostile matcher
witnesses; static rejection still does not prove all architectural or runtime defects are caught.
Linguistic RAG branches and arbitrary user conversations are not comprehensively characterized.
Retained vendor recovery source is a supported explicit catalog/provenance dependency, not an unknown
external convenience API; removing it would change a public model capability.

This stage establishes bounded cleanup and protection, not universal defect-freedom, full branch
coverage, scientific correctness or Stable Assistant promotion. Exact-source line/branch coverage and
cross-platform/data/native evidence still must pass before handoff.

### Final candidate steps and stop condition

1. Independently review integrated diff plus inventory completeness and deleted-test/retained-behavior
   mapping. Close concrete in-scope gaps; no speculative new platform or feature.
2. Commit reviewed architecture truth cleanup and this consolidated plan; freeze one candidate, push
   the single integration PR and require all applicable same-head CI checks. Reuse CI regression,
   typing, docs, source-diverse, platform and UI artifacts; do not run an equivalent full local suite.
3. Fill CI-missing real Assistant evidence using the existing pinned offline caches and native Windows
   shared environment. Use current bounded-baseline/model-eval contract and real ChatPanel multi-turn/
   deactivate/re-enable/cleanup capture, not tool-debug as a replacement for inference.
4. Open exact-source native Windows app with one PowerShell log, verify responsiveness, and provide
   restart command plus one concentrated flow checklist: import/class/channel/montage, filters/reference/
   epoch, subject/session split, training Stop/restart, save/reopen, Evaluation, selected Saliency methods/
   SmoothGrad recompute/display switching and Assistant confirmation/cancel/direct-filter paths.

Stop only at that handoff, explicit user pause, or a genuine new authority/resource blocker. CI pending,
audit completion or commit is not an endpoint. After user acceptance and explicit merge permission,
recheck exact source/checks, merge once through PR, then safely clean only this stage's disposable work.
