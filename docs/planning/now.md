# XBrainLab Now

最後更新：`2026-09-09`

## Active — repair the Windows manual-test findings in #131

### Outcome and authority

The user approved one integrated repair of the manual findings and explicitly authorized the
necessary visible Filter error messages, Saliency progress/result/failure presentation and Montage
size-constraint corrections without redesign. Implement on `cleanup/quality-hardening`, starting at
`c07b3351`, and retain Draft #131 as the only delivery. The previous complete CI is historical
evidence, not certification of the changed source. No merge before new manual acceptance and approval.

Use existing ApplicationService/Command, publication, operation and rendering owners. Preserve the
18-tool Assistant contract, user confirmation, supported data/recipe/result semantics and privacy.
No model/prompt/RAG-strategy experiment, second control layer, blanket refresh or weakened gate.
The original dirty worktree, root settings.json, raw data, shared environments and prior evidence
are protected. Never replace source under a running application.

### Findings and completion requirements

| Finding | Evidence / required outcome |
| --- | --- |
| Re-reference | The retired refresh keyword was repaired in c07b3351. Retain real button/dialog/command cancel, average, selected-reference and stale-review regression. |
| Filter | Native log at 12:46 and 12:49 records h_freq=100 rejected against Nyquist 80 and 50. The Assistant shows only its generic diagnostics failure. Validate the bandpass upper bound against every input's sampling rate in the shared backend; return a safe actionable precondition before mutation. Valid filters work; invalid input preserves source, working data and history. Original user text is unavailable: do not claim a model interpretation defect without evidence. |
| RAG | The launcher selects D:\XBrainLabCache\rag, currently empty. The existing WSL MiniLM snapshot at pinned revision 1110a243fdf4706b3f48f1d95db1a4f5529b4d41 passes the product cache check (11 files, 91,578,415 materialized bytes). Materialize and verify those existing files in the dedicated Windows cache; use native initialization/index/retrieval as evidence, not just the main-model check. |
| Saliency | The user clarified: Compute can be pressed again, but the view remains blank/not computed. Two confirmed Assistant requests at 12:53 logged OK, which does not prove computation or display. Reproduce with real trained results and both GUI/Assistant entrypoints; trace run/model/method identity, admission, computation, publication, render and canvas. Deliver actual selected-result display, or a specific legitimate blocked/failure reason; no silent return to uncomputed. |
| Montage | Native warnings show contradictory 700 minimum / 560 maximum width during summary/mapping transitions. Correct existing constraint/layout ordering, retaining design and functionality; check native Windows DPI and monitor placement. |

### Implementation and review

1. Test-first per defect; for Saliency first identify the earliest broken boundary with a real workflow,
   then repair the existing owner. Investigate fast completion, recompute, result/method/tab changes,
   stale callbacks and failure/cancellation only where they protect this reported flow.
2. Filter uses the existing typed precondition/public-safe result path. Do not clamp frequencies,
   resample automatically, expose raw tracebacks or alter other valid filtering semantics.
3. RAG keeps the approved embedder, revision and corpus. Stage copied real files and validate their
   hashes/containment before native publication; do not carry WSL symlinks or copy a live Qdrant store.
   Build the native index using the existing retriever. Check main-model and RAG readiness separately;
   do not hide genuine degraded-mode warnings. No new download is needed.
4. Montage fixes its existing size owner. Characterize visible controls before editing; test summary
   and mapping transitions and real Windows geometry at 100/125/150%.
5. Keep bounded commits and non-overlapping worker ownership (Filter and Montage); main owns
   Saliency, integration and RAG provisioning. Inspect actual worker diffs/tests. Independently review
   any Saliency lifecycle/publication change against an explicit stale/result/render risk question.
6. Update current truth or evidence contracts only where actually changed; use Git/PR for construction
   history, not another inventory platform or duplicate worklog.

### Validation, delivery and stop condition

Use tdd-guard, test-quality-reviewer and code-reviewer for real observable red/green evidence.
Use validation-runner for applicable gates; UI, tool-contract, privacy and Windows packaging skills
apply only to their respective boundaries. Focused checks precede integration, not full CI per edit.

- Filter: valid, equal/above Nyquist, mixed sampling rates, resample-before-filter and preservation;
  prove safe Assistant feedback and original parameter delivery through the real shared command.
- Saliency: real finite attribution data and actual canvas content for the selected run/method,
  initial compute/recompute, stale and failure/cancel neighbors, result reopening and relevant views.
  No mock command/render or empty "OK" may certify the user outcome.
- RAG: pinned native snapshot, real load/index/retrieval and repeat launch; normal English Assistant
  Filter/Saliency operation with the existing approved local model, not debug transport as a substitute.
- Retain Re-reference checks. Run changed-file Ruff, locked typing and focused regressions.
- Final exact head: all applicable non-skipped CI completed/success, 85% line coverage with the
  unchanged exclusion policy, separate branch baseline, source-diverse data, platform, UI and Windows
  DPI evidence. Reuse equivalent same-head CI; do not duplicate a local full suite.
- Once all findings have their evidence, open one isolated native Windows candidate and PowerShell
  stdout/log, verify responsiveness, and provide the reusable launch command plus one targeted manual
  checklist. Do not add a second log-viewer GUI or monitor the user's subsequent operation.

Do not stop at a single repaired finding, commit or pending CI. Stop at the validated live handoff,
a user pause, or a concrete missing user-only resource/decision after safe alternatives are exhausted.
If the Saliency defect cannot yet be reproduced, keep it unresolved and identify the exact missing
evidence; passing generic tests does not close it. Manual retest covers the affected workflows, not
every already-tested unaffected GUI action. Merge remains a subsequent explicitly approved action.

### Current next step

The user's new manual finding supersedes the handoff endpoint below: first Compute can finish,
but adding only default SmoothGrad in Settings and recomputing remains at Computing without a
result, and Cancel cannot be operated. The waiting cursor is a separate confirmed presentation
defect, not an explanation for the stalled recomputation. The user approved the integrated repair
plan and its necessary UI fixes on 2026-09-09. Start from 34404b7a; retain PR #131 and do not
replace source underneath the user's running native application.

Reproduce first compute -> Settings/add default SmoothGrad -> Recompute with actual training,
commands and rendering. Trace selected parameters/run, operation ownership, computation,
publication and rendering to the first failing boundary; distinguish disabled Cancel from a
blocked GUI or unobserved cancellation. Measure the relevant responsiveness/workload before
calling this resource exhaustion. Add a target-reason failing regression, repair the existing
owner, and remove the Visualization-wide WaitCursor while preserving target fences. No new
owner, polling, model change, reduced samples, forced thread termination or partial publication.
If evaluation cancellation granularity proves relevant, pass the existing cancellation signal
to safe batch/method boundaries. Verify real default SmoothGrad completion with finite rendered
results, operable cancellation, cancel/retry, terminal control restoration, stale callbacks,
ordinary cursor and cross-panel responsiveness. Use focused tests first and applicable same-head
CI/source-diverse/native/UI evidence for final handoff. Stop at one validated Windows candidate
with PowerShell log and restart command, or a concrete user-only blocker; never close this finding
on generic green tests or a cursor-only fix. No merge without fresh manual acceptance and approval.

Reproduction now identifies a UI lifecycle defect, not failed SmoothGrad mathematics: on both
Topographic Map and native Windows 3D, the backend publishes SUCCEEDED with complete noise-method
coverage, but the UI remains Computing for the 120-second bounded observation. The user's live
Windows accessibility state confirms 3D selected, Computing, and no operable Cancel. Topographic
and 3D render jobs lacked the completion/commit binding already used by Map/Spectrogram. The
existing four-view wiring is now consolidated; 3D exposes its existing request/publication identity
and reports terminal/commit through that same parent owner. Cached geometry uses queued Qt signal
delivery, not a timing workaround. The panel-wide WaitCursor is removed while mutation fences stay.

Two cancellation regressions were also reproduced and repaired in the same owner: explicit render
Cancel removed its binding without releasing Computing; navigation during computation could start
an old-result render that stole the compute Cancel. User cancellation now uses the normal render
terminal path; internal tab-change/close cancellation retains the compute fence, and active compute
defers old-result rendering until its terminal publication. No evaluator, algorithm, sample count,
backend API or owner was added/changed. The production delta is two UI files, about 25 net lines.

Focused evidence: 271 adjacent Qt/view/lifecycle tests pass; four real GUI/Assistant Map/Topo
journeys pass default SmoothGrad, heartbeat/cross-panel navigation, compute cancellation with no
result replacement, native-render cancellation with no late commit, and retry. Native Windows
Fusion journeys pass both default SmoothGrad and SmoothGrad Squared, including 3D compute/render
cancel-retry and non-empty OpenGL framebuffers; ordinary QWidget captures alone were insufficient
for the VTK child, so native screen/framebuffer captures are checked. Independent lifecycle review
has no remaining blocker. Next: final static/same-head CI and one isolated native Windows handoff;
prior 34404b7a CI/manual delivery does not certify this changed source.

Filter, Montage and the reproduced Saliency first-entry repair are implemented and independently
reviewed. The remaining endpoint is exact-head integrated validation and one native Windows launch
for the user's targeted GUI/Assistant acceptance. Do not request merge or call pending CI green.
Native multi-monitor validation then exposed a remaining Montage height request defect: on both
DELL P2314H (0,0) and VA24D (-1920,362), mapping transitions request 700x320 but Windows requires
700x400 and logs setGeometry warnings. The prior width fix is insufficient to close the reported
geometry issue. The existing dialog now activates/measures the visible mapping layout before its
first minimum-height request. A real Qt regression failed against the 320px request; all 43 Montage
tests pass after repair. The same two-screen native probe now completes both directions twice with
no setGeometry warnings. No BaseDialog redesign. Validate the resulting final commit before handoff.
The existing pinned RAG snapshot was materialized with 11 matching SHA-256 hashes (91,578,415 bytes).
Native offline initialization indexed the unchanged 23-example corpus; Filter and Saliency retrieval
passed twice, including reopening/reusing the verified index. No model download or strategy change.

Initial Saliency characterization: real MainWindow-before-training / Braindecode EEGNet / no preconfigured
saliency / actual button compute renders on Linux and Windows CPU/CUDA. On native c07b3351, the normal
Granite ChatPanel confirmation also computes and renders finite maps. A separate 30-record/four-class
synthetic sequence reproduced the two Nyquist errors (80 then 50 Hz), resampling, average reference,
normalization, group trial split, training and Assistant compute; it still rendered all four maps.
The new unmocked integration test exposed a test timing defect: QTest clicked a hidden enabled
button before the asynchronous selection query completed. Waiting for actual visibility (not a
sleep) passes all 35 focused native cases. Separately, a real cold Assistant handoff now reproduces
a product failure: its panel-ready callback calls Compute before the selection query completes,
returns BLOCKED / "Review Saliency Settings Again", and leaves sticky review state without any
Saliency command. Repair admission through the existing query/interaction lifecycle, preserving
stale-generation, cancellation and failure protection; no polling timer or independent readiness
policy. Require cold GUI and cold Assistant entry, method/tab change, new-generation recompute and
visible finite canvas. The user's exact dataset/view remains unknown; do not claim every blank-view
case is proven identical to this reproducible first-entry failure.
The bounded repair passes both real entrypoints on Linux and native Windows (36 native focused
cases), 176 adjacent UI/handoff cases and zero-diagnostic locked typing. An independent lifecycle
review found no blocker; the additional stale-catalog test proves a changed publication cannot chain
compute or claim completion. A normal native Granite ChatPanel walkthrough also verified actionable
Nyquist feedback, a real valid 4–40 Hz filter, training, first-entry confirmation and 2,316 finite
Saliency canvas values. The changed screenshot was inspected. Keep these source-bound results
distinct from the final integrated candidate checks; no unsupported claim about every unseen dataset.
Persisted evaluation files have no saliency, but this alone cannot prove memory computation failed:
the existing post-training publication path updates in-memory records, not those artifact files.

The user explicitly approved deletion of three named WSL Poetry environments: rd24cvJ2, TKrzxeIe
and Y5M5tkh1 (all xbrainlab-*-py3.12). Their exact paths were checked before deletion and verified
absent afterward; WSL available space increased by 20,329,267,200 bytes (about 18.93 GiB allocated).
The retained IiX9BmR2 test Python and xaLO7TCQ Git-hook Python/pre-commit were smoke-checked.
No new environment was created; original data, caches and current Windows .venv were untouched.
Do not delete any other environment without approval: Windows PR-specific copies and the historical
C: Poetry environment with an external research Conda base remain only candidates. Windows C: had
47.67 GiB free and D: about 262 GiB before cleanup. WSL internal free space is not evidence that C:'s
VHDX backing file shrank; no shutdown or compaction is authorized as part of this running repair.
