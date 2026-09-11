# XBrainLab Now

最後更新：`2026-09-11`

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
| 2 Import/interpretation | Loaders, BIDS, labels/classes, channel/montage, metadata, recipes, related UI | Reviewed/reconciled; authorized onset/remap fixes verified c697e4b8 with native captures; final evidence remains |
| 3 Preprocess/epoch/split | Processing, copies, invalidation, preview/materialization, related UI/tools | Reviewed3A–3U; unused split-artifact chain retired2d7b43a0; real leakage/publication/rollback retained; final evidence remains |
| 4 Models/training | Catalog, resource preflight, settings, stop/rerun, history/checkpoints | Reviewed/reconciled; authorized zero-metric/device fixes verified fbf2f50d; final evidence remains |
| 5 Evaluation/saliency/views | Read/publication, SmoothGrad/recompute, four views, stale work/render lifecycle | Reviewed/reconciled;5E aliases and5F dormant scheduler retired9ddc44ee/1a4bbfa8; explicit lifecycle verified; final evidence remains |
| 6 Assistant/chat | Tool adapters, turns/confirmation/execution, model/RAG lifecycle and shutdown | Reviewed through6AH;6E/6G retiredecf71cc1/053dda75 with exact prompt/tool equality; original safety guard retained; final evidence remains |
| 7 Shared desktop/runtime | Shell/navigation, shared components, configuration, errors/logging/start/close | Owners reviewed; Qt config routing and native first-paint8J fixed; final same-source closure remains |
| 8 Scripts/dev/CI | Launch/setup, Poe/hooks, runners, walkthroughs/evaluators/reports and artifacts | Dispositions reconciled;8R exit/8T resume/8J frame evidence fixed; integrated CI fixture repairs and final gates remain |
| 9 Cross-module tests/docs | Shared fixtures/guards, dependencies, canonical truth/navigation and coverage gaps | All tracked paths accounted;9O exact offline lock refresh verified; final strict docs/coverage/evidence remain |

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

**2026-09-11 approved bounded Assistant repair.** User explicitly authorized fixing the two failed
response paths and continuing through Windows manual handoff ("授權 做到手冊再給我", understood from
the preceding request as 手測). This supersedes the authority blocker below only for these paths:
out-of-stage split and ordinary GUI workflow-status explanation. Necessary existing prompt/response
flow corrections are permitted; keep pinned model/revision,18-tool/public schema, admission/confirmation,
strict parsing, retry budget and all acceptance thresholds. No model/RAG experiments or new owner.
First capture the exact real GUI assembled request/raw shape using existing bounded private diagnostics,
compare current source/contract to identify the contradiction, and retain ecb failures as RED evidence.
Add focused prompt/request/controller regressions for the diagnosed defect, implement deletion/reuse-
first in the current owner, verify current non-action and action/clarification safety cases, and review
the actual diff independently. Then freeze one new exact head, run required real-model/native GUI and
same-head CI (reuse unaffected focused evidence), and launch Windows GUI+same PowerShell log with the
consolidated checklist. No intermediate manual test/merge request; only handoff-ready or a genuine
new authority/resource blocker is the endpoint. Plan and uncommitted prior evidence updates remain owned
by main. No UI layout/copy source changes planned; authorized response repair is the visible outcome.
Diagnostic original51.76s reproduces the GUI failure with private existing prompt capture enabled;
all three raw responses are ordinary English sentences rather than JSON. Actual publication is empty,
not unavailable, so the retired unavailable-publication prose is not this cause. Model follows the
one-sentence request but omits its envelope despite generic schema instructions. Repair existing final
output reminder with an explicit no-action envelope shape and clarify that sentence-length requests
apply to parameters.message; keep the latest user text unchanged and do not force a specific answer.
Correct rule9's erroneous rule2 reference to the actual typed-clarification rule3, and make unavailable
action blocker message-only explicit. Two existing prompt owners, no new owner/module; only prompt text
changes, parser/registry/retry/schemas unchanged. Direct request/policy tests must fail before edits;
real exact GUI and frozen81cases remain necessary behavioral proof, not phrase assertions alone.
Repair1:215focused pass13.24s and independent diff review approve, but native GUI44.61s still fails
with three bare sentences; not fixed and not committed/promoted. Captured transport includes a
host-inserted assistant-role plain-text context acknowledgment after the system output contract.
Inspect its existing shared owner/two consumers; next bounded correction clarifies in that same
acknowledgment that the following user text is a request (not a reply) and its response must follow
the system JSON envelope, including brief answers inside parameters.message. Preserve the existing
untrusted/authorization restrictions and alternating role topology; no new message/control owner.
Add a discriminating existing real-template projection assertion before editing; run byte-budget,
template/parser/security adjacent tests and identical native journey. This is a measured prompt-repair
iteration, not evidence that the acknowledgment is proven sole cause or a license for wider changes.
Repair2:249focused pass13.94s but native43.97s still fails all three response formats. Remove the
ineffective acknowledgment suffix along with the artificial acknowledgment itself only after template
compatibility review: actual pinned4.0 chat_template.jinja renders consecutive user messages without
alternation checks; official pinned3.3 tokenizer_config.json (707f574c...,9930bytes read-only, no weights)
does likewise. Both current supported native-system templates can preserve separate context/request
user messages without fabricating an assistant response. Keep generic same-role merging/legacy
system handling, current system untrusted policy and host admission. Remove the now-unused shared
acknowledgment constant and phantom byte-budget allowance; migrate actual template/evaluator tests to
system/context-user/request-user with exact unchanged contents. Native model behavior still requires
validation; template compatibility does not prove model accuracy or lower-memory model acceptance.
Repair3 native45.27s still fails the informational envelope; focused248pass/one old topology
assertion needs migration. Independent trust/compatibility review approves deletion, but no behavioral
success claimed. Actual retry prompt reveals a concrete authority mismatch: controller stores its
fixed FORMAT CORRECTION instruction in untrusted runtime_context, which system explicitly says cannot
carry instructions. Next repair uses the existing retry counter to request the fixed recovery policy
inside the existing system message, before byte/token admission. Never promote context/model strings
to system authority; no new state owner, retries or parser changes. Migrate evaluator projections to
the same assembler flag, preserve first-generation/raw versus recovered outcome, and prove system
placement, unchanged latest request, next-turn reset and hostile-context isolation before real GUI.
Repair4 native44.58s still fails; captured system now includes the fixed correction, so channel repair
alone does not establish usable recovery. Next bounded correction addresses the existing opening role:
it calls the model an EEG workflow guide but omits that raw output is consumed by a JSON parser, not
shown directly. State that transport role at the opening, retaining the existing decision catalog,
system authority and exact latest request. This remains the same two-defect repair, not a new model
experiment; success still requires unchanged native questions and full frozen81cases.
Repair5 native44.73s still bare prose. Stop adding wording without a discriminator. The pinned
model's official JSON example uses a formal output schema; current catalog contains only individual
input schemas plus prose/example envelopes. Read-only bounded diagnosis will compare the captured
exact request against the same request with the existing root envelope expressed as a JSON Schema
(no tools/parameters/state changed), using the same installed engine and greedy512-token policy.
No model download, constrained decoder, answer prefill or parser rescue; retain both raw outputs.
Diagnostic15.89s: captured control and added root schema both return bare prose; no schema addition
will be shipped. Diagnostic17.19s: minimal transport emits JSON but wrong content/stage, while the
unchanged full captured prompt with only "with/use message only" changed to "with/use parameters
containing only message" emits the correct empty/respond_to_user/message envelope. This isolates
ambiguous field scope in existing rules, not basic model JSON incapability. Apply that exact scope
correction in decision/recovery policy; unchanged native questions and full81cases still required.
Repair6 passes the unchanged native two-turn/deactivation journey46.92s: first answer one generation,
second answer one existing format retry, no tools or mutations; controller/dispatcher/threads released.
Main visually reviewed the final native transcript. Same565focused cases pass25.35s, including real
controller retry dispatch/new-turn reset, hostile context and evaluator parity. Independent reviewer
approves actual diff. Production5files +41/-43/net-2, zero owner delta; script changes only keep the
evaluator on the product request path, frozen cases/thresholds untouched. Freeze this repair with normal
hooks, then exact-head81model/native evidence and CI. This is not yet final handoff or Stable promotion.
Exact0ffd88d6 full81run143.27s fixes split_before_epochs_en and select_channels_before_data_en,
retains36/36positive and10/10+5/5origin guards, but introduces ambiguous_en_alt: a broad desired outcome
is turned into an unsolicited bandpass proposal with invented cutoffs. Host blocks all side effects
and asks for cutoffs, but that wrong-action clarification still fails the unchanged baseline. Do not
accept the new ID. Direct regression repair clarifies existing Rule3/4: parameter collection applies
only after the user requests a specific operation; an unspecified operation needs an operation-choice
question, not assumed preprocessing/cutoff collection. No Host intent grammar or new routing owner.
Retain0ffd evidence; revalidate both native questions and full81 before pushing the next candidate.
Reviewer narrowed the operation-choice rule to ambiguous action requests only, preserving ordinary
informational answers.71focused policy/request tests passed6.17s before that narrowing; final wording
and frozen model/native evidence are next. No new failure is accepted or reclassified.

**Exact candidate ecb68e3f — final evidence / bounded authority question.**204commits after4770,
PR134 draft pushed, manual Windows checkout clean at ecb68e3f764150c828beae753f95d439d18af356 with
the existing installed environment. Independent942..ecb delta/inventory closure approved. Main plan
updates after this freeze are uncommitted progress only, not a new validated candidate. No handoff/merge.
Same-head offline81-case model evaluation183.45s again fails bounded gate on split_before_epochs_en
beyond the three accepted IDs;36positive/10explicit-origin/5missing-origin pass. First clarification
contains non-admissible pending-action inputs, both recovery envelopes fail, no confirmation/tool/UI
handoff/mutation. Preserve d8 and ecb failures; no retry-until-green, allowed-list/threshold change.
Current native GUI/deactivation capture51.42s independently fails first explanatory prompt after three
invalid structured responses; user-visible terminal error, no tool execution. Deactivation/re-enable,
cache preservation and final runtime/dispatcher/thread cleanup all pass. Exact runtime/cache identity
matches pinned Granite4.0-micro. Main inspected its native ready PNG; full two-turn journey NOT passed.
RAG strict10checks/3known queries pass14.27s at exact clean ecb. Existing owned-process trees all exited.
Exact ecb native preprocessing8cycles and render12cycles pass; render is intentionally Windows-native
offscreen, actual3D skipped. No3D-interactive claim. Final CI source-diverse/default/DPI/docs/static/
most platform/shards passed; Linux-unit-rest and Windows-product-lifecycle plus aggregate still pending
at08:09UTC. Fetch actual final CI outcomes next; do not duplicate equivalent full local regression.
Main asked asynchronously for explicit authorization to repair exactly the two Assistant failing paths,
including necessary existing prompt/response flow adjustments, keeping model/18-tools/safety/gates
unchanged and no RAG experiments. No answer yet; current stage excludes prompt/model experiments.
Continue unaffected checks and read-only diagnosis, then request decision if still missing. Do not
launch a manual acceptance candidate or silently accept either newly observed failure. Consolidated
draft manual checklist lives in ignored build/handoff-evidence/<ecb-full-SHA>/manual-checklist.md.
Read-only final diagnosis: the d8 and ecb split-case payloads are identical, with structured profile
512tokens/greedy/two recovery attempts. Independent GUI review confirms same structured generation
profile, unchanged walkthrough prompt and no proven runtime/config plumbing bug. GUI raw envelopes
were not retained, so malformed shape/cause cannot be claimed. Real GUI assembled context differs
from evaluator synthetic cases; removed unavailable-publication prose could matter only if that
unrecorded condition applied. Do not claim either cleanup causality or random-model variation without
evidence. Prompt/parser acceptance/retry/model changes remain outside current approval.
Final CI34577058477 completed/success at08:12:13UTC; exact PR134 base4770b049/head ecb68e3f rechecked.
All24non-skipped checks are completed/success (three intentional workflow-routing/deploy skips).
Full Linux aggregate and unchanged85%line/branch-data gate pass, as do source-diverse datasets,
WindowsDPI/defaultvisual, human-like journey, static/docs and Windows/macOS native/platform gates.
CI success does not cancel the two local Assistant failures. No local native process remains; no
manual acceptance app launched. Only necessary new Assistant repair authority is outstanding.
Canonical aggregate reports line86.97% (80593/92672) and branch72.49% (21445/29584); the displayed83%
coverage.py total combines lines/branches and is not the line-only85%gate. PR134 checkpoint comment
records successful CI plus both failed local Assistant gates, pending manual acceptance/no merge.

**Bounded8U — retire obsolete Assistant tool-chain capture.** Final entrypoint review reopens the
script inventory: capture_chatpanel_local_tool_chain_walkthrough expects scan_source, preview_interpretation
and validate_interpretation, none exposed by the current formal18-tool registry. No configured CI/Poe/
handoff consumer exists. Remove that obsolete CLI, four exclusive tests, its config-isolation parameter/
fixture branch and obsolete developer command. Preserve all actual Data Interpretation backend/UI
commands and current local Assistant captures. Visualization's sole helper import can use the already
imported local_walkthrough module: identical screen-origin movement and1280x800 size, no new helper,
owner or production change. Establish the original five-script-suite baseline; after deletion run the
four retained suites, Ruff and independent actual-diff/caller review. Correct stale inventory retention
instead of counting the obsolete trajectory as model evidence. Git-reversible separate small commit,
then refresh exact-source CI/manual checkout and finish final native/current-model evidence; no manual
handoff until applicable gates pass. User's whole-unused-capability retirement authorization applies;
no UI source, public tool membership, model/prompt change or new approval is needed.
Result: original113pass10.96s, retained108pass10.37s; exactly four obsolete direct cases plus one
entrypoint-isolation parameter retired. Initial after invocation had a temporary command quoting
SyntaxError, no test result; corrected invocation and owned tree cleanup succeeded. Independent
actual-diff review approves identical geometry reuse and no live caller loss. Scripts net-593,
tests-109, production unchanged. Current source inventory1255tracked plus44retired remains1299rows.
Commit0851b962 accidentally used a nonexistent command-local hooks path; main immediately ran all
configured pre-commit checks against exact HEAD~1..HEAD, all applicable hooks passed. No persistent
Git hook configuration changed; subsequent commits use normal hooks without override.

**CI cancellation evidence repair.** Exact942 CI now passes all other applicable jobs, but backend
has3755pass/1fail: explicit saliency cancel elapsed0.331s exceeds an arbitrary0.1s assertion. Actual
service/manager path uses wait=False and never joins the evaluator; independent read agrees elapsed
includes shared-runner scheduling and does not isolate blocking. Replace only this test's timing
heuristic with a test-owned cancellation thread and existing watchdog: cancellation must return while
the evaluator remains Event-blocked, publish cancel_requested/CANCELLING before release, then become
CANCELLED after cleanup with the original evaluation preserved. Always release/join owned work in
finally. Keep current watchdog and adjacent real saliency publication/cancellation tests; do not relax
latency constants, skip a case or change production. Verify normal behavior plus a process-local
blocking-cancellation fault rejected by the strengthened assertion; independent actual-diff review
and focused tests precede a separate test-only commit and fresh integrated CI.
Result:30selected saliency/real accumulation cases pass13.34s. Process-local blocking-cancel fault
fails the exact compute_finished ordering assertion1fail10.33s; evaluator watchdog expiry cannot
masquerade as nonblocking success, and owned tree exits. No fault source persisted. Independent
actual-diff review approves cleanup/order/terminal/original-result identity protection; test net+30,
production unchanged. Earlier942 native stress completed8preprocess and12render cycles with owned
cleanup; render script intentionally forces offscreen and skips actual3D, not native interactive3D
acceptance. Those artifacts remain942 checkpoints, not final-new-head evidence.

Git recovery checkpoint: product branch `cleanup/module-quality`, HEAD `d8dcef26`, 200 commits after baseline
`4770b049`. Original checkout UI/test/settings dirt remains protected. Recheck Git after reboot;
old session IDs and plan text do not prove a process is running. No manual candidate or merge request.

**Checkpoint —8J repaired; PR134 integrated CI repairs and final model/native evidence in progress.**
**2026-09-11 authorization update.** In direct response to the preceding explicit request naming
four visible repairs and the five retirement groups (including loss of corresponding old Python/CLI
entry points), the user instructed "繼續做". Proceed with precisely those listed corrections and
retirements; this is not general UI redesign, a changed formal18-tool/Command contract, new download
permission, handoff acceptance or merge approval. Earlier no-reply/pending paragraphs below are
historical evidence of the rejected attempts, superseded for these exact decisions only.
Start with test-first UI/domain fixes in two non-overlapping groups: import readiness/remap label and
training zero-metric/device adapter. Main owns integration/plan, focused actual Windows runs and
small commits; workers initially write regression tests only. Observe each intended RED before source
fix, then identical retained/adjacent tests and native screenshots/walkthrough without asking for
intermediate handtest. Keep the backend readiness owner, wizard label parent/layout, table renderer
and existing typed recommendation adapter; no second readiness/state owner or unrelated copy/layout.
In parallel main resumes5E with fresh owner/exact-hash/context baseline, exact eight-alias deletion
and corresponding exclusive guard/test retirement. Preserve real schema/hash/cancellation/ownership
tests. Continue5F/6E/6G/split artifacts afterward under their bounded steps below. Stop each slice at
verified source/evidence and continue the stage; only final applicable same-source gates precede
one Windows manual handoff.

**Authorized repair evidence — import and training.** Four reported defects reproduced before
source changes: actual TSV preview ready instead of needs_review and parentless Qt confirmation label
(2fail2.06s); zero metrics N/A and concrete adapter TypeError (2fail6.27s; stronger CPU/blank case
3fail6.36s). Fixes retain existing placement status owner, add the label to the review layout, reuse
the optional metric reader and pass existing prospective_device through Protocol/concrete adapter.
Initial extra expectations were corrected, not production policy: strict BIDS independently rejects
the fixture's nonnumeric onset; empty Study legitimately supplies a starting recommendation. The
device test now compares actual runtime/service DTOs and requires backend invalid-device rejection,
with service finally-close. Full training/UI65pass7.15s; corrected import/domain/UI206pass12.45s.
One pre-existing fixed126px clipping test failed identically on original layout0.79s; actual font-
metric-derived clipping preserves all original tooltip/fit assertions and passes original0.63s.
Both independent actual-diff reviews and Ruff pass. Native Windows isolated example captures show
0.0000/0.00% versus N/A, and remap label visible inside dialog at20,158 (not a top-level window).
Main inspected both PNGs under build/dev-artifacts/module-quality-audit/approved-ui-repairs; no
clipping of the changed elements, no user data/settings changed, and owned preview widgets closed.
These are focused examples, not real EEG import/training or final Windows manual acceptance.

**Resumed5E result.** Fresh owner/exact-hash/record-context39pass9.17s before; retained38pass8.94s
after removing eight uncalled eval.py alias imports and one exclusive re-export identity test. The
domain owner, three genuinely used record types, schema/hash/sealing/cancellation behavior and all
negative ownership/import guards remain. Independent actualdiff/caller review and Ruff pass.
Production-8, no owner added; old imports of those aliases now fail as explicitly disclosed.

**Resumed5F/6G execution scope.** Re-read graphs confirm5F also owns the now-exclusive runtime port
and TrainingManager submission-failure forwarder. Actual5F ceiling is five production files plus
one native-stress script, not the historical three-file estimate; delete only scheduler/submission
failure chain and exclusive fixtures, preserve command/target/cancel/terminal/delivery owners. Owner
delta-1 scheduler, expected production deletion-only around350lines; no new module/class/receipt.
Worker5F initially prepares only the declared graph; fresh baseline then migrated-test passing baseline
must precede source retirement. Worker6G owns disjoint tools/coordinator and exclusive tests/guard
after fresh18-tool payload digest and surface/realflow baseline. Main owns6E/plan/commits and actual
diff review. Both workers stay read-only during hooks; no overlapping architecture guard writer.
For6G use agent-toolcall-designer checks: runtime compatibility removal only, same backend admission,
exact names/order/descriptions/schema/confirmation and no altered public membership or model prompt.
Fresh5F baseline585pass45.19s. Concurrent6G baseline collected340, with201pass/139setup errors after
its shared pytest temporary root disappeared while5F finished; this is environment interference,
not a product RED or valid baseline. Both sessions ended; rerun6G with a unique per-run
XBRAINLAB_TEST_TMPDIR and use distinct roots for every concurrent pytest job from now on. No gate
assertion/timeout/retention rule changed. Initial18-tool digest169558e0df13cd02d242d8949628f1d30c299e427d9172d07367d505747a9e42
was confirmed by the isolated rerun:340pass/6warnings73.65s, after which6G source retirement began.
5F migrated retained tests566pass/640warnings37.66s against unchanged production before scheduler
deletion.6E fresh91pass1.24s, retained87pass0.85s; all seven full prompt hashes match before/after,
and pre-deletion sentinel substitution changed none. Review/lint and small commits follow.

**Resumed split-artifact retirement.** The authorized old output/CLI/schema chain has no live
producer or configured/dynamic caller. Remove build/write/split_indices convenience APIs and exports,
their exclusive group/provenance/selection renderers/constants, validator CLI/schema/direct tests.
Keep audit_dataset_splits, materialization_digest, preview rows, epoch-window validation, diagnostic
bounds/privacy, group/class leakage, actual dataset publication/receipt/rollback and stored data.
Two production files, one script and related tests/docs; expected production around-260LOC, no owner
added. First baseline direct audit/validator plus dataset generation and split application boundary;
migrate privacy/invalid-source tests to actual audit.to_dict() and keep their assertions against the
live diagnostic owner, then verify unchanged production before deleting artifact-only tests/source.
Truth-sync thesis protocol to label future reproducible EEG evidence requirements as requirements,
not an existing export/rerun product capability. No replacement schema/exporter or scientific claim.
Independent actual-diff/data review, retained focused tests and doc links required before commit.
Result:48baseline4.57s,44migrated-on-original4.29s,42retained-after4.42s; deleted four artifact-only
domain cases and two validator-only cases, preserved actual diagnostic privacy/invalid-source tests.
Production-258, script-123, no owner added. Independent review approved runtime/test deletion and
requested one adjacent future-runner wording correction, now applied; no scientific evidence claim.

**Resumed retirements verified.**5F retained566pass/640warnings35.98s after source deletion; independent
lifecycle review confirms explicit target, cancellation, staging/publication, retry/discard and
shutdown remain. Production-359 and script-3; one dormant owner removed.6G retained332pass/6warnings
70.42s with the exact same18-tool digest; independent actual routing review approved. Its architecture
guard/test deletion was policy-rejected, so those files were restored intact and remain a safety
check against future legacy-adapter reintroduction. No retry or indirect removal; eight exclusive
adapter cases retired.6E independent actual-diff review approved; production-104, four exclusive
prose cases retired, seven full prompt digests unchanged. All20 changed retained Python files pass
Ruff after formatting/import cleanup. These are focused results, not final same-source gates.
Actual Git inventory1257 tracked files now all have dispositions; the audit has1299 unique rows,
including42 retired paths for traceability. Static/binary/generated groups are not line-by-line source
review claims. Forty-two stale candidate rows were reconciled to actual stage commits/callers and one
new CUDA test row added. No bare unassigned tracked path remains; this does not close UI decisions,
unrun gates or scientifically validate all EEG/model behavior.
At product/test source bf231298, installed Basedpyright1.39.2 observes0 diagnostics against the
unchanged0 baseline; whole Ruff check passes and1111files are formatted. Current test delta is
net-1216 (the previously reported-1266 was before the50-line6AH regression); production/scripts stay
net-7391/-1099. No full coverage, same-head CI, source-diverse, native/model or handoff PASS claimed.
At2d7b43a0 the unchanged Basedpyright1.39.2 gate again observes0diagnostics against0 baseline.
Whole architecture guard, Ruff/1105formatted files, user-site source/navigation and guidance audits
pass. Stage code totals versus4770b049:production+376/-8734/net-8358, scripts+447/-1672/net-1225,
tests+7169/-9259/net-2090. These totals do not measure correctness or scientific coverage.
Next: resolve8J first-paint evidence, then final source freeze/gates. Do not repeat
rejected deletions indirectly, reopen compaction or ask for an intermediate merge/manual test.
Independent integration closure review finds0missing paths and exactly42retired rows matching Git;
no live deleted-module/API caller or additional command/publication/lifecycle blocker found. This
does not replace final CI/data/native/model evidence.9O reviewed, ready small commit.
8J resumed diagnostics initially failed on sandbox/quoting and diagnostic-only nonexistent geometry
key; stale JSON is not evidence. Main identified exact owned WindowsPython28196/launcher11228 via
decoded probe payload, stopped28196, and verified both exited (launcher exited naturally). No user
process stopped. Main used the existing owned-process Job Object supervisor plus existing capture
wrappers (no source changes), recording first-paint geometry and native window pixels before
QWidget.grab under isolated preferences. The65s-bounded diagnostic completed with owned_tree_exited
true; no preview process remains. Evidence is under
build/dev-artifacts/module-quality-audit/first-paint-native-main/diagnostic.json and adjacent PNGs.
Main inspected the native images: standalone320px runtime surface extends to355px, clipping the
Open Assistant Settings button. Its horizontal maximum is0, so the existing standalone check misses
the clipped surface. Real dock pre-paint geometry has content564px/viewport320px/horizontal maximum244;
before the subsequent native capture it has already settled to323px/content323px/maximum0. Thus the
gate's geometry and image are not guaranteed to represent the same frame. Overall gate remains
failed; no weakened assertion or artificial pre-observation settle was applied.

**New8J visible repair authorized.** The four previously authorized UI repairs did not cover
this newly confirmed clipping. Main explicitly requested permission for bounded first-show width/
layout synchronization, preserving copy/functions/normal layout, plus corresponding honest frame
evidence. The user explicitly replied "同意" to that exact request on2026-09-11. Proceed with this
bounded repair and then final integration gates;9O is committed78900414,199commits after baseline.
Main owns panel regression/source; one non-overlapping worker owns capture evidence regression/source.
Existing panel show/resize/reflow and capture owners remain the candidates;
no new state machine/timer/control layer. If authorized, first reproduce actual first-frame clipping,
fix only the existing width/layout owner and frame correspondence, then retain strict320px checks,
run adjacent reflow tests, inspect native before/after images and obtain independent review before
final source freeze. No authority blocker remains for this repair; still no manual-test candidate.

**8J repair result.** Native first-paint regression reproduces actual runtime QRect59,12,296,176
outside320px panel (1failed0.82s). Activating the child layout alone still fails: measured content
width564px while viewport320px; flushing posted scroll-area requests has no effect. The existing
reflow convergence now activates chat_layout and synchronously sends LayoutRequest to QScrollArea,
letting its widget-resizable owner recompute content geometry. Production+2, no owner/timer/state
added. Same direct regression plus capture checks3pass6.60s; full chat/history/scroll/capture174pass
34.23s, final stronger capture-time geometry-change case within174pass35.32s. Missing runtime-bound
gate originally reproduces KeyError1fail6.36s; real moved-surface/hmax0 and prepaint-valid/postgrab-
invalid cases now reject clipping without weakening320px checks. Capture narrative distinguishes
strict pre-handler geometry from a later widget.grab and its post-grab geometry; it no longer claims
they are the same presented frame. Independent panel lifecycle review finds no synchronous reflow
recursion; existing coalesced scrollbar timer/history guards remain.
Native owned diagnostic under first-paint-native-repaired passes the complete walkthrough; first
standalone/dock content width320px,hmax0,runtime right308px. Main visually inspected both native
before-grab PNGs: settings button complete, no changed copy/function. Owned process tree exited.
These are focused native examples, not real-model readiness or final same-head CI/manual acceptance.
Next freeze the reviewed source and create the single stage PR; run required same-head CI and only
CI-uncovered local Assistant/native evidence. Original failure artifacts remain for comparison.

**Integrated candidate d8dcef26 / PR134.** Pushed the single draft stage PR with exact base4770b049;
200small commits, clean source. Native manual checkout prepared at the same SHA with existing shared
Python and exact installed direct-lock dependencies; deployed D-cache manual launcher hashes match
the retained infrastructure source. Model/cache preflight is gpu-ready, pinned Granite4.0-micro
cache6,815,495,237bytes, embedding ready, no downloads/new environment. Same-head CI is running;
docs/lint/default-visual and Windows/macOS product smoke passed so far, not the full set. Bounded
offline real-model evaluation is running against the frozen manual checkout under an owned process
timeout; later changed source requires fresh exact-head evidence.

**CI repair — POSIX wrong-kind error classification.** macOS platform-core-contracts job103179649989
fails one actual file-requested-as-directory case (151pass/2Windows-onlyskips): O_DIRECTORY rejects
with ENOTDIR before fstat and generic OSError wrapping hides the intended directory requirement.
Do not remove O_DIRECTORY: on platforms without O_PATH this could open/block on special files before
kind validation. Preserve all descriptor/no-follow/containment/cleanup owners and flags. Normalize
NotADirectoryError at the existing admission error boundary to a private-path-free directory-component
requirement; retain existing mismatch assertion and add actual non-directory ancestor rejection.
One production file, no new owner/API; expected+4LOC. Verify actual POSIX rejection before/after,
native Windows adjacent admission/verifier suite, independent security review, then fresh CI.
This is an in-scope cross-platform gate repair, not permission to weaken checks or change UI/tool policy.
Actual Linux stdlib component probe (real POSIX filesystem, direct source-module load because no
Linux pytest/product environment is installed) reproduces final+ancestor refusal message2fail and
same2pass after normalization. Existing native Windows admission suite13pass/3POSIXskips5.89s; flags
and Windows branch unchanged. Independent security review approves preserving directory-only opens.

**CI fixture repairs.** Linux integration-rest exposes a stale navigation double: list.append cannot
accept the real switch_page on_ready/on_failed callbacks. Keep actual AgentManager/controller/signal
topology and model-engine external isolation; model asynchronous readiness with a captured callback,
assert no dialog/terminal before readiness, then invoke readiness and retain exact one-outcome/terminal
checks. No production routing fallback. Linux backend six prepared-apply tests inject resource results
after a cached SAFE preview, so reliable POSIX ctime correctly bypasses that new probe. Worker owns
only the affected test fixtures: explicitly select the existing non-reusable stat capability when
testing fresh apply admission; retain real receipt/warning/blocking assertions and separate safe-reuse
tests. CI provides actual RED; focused native tests then next Linux CI provide corrected evidence.
Do not alter resource/cache policy or weaken gate expectations.
Two further fixture/selection gaps: four synthetic deferred-manifest failure cases supply ordinary
Linux tmp model paths despite the retained D-mounted cache contract; use inert platform-valid D paths
only (these synthetic commands do not use model/RAG storage), keep real execution/log/no-dossier
assertions and the cache guard. Four Windows font-policy cases intentionally skip on Linux, which
the mandatory root-contract attestation rejects. Run the same real conftest subprocess cases on
all platforms: preserve every Windows expectation and explicitly verify no Windows-font injection
on non-Windows, including override preservation. No new allowed-skip category or production change.

**Real-model checkpoint limitation.** d8 bounded offline evaluation completed81cases and owned tree
exited.36/36positive,10/10explicit-origin,5/5missing-origin passed; strict bounded gate fails because
split_before_epochs_en adds a fourth failure beyond the three accepted case IDs. No execution or
mutation occurred for this case; malformed clarification/recovery safely exhausted. Attribution is
not established: unchanged source since the run is not proof against regression versus4770baseline.
Read-only relevant baseline diff/accepted evidence comparison continues; no model/prompt/RAG
experiment, expanded allowed-failure list or Stable promotion authorized.
Relevant4770-to-d8 review finds no change to the evaluator's used strict parser/recovery policy;
retired parser conveniences and unpopulated recovery feedback were not this execution path. No prior
accepted raw-output artifact is available locally, so causality remains qualified. Final-source
required rerun must retain this failed report; do not retry unchanged source until green.

**CI repair verification.** Prepared-apply selection29pass (including retained safe reuse); corrected
manifest/font suites16pass. Initial asynchronous handoff fixture asserted only a terminal outcome,
but the real asynchronous host also reports DEFERRED_TO_UI progress; fixture now requires exactly
that progress while no dialog/terminal exists, followed by one completed outcome and one terminal.
Its original create_epoch correlation is retained (for_decision omits a separate public tool name).
Independent actual-diff/security review approves all fixes. Added POSIX-only ancestor case uses the
existing platform_contract classification; no allowed-skip policy changed. Full native runtime run
stalled after8cases and reached its180s bound without a stack; exact owned child36604 was identified
and stopped, launcher35080 exited naturally, subsequent exact scan empty. No user process touched.
Isolated cancel case1pass8.26s; full same-source sequence with15s per-test stack diagnostics under
existing Job Object supervisor16pass17.23s, no stderr, owned tree exited. Cause of first stall remains
unproven; do not call it a reproduced product loop or omit it from evidence. No timeout extended,
test skipped or speculative production reflow change made. All further native jobs use the existing
owned-process supervisor. First integrated CI otherwise passed static/docs/visual/DPI/public multi-
dataset/Windows+macOS product and startup/platform-lifecycle/human-like gates; repaired shards and
aggregate must pass again on the new exact head. Continue through that verification and local native/
Assistant gaps before any manual handoff.

**Bounded6AH — characterize the retained final Assistant result byte cap.** Main and independent
actual projection/caller audit retain _fit_public_tool_payload: restoring required contract fields
after node-exhausted global projection can increase the final envelope size. No actual to_payload byte-cap
test was found. Add a small real ToolCommandResult result with bounded large fields; assert final
compact JSON UTF-8 size and contract shape without mocking production projection. A process-
local bypass fault must fail the actual cap assertion before claiming useful protection; keep normal
surface tests. Tests only, no cap/public contract/prompt change, no new policy or control plane.
Initial oversized multibyte fixture passed even under bypass, so it was replaced, not counted as
mutation protection. Main rejected a reviewer deletion proof that overlooked node-only exhaustion.
Measured real two-text/nested-null state produces262152bytes after contract restoration against262144
cap; actual26surface tests pass8.18s, process-only bypass fails the exact byte assertion1.66s.
No source fault persisted. Independent non-author final review and Ruff pass; production unchanged.

**Remaining stage closure review.** Reconcile all file dispositions with actual Git (not surviving
owner names), then review cross-module admission/publication/error/lifecycle boundaries against
current/target architecture. Main and independent review must separate closed internal cleanup from
explicit UI/retirement decisions and missing same-source validation. No new generic hardening or
second audit platform. At1e214d1f tracked production+338/-7729/net-7391; scripts+447/-1546/net-1099;
tests+6989/-8255/net-1266. These are Git text deltas, not coverage or percentage-quality evidence.

**Bounded8T — prevent resumed journey evidence from acquiring newer provenance.** Main and
independent full CLI334/evidence463 find _run_resume builds current source/environment metadata
then reuses old completed rows based only on registry/profile. Bind reuse to identical clean source
SHA, runner execution metadata and data root; different subset argv remains allowed. No new schema,
receipt, owner, download or actual EEG/model run. Add real manifest read/write/resume regression
with source/environment/data-root mismatch and unchanged subset reuse; isolate only external product
execution/fixture provisioning. Observe RED before source fix, then identical green, existing MOABB
evidence/cache tests, Ruff and independent provenance review. The separate Qt/site evidence path
does not use this resume branch; do not overstate it as a site-publication bypass. One script fix,
not a product contract change, followed by continued stage work.
Observed first8test command failed before exercising resume because fixture used actual Windows Git
against a WSL-linked worktree; not RED evidence. Narrow synthetic Git seam plus actual attempt1
checkpoint corrected the fixture. Then7mismatch cases fail on wrongful reuse/1allowedsubset passes
0.41s; same8pass0.30s after fix; full evidence/registry/storage39pass9.42s. Ruff and independent
actual-diff review pass. Retain existing cache validation; no stronger raw-data-content claim added.

**Bounded6AG — retire unused post-admission path handles, preserve live admission safety.** Full
authorized_paths743/direct303 independent security audit and main grant/Windows lease/caller trace
show no runtime consumer for open_authorized_path/OpenedAuthorizedPath/AuthorizedPath.grant.
Verifier uses the admitted string only. Initial proposal to remove Windows snapshot construction
was rejected by main: it also performs live anti-replacement/ancestor identity validation. Preserve
the real retain_directory_identity lease and _require_directory_lease_matches calls for root and
distinct target directories; replace only its unused snapshot return with no-output validation.
Retain all POSIX no-follow descriptor walking and final containment/kind checks. Remove unused
post-admission open/grant DTOs/helpers, return the original string after unchanged admission checks;
no backend IO, public tool, confirmation or downstream TOCTOU claim changes, owner delta0.
Before source edits strengthen real normal/wrong-kind admission and a Windows-only actual renamed/
recreated root regression (wrap only final-identity resolution timing, use real retained lease).
Replace only retired post-admission lease test after the stronger baseline; keep POSIX symlink,
Windows final escape/failure and actual generic-root verifier admission protection. Focused before/
after + bounded no-op admission-guard fault, Ruff/type boundary and independent actual-diff security
review. One source file deletion-only, separate reversible commit;6E/6G denied scopes untouched.
Strengthened Windows baseline12pass/2POSIXskip6.22s recreates both root and target so missing target
cannot mask admission failure. Exact process-local no-op lease-match fault produces DID NOT RAISE
0.33s, proving the retained guard is protected; no fault persisted. After cleanup12pass/2POSIXskip,
native replacement and actual wrong-kind/normal/verifier behavior retained; POSIX is not claimed run.
Independent review required a separate target-only replacement while root remains stable. Parameterized
the actual native case:13pass/2POSIXskip6.08s. Bypassing only target admission (root still checked)
makes the exact target case fail DID NOT RAISE0.31s. Root and distinct-target checks now have separate
mutation evidence. Ruff passes; production+15/-205/net-190, no owner added or live safety removed.
Broader live verifier111pass6.32s; independent final review confirms target-only gap closed.

**Bounded6AF — remove unused intent and prompt-result convenience projections.** Independent full
intent935/policy215 and main changed graph/three actual test callers confirm target_command,
ambiguous and path_label_for_intent are uncalled; both to_prompt_payload methods only serve three
serializer tests. Actual assembler consumes policy fields/blocked_reason_map/backend_generation.
Retain target_intents/target_intent, all classification/RAG suppression and exact prompt text. Migrate
the three tests to actual returned fields/public safe error message while retaining real assembler
unavailable-state/no-tool prompt assertions; passing baseline before deletion and same suite after.
No test cases removed, new policy owner, model/prompt treatment, schema/tool/confirmation change or
6E stage-prose/history scope. Ruff/independent actual-diff review and Git-reversible two-file cleanup;
continue authorized stage work afterward. No UI modification or new approval needed for unused
Python conveniences under the user's explicit scope.
The first baseline command included nonexistent test_intent.py and collected no tests; this is a
selector error, not RED evidence. Corrected to the actual full ContextAssembler suite, which covers
real policy projection/RAG context and unavailable-state prompt behavior; no invented direct suite.
Observed corrected Windows baseline57pass7.34s and identical retained after57pass7.11s. Production
deletes34 lines across two files; no test cases removed. Independent actual-diff review confirms no
runtime prompt/classification/tool registry change and retained real assembled unavailable prompt.

**Bounded6AE — remove unused Assistant UI conveniences/stored projection.** Full suggestion card167,
dispatcher532, publication coordinator251 and actual call/test trace identify set_subtitle with no
callers, is_queued projection only asserted beside real no-thread/affinity checks, and unread
AssistantTrainingAttemptSession.handoff_generation. Remove only those methods/stored field; keep
constructor subtitle/accessibility/render/click behavior, live dispatcher _queued state/transport,
and positive-integer training_handoff_generation admission validation. Before source changes extend
the existing rejected-handoff case across None/bool/zero/negative/string, then passing actual Qt
suggestion/dispatcher-threading/coordinator baseline; afterward identical retained tests, Ruff and
independent async/admission actual-diff review. No authoritative owner change, training generation
contract/public diagnostics mutation or visible UI change; existing UI-internal authorization applies.
Three production files, deletion only, no new owner/module. Independent review before commit and
continue remaining candidates/final integration, not an intermediate handoff.
Result: strengthened41cases pass8.67s before source edits and same41pass8.84s after. No collected
test removed (one redundant queue flag assertion removed); malformed-generation cases increased
by4. Production deletion-only-13; Ruff/format and independent async/admission actual-diff review
pass. Visible copy/layout and backend diagnostic/generation contracts unchanged.

**Bounded9Z — close shared utility behavior-test gaps.** Full CUDA helper38 and filename parser204/
direct68 audit identifies uncharacterized external cache-release failure and invalid/partial regex
paths. Keep both live owners and production behavior unchanged. Extend direct tests for CUDA typed/
message OOM classification, unavailable cache/no release and availability/release failure isolation
using narrow external CUDA stubs (not a GPU performance claim); add actual filename regex invalid,
missing numeric/named group and no-match cases, removing misleading mock/folder comments. No UI
or data semantic change, generic source guard, environment/GPU/model download. Focused existing
unchanged-production characterization, Ruff and independent test-quality review; no artificial RED
required for tests-only characterization. Separate test files from8S, no production writes.
Result: original4filename tests retained;2new filename cases and4CUDA cases, final10pass2.94s using
actual installed torch.OutOfMemoryError without GPU allocation. External cache operations alone
are stubbed. Production unchanged, tests+60net; Ruff/format and independent test-quality review
pass. This closes the stated utility evidence gaps, not actual GPU/resource performance validation.

**Bounded8S — remove unused MOABB evidence conveniences.** Main full evidence481/direct598 and
package marker5 read, plus whole-tree caller/config/doc search, finds no caller for private
_row_has_held_out_metric or package-level registry reexports. Live quality acceptance reads actual
held-out evaluations through evaluate_quality_acceptance/showcase_quality_complete; keep those
strict metric/provenance/artifact checks and direct registry imports unchanged. Remove only the
unused helper and two convenience reexports; retain importable package marker, registry assets,
plan/cache/UI evidence entrypoints and raw data. No HTTP/download/runtime/manifest/schema change,
no owner added or exclusive test deletion. Run current evidence+registry+storage tests before/after,
Ruff and independent actual-diff/caller review; one Git-reversible script slice, then continue stage.
First Windows baseline30pass/1fail14.08s: existing test builds a filename from saliency method
"Gradient * Input", producing forbidden '*' on Windows before evaluating the evidence contract.
Repair only test-owned artifact filenames with numeric indices, preserve exact method metadata and
all integrity assertions. Observe repaired31baseline before deleting source; no product name/filename
or saliency contract change. This directly blocks focused evidence and belongs to this slice.
Result: repaired31baseline pass9.56s, identical31pass9.68s after deleting22script lines. All test
cases/method metadata/quality thresholds retained; tests only+2/-2 portable paths. Ruff/format and
independent actual-diff/caller review pass. Resume provenance remains a separate assessment, not
silently closed by helper deletion.

**Early integrated static checkpoint.** With whole-file dispositions populated and source at
1aee34a9 (183 reversible stage commits), run the existing whole-project Basedpyright regression
runner and Ruff checks once in the sole Windows environment. This directly checks deleted API
callers/type boundaries after accumulated refactors; no same-source CI exists to reuse. Keep the
empty diagnostic baseline immutable and verify actual PyQt dependency resolution. This is early
integration evidence, not final exact-source CI, full coverage, native/real-model evidence or manual
handoff. Resolve concrete regressions in bounded slices; do not weaken analyzer configuration.
Result: pinned Basedpyright1.39.2 with actual PyQt dependency probe observes0diagnostics against
immutable0baseline; whole-tree Ruff passes and1110files already formatted. This checkpoint covers
production1aee34a9 before subsequent6AE edits; final same-head integrated evidence still required.

**Bounded9Y — disambiguate the approved stage exception in validation guidance.** Main full
validation read finds the explicit one-integration-PR exception immediately followed by unqualified
multi-PR instructions requiring a PR per slice. Scope those latter instructions to product rebuilds
without the approved stage exception. No gate, public contract, manual acceptance or merge rule is
weakened; stage still needs final exact-source CI and independent review. One prose qualifier, no
new planning/control document. Guidance audit, independent wording review and same-head docs CI;
local strict MkDocs remains unavailable without dependency installation (not authorized). Continue
remaining inventory and blockers, not an intermediate manual-test request.
Result: existing guidance audit check --format json returns ok=true/errors=[]; independent actual
wording review approved. No gate registry or runtime edits. Strict docs build remains same-head CI
evidence still to obtain, not claimed from the source audit.

**Bounded8R — report failed deferred gates before dossier persistence.** Full runner424/direct465
and independent recorder1489 audit finds failed prerequisites/parallel lanes reach success-only
record validation before the explicit failure return; real missing-artifact failure raises an
infrastructure error instead of the structured gate-failure result. Existing orchestration tests
mock persistence and miss this boundary. Add a real temporary clean Git repo/child command/recorder
regression for prerequisite and parallel failures, including exit-zero/missing required artifact.
Move existing failure inspection ahead of deferred persistence; keep raw child logs and attempted
IDs, do not publish an incomplete deferred dossier or run final gates. Successful batch persistence,
serial handling, exact-source/artifact verification and all required gates stay unchanged. No new
validation mode, owner, dependency or UI change. Observe RED before source edits, then same tests
and adjacent real recorder tests, Ruff and independent actual-diff review. One isolated reversible
script repair, continue inventory/integrated gates afterward; not handoff-ready at slice completion.
Result: four real Git/child/recorder regressions fail before source change with the exact deferred
persistence exception (3.49s); full manifest/recorder pair after change52pass/2skip73.20s. Both skips
are existing POSIX process-group contracts on Windows, not represented as passing Linux evidence.
Ruff/format and independent actual-diff review pass. Script+11/-11/net0, tests+96 for four real
failure cases; no recorder/validator/gate weakening. Partial deferred batches leave raw diagnostics,
not an incomplete dossier; all-success batch behavior remains covered by existing real persistence.

**Bounded7O — narrow AppConfig to its actual resource/release responsibility.** Main and independent
full config74/direct73, icon-render36 and whole-tree caller/config audit find only icon lookup is a
runtime consumer; importantly VERSION is a real Commitizen version_files target and must remain.
Remove unused APP_NAME, 3D directory, platform-font/default-size and BIDS regex constants plus their
six exclusive self-assertion tests. Retain frozen/dev BASE_DIR/resources/icons/get_icon_path and
VERSION/FALLBACK/pyproject/Commitizen equality. Strengthen get_icon_path against the real settings.svg
asset and retain actual QIcon pixel render before removing three redundant path-composition tests.
Original/stronger same direct+icon baseline before, retained after, Ruff and independent actual-diff
review. No resource/font/UI behavior change, release configuration edit or new owner/module. One
production file deletion-first; test baseline reduction must distinguish six retired-only cases and
three replaced assertions. Git-reversible isolated commit, then continue stage work.
Result: original13pass0.08s and strengthened13pass0.08s before source edits (recovered run observed),
retained4pass0.05s afterward; Ruff/format and independent actual-diff/caller/release review pass.
Nine collected cases removed: six obsolete-only, three path composition assertions replaced by
the actual shipped SVG assertion. Existing QIcon pixel test retained. No UI/font/release behavior
change; Git-reversible constants/test cleanup, not final stage acceptance.

**Bounded6AD — retire the unused standalone debug executor, not live diagnostic walkthrough.** Main
and independent full executor562/direct101 plus shared test387/72/caller audit finds no production,
script, dynamic registration or CLI consumer. Actual --tool-debug runs ToolDebugMode through the
normal ChatPanel/controller/Command lifecycle. Remove the unused executor module and its private
admission/evidence/wrapping classes; remove only its7direct tests,2shared tests and6executor-dependent
adapter cases. Keep real registry and direct compute-saliency UiRequest tests, ToolDebugMode lifecycle,
run.py CWD/profile tests and actual command coordinator/product-flow protection. Remove only the
retired file from the public-log source guard, keeping all other boundaries/assertions. Clarify seven
implementation-named docs references as actual tool execution, not a new owner; evaluator's public
tool_executor_called field and scoring semantics stay unchanged. User authorized removal of unused
whole capabilities/exclusive tests and unsupported external Python conveniences. Production owner
delta: standalone debug admission/execution1→0, live owners unchanged; one production module-562,
no replacement facade, public tool/schema/UI change or model experiment. Baseline direct/shared/
privacy/live CLI/coordinator cases before, identical retained cases after, Ruff/caller/docs checks and
independent actual-diff review. Git-reversible isolated commit, then continue stage audit; no manual
candidate or full model/data evidence claim from this slice.
Result: original87pass7.01s; same retained72pass6.26s after removing15executor-exclusive collected
cases. Production-562/tests-175; Ruff/format, zero stale class/module callers, main full diff and
independent actual-diff/privacy/caller/docs review pass. Evaluator fields and live walkthrough
profiles/launch path remain unchanged. Deleted source/tests are recoverable from this isolated Git
commit; no user data/model/cache was deleted and no replacement control layer was introduced.

**Bounded9X — align Assistant user-guide model wording with the live catalog.** Independent full user
guide/case/manifest/style audit and main guide73/catalog constants/specs/current truth read find
assistant.md claims one fixed Granite model despite two supported local choices. Replace only
"fixed" with "supported"; retain local-only, no-cloud, no-silent-runtime-fallback and one-action
boundaries. No product/model/prompt change or site redesign. Existing user-site source/link validator
and independent wording review; strict MkDocs build still requires the absent existing dependency or
same-head CI, no installation authorized. Case-study registry assets remain exact-byte provenance,
not downloader code; all unverified evidence qualifications remain. Continue stage cleanup afterward.
Result: existing user-site source/IA/link/claim validator passes in Windows; independent one-word
diff review approves. No strict MkDocs or rendered-site claim. Main full reusable-guidance audit also
finds the same Validation link twice in thesis context navigation; remove only the duplicate link,
preserving research context and canonical evidence authority, then run the existing guidance audit.
Guidance audit returns ok=true/errors[]; independent duplicate-link diff review approves. Docs-only
changes do not establish a new product/model or rendered-site baseline.

**Bounded6AB — remove unreachable mock-only state conveniences.** Full mock source105/47/84/40,
direct155, registry assembly and evaluator caller trace retain the live mock tool mode and its18
formal schemas. Remove only MockWorkflowState.epochs_ready and its three uncalled mutators
mark_data_loaded/mark_epochs_ready/reset_preprocess. Live prerequisite fields and missing-training
policy stay. Replace the unused MagicMock Study fixture with a plain object to make any accidental
Study dependency visible; mock tests remain simulation evidence, not real EEG/training evidence.
Passing original/stronger plain-object characterization before state deletion, identical retained
tests after, Ruff and independent actual-diff/caller review. One production file, no owner addition
or public tool change; no UI source. Independent Git-reversible commit, then continue stage work.

**Bounded6AC — retire model-settings get_config forwarding convenience.** Independent full dialog1564/
direct1402 and main exact get_result/BaseDialog/caller trace find get_config only used by get_result
and one exclusive convenience test. Preserve live BaseDialog.get_result contract and same self.config
object; remove get_config and return self.config directly from get_result. Migrate the existing test
to get_result identity, passing before and after. No download/settings/runtime/visible UI behavior
change; existing UI-internal cleanup authorization applies. One production file, no owner addition;
Ruff, direct dialog suite and independent actual-diff review. Separate Git-reversible commit; the
uncharacterized cross-selection terminal-message question is outside this convenience deletion.

6AB/6AC validation: original combined80pass23.96s; stronger plain-object mock fixture and formal
get_result identity80pass6.44s before source deletion; same80pass6.41s after. No cases removed.
Ruff/format and independent actual-diff/caller review approve both.6AB production-20/tests net-2;
6AC production net-9/tests net0. Timing differences are not a measured application speedup.

**Bounded8Q — retire the explicitly user-approved one-time MOABB downloader.** On2026-09-11 the
user authorized deletion of the one-time download script and reiterated the final Windows handoff
endpoint. Main full CLI366/storage294/registry430, package entry points and direct storage115 tests;
repository/config/docs search finds fetch_plan used only by the fetch subcommand, and download_file/
cached_file_is_valid only by that retired path and two exclusive tests. Remove fetch parser/dispatch/
handler, download functions and HTTP/SSL/bounded-copy-only imports, plus those two tests
and their response fixture. No replacement downloader or compatibility shell. Preserve plan/build/
load_validated_plan/cache-integrity/atomic JSON paths because moabb_ui_evidence.cli uses them before
Qt startup; preserve registry assets, source metadata, original downloaded data and journeys.
Owners: one-time download executor1→0, live validation/product/UI owners unchanged. Two script files,
one directly related test file, deletion-only production scope; no visible UI change or dependency
installation. Establish direct storage baseline and retained parser/real-file characterization;
repeat after, verify CLI rejects fetch while plan/validate/run-resume remain, caller search and
independent actual-diff review. Use existing Windows runtime if approved for this newly authorized
slice; do not retry or bypass the previously rejected6AA command. Persist any execution limitation
without substituting synthetic checks for native/pytest evidence. Git-reversible; proceed to remaining
module work after this slice, not manual delivery before stage gates pass.
Original Windows baseline14pass0.17s; stronger retained real-file/parser characterization21pass0.17s.
Independent pre-diff review corrected the proposed CHUNK_SIZE removal: retain it because live
_hash_file still uses it. CLI help must no longer advertise fetch. New authorized8Q execution and
independent reviewers succeeded; the earlier quota restriction is historical, not a current blanket
execution failure. Product6AA still needs its own baseline before editing.
Result: retired only fetch/download executor and two exclusive HTTP tests/fixture; retained suite20
plus11adjacent UI evidence contract cases31pass0.42s. Ruff/format and independent actual-diff/caller
review pass after correcting the stale pre-retirement inventory wording. Script+3/-138/net-135;
test+62/-62/net0 with real-file and CLI coverage replacing downloader-only cases. No original data,
cache, registry, source-diverse gate or native UI workflow was removed; no actual capture claim.

**Bounded6AA — remove unused handoff-resolution convenience projections.** Main full typed handoff687/
direct642, host exact-status callers and repository search find resolution.suggestions/routed unused,
is_verified_completion only in four tests. Retain request.suggestions (live GUI consumer), all DTO
fields/correlation/session transitions/status enum and distinct WorkflowSurfaceOutcome helpers.
Delete only those three resolution properties; use exact returned status in the direct terminal test
and retain existing exact pending/deferred/failed status assertions in host tests. No case removed or
public Assistant action/navigation/copy change. Existing UI-internal authorization suffices; no UI
source edit. Same direct+host baseline before/after, Ruff/caller check and independent actual-diff
review; production deletion only, live owners unchanged. Stop this slice after evidence then continue
remaining module audits, not final handoff. Git-reversible, no compatibility shell.

Recovered execution: the first6AA baseline request was rejected before execution due to an approval
reviewer usage limit. After newly authorized8Q focused execution and independent review both
succeeded, the same approved Windows6AA baseline was resumed normally:94pass0.78s. No alternate
runner/sandbox bypass, environment creation or rejected result was counted as passing evidence.
Result: same94pass0.73s after; no collected case removed. Ruff/format and independent actual-diff/
caller/terminal-contract review pass. Production-18, tests+1/-4/net-3; no owner or UI source change.

Remaining read-only findings (not implemented or counted as verified removals):
- Assistant model settings belongs to module6, not training module4. Independent full source1564/
  tests1402 read retains config persistence, download lifecycle and manager activation ownership.
  get_config is a one-test convenience; get_result remains the BaseDialog contract. A possible
  cross-selection download terminal-message ambiguity needs characterization before any visible fix.
- Mock tools remain live through the evaluation registry; their simulated training is not real
  training evidence. Main full mock source/test audit finds three MockWorkflowState convenience
  mutators and epochs_ready with no callers; preserve live prerequisite fields and formal schemas.
  Any removal needs its own passing baseline and reviewed bounded slice after execution resumes.
- Walkthrough validator source1305 has an independent full read. Preserve its artifact/source/state
  checks; current test-file reread coverage is recorded separately from historical full-file review.
- MOABB script package markers/CLI/registry/storage and registry/storage tests fully read (1454lines).
  CLI plan/validate/run-resume and the separate UI evidence workflow remain live;8Q retires fetch and
  its two downloader-only tests under explicit user authorization. New real-file cache validation
  retains valid/missing/size/hash checks without HTTP mocks. Download retry/forced-replacement
  evidence is no longer a requirement for this retired capability. Package-level registry reexports have
  no located caller and remain a bounded removal candidate, not yet changed. Resume provenance
  must be checked against the remaining evidence/product owner before judging CLI reuse complete.

Size checkpoint at af7f9079 versus4770b049: scripts25changed files,+410/-1369/net-959;
tests197changed files,+6389/-7906/net-1517. These are physical diff counts, not execution coverage,
file-audit completion or a claim that all remaining architecture is clean.

Inventory qualification: the approved retained-vendor group contains79tracked legacy files; actual
catalog57symbols/49modelleaves and18supportleaves/attribution assets match manifests and dynamic leaf
factories. This is a responsibility/disposition audit, not full per-line model review. Provenance
tests verify pinned upstream hashes, not exact adapted local bytes; family/runtime checks remain
necessary. Package markers retain import identity without adding runtime policy. Do not report these
group dispositions as newly deep-read production files or as proof that all architecture is clean.

**Bounded6Z — retire unused tool-result bridge and repair failure-test reachability.** Main full
result_contract423/direct538 and repo-wide caller search find tool_result_from_command only exercised
by its exclusive test; actual mapped tools use application_surface's existing command projection.
Remove dead bridge/backend CommandResult import/exclusive case, plus private _public_safe_value
single-use forwarder (reuse existing shared redactor directly). No ToolResult fields, registered tool,
public command/query/result semantics, consent or privacy policy change; no new owner. User approved
unused whole-capability/test retirement. Current hostile-publication test rejects unsupported type
before its raising property, so it does not exercise BaseException interception as named. Keep that
no-protocol-execution boundary and add actual failing runtime read as a separate parameter case.
Baseline direct suite, stronger passing characterization, same retained suite after; in-memory catch
narrowing should expose the failure case, then restore. Independent privacy/caller/diff review, Ruff
and focused adjacent tool execution evidence. No real-model or full Assistant handoff claim. Continue
stage audit; removal is Git-reversible, not retirement of a formal tool or command.
Result: original32pass5.64s; stronger33pass5.81s; after32retained direct plus14live coordinator/
command-ownership cases46pass6.12s. One dead-bridge case removed, actual failure-reader case added.
In-memory narrowing to except Exception leaves unsupported-type case passing but actual BaseException
case fails; restored original function, no fault source retained. Ruff/format and independent actual
diff/caller/privacy review pass. Production+1/-47/net-46, tests+10/-21/net-11; owners unchanged.

**Bounded8P — measure screenshot-readiness pixel materialization before consolidation.** Main full
readiness341/callers and direct black-region/frame tests identify two list(_pixels(...)) copies used
only for iteration and length. Measure actual PNG760x520 warmed validation in the existing Windows
Pillow runtime (wall time and Python traced peak; not total process/native RAM). If material, iterate
existing pixel data without a second list and use exact dimensions; preserve thresholds, tiles/errors.
Characterize valid dark-theme frame, global black area and small all-black tile before edits, then
same cases after plus existing frame-stability protection. No UI/gate policy or new dependency/owner;
script-only two loops, focused Ruff and independent actual-diff review. Measurement/test failure is
not a reason to relax image acceptance. Continue stage audit after this bounded work.
Baseline760x520: Pillow pixel API already returns a tuple; the extra list is redundant. Three warmed
runs with tracemalloc:0.4759/0.4636/0.4613s, peak31,619,373/31,619,357/31,619,349bytes. This targets
one transient list allocation, not all Pillow pixel materialization or general application speed.
Result: exact four real-PNG cases before4pass6.98s/after4pass6.99s. Forced in-memory tile-check
bypass fails only small-black-tile rejection (DID NOT RAISE), clean dark frame still passes; original
function restored, no fault source persisted. Same warmed after samples0.4543/0.4559/0.4600s and
peak28,458,270/28,458,254/28,458,246bytes: ~3.16MB less traced peak; no total-RAM/app-speed claim.
Ruff/format and independent actual-diff/caller review pass. Script+4/-6/net-2, tests+22, owners unchanged.

**Bounded8O — retire unreachable script-only Qt shutdown coordinator.** Main and independent full
read of bounded_qt_shutdown98/direct188, repository-wide symbol/module search, runner registry and
live capture cleanup callers find no runtime consumer. Remove this unused owner, its five exclusive
tests and only its platform test-path entry. Keep product qt_runtime and its real capture/desktop
consumers unchanged; no replacement owner or visible UI change. User has approved unused whole-
capability/test retirement. Script -99/test -188; dormant owner1→0, live owners unchanged. Before:
direct suite plus existing Qt runtime and platform-registry/termination guards; after: same retained
adjacent protection, Ruff and no stale caller/path. Independent actual-diff review required. This does
not claim native GUI shutdown acceptance. Restore via this slice's Git commit if needed, then continue
remaining module inventory, not a handoff or stage completion.
Result: before16pass0.61s includes five exclusive retired cases; unchanged retained runtime/registry/
termination protection11pass0.37s after. Ruff/format/caller search and independent actual-diff review
pass. Live product cleanup, its tests and native capture consumers remain unchanged; no GUI claim.

**Bounded8N — retire dashboard-only UI pytest shell indirection.** Independent full dashboard1711/
direct2038 plus main shell23/caller/env/attestation trace confirms run_ui_pytest.sh has exactly two
dashboard consumers and no docs/Poe/CI entry. Both can use the existing direct required-pytest runner,
as other dashboard UI checks already do. Preserve exact dialog/product/wizard nodes, --capture=sys,
ui=True/offscreen/Agg/cache setup and actual completion-attestation requirement. Add semantic command
selection characterization that passes before and after, then delete only wrapper, UI_WRAPPER and its
special-case parser branch; no new adapter. Keep sharded UI unit gate, all non-skipped policies and
dashboard's existing Poetry executable policy unchanged (this is not dashboard portability work).
Original/stronger/after direct tests, Ruff, static caller check and independent review; no actual full
dashboard/UI/model/data gate or new environment. Continue stage inventory after bounded completion.
Result: original87pass/1POSIXskip plus two failures traced to Windows Git reading a WSL .git path
(check-ignore128). Exact process-local Git dirs/HEAD verified; those two pass0.20s without source
or Git metadata edits. Keep this mapping away from other tests that create temporary Git repos.
Two new semantic cases pass before deletion0.15s; their initial POSIX tokenization lost Windows
backslashes, corrected to existing suite platform-aware split (not product portability evidence).
After:89pass/1samePOSIXskip0.80s in normal environment, plus two Git-dependent cases separately
mapped pass0.19s; no case removed. Wrapper23lines and parser indirection retired, script net-23/tests+33;
Ruff/format, no remaining callers, independent environment/attestation review approve. Native
dashboard/GUI execution and final CI are not implied by these command-construction tests.

**Bounded9W — actual Windows process-tree containment evidence.** Main fully read owned_process_group
441/bootstrap33/native_safety29 and direct owned tests388/native61; current Windows Job Object tests
replace the entire native owner while actual recorder descendant cases are POSIX-only. Retain those
platform/ordering/error seams and add bounded native Windows evidence for a live descendant when its
parent either exits normally or remains running. Use only the existing interpreter, exact test-created
PIDs, tiny temporary PID file, explicit startup/collect/reap deadlines and finally owner cleanup. No
unrelated process signal, WSL operation, environment creation, app settings or model/cache writes.
Exercise real spawn/handshake/Job Object/quiescence/termination, not fake WinAPI success. Run original
owned tests before, then retained plus two native cases; native failure is evidence to diagnose, not
a skip/timeout increase. No production change unless an observed defect is separately declared.
Independent lifecycle review; continue scripts/inventory after this bounded test-quality step.
Result: original11pass/4POSIXskips0.05s, final13pass/same4skips0.52s. Both native Windows Job Object
cases execute with no mocked process/job owner; parent-exit case observes surviving descendant via
real Job accounting before close, live-parent case exercises bounded terminate-and-collect. Readiness
is atomic and published after stdout flush; cleanup only test-owned Job/PID. Ruff/format and
independent lifecycle review pass; tests+55, production unchanged. No general app shutdown/CI claim.

**Bounded4P — remove unused resource-view conveniences and unreachable shape serialization.**
Main fully read resource_preflight563/resource_receipt322/training_resource_receipt517 and direct
contract300/training256 cases. Product callers use challenge_id and create/from/to_diagnostics;
with_challenge has no callers, token property only supports tests. Migrate only test property reads
to challenge_id, preserve canonical/flat serialized token fields and every receipt assertion. The
training-only recursive _canonical_value is called solely on _normalized_shape's tuple[int,...]|None;
replace with direct list conversion and remove unreachable dict/set/enum/string branches/sole json
import. No change to generic fingerprint owner, bounded sampling, TTL, one-shot authorization,
confirmation/UI/public wire contract. Owners unchanged, no new modules or abstraction. Baseline
same direct contracts, training freshness and affected Assistant receipt tests before/after; compare
descriptor/fingerprint parity in memory for real scalar/empty/multidimensional and unavailable shapes;
Ruff and independent review. No downloads/weights/state changes. Roll back this bounded slice if
parity fails; continue remaining inventory, not handoff at this checkpoint.
Result: same52before8.99s/after7.94s, sameone warning. Seven in-memory comparisons using the exact
old converter show descriptor and final SHA parity for real multidimensional/scalar/empty arrays,
missing/invalid/excess-dimensional shapes and None. No fault source or weight persisted. Initial
after lint caught three now-unused S105 exemptions after token-property rename; removed only those,
five-file Ruff/format then pass. Independent actual-diff review approves; product+1/-52/net-51,
no tests removed, no receipt wire/admission/lifecycle changes.

**Bounded4O — stop importing every legacy model for a concrete model selection.** Main/independent
caller trace finds product catalog imports concrete submodules; only ten model tests consume the
private117-line eager facade. Measure cold concrete EEGNet import time/module count in the existing
Windows environment before intervention. Migrate tests to concrete modules using their existing
family cases (no new registry/loader), preserve all parity/state/gradient/offline assertions, obtain
passing characterization, then reduce only models/__init__.py to a package docstring. Preserve all
model/support/provenance files, catalog IDs, public selection and saved-result semantics. Owners
unchanged; anticipated production-116 in one file. No UI/public contract or pretrained-weight changes.
Validation: identical bounded small-configuration ten-family suite before/after, fresh-process
no-upstream/no-unrelated-model import protection, Ruff, independent actual-diff review, repeated cold
import measurement. No downloads, new environment or GPU runs; do not extrapolate to application
startup or model training speed. Rollback this slice only. Then resume outstanding inventory.
Result: original89pass18.81s, migrated89pass13.87s, strengthened subprocess red8.12s, final89pass
12.08s (same44 upstream/model warnings). Independent actual-diff review approves preserved cases,
catalog IDs and concrete model imports. Production-116; model/support/provenance untouched.
Three fresh-process EEGNet imports load52 ->2 local model modules. Before19.4376/5.5232/5.4771s;
after3.9682/3.9190/3.9098s. First-before OS-cache outlier prevents a claimed percentage speedup;
this measures interpreter-cold concrete imports only, not OS-cold application startup or training.
Changed11-file Ruff/format passes; actual legacy EEGNet catalog factory CPU forward is finite with
expected2x2 output, and seven provenance plus three legacy catalog cases pass10/0.08s. Tests net+131;
no case removed. This does not replace final source-diverse/native model workflow gates.

Remaining large-file qualification: independent source audit now fully reads architecture_compliance.py
1-11617 and direct characterization1-5996. No proven obsolete/duplicate guard or removable test;
distinct mutable-state/consent/publication/async bypass checks remain. Real hostile/allowed source
fixtures characterize scanner behavior, not runtime product safety. Retain this stage: concentrated
AST/guard families impose maintenance cost but splitting solely for LOC creates churn without an
observed boundary fix. Three coupling limits remain: combined receipt fixture, direct coordinator
AST assertions, exact mutable-object debt list. Future family changes may split matching source/tests
behind the existing aggregator; no new framework. This review is not an execution PASS or ideal-
architecture claim.

**Bounded9V — retain real downloader safety while removing duplicate profile membership.** Full
independent fetcher1135/direct427 and main download chain read retain one pinned-size/SHA/atomic
publication owner. Teacher profile redundantly names OpenNeuro already present in its expanded
required-CI set; remove only that element after passing identical manifest behavior. Current tests
mock download_file in atomic-publication cases, leaving actual URL admission/streamed size bounds
unobserved. Add no-network tests that replace only urlopen: reject non-HTTPS/unapproved host before
destination mutation; real chunked stream at exact limit installs after real hash/size verification,
one byte over limit rejects and preserves old destination/cleans .part. Preserve actual SSL context,
request construction, IO, hash and cleanup. Original/stronger/after direct suite, bounded in-memory
size-guard omission must fail the oversized-stream case, Ruff and independent diff review. No actual
download, new environment, model cache/data or runtime policy change. Continue inventory afterward.
Result: original19pass1.67s, strengthened23pass1.66s, identical23after5.56s; Ruff check/format
both pass. Recovered explicit in-memory omitted-size-guard run: oversized case fails on late size
mismatch instead of bounded streaming rejection, exact-limit case passes (0.17s); original restored.
No fault source persisted. Independent actual-diff review finds no blockers; script-1/test+59,
no cases retired. This is no-network safety evidence, not a successful public dataset download.

**Bounded9U — align fixture/architecture evidence descriptions with required CI.** Main fully read
public fixture README190, baseline README19 and multiformat README23; source/CI trace shows required
CI fetches/verifies pinned data and runs strict IO/BIDS/cross-source checks, while architecture still
calls this local-only/skippable CI. Correct this distinction without claiming a current pass. Pure
manifest inspection (no download) shows required-ci8groups/52files/205255918bytes, teacher10/57/
277106963bytes, p3002/68/569171066bytes. Public README wrongly calls teacher an extension of7groups
adding OpenNeuro: OpenNeuro is already among required8, teacher adds only CHB-MIT and Sleep-EDF.
Fix that source mapping, remove machine-specific Poetry executable paths, qualify default BIDS root
versus DATA_DIR override. Preserve dataset/task limitations, all byte limits and current source/label
contracts; checked-in multiformat fixtures remain one-source format coverage, not source diversity.
Docs-only source/manifest/link review and guidance/user-site source audit; known missing local MkDocs
remains final same-head docs CI obligation. Do not install/download or change fixture bytes/references.
Result: all three pinned profile counts/sizes match source; nine unchanged reference PNGs verify as
valid images (seven1280x800 shell/panels plus two520x316 filter states), not a fresh visual comparison.
Guidance and user-site source checks pass; independent actual CI/manifest/doc review approves.
Strict docs-site build remains pending final CI; no download, image rebaseline or EEG execution.

**Bounded9T — remove inactive global PyTorch coverage import hook.** Main/independent full
tests/fixtures/sitecustomize.py60 and source/CI/Poe/docs/startup trace find no route that adds its
directory to Python startup search paths or imports it. Current pytest pythonpath is repo root;
coverage flags do not activate a sitecustomize in an unrelated directory. Retire this entire unused
builtins.__import__/_add_docstr mutation capability, including its own stale Usage comments. No
dedicated tests exist; retain live test-temp policy and runner coverage/85% verification tests. First
check actual native startup resolution/path and focused runtime-path/coverage tests, delete exactly
this tracked file, rerun same protection and caller/dynamic search. No installed Python/sitecustomize,
coverage denominator, environment, model, user data or CI gate changes. Independent retirement review
already confirms no dynamic caller; review final diff and commit separately, then continue fixture
documentation contradictions and remaining inventory.
Result: actual Windows startup cannot resolve the retired fixture hook; same26 retained temp/coverage
tests pass before0.32s and after0.27s. Source/config/docs residual-reference scan and diff check pass.
Exactly60 inactive fixture lines removed, no tests retired; Git preserves recovery. Actual coverage
collection/Linux aggregate is still a final CI obligation, not proved by these runner contract tests.

**Bounded9S — retire stale package descriptions and absent-path secret-scan exclusions.** Main full
package initializer/hook reads and live engine/catalog/sidebar trace retain real package markers,
reviewed model closures and training-dialog exports. Correct only styles' removed icon registry claim
and LLM's obsolete multiple-backend description to existing local-only engine truth. Hook excludes
package-lock.json and retired artifacts/user-journeys registry path, neither tracked nor a current
generated output/caller; remove those two exemptions without adding broader replacements. Retain
the existing baseline, pinned hooks and live public-checksum exclusions. No runtime imports, user
config, dependency versions, secrets or UI behavior change. Review exact diff, YAML/source guidance
audit and existing pre-commit checks; this tightens scan coverage, not a new security policy owner.
Continue remaining module8/9 file coverage; no full docs-site rebuild for Python comments/hook paths.
Result: actual YAML parse and narrowed regex checks preserve live exclusions/baseline, two-file
Ruff/format and guidance audit(ok=true/no errors) pass. Independent actual diff review approves;
only two absent-path scan exemptions and two false docstring claims changed, no runtime behavior.

**Bounded8M — reject contradictory MOABB evaluation evidence.** Independent full capture779/
contract506/direct305 and main publication trace find validator checks route_semantics_match type,
but trusts its truth even when recorded expected/observed labels disagree. Site publication invokes
this validator, so forged/buggy true claims can qualify. Capture already defines the value by set
equality; reuse that exact meaning after existing nonempty string-list checks. Reject contradictory
flags in both directions, retain honest mismatch as valid but unqualified, and preserve order-insensitive
matching. No EEG execution/class mapping, schema, public Command/UI, new owner or data download change.
Add full-manifest tests with real source/PNG/hash fixtures for mismatched-true, matching-false and
reordered-matching-true; baseline direct suite before source, same after, publication-caller review,
Ruff/diff checks. This validates evidence consistency, not actual dataset correctness or fresh MOABB
source-diverse gate success. Continue full script inventory after repair.
Result: two contradictory manifests reproduce false acceptance;9 retained/valid cases pass0.36s.
After repair all11 pass0.26s, including honest mismatch and reordered match. Ruff/format, diff and
independent publication/capture-semantics review pass. Script+4/test+36, zero schema or owner change.

Next integration check: the missed script-to-MetricTab API caller in8J warrants one early existing
whole-project Basedpyright regression gate after the current commit. This is shared-boundary feedback,
not final same-head CI; preserve its baseline/version/denominator, use sole existing Windows Python,
no install/new environment and do not run full pytest in parallel. Any failure needs cause triage.
Scope correction before execution: configured analyzer includes XBrainLab only, not scripts/tests;
it checks product-to-product API integration, not the8J script caller. Script consumers still require
their actual focused workflow/CLI tests. Do not silently broaden analyzer include or claim script
coverage. Checked-in allowlist is empty; retain zero-new-diagnostics policy and PyQt type probe.
Result at product source500d4717: existing Basedpyright1.39.2 gate passes its real PyQt dependency
probe and reports0 baseline/0 observed/0 new diagnostics. No baseline/config/denominator changed;
only this plan was dirty. This is whole configured product type evidence, not scripts or full CI.

**Bounded8L — retire orphan capture alias and correct generated app-polish report.** Independent
full capture2231/direct1282 and main factory/report/caller traces find _epoching_dialog only forwards
to the live internal-events factory with no caller/registration/config/doc use. Remove that alias,
not either live epoch scenario. Generated README omits both filtering images, mislabels the requested
820x470 split factory as752x470, and hardcodes offscreen despite native DPI callers. Correct only
report text/list, point runtime platform/scale to the existing manifest and distinguish requested size
from observed geometry. Strengthen existing real-file README test against all canonical surfaces and
these facts; before-source run also retains real filtering/epoch/split geometry cases. Then same tests,
Ruff/caller/diff review. No product/UI layout/schema/gate change, new owner or screenshot rebasing;
continue remaining evidence contract audit after this slice.
Result: original live native filtering/epoch/split7 pass while strengthened README fails missing
inventory8.58s; same8 pass8.56s after. Ruff/format, diff and independent caller/manifest-truth review
pass. Script+4/-7/net-3, test+4, no case retirement or product/UI source change.

**Bounded8K — remove unused phase-alias arguments without changing evidence.** Independent full
human-like parent4966/direct5939 and main four-caller/helper read find append_phase_alias ignores
widget and service; these are not state owners or observation hooks. Characterize actual helper output
and rejection of undeclared/source-missing/mismatched aliases before removal, retaining existing phase
contract/payload validators. Then delete two parameters and eight passed arguments only. Existing
source phase supplies copied visible text/buttons/workflow state; notes and screenshot identity remain
unchanged. No real dataset/training/model run, product/UI/schema/public gate change or new helper.
Focused characterization before/after, caller sweep, Ruff and actual diff review; continue app-polish
full-audit findings and inventory instead of claiming module closure.
Result:8 cases pass before7.11s and after6.93s, preserving actual helper output/rejection and existing
phase ordering/alias validators. Script-10 lines; tests+36 lines/4 actual behavior cases, no cases
retired. Ruff/format pass; repo-wide source/config/docs search finds only the four migrated callers.

**Bounded9L4B — isolate MOABB CLI capture preferences after exact-source preflight.** Full CLI138
and actual capture MainWindow construction/close trace show the same inherited preferences risk.
Reuse existing isolated_capture_config around Qt import/configuration, capture, drain and summary/return;
keep run-id/registry/plan/cache verification and owned build-output admission before it. No download,
force deletion, dataset execution, new owner or changed exit/publication contract. Extend shared
pre-GUI test matrix with real INI roundtrip/host restoration, isolating registry/cache inputs only;
preserve actual build-containment function with test-owned root and assert cache check precedes config
override. Test local QApplication import at its external constructor seam. One targeted red, shared
18 cases, real CLI help/option checks, Ruff and independent lifetime/preflight review; no MOABB data
gate claim. Then continue remaining scripts and first-paint diagnosis, not handoff.
Result: targeted red fails before GUI at inherited host root0.15s; all18 shared cases pass7.34s.
Ruff/format, diff check and independent actual preflight/lifetime review pass. Product source and
dataset execution unchanged; the independent review confirms existing force semantics were not run.

**Bounded8J — correct actual Settings screenshot labels in the UI/UX report.** Independent full
walkthrough3713/direct747 audit and main's renderer/capture-order trace identify README advanced and
disabled links selecting runtime-loading and advanced images respectively. Preserve the existing seven
states and their order; fix only two renderer indices. Strengthen the existing real Qt capture test
with exact generated README-to-image mappings, first red at that mismatch, then green without relaxing
geometry/content/lifecycle assertions. No product/UI/model/prompt/schema change, ownerdelta0. Use the
existing Windows interpreter and isolated test preferences; focused full-capture case, Ruff and actual
diff review. This validates the report artifact, not final DPI/manual/real-model acceptance. Continue
MOABB CLI isolation and remaining full-script/inventory audit after this bounded repair.
First native full-capture run fails before report assertions: MetricTab.update_plot was retired in
eac27aad but this script caller was missed. This is a directly blocking stage regression, not valid
README red evidence. Migrate that real caller to existing set_series([1], [72.0], [68.0]) and update
the report's API description; preserve all first-data/empty-state assertions. Then reproduce the
README mismatch and fix its indices. No compatibility wrapper or product API reintroduction.
The migrated caller now executes, but native and offscreen full captures both report real-dock320px
first-paint no_horizontal_scroll failure. Keep that original strict test/assertions intact; independent
source diagnosis proceeds separately. Add a focused real-artifact report test that verifies links to
actually generated Settings images and preserves the actual machine-gate status, including failed
captures. This is report evidence only, not a green full-capture claim or weakened geometry gate.
Result: real native report test red at the advanced link12.79s, then pass12.69s after two-index fix;
two-file Ruff/format and diff check pass. MetricTab caller now completes via the unchanged bulk API.
Independent first-paint diagnosis identifies post-show dock-width/reflow scheduling as a candidate,
not proven root cause; raw geometry/pixel evidence remains required before any visible repair decision.
Full capture remains failing on the retained no-horizontal-scroll first-paint gate in both backends.
Next8J diagnostic is read-only: in-memory wrap the existing first-paint observer to record raw panel/
viewport/content widths, minimum hints, horizontal range, child bounds and reflow timers, then the
same fields after original capture and three explicit event turns. Run only the real-artifact test
under existing isolated native Qt fixtures; restore wrappers in finally, no persisted source patch,
model/data/cache writes or altered first-paint assertion. Geometry establishes whether overflow
persists, not whether raw first-frame pixels visibly clip; any visible product repair needs approval.
Diagnostic: initial instrumentation failed on parentless standalone widget and sibling mapTo usage;
no product evidence from that attempt. Corrected temporary observer: real-dock raw first paint has
viewport320/content564/horizontal max244/deferred reflow active, but measured runtime/composer bounds
both12..308 already fit. After original capture, range is0/content matches viewport; extra turns
retain0. Standalone range0 nevertheless has runtime widget59..355 until next turn12..308. This proves
transient geometry/range settling and a limit of range-only evidence, not persistent or visually proven
clipping. Raw first-frame pixels were not captured. Keep the full gate failure open; do not relabel it
passing or implement a visible UI correction from these observations alone. Diagnostic report test
passed6.81s; its extra observation turns are not uninstrumented full-gate evidence.

**Bounded9L4A — cover remaining standalone replay/dialog preference consumers.** Same-class caller
scan finds Data Interpretation replay constructs/closes real MainWindow, reviewer-fixes opens real
SmartParser, and app-polish constructs MontagePicker; all reach application_settings without an outer
config override. Reuse existing isolated_capture_config around each Qt-to-publication lifetime after
CLI/preflight, preserving validate-only, source/fixture validation, staging, output and existing cleanup.
No new owner/helper, dataset/model execution or visible product change. Extend the shared pre-GUI
matrix7→10 with only external fixture/Git seams isolated; restore replay's existing mutable artifact
directory in test teardown. Three target reds before source edits; shared17 cases and directly related
CLI/validation controls, independent actual lifetime review and Ruff. Pure config isolation is not a
claim that the giant script bodies are fully audited or their full captures pass. MOABB local-import
CLI is a separate next slice; normal Windows/WSL product launcher preference policy stays untouched.
Result: three targeted reds fail at inherited host config before GUI6.75s; all17 shared cases pass7.40s.
All three real CLI help/declared-option checks pass without GUI/data/model execution. Four-file Ruff
and format pass; independent actual lifetime/publication diff review approves. Only existing context
reuse and entrypoint tests change; full capture execution and whole-script audit are not claimed.

**Bounded9Q — remove stale architecture cache/status/dispatch claims.** Independent full agent543/
target425/backend860/data-pipeline430 and main's affected source traces identify: unconditional old
repo-local cache default, dated host cache/benchmark values presented among current runtime facts,
TrainingManager CSV-export responsibility after5A retirement, undated dashboard PASS, and data-pipeline
next-slice instructions outside Now. Replace physical cache/config claims with existing platform/explicit
override owners and narrow WSL launcher policy; preserve model/revision/quota/fail-closed contracts,
normal JSON/NPZ result persistence and all actual dataset limitations. Remove obsolete measurements
and dispatch instead of moving them to a new record; Git remains historical provenance. Describe
evidence kinds and link canonical validation/Now, not fresh PASS or new target. Target files unchanged.
Independent actualdiff/source-backed review, guidance/source-link checks, diff check. Strict site build
remains the already-known missing-MkDocs/final same-head CI obligation; do not rerun that unavailable
tool or install another environment. Continue unfinished module audit after this doc-only slice.
Result: independent actual source/authority/link review approved; user-site source validation,
guidance audit (ok=true/no errors) and diff check pass. Three architecture pages net-25 lines;
no new record/target/contract. Final same-head strict docs build remains open; not site-build complete.

**Bounded9L3 — extend existing capture preferences isolation to two uncovered native entries.**
Independent caller trace and main's complete short main/lifecycle reads find human-like capture closes
real MainWindow (therefore persists normal host geometry), while UI/UX capture reads native geometry
and may remove invalid saved values. Neither entry sets CONFIG_DIR; CI/DPI/handoff callers do not
shield it. The inner human-like Assistant settings helper only isolates LLM JSON/cache, not Qt.
Wrap each existing post-parse main body in isolated_capture_config() with no config copy; deterministic
human-like driver explicitly constructs primary-model/fake-runtime configuration and does not require
host model/enabled preferences. Preserve args, staging/publication, failure codes, Qt lifecycle, content,
model/prompt contracts and all production source. No new helper/owner, environment or real-model run.
Extend existing shared pre-GUI test matrix from five to seven mains, retaining real Qt INI roundtrip,
host-byte/env checks and owned-root cleanup; adapt only factory .instance() test seam and Git provenance
seam for pre-GUI interception. Reproduce both paths before edits, rerun shared tests + existing human-like
main-failure test with verified process-local Windows Git mapping, independent lifecycle/diff review
and Ruff. Continue remaining captures/docs inventory; not a full capture or handoff claim.
Result: two targeted reds fail at inherited host config before GUI6.89s; all14 shared isolation cases
pass6.86s after. Existing main-failure plus two inner-settings cases pass8.50s with exact8080dd0e
Windows Git mapping. Three-file Ruff/format, diff check and independent actual lifetime review pass.
Scripts +55/-51/net+4 (mostly context indentation), test +15/-2/net+13; zero product changes/new owners.
The two large parent files were entry/lifecycle traced, not fully audited; remaining file review stays open.

**Bounded9P — prove walkthrough settings/cache cleanup on both exits.** Independent full human-like
capture helper1207 retains real readiness classification and outer-owned GUI lifecycle. Existing direct
8-line test checks only in-context cache completeness, not host bytes/default-path restoration or
temporary cache cleanup. Strengthen it using test-owned host/legacy paths and original method bindings,
with normal and raised-exception exits; retain actual LLMConfig load and actual pinned cache inspection.
The256MiB logical fixture crosses production's256,000,000-byte readiness threshold: retain it in an
owned temporary D-drive directory, not a smaller fake or permanent weight. Do not invoke a model,
GUI, download or change product/helper behavior. First run original single case; strengthened two-case
suite, bounded in-memory lost-restore/cleanup fault, independent actualdiff/evidence review and Ruff.
Normal-exit host-digest receipt is asserted only on normal completion; on error actual bytes/restored
bindings/root absence prove cleanup without inventing an error-path artifact contract. Continue audit.
Result: original1passed7.16s, stronger2passed7.26s. In-memory omitted temporary-directory cleanup
fails both cases at the cache-exists assertion; pytest-owned roots clean up the intentional leftovers.
Independent diff review approved. Ruff required combined with-context/style formatting; final focused
rerun2passed7.26s and lint/format pass. Production unchanged, no test removed, one parameter case added.

**Bounded9O — retire two unconsumed direct dependencies, preserve external reader requirements.**
Resumed bounded method: installed Poetry2.3.4 can solve entirely from existing locked package metadata
when each in-memory repository retains original PyPI PRIMARY / pytorch-cpu and pytorch-cu130 EXPLICIT
priority. A flat-priority experiment incorrectly collapsed three generic Torch records and changed
CUDA markers even on unchanged root; rejected without write. Priority-preserving independent control
has identical full package records; reduced-root comparison removes exactly dotenv1.2.1/qdarkstyle3.2.3.
Main repeats control/candidate exact keyed-record comparison (all fields), forbids all network, checks
only two pyproject declarations changed, then uses official Locker writer once. Abort on any surviving
version/source/marker/group/dependency/extras/file hash drift. No manual lock edits/install/newenv/cache
payloads. Verify official lock freshness, denied-import startup tests and independent resulting diff.
Result: sequential control/candidate initially shared mutable Poetry packages and restored the two
removed records; full-record guard aborted before write. Fresh Factory/Locker/root/packages/pool per
solve fixes this verified harness isolation error. One sandbox read-only file-open rejection made no
lock change; the same guarded official writer under normal escalation succeeds.217->215 exact records,
only dotenv/qdarkstyle removed, all surviving fields unchanged; poetry check --lock --strict passes.
43real config/startup/MainWindow/shutdown tests pass12.05s with imports of both packages denied.
Independent exact diff/record comparison and freshness review approves. No downloads/installs,
environment changes or actual disk-reclamation claim. The earlier unresolved attempts below are history.
Independent full pyproject314 plus package/lock/caller audit finds no product/script/test/dynamic theme
or environment loader for qdarkstyle and python-dotenv. Main verified the removed comments-only .env
template was not a loader. Keep pymatreader: installed MNE EEGLAB reader invokes it for supported
.set/MATLAB HDF5 handling despite no project import; initial static-only removal suggestion rejected.
Keep requests/tqdm and optional hosted SDK group pending separate ownership decisions; no broad dep
upgrades or model/runtime changes. Remove exactly these two direct declarations and regenerate the
existing lock through installed Poetry2.3.4, preserving versions/sources/hashes of surviving packages.
No environment creation/sync/install, package/model payload download, global config write or manual
transitive stanza edits. Read-only PyPI JSON metadata for already locked exact versions is permitted
when the installed resolver needs it; restrict requests to those endpoints and use a creator-owned
temporary metadata cache. Reject wheel/source payload URLs and unpinned/latest/version changes.
Original poetry check --lock --strict passes. Run lock refresh with network denied and environment
creation disabled. Offline diagnosis identified missing google-genai1.59.0 metadata (an unchanged
optional group dependency); a bounded pinned-JSON-only refresh may fill this, otherwise leave the
candidate explicitly unresolved, not a hand-edited supposedly valid lock. Verify exact graph delta/lock freshness, focused startup/shared Qt
paths with imports of retired dependencies denied in memory, independent diff review and CI remains
required. This is metadata cleanup, not a claim of reclaimed installed-package bytes.
Unresolved result: offline refresh lacks pinned metadata. The bounded read-only metadata attempt
subsequently reached an unpinned /simple/types-pyyaml/ lookup and was deliberately rejected before
any lock write or payload download. No lock diff was produced. Restored only this slice's two direct
declarations so pyproject and the existing lock remain consistent; no installed package changed.
Independent caller audit approves the deletion candidates, not a nonexistent lock refresh. These two
retirements remain open until exact-pinned resolution can be obtained without an unrelated upgrade;
continue independent authorized work instead of bypassing the resolver or expanding dependency scope.

**Bounded9N — retire historical repository-wide terminal auto-approval.** Main fully read the tracked
17-line .vscode/settings.json: its only content is blanket Poetry auto-approval, two one-off compile
command regexes naming already removed modules, and automatic git add -A. No editor formatting/debug
configuration exists in it. Those grants are not needed to run the application or existing developer
commands and may approve unrelated edits/settings staging. Delete this exact repo-local file only;
do not modify root settings.json, user/global VS Code settings, installed editor state or runtime
permissions. Generic dashboard/handoff dirty-path fixtures mentioning the path test arbitrary Git
status and remain meaningful after deletion. Retain all checks and commands; no replacement allowlist
or second approval owner. Independent actual file/reference/security review, guidance audit and diff
check; no product tests or screenshot needed for this configuration deletion. Continue module audit.
Result: independent actual-file/security/caller review approved; guidance audit ok=true/no errors and
diff check pass. Seventeen tracked config lines removed, recoverable in Git. Existing generic dirty-path
tests retained; no global editor settings or root settings.json changed, no product behavior claim.

**Bounded9M — remove stale developer instructions without weakening gates.** Main fully read developer
setup214/testing406/index32/map32/change56, root README69, docs index52 and local dev configs. Testing
guide still demands a full manifest for every candidate, contradicting the existing validation L0–L3
contract and handoff workflow; it also says capture clears native geometry after9L2 removed that action.
Synchronize these exact statements and docs index navigation with existing authority: focused checks
first, same-head applicable CI for delivery, full unchanged manifest only when explicitly required.
Document current capture-owned settings lifetime, retaining legacy preflight normalization limitation.
Clarify actual per-user settings versus protected root legacy import using platform_paths/config and
9K Qt adapter; do not change config/loading behavior or model selection. Remove orphan .env.example
comments-only template (no loader/reference, deleted download planner, obsolete cache path); keep actual
environment-variable support and dependency decisions separate. No product/UI behavior, version or
public gate changes. Independent source-backed doc review, link/user-site checks and strict portal
build in existing environment; no new environment/downloads. Continue modules after docs slice.
Result: independent source-backed doc/deletion review and diff check pass. User-site source validation
and guidance audit (ok=true/no errors) pass. Strict portal build cannot start: sole Windows environment
and system Python both lack MkDocs; no install/new environment was attempted. Owned build temp root
was cleaned by its creator. Existing same-head docs CI must supply strict build/built-site evidence
before final delivery;9M is source-reviewed, not a successful site-build claim. Deleted .env.example
contains only stale comments and is recoverable from Git; no user .env/config/model/data was removed.

**Bounded7J — retire test-only window bounds forwarder.** Full main geometry lifecycle373/placement439
and direct185/193/integration332 retain sole Qt restore/show/persist owner and pure multi-screen policy.
Only lifecycle.position_bounds has one test caller and no runtime/script/config/doc consumer; it repeats
the live pure usable_window_position_bounds adapter. Migrate that first-launch assertion to the actual
pure helper plus native frame_extents, preserving every geometry assertion; remove only the unused
method/import. Keep policy accessor used throughout geometry tests, actual bounded_position used by
MainWindow, saved settings and0/250ms recovery timers. No visible placement/timing change, new owner
or user settings write. Three suites before/after, Windows actual Qt platform where available; review
actual diff/callers and Ruff, commit independently; then continue module audit, not handoff.
Result:31geometry+6seed baseline37passed4.49s on Windows Qt windows; migrated first-launch1passed0.50s,
retained geometry31passed2.26s after. Production-27, testnet+8, zero case removal; exact policy/frame
assertions unchanged. Independent actualdiff review approved, Ruff/format passed.

**Bounded9B — strengthen actual RNG reproducibility evidence.** Utility audit full seed90/direct79
retains shared real Python/NumPy/Torch state ownership. Existing restore test captures and restores
without advancing generators, so an omitted restore can pass. Replace it with actual draws, advancing
all three streams and then verifying exact replay; strengthen set_seed with repeated real draws.
Preserve original state in finally, isolate only CUDA availability, keep actual CUDA configuration/
state seam cases and automatically generated seed assertion. Add rejected malformed-state/CUDA-unavailable
cases proving no partial CPU mutation. Production unchanged, no model/download/GPU allocation or
scientific reproducibility claim. Original six-case baseline, stronger focused suite, intentional omitted
restore fault must fail, main nonauthor review and Ruff before tests-only commit.
Result:9passed2.18s, original6 cases preserved/replaced plus3 new. Main review corrected CUDA
atomicity fixture to use requestedseed123 versus currentseed456; same-state input would miss premature
mutation. Three separate in-memory omitted Python/NumPy/Torch restore faults fail each exact stream,
and moved CPU mutation before unavailable-CUDA rejection fails fourth case. No faulty source written.
Ruff initially flags intentional experiment random.random as non-cryptographic; file-scoped S311
annotation documents exact test purpose, formatter/Ruff then pass. Only CUDA availability is isolated
for CPU cases; real CUDA allocation/reproducibility is not claimed.

**Bounded9C — replace mock-only VRAM warning tests with actual widget conditions.** Full main checker124/
direct147 finds one no-assertion negative case, two identical snapshot helper cases and policy tests
mocking both predicates. Preserve existing heuristic/copy/public behavior (not resource admission).
Use real QMainWindow/QStackedWidget/QTabWidget and immutable runtime snapshots, isolate only modal
show_alert. Cover initialized local+active3D warning, other tab/hidden/other workspace/no local,
explicit switching entrypoints, unavailable snapshot and lazy placeholder. Migrate assertions to
check()/on_viz_tab_changed results, retire exact duplicate/private-helper cases only after stronger
baseline. No production change or GPU/model invocation. Focused original and stronger suites,
intentional ignored-local or ignored-tab guard fault, main nonauthor review/Ruff; no handoff claim.
Result:13original0.09s ->23stronger0.15s ->10retained0.13s. All old behavior assertions migrated to
actual widget conditions, including non3D signal ignored and exact warning copy; one literal duplicate
and no-assertion path replaced. First stronger run22pass/1fail exposed fixture.show overriding stack
hiding; fixed fixture order, removed import-time QApplication, retained assertions. Omitted local and
tab guards each fail at unexpected show_alert. Production unchanged; tests+163/-124/net+39; Ruff pass.

**Security utility audit disposition.** Independent full filesystem_identity1115/direct121,
public_diagnostics1897/direct2256, structured projection531 and runtime collector71 retain live
descriptor/handle identity and single fail-closed privacy boundary. Tests exercise real hostile inputs,
budgets/cycles/idempotence and recovery-text preservation; no justified duplicate deletion. Runtime
collector intentionally returns internal filename/GDF details to dataset/preprocess state services.
Main traced state_builder->typed snapshot/query; model state-card assembler423–496 selects counts/
readiness, not raw diagnostics. ToolCommandResult.to_payload uses public_safe_result_projection and
final public_diagnostic_value for nested state/diagnostics. Raw internal snapshots are not public-safe
payload claims; no new leak or sanitizer rewrite justified by these internal fields alone.

**Bounded7K — retire orphan error decorator capability.** Full main utils/error_handler81/direct182
and actual exceptions141/application errors246 audit finds all three bespoke subclasses, handle_error
and its private message/storage helpers have only11 exclusive test callers. Git-wide source/config/
script/docs search and utils package exports show no registration/decorator use. Actual backend
XBrainLabError/subtypes, application map_exception and UI error presentation remain separate live
boundaries with retained real privacy/hostile-protocol tests; do not move these into the retired file.
Delete exactly orphan source/test file after original+live exceptions/results baseline, independent
caller/privacy review, then same retained cases. Production-81/test-182, live owner0delta, no public
Command/query/Assistant or visible semantics change; unknown external convenience imports are not
preserved per stage authorization. No replacement wrapper or new policy. Commit independently, then
continue shared UI/scripts audit; a failed permission decision stops only this deletion, not other work.
Result: original decorator11 plus live mapping/privacy25 and styles25 baseline61passed6.92s;
retained live exceptions/results25passed5.38s after deletion. Independent actualdiff/caller review
approved; public error/privacy owners unchanged. Only orphan source81/test182 lines removed, no data.

**Bounded7L — remove unused theme/registry surface.** Full independent and main icons52/direct65,
theme192/direct133 plus actual AgentManager474/settings button3128–3197 and AppConfig owner74 read.
Six icon entries reference absent assets and have no consumers; the only real SETTINGS.path forwards
literal settings.svg to AppConfig.get_icon_path. Use that existing owner directly in AgentManager and
the actual QIcon pixel test, then remove whole Icons module and its four exclusive registry mocks.
Retain actual settings.svg and standardIcon fallback unchanged; no visible UI/art change. Remove six
unused theme tokens and test-only get_style_sheet/three exclusive tests, not Stylesheets.MAIN_WINDOW
or live Matplotlib styling. Strengthen actual figure/axes/legend color assertions before retirement:
current not-white/legend-exists assertions can miss a styling no-op. Keep existing case shapes and
live color/style semantics. Baseline icons/theme/actual dock-titlebar test, stronger pre-delete then
retained after; exact path equality/pixel assertions, intentional no-style fault, Ruff and independent
actualdiff review. Three production files netnegative, ownerdelta0, no generic registry replacement.
Result:25original ->25stronger6.52s ->18retained6.49s. Seven exclusive registry/stylesheet cases
removed only after stronger live evidence; six actual Matplotlib cases remain. In-memory styling
no-op fails five exact color cases (one None case passes), proving detection. Production+2/-86/net-84;
tests net-8; independent actualdiff review approved and Ruff/format passed. No asset/layout change.

**Inventory corrections.** Current Windows setup launcher is87lines, not earlier187 typo. Installer
integrity tests belong to tests/unit/scripts/test_windows_source_bootstrap.py, not the UI local-bootstrap
suite. Main corrected the misattributed inventory row and then fully read the actual340line UI suite:
real dialog/runtime/settings behavior retained; its256MB-per-file fake weights need a bounded fixture
budget reduction (not model admission weakening). Reading that suite is not installer evidence.

**Bounded9D — shrink runtime-readiness fake weight fixtures.** Three fully audited suites (UI
local-bootstrap340, config761, runtime-inspection383) create seven256MB fake weights per full run;
they test settings/selection/readiness/classification, not production model size policy. First measure
actual fixture file counts/logical bytes on the existing Windows environment with pytest-owned
temporary cleanup, retaining all assertions. Then explicitly inject a test-local scaled minimum and
write tiny real weight files in the existing helpers; no global/autouse patch, mock cache-complete,
new shared fixture framework or production admission change. Preserve metadata/pinned revision and
real Qt inspection workers, wait through their terminal state before fixture teardown. Production
unchanged. Same three suites before/after, byte measurement, unchanged catalog tiny-weight rejection
and deliberate empty-weight fault must fail. Main/independent actualdiff review and Ruff; continue
catalog/lifecycle fixture audit separately, not final handoff. No real model/cache/env deletion.
Result: same72passed before7.72s/after6.34s; measured fake-weight logical bytes1792000000->7168
across7files. This is not physical disk reclamation or a stable speed claim. Production unchanged,
tests+52/-33/net+19, zero removed assertions/cases. Three empty-weight injected cases fail their
actual readiness/classification assertions; unpatched256MB minimum plus tiny-weight rejection passes.
Independent actualdiff/lifetime review and Ruff pass; all test artifacts use pytest temporary cleanup.

**Bounded9E — scale catalog/lifecycle fake weights without losing admission boundaries.** Full
independent catalog655/lifecycle659 and main affected helpers/callers show300MB complete/150MB shard
fixtures only cross the256MB minimum; no actual model loading/process download uses them. Baseline
both suites with temporary cleanup and measured logical artifact bytes. Replace giant weights with
real1KiB files and explicitly opt affected cases into a local threshold fixture (not global/autouse).
Keep default-size rejection outside that fixture, add below/equal/above scaled-limit assertions;
shard test must reject a missing shard even when its present shard alone meets total minimum.
Preserve actual pinned metadata, symlink/hardlink guards, partial quota accounting, Qt thread/terminal/
cleanup assertions and fake downloader external isolation. No production/runtime/download policy or
user files changed, no shared fixture platform. Same focused suites plus small boundary cases,
intentional missing-shard and strict-greater-than faults, independent actualdiff review and Ruff;
commit tests-only and continue remaining module audit, not manual handoff.
Result: original50passed3.59s, stronger54passed0.77s, weights20paths4800000308logicalbytes ->
24paths21812bytes (four added boundary/policy cases). First baseline attempt49pass/2errors was an
ephemeral measurement-hook conflict with mocked scandir; isolated measurement scan and repeated once,
no product/test assertion changed. Strict > instead of >= fails exact-limit case (other2pass);
omitted missing-shard check fails despite present weight meeting minimum. Production unchanged,
tests+61/-18/net+43, independent actualdiff approved, Ruff pass. No physical disk/speed certification.

**Bounded7M — retire MainWindow test-only global loader bypasses.** Independent source1–240 and
Git-wide dynamic/config/script/doc audit identifies seven None compatibility globals and three
globals().get early returns, with only five InfoPanelService test patch sites. Actual three lazy
loaders, module imports, panel import lock and GUI-only preparation flags remain sole owners. First
baseline main-window sync/launch/lazy-completion suites; try removing the five obsolete service mocks
so those cases compose the real lightweight InfoPanelService. Preserve controller-free typed-port
and real widget assertions; no new fake/adapter unless an actual external seam requires isolation.
After passing migrated tests, remove the unused globals/bypass branches. No visible UI, eager import,
timing/shutdown/publication change, ownerdelta0. Same focused suites plus independent actualdiff
review/Ruff; one independently reversible commit, then continue inventory/remaining tests/scripts.
Result:121before11.01s; six migrated real-service construction cases pass0.58s before removal;
same121after11.03s. Production-19/test-5, no cases/assertions removed. Independent actualdiff
review approves lazy/thread/startup invariants; Ruff passes after restoring one required import/class
blank line. Seven unused globals/three bypasses gone, real InfoPanelService used in all five patch sites.

**Bounded9F — consolidate all-page refresh behavior evidence.** Full independent MainWindow sync
3052lines (93definitions) retains real Qt/service/render/thread cases and distinct shutdown gates.
Five one-page positive refresh cases duplicate the same shape; existing stronger only-target case
covers training only. Parametrize that stronger case across all five pages and pass before retiring
the five weaker single-page cases. Assert selected refresh exactly once and all other panels untouched
through MainWindow.switch_page, not a mocked refresh policy. Keep nav checked-state, delegated refresh,
publication/status and all lifecycle assertions. Original7M121case baseline covers these six cases;
focused stronger10 then retained5 mapping cases, intentional wrong-page/all-pages refresh fault,
independent actualdiff review/Ruff. Production unchanged, one fewer case only with stronger evidence;
no new helper framework, native/manual model claim or module closure inferred.
Result: six old mapping cases covered in7M121baseline;10stronger0.62s ->5retained0.58s. Tests
+6/-34/net-28, production unchanged. Wrong-page in-memory fault fails4/5; all-pages refresh fails5/5
at exact selected/non-selected assertions. Independent actualdiff review and Ruff pass; unrelated
navigation/delegation/publication/shutdown cases unchanged.

**Bounded9G — retire misleading publication test duplicates only after preserving their nuances.**
Full main/independent primary publication suite570 uses real panels/Observable/Qt timers with narrow
render/query isolation. Dataset-only case's controller is never wired, so its notify proves nothing;
Preprocess-only case overlaps all-three-panel ledger evidence. Main identified two details not yet
subsumed: idle-before-any-event25ms negative window and repeated identical pending revision before
first render. Fold both into existing all-panel commit/coalescing cases, pass strengthened baseline,
then remove only those two superseded cases. Retain query failure/row preservation, queued filtering
readiness, transient training updates, retry/backoff/cleanup/stale and synchronous-command no-refresh.
Production unchanged; no reset of publication policy or mock readiness. Original/full stronger/retained
suite and an intentional premature-render fault, independent mapping/diff review/Ruff. The retained
bounded negative-observation window is test evidence, not an introduced UI wait or speed claim.
Result:32original8.68s ->32stronger8.81s ->30retained8.67s; productionunchanged, tests+5/-37/net-32.
Idle spontaneous-render fault fails all3 exact no-render assertions; same-pending immediate-render
fault fails all3 pre-queue assertions. Main corrected review's initially incomplete replacement map
before deleting anything; independent final diff approves, Ruff passes. No source fault persisted.

**Bounded9H — remove blind waits from navigation smoke when measured state evidence permits.**
Full main/independent integration smoke194 and shared test_app fixture retain real Study/MainWindow,
lazy panels and exact dock/stack assertions. _click always waits50ms, regardless of ready state;
measure count/helper duration and full-suite baseline first. Replace fixed delay with existing
_wait_for_panel at navigation assertions and explicit bounded dock-visibility waits; retain all
current state/type/ownership assertions and remove only unused EXPECTED_EVALUATION_TABS constant.
Evaluation intentionally supports bottom long-label and chart short-label layouts (source1974–2130),
so both labels remain accepted; this is not a copy defect or UI change. No production edits, model
activation/download or environment change. Same suite before/after, actual click/wait measurement,
Ruff/main+independent review. Report measured helper overhead only, not application speed or native
manual acceptance. Keep meaningful negative-observation waits in other tests; do not strip waits globally.
Result:11 cases before9.03s and after8.74s; same11 click calls measured0.938120s before versus
0.019085s after in helper (including event processing). Removed only the fixed50ms delay and unused
constant; readiness now uses bounded loaded-panel/dock-visibility conditions. Whole-suite timing is
a single-run observation, not a stable speedup claim; no production performance claim. Independent
actual-diff review approves readiness ordering and all unchanged assertions; Ruff/format pass.

**Bounded9J — isolate actual Qt settings before more GUI tests.** Main found three live Python
QSettings consumers: main-window geometry, montage preferences and SmartParser settings. Test root
has no QSettings isolation; montage tests attempt NativeFormat.setPath, ineffective on Windows/macOS.
Read-only Windows probe confirms setDefaultFormat(IniFormat) does not alter the two-string org/app
constructor (stillNativeFormat), consistent with [Qt's constructor/setPath documentation](https://doc.qt.io/qt-6/qsettings.html).
Do not run further native-preference-consuming tests until isolated. Previous preference changes
cannot be excluded without before-state; do not claim no QSettings side effects or restore guessed
values. Root settings.json/model/data/env remain out of scope and untouched.
Scope: tests-only fail-closed isolation at the actual Qt constructor seam, preserving real per-test
INI serialization/roundtrip instead of Mock settings. First validate that scoped monkeypatching the
real QSettings.__init__ reaches existing imported aliases without eager UI imports. Audit actual
overloads and teardown order; avoid generic storage/control framework and extra temp allocation for
tests that never construct settings. Add red path/format assertion before any write, then isolation,
roundtrip and per-test reset tests; retire ineffective montage NativeFormat path/env redirects.
Keep production QSettings/native behavior and existing geometry-specific fakes unchanged. Focused
isolation/geometry/montage/SmartParser and9H baseline only after safe routing, independent safety/diff
review/Ruff. Necessary shared-fixture evidence may widen only to affected UI paths. Native registry
persistence is not claimed by INI-backed tests; required out-of-process gates retain separate review.
Result:4 red cases fail on NativeFormat before any write; isolated5 cases (including explicit INI
pass-through) pass0.30s. Affected85-case offscreen run83pass/2montage height failures; same assertions
on verified Qt windows platform85pass15.26s, with18 MNE/NumPy deprecation warnings. Keep offscreen
geometry limitation visible; no weakened assertions or claimed native registry persistence. Scoped
real constructor patch reaches imported aliases without eager UI imports; ineffective four NativeFormat
and six XDG redirects retired. Independent actual-diff/fixture-order review approves. Production unchanged.

**Reviewer-capture disposition.** Full independent script1629/direct767 plus actual handoff registry
and manifest consumers retain ui-reviewer-fixes as a required gate. It owns real A01T preview/time/PSD
curves, history/normalization/resampling/SmartParser/import-review states and unique multi-method/split
geometry evidence. App-polish/baseline overlap conceptually but no equivalent per-surface contract was
proved. No script/test/gate deletion; any future surface migration needs an explicit evidence-preserving
decision. Source inspection is not a newly executed capture or performance result.

**Bounded9K — make the existing config override reach actual Qt preferences.** Follow-up read of
run.py370/platform_paths247/native-smoke251/startup-smoke141 confirms the same real defect outside
pytest: smoke sets a static Ini default/path but splash and geometry/dialog consumers still construct
native settings. A smoke close can therefore persist to the user's native store. Do not run startup,
native-product or capture gates until their actual settings path is proven isolated.
Outcome: explicit XBRAINLAB_CONFIG_DIR routes real Qt preferences into per-application INI files in
that existing config root; absent override retains the exact native org/app store. Reuse existing
platform_paths.user_config_dir resolution, retain preference names/values and geometry lifecycle;
no normal-launch visible behavior, model/EEG/public-command change or settings migration. UI-internal
authorization already covers this boundary repair. First add red actual geometry path assertion before
write, then route splash/geometry/MontagePicker/SmartParser through one small UI Qt constructor helper.
Retire the orphan geometry factory and ineffective startup static Qt setters, replacing mocked-setter
tests with real storage/reopen assertions. Keep explicit smoke absolute-path admission.
Complexity review before implementation: new module is a pure Qt construction seam for four real
consumers, not an admission/publication/async owner; authoritative owner counts unchanged. Expected
five production files and about+25/-20 LOC; exact delta required after edit. Separate scripts/capture
migration into9L so no unsafe capture is run between slices. Do not add a general storage framework.
Validate normal native constructor selection read-only, override path/partition/roundtrip, actual
geometry/montage/parser/splash focused tests, caller/diff review and Ruff. One reversible commit;
then directly continue9L to remove duplicated unsafe capture clearing/global setter paths. Capture
entrypoints must establish isolation themselves or fail closed, never rely on pytest monkeypatching.
Direct shared-fixture dependency: an inherited config override makes the new explicit INI route
bypass9J's org/app-only interception. Add a before-write regression using an external test-owned config
root. Extend only the current product INI path interception to per-test storage when the requested
file is outside that test's tmp_path; preserve explicit overrides already owned by the test and all
unrelated explicit INI callers. No config-env or Assistant JSON override. This is necessary before
broader GUI tests; final factory/native and test-isolation claims must be separately verified.
Execution:24 settings/splash cases pass0.55s; independent Windows probe without pytest confirms
unchanged native filename/format read-only and all3 override stores sync/reopen within a temporary root.
Native combined104 run102pass/2splash centering failures: tests assume primary screen, while existing
product policy correctly chooses the cursor's secondary monitor (observed x=-960 vs primary959).
Do not change product placement or weaken centering assertions. Fix the two test preconditions by
isolating QCursor.pos at primary center, retaining real screen choice/placement and exact pixel bounds;
then revalidate only affected settings/native paths. New fixture routing also needs final Ruff/review.
Final focused24 native cases pass0.61s after deterministic cursor setup. The other80 native component
cases already passed against the same production source. Both before-write defects reproduced before
repair; nine changed Python files pass Ruff/format and independent final actual-diff review approves.
Production5 files+28/-19/net+9 (includes15-line Qt adapter); no owner increase, migration shim or
user/native settings write. Script callers retain9L as an explicit unresolved blocker to capture gates.

**Bounded9L — isolate smoke/capture preferences and retire unsafe clears.** Full main/independent
native-smoke251/startup141/prepare65 and direct native117/startup191/prepare29 retain existing
process ownership, absolute Unicode isolated-root admission, timeout and shutdown evidence. Full
independent baseline667/local510/tool-chain600/workflow911 capture source; visualization entry310
of2854 only, remaining source audit still open. Four capture helpers delete native preferences; the
tool-chain helper (also used by visualization) deletes obsolete geometry/windowState keys. Do not run
any capture until it owns an isolated config lifetime before actual Qt preferences are created.
First9L1: retire native smoke static Qt defaults/path setup; obtain actual settings from9K factory,
fail closed before creating MainWindow if its file escapes the admitted config root or is non-INI,
and report the actual qsettings_root in the unchanged artifact schema. Add an out-of-root negative
test that fails before any preference write. Focused script tests, independent review, then bounded
real Windows startup/native smoke using existing isolated environment and process owner. No live
model activation/download, data/training operation or new environment.
9L1 result: out-of-root case first fails at wrong-platform check (proves missing admission, no window
or write); after repair21 focused startup/native/prepare tests pass0.13s. Independent diff review and
Ruff/format pass. First real-smoke invocation was rejected before execution for implicit parent-isolation
risk; re-read exact source and strengthened invocation to establish/validate all parent paths plus all3
actual INI stores before any GUI. Approved safer run: real Windows startup exit0, clean close/quiescent;
native product exit0, five real panels, New Session generation, actual config-root assertion and clean
shutdown with zero workers/subprocesses. No data/train/model work. Both used existing bounded process
ownership; temporary roots cleaned by their creator. These focused results do not certify same-head CI
or manual acceptance. Capture entrypoints below are still pending, not covered by this pass.
Next9L2: capture entrypoints need a temporary owned config lifetime, preserving real host Assistant
selection/cache by loading the existing config before isolation and using that same config inside it.
Remove duplicated clear helpers only when all callers have isolation; retain explicit deactivation
CLI/settings-path contract unless a separate decision changes it. Review helper reuse vs repeated
setup without introducing a generic capture framework. Existing model-free/capture direct tests plus
safe real Qt storage evidence; full model/data captures remain final applicable gate work.
9L2 design review approves one small scripts/dev/capture_config.py context for five real main callers:
stdlib TemporaryDirectory and scoped env restoration; optional exact ready host config copy using its
existing save_to_file, fail closed on write failure. No new product owner/module or broad capture
framework. The context encloses QApplication creation and the entire existing run-function/shutdown
return, not an inner event-loop section. All five run functions have only their main caller; no external
script/doc run-function contract found. Workflow deactivation preserves its explicit OS-temp settings
filename and existing preparation, skips redundant config copy, and restores its temporary class-path
override through ExitStack even on failure. Keep model/data/cache paths and CLI unchanged.
First add red parameterized main-entry assertions before GUI creation (actual temp config/storage and
real non-default LLMConfig save/load; isolate only classification, synthetic EEG writing and GUI/capture
execution). Then shared context + five caller migrations and four helper deletions. Verify exception
restoration/config-copy failure/normal context cleanup, retained direct tests, actual Qt roundtrip without
pytest monkeypatch and independent final review. Do not run real model captures for this focused slice.
9L2 result: corrected five-case red reproduces inherited host config before any GUI; initial three
Assistant fixture failures were cache-path setup, corrected to existing MODEL_CACHE_DIR authority,
not product policy changes. Twelve new storage/lifetime/entrypoint/deactivation cases pass5.88s.
Retained focused set43pass/2source-identity failures7.66s: Windows Git cannot interpret this WSL-created
worktree's .git absolute path. Read-only explicit GIT_DIR/COMMON_DIR/WORK_TREE and OPTIONAL_LOCKS=0
prove the same root/HEAD; those two unchanged tests pass2.40s. Do not weaken identity assertions or
modify/prune Git metadata; this process-local mapping is required for further Windows evidence here.
Separate Windows probe without pytest proves all3 real Qt stores, model copy, environment restoration
and creator-owned root cleanup. Seven-file Ruff/format and independent final diff review pass. Main
integration review caught/removed one residual call to a deleted helper before validation. All four
direct native-preference clear helpers and their capture callers are gone; production behavior unchanged.
Scope limit: valid host settings remain byte-identical in tests. Existing Assistant preflight
load_from_file may normalize retired host configurations before isolation; that public policy remains
unchanged, so this is capture-time isolation, not a blanket no-write guarantee for legacy preflight.

**Bounded7N — retire an orphan import callback and collapse identical admission paths.** Main's
caller trace supersedes the earlier9I warning-test consolidation candidate: DatasetActionHandler's
on_import_finished has only three dedicated tests, no source/script/docs/config/Qt-registration caller.
Pure Python action handler construction binds explicit typed coordinator callbacks, not this obsolete
controller completion hook. Verify independently before deleting the method and exclusive tests;
retain all live import warnings, publication-driven refresh and command contracts.
In coordinator.import_data, missing scan capability returns identical blocked message for real/nonreal
contexts; after that return, scan_capability is provably non-None and a later compatibility branch is
unreachable. Collapse only these branches, preserving exact warning/error/outcome and chooser/async
ordering. No new policy owner, compatibility shim, UI copy/layout change or data semantics. Two
production files, expected net decrease; user-approved unchanged-visible UI internals apply.
Start with current DatasetActionHandler suite, then parameterize existing strong missing-capability
case across real Study and fixture context before retiring two weaker cases. Keep distinct no-sync/
no-command-bypass/worker tests. Independent caller+diff review, retained focused suite, one intentional
admission-guard omission, Ruff. Three dead-callback tests are retired with their unused capability,
not treated as replaced live coverage. Then continue module/script inventory, not manual handoff.
Result: original28passed2.29s; stronger two-context admission baseline2passed0.68s before production
edits; retained24passed2.25s after. In-memory omission of the admission guard makes both stronger
cases fail because the chooser is opened; no source fault persisted. Removed three orphan tests and
two weak duplicates, added one parameter value (net-4 cases), without reducing live no-bypass/worker
protection. Production two files +6/-52/net-46; tests +5/-38/net-33; owners unchanged. Independent
caller/actual-diff review and three-file Ruff/format pass. This is bounded import evidence, not full GUI
or module closure. Next: finish script dispositions and remaining script/docs/dependency deep audit.

**Module8 CI/Poe disposition.** Independent full ci925/docsworkflow83/pyproject314 plus routing109,
artifact verifier216/direct311 and reliability409/UI40/data58/integration-trigger24 retains distinct
Linux coverage shards/coverage-only aggregate, platform/native/data/visual/provenance gates. Repeated
setup occurs on isolated runners; aggregate already avoids full Poetry environment. No measured
redundant install or equivalent removable gate found. Existing developer CLI tasks remain live public
entrypoints, not orphan Python helpers. Docs workflow's direct bounded dependencies duplicate docs
group constraints without lock-exact install; record as a reproducibility decision candidate, not an
authorized environment migration or speed claim. This is full source audit, not same-head CI success.

**Module7 logging audit.** Independent full logger874/direct1304, run.py370,
Windows/WSL launcher sources and tests traced console output: StreamHandler binds native stdout;
CP950/strict cannot encode actual metrics `≈`, losing/noising that console record while UTF8 file
logging remains intact. Reproduce with a real strict encoded stream before any console-boundary fix;
do not change metrics copy, global/user encoding, redaction policy or introduce another log window.

7A is committed e6aa7d44: console fallback preserves already-redacted records, UTF8 file fidelity and
user stdout policy. Real strict CP950/ASCII/UTF8 streams test both sink orders; arbitrary third-party
stream partial-write atomicity is not claimed. Eight POSIX storage cases remain Linux CI obligations.

**Controller test audit completed (not module closure).** Independent full unit5429/integration582
reads retain typed receipt/confirmation generation, strict envelope, stale/duplicate terminal and
handoff contracts. High-mock units isolate real narrow seams; actual QObject/AgentWorker/QThread
integration covers nonblocking RAG/stop/setup rollback. No justified obsolete/duplicate case found;
neither suite alone claims real model/tool execution. Chat/AgentManager full test audit continues.

6Q retired unused snapshot serialization only; all typed fields/device/activation validation remain.
The six-state fault matrix catches five omitted-validation failures; string activation id is separately
rejected by coordinator correlation. Removing its two exclusive serializer cases is not reduced gate scope.

**Latest full UI reads (not closure).** Independent panel2349/controller483/history235+62 retains
sole backend transcript owner and bounded Qt reconciliation, stale deltas, reader-anchor/tail-follow
and typed confirmation/runtime controls. Zero-delay coalescing and capped8ms anchor retries are not
measured redundant waits. 6T removed the proven ignored-column/redundant-reflow and unused render paths after caller/geometry evidence. AgentManager direct3769 retains actual Qt/Study/
ApplicationService publication and real-controller debug blocked-command cases alongside isolated
manager correlation mocks. 6R replaced the zero-assert processing case with real widgets and removed only two exact duplicate
model-forwarding/dock-toggle cases after main nonauthor review.
Direct panel3041 now fully independently read: actual Qt runtime/confirmation, chunked rebuild/deltas,
prune/reader anchor/tail, resize/code/text geometry and clear lifecycle retain. Compatibility append
tests need caller migration evidence before retirement; no blanket deletion of rendering protection.

6R replaces the zero-assert processing check with actual ready -> Working/disabled -> Send/enabled
widgets; two exact duplicate cases retired.6S retains literal conversation append/prune/clear and
controller history field access; four exclusive convenience cases retired. Windows pre-import probes
can emit a Qt font-directory warning, but actual fault failures were state/order assertions.

**Additional chat widget audit.** Full independent action_card783/message_bubble776 retains exact
typed request capture/disable-before-emit and safe link/Markdown/streaming/geometry handling. Full
composer144/suggestion167/segmented98/styles753/package6 retains IME/bounded input, live model-setting
selection and shared design tokens. Direct action_card438/bubble824 tests fully read: exact request,
doubleclick, privacy/HTTPS confirmation, Markdown streaming/reuse and geometry evidence retained.
6T removed only proven unused conveniences and redundant row relocation; hidden icon/style remains.

6T places unchanged suggestion rows once; at400/620/900, five reflows each remove/add15+15 ->0+0,
with exact equal geometry/text/order. This is work elimination, not a wall-time speed claim. Deleted
panel._render_message, bubble.setText and ignored icon argument; typed rendering, script-used
append_message and hidden icon widget/style remain. Native Windows/DPI handoff remains required.

6U removed only _optional_str_list after full application_surface1687/direct264/authorized_paths303/
result_contract538 audit and caller/config/script/doc search. Formal contracts unchanged. Existing
ToolCommandResult.to_payload privacy/capability evidence also lives in controller5289, feedback82 and
execution coordinator92; absence in one direct file is not an overall coverage gap. Final byte-fit
behavior still needs bounded test/caller review.


**Publication/turn audit.** Full main presentation199/turn_state141/direct121+63 retains typed view-only
progress and exact admission/stop/terminal lease ownership. Independent coordinator251/direct149 and
actual AgentManager callers retain newest-revision retry/cadence and originating-turn training notice.
Stored training handoff_generation is unread after admission; retain admission validation pending a
bounded field-only cleanup decision. Manager/long-session evidence, not direct149 alone, protects
stale/missing run identity and exactly-once transcript delivery. Tool definitions/authorized paths and
remaining worker/runtime audit continue alongside inventory reconciliation.

**Tool/path audit correction.** Full independent definitions1+116+65+159/base65/registry62/tools-init288
and direct126+95 retain live schema providers and the18-tool projection. Full authorized_paths743/
direct303 initially misclassified the whole path capability as orphan; main challenged verifier968's
generic root branch and independent re-audit confirmed live scan/preview/recipe admission consumers.
Retain authorize_existing_path and POSIX/Windows identity checks. Only retained-handle open/grant
consumer absence is a retirement candidate; downstream backend IO protections were not examined in
this bounded audit, so no end-to-end TOCTOU defect is established. Do not delete the whole capability.

**Completed shared UI/runtime audit (not module closure).** Full capabilities1654/direct1610,
renderer428/direct377 and runner431/direct509 retain existing publication/Qt owners. Full main and
independent info_panel626/direct605 retain detached13row rendering, preprocessed precedence and actual
narrow/DPI/font/scrollbar geometry. Full service131/direct238 retained committed rows and weak listeners;
7D removed only unused Study retention. Full sizing60/direct24 and button policy78/direct97 retain
two-surface exact-pixel sizing and global post-style/safe Cancel policy. Full modal406/error319/common463/
BaseDialog209 and direct448/26/891/138/147 retain shared confirmation, geometry and diagnostic privacy.
Completed slices and evidence are in the table below; no unresolved item is closed by their test counts.

**Completed-slice qualifications.** 6V was explicitly approved by user
「同意移除未使用的整段能力與專屬測試」 after rejection before mutation; separate6E/6G remain untouched.
Its14stage/stale typed fixtures preserve133367bytes, SHA256
e5e84c01e0b44eac4ab4c8fe183969cc32adbeef90550c3b1d2eb22fb6f64872; not real-model/scientific evidence.
6Y reviewer initially confused LocalRuntimeProcessOwner alias with child core.engine.LLMEngine, then
checked actual constructor/callers and withdrew the injection-only blocker. Real QObject/load-thread
fixtures retain owned async initialization; no external monkeypatch compatibility claim.
7C intermediate test caught a removed QWidget import needed by a live chart; restored, final50pass.
7G initially39pass/3fail under Windows Python offscreen with missing fonts: message height30/minimum15,
unchanged after event drain. Same42pass on actual Windows Qt before/after and offscreen with installed
fonts. 9A defaults that existing directory in direct pytest, matching existing CI without product font/
assertion changes. Earlier Windows-interpreter offscreen counts are unit/component, not native-window
acceptance. Local MkDocs remains unavailable; final same-head CI docs validation is still required.
8H initial oversized-byte pytest ID caused Windows temp-path setup errors; explicit short IDs repaired
fixture only. Initial fault run with that error is invalid; corrected SHA-bypass gives1failed/2passed.
Public fixture SHA triggered detect-secrets; exact known test checksum annotated, hooks then passed.

**Module8 setup audit.** Full independent setup881/PS87/rootCMD20/direct436 retains
cmd->PS1->Python->existing model lifecycle ownership. Integrity evidence improved8H; orchestration
order/env failure-stop and wrapper argument forwarding remain bounded test-quality candidates.
Full WSL launcher CMD42/PS1276/direct89 retains console-only child output, bounded log retention,
exit propagation and safe optional IBus; source guards are not native launch/wait evidence.
Independent initially proposed integrating infraacf7c56d; main challenged absent product paths. Exact
Git has no compact/manual_environment tracked files and common ancestor4770b049, not a dependency.
Recommendation withdrawn: retain separate infra history, do not import absent tooling to withdraw it.

**Shared async handoff audit.** Full independent router260/host1004/interaction624 and direct265/939/
343/616 retain request-correlated session terminal-once, continuation leases, cancellation, stale
navigation and synchronous failure delivery. Host, interaction session and Assistant pending coordinator
have distinct live responsibilities, not duplicate state owners. Main traced actual MainWindow callbacks.

**Bounded7H — use actual lazy-navigation callback contract.** Sole production host is constructed by
AgentManager with real MainWindow.switch_page(index,on_ready,on_failed). Remove signature inspection,
optional failure callback and no-ready legacy path; keep generation/one-shot/reentrant failure/exception
cleanup and current UI messages. First migrate existing test doubles to explicit on_ready/on_failed
contracts and real immediate/deferred callback delivery, preserving all outcome/cancel/stale assertions.
Characterize full router/host/outcome/interaction suites and actual lazy MainWindow callback tests
before source changes; after identicalcases, fault dropped failure callback must fail. One production
file expectednegativeLOC/noowner/public/UI change, two direct test files at most; independent actual
lifecycle review/Ruff before reversible commit. Keep pending publication/admission owners untouched.
Result: migrated characterization94passed0.93s before, identical94passed0.85s after; production
+13/-42/net-29, tests net+13, no cases removed. In-memory omitted failure callback fails actual
MainWindow terminal-count assertion (1failed0.26s); faulty source never written. Independent actual
caller/lifecycle review approved; Ruff/format six7H/7I files passed. Integration callers use actual
MainWindow, not the retired compatibility route. Existing closing-window False/no-callback behavior
still relies on host/controller abandon; this slice does not claim to improve that boundary.

**Bounded7I — remove unused stateless presentation residue.** Full main language111/direct188,
status401/ownedpresenter132/direct320 and refresh50/direct78 plus caller sweep identify unused
COMMAND_LABELS alias/import and command_labels helper; _display_progress ignores completed/total;
refresh_panel only forwards to _call_noarg with literal update_panel. Remove unused labels and ignored
arguments; inline only private noarg helper into existing refresh_panel, preserving exact logging,
guard release, status timing/copy and every active caller. Three production files expectednegativeLOC,
no new owner or visible behavior. Baseline product-language/refresh/ownedpresenter suites, same tests
after, main actualdiff/lint; no case removal. Separate commit from7H, continue audit rather than handoff.
Result:40passed2.55s baseline,40passed2.52s after; production+2/-20/net-18, no test or owner changes.
Main actualdiff/caller review and changed-file Ruff/format pass. Earlier7H/7I terminal outputs lost
during context recovery were not counted; the recovered runs above provide the evidence.

**Module6 initial full owner audit (not closure).** Independent full controller2949/attempt898/
execution342/confirmation314/pending443 and respective direct confirmation154/pending560/execution151/
closure91 plus controller4625–4805 retain one host-turn/Qt orchestration, deterministic admission,
one pending correlation owner and authoritative ApplicationService expected-generation execution.
Real tiny-FIF product-flow528 proves a current direct-input receipt makes one resample without model/
RAG and stale receipt makes none; it does not prove confirmation-card approval through real mutation.
No controller split merely for LOC: lifecycle/presentation delegation already exists, with no proven
competing owner. Remaining helpers/direct suites/model/RAG/UI/scripts still require full audit.

**Pending explicit decision6E — retire unused stage prose and unreachable history suppression.** Full pipeline190/
direct298 and assembler835 audit, plus independent exact caller search, find STAGE_CONFIG's seven
system_prompt values unused by runtime: assembler and evaluator consume only tools. Preserve that
live stage/tool ledger, public membership and all actual generated prompt bytes. Before deletion,
compare full prompts for all seven fixed-publication stages with unique sentinel prose substituted;
also record exact before/after prompt digests. Remove only prose builder/values, unused fallback
prose/docs and exclusive prose tests; retain tool-stage and label assertions. Separately remove
receipt_question whose sole caller always passes None, retaining selected/sanitized bounded history.
No model/prompt experiment, new owner or compatibility shell; approximately-120productionLOC across
two files, owner delta0. Full stage/config/context baseline and retained after, exact output comparison,
Ruff and independent actualdiff review are required. No UI behavior change or confirmation-policy edit.
Stop this slice at verified output-preserving deletion, then continue module6 lifecycle/tool/UI audit.
Baseline92passed0.89s after imports; all seven fixed-publication prompt bytes remain exactly equal
when old prose is replaced with a stage-unique sentinel. Edit review rejected removal as potentially
external-contract-sensitive and correctly caught malformed generated source (nested closing lines
were not removed). Restored both uncommitted source files to5afdb10d with apply_patch; tests unchanged,
clean Git confirmed. Do not retry the rejected retirement without the separately requested approval.
No malformed source was committed or handed off. Corrected construction and full parse/output checks
would be required if approved. This item is not completed and does not block unrelated module work.

**Module6 async responsibility audit.** Independent full worker1065, RAG thread214/process466 and
their six direct suites2193 retain actual load/generation ownership, correlation/cancel fencing,
restart-required state and production child/queue/monitor lifecycle. Thread lifecycle remains the
intentional injected retriever seam; production process lifecycle has real spawned-process tests.
No measured redundant wait found; preserve close grace, deadlines and monitor polling. Candidate6F:
four diagnostic-only properties on each RAG lifecycle have no product caller; process has_active_process
is live in native shutdown and must remain.

**Pending explicit decision6G — retire bypassed legacy direct-tool forwarding.** Full real adapters/definitions/registry
audit plus main package288/coordinator path/guard review proves all18 contracts are9 Application
commands and9 UI requests; READ_ONLY projection is empty and pinned by actual surface tests. Mapped
commands always execute through application_surface; a missing mapped result fails closed before
legacy tool.execute. Remove seven unused Real command adapters (two modules), their now-orphan
execute_real_application_tool/context-binding chain and coordinator's unreachable wrapping branch.
Instantiate existing schema definitions in real registration (concrete execute intentionally raises
if incorrectly called), preserving names/order/descriptions/schemas/confirmation and switch-panel
live UI request adapter. No empty subclasses, replacement owner or execution route. External direct
Python Real adapters cease to be supported under the approved unused-convenience policy; model/UI/
formal Command contracts do not change. Remove only exclusive high-mock forwarding tests and the
guard/fixtures that enforce those retired adapters; retain actual command ownership/negative mapped
fallback, generic tool contracts, UI request and real application workflow evidence. Approximately
-240productionLOC across4files, owner delta0; guard retirement is not a general gate relaxation.
Before edits run surface/coordinator/controller/debug/registry/architecture +real product-flow focused
baseline and snapshot exact18 schema/confirmation payloads. After deletion compare exact payloads,
same retained tests plus6B real confirmation cases, Ruff and independent main nonauthor actualdiff
review. Stop slice only at verified complete dead-chain removal, then continue remaining module audit.
Baseline602passed42.55s, three MNE deprecations; exact18 schema/description/confirmation SHA256
ec17216b9683a2ae275511a83cbbce037c62b9729c0b753e9cfc02dd879e74db. Worker owns only declared adapter/
coordinator and exclusive guard/test files; main owns after verification, plan and actualdiff review.
Safety review rejected the whole write before any change, classifying the legacy adapter removal/
base registration as potentially public-tool behavior. Worker verified all seven scoped paths clean.
Concrete external direct-Python API removal approval requested separately; no split/indirect retry.
The baseline/digest and independent whole-chain audit remain evidence, not permission or completion.

6N92d6a091 retires only unused tolerant parser/strict-result convenience. Before removal, malformed
field fixtures were fixed to include workflow_stage so they actually reach type validation; bare
evaluate rejection moved into the retained malformed matrix. The first strengthened run404pass/1fail
uncovered6P's Windows capture newline defect; after6P the complete baseline452passed, then retained
403passed21.31s after exactlytwo diagnostic cases were removed. One MNE warning persists.57exact
parse-result payloads before/after share SHA2562634fe1b345c4c129ee13a3f370c5ad01d5f08c654a02f207f9bf054623e7428.
Omitting the parameter-type guard fails null/string cases; actual strict grammar/negative guards unchanged.

**Module6 completed reads and remaining candidates (not module closure).** Full core model download
lifecycle665/direct659 and downloader1086/direct1178 retain shared lifecycle composition, bounded
consumption/inactivity, conservative process ownership/reap/retry and terminal-after-reap. Confirmed
unused shutdown(wait_ms) argument and cleanup-result message alias are retired by6O above.

Full context_encoding712/direct683 retain exact-type admission, cycle/node/UTF8 limits, path/secret/
role sanitation and final assembler re-encoding; no serialization or model-obedience gap established.
Only unused CHARS constant alias (same BYTES value) is a candidate. Full intent935/training_request75/
prompt_policy215 retains RAG suppression classification, not host action routing. path_label_for_intent,
BlockedExplanationIntent.target_command/ambiguous and test-only prompt payload helpers are candidates;
do not alter classifier semantics, actual prompt bytes or recovery taxonomy without separate review.

Main full conversation76/direct51, runtime_snapshot120/direct43, coordinator289/direct290,
activity102/direct137, turn456, orchestrator362/direct211, confidence91/direct96,
decision55/direct115 and tool_feedback574/direct445 distinguish real typed/correlated state from
test-only convenience projections. Candidate runtime to_dict/from_payload/fallback aliases and
conversation get/index/equality/repr need full caller/test migration before retirement. Preserve all
typed snapshots, validation_error, publication/activation/turn/cancellation and actual history limits.
ToolRecoveryFeedback builder appears test-only; assembler recovery state must be fully traced before
retiring that chain. Actual summary/compact transcript payloads and public diagnostic bounds remain.

Source counts denote exact read versions, not current LOC or automatically approved closure. Main
reconciled50 existing core/RAG inventory rows; module6 direct controller/UI suites and other modules
still have uncovered ranges. Completed6B/P show concrete workflow/capture protection, not model or
manual acceptance. Preimported Windows probes exposed cp950 logger output failures; module7 owns
the unresolved logger/launcher defect. Both registered WSLs, sole Windows environment and real model/
dataset caches remain untouched; no repeated compaction. Continue independent authorized work.

Independent full runtime_lifecycle1531/dispatcher532/AgentManager2163 retain one UI composition owner,
one correlated runtime admission owner and one queued transport/QThread owner; controller owns its
worker thread. MainWindow cleanup-fence/retry and actual script diagnostics are live. Full direct
dispatcher529/delivery547/service1956/threading749 and integration lifecycle1303 retain distinct
admission, delivery timeout/stale, real command-thread affinity and real topology close/recreate
protection. No arbitrary AgentManager split or duplicate-test deletion justified. Only unread
RuntimeSetupOutcome.message and one-test is_queued property are future candidates; preserve important
expected_activation_id/turn_in_flight witnesses until equivalent behavior evidence exists.

Completed2AD–2AG and8C–8E are indexed below and fully traceable in Git. For source-bound Windows
capture tests only, use process-local GIT_DIR/GIT_WORK_TREE pointing to the actual Windows paths:
Windows Git cannot follow the WSL-absolute worktree pointer. Keep the existing identity guard;
do not edit .git pointers, shared environments or substitute a synthetic source digest.

**Module2 independent closure review.** Reviewer did not approve module closure: two confirmed
visible defects below remain unresolved, not merely documentation or LOC concerns. The audited
interior has one command spine, separate backend mutation/publication and UI draft/presentation;
large file size alone did not establish a competing owner. Three stale tracker pending rows were
actually inspected (montage capability80 +owner170, empty loader test package marker needed for
relative imports, DrawRegion148 +owner75–250). Reconcile these; DrawRegion belongs to module3.
Main fully read wizard runtime145 (real Scan/Preview/Validate +Qt draft handoff, intentionally invalid
FIF not actual EEG Apply). Main1–440 +independent441–1788 fully cover real-fixture wizard acceptance:
retain all five-step, exact fresh review, no-publication, cancellation/drain/retry and BIDS recovery
contracts. Optional fixtures were not run here; final required-source gate still applies.
Continue authorized module3 while awaiting visible decisions; do not markmodule2closed or handoff.

**Module3 progress and remaining boundaries.** Completed3A–3O/3Q are indexed below; full
chronology, baselines, correction details and reversible changes remain in their Git commits.
The actual prepared command spine now has real ordinary preprocessing, boundary ratio/multirecord,
RAM-before-deepcopy, BIDS receipt/reimport and display-alias materialization protection. Data/render
publication, immutable buffer copies, cancellation and SET_MONTAGE confirmation stay live; generic
callback-only epoch tests do not define a second public snapshot contract.

Module3 is not closed. Remaining obligations:

- Complete caller/test/script inventory reconciliation and independent closure review, including
  current dataset UI adapters and real-data/native lifecycle entries; zero pending rows is not
  a substitute for evidence or resolution of confirmed findings.
- Decide the documented split-artifact chain below; actual Generator/provenance/audit and receipt/
  rollback state remain intact. No restoration of retired picker-expanded indices.
- Shared-runtime module7 owns the native split-dialog center investigation: Windows QPA windows
  compact752/760 cases both pass (horizontal range0); offscreen30/22px overflow was a font/platform
  artifact. Native full layout26pass/1fail shows client center31px below screen center. Inspect actual
  frame/client geometry before requesting visible change; do not weaken assertions.
- Existing UI RAM presentation test spies Raw.copy, which is not the live preprocessing allocation
  seam. Actual no-allocation evidence is3H's deepcopy witness and omitted-guard fault, not that spy.
- 4E removed suppressed persistence from real-GDF training and successful OOM retry; actual safe
  checkpoint/EvalRecord reads now verify artifacts under pytest tmp paths. This is not GUI restart/reopen.

Evidence qualifications: 3G removed307 collected obsolete cases, not the earlier mistaken309
(actual108 trial-list entries times2, not109). 3E/F terminal output lost during context recovery was
rerun:291combined/25plotter passed. 3I's alleged third enum argument was a reviewer misread, retracted
without product edits. 3O fixture default class maps were corrected before the passing baseline.
3Q proves control synchronization/coalescing/real signal/shutdown, not precise restart latency.
No measured end-user speed gain, whole-module approval or final Windows manual acceptance is claimed.

**Module3 unresolved artifact decision.** Independent full validator123/direct45/schema134/split_audit1085
and thesis protocol285–375 audit found artifact writers have no product producer, but the documented
CLI/schema remain a public thesis evidence entry. Validator only checks reported audit and cross-split
overlap, not the full claimed schema/provenance. User asked asynchronously to retire the unused entry
or retain-and-align its contract. No deletion, acceptance-strengthening or scientific claim until choice.
Unused build_training_ready_state test helper is separately removable; actual saved split/receipt seam
helpers retain live integration callers. Continue independent cleanup; module3 not closed.

**Module4 bounded read-only audit (not closure or implementation permission).** Independent full
model_catalog892/braindecode_catalog408/catalog_contract20/model_holder117/input_contract201/
option909/training_service687/model_base.__init__7/training.__init__23 =3264source lines, plus
catalog662/model_holder114/option450direct tests. Subsequent full resource/runtime audits below
supersede the initial partial reads; whole training closure remains pending. Retain static
catalog browsing (no provider import), stable identity/provider admission, numeric/device/class-weight
validation, conditional model context and single configure/build/preflight/receipt owner. Actual
preflight differs intentionally from advisory preview. Catalog command-name helper/input aliases and
optimizer repr duplicate have no consumers; TestOnlyOption and its export are used only by exclusive
tests, while actual manager accepts base TrainingOption. Declare separate baseline slices before
removing these. Subsequent independent full TrainingManager2413/direct1122/training_runtime587 audit
retains real config/start-stop/wait/CAS/lease/rollback ownership; saliency724–2115 is module5's obligation.
Study110–360/shutdown180–245/pipeline tests1–230/integration1–250 remain partial, not full audits.
4B closes the real-manager startup restore evidence gap with a completed actual Trainer, retirement,
snapshot restore and an omitted-restore fault. Keep useful Thread/Event/identity tests.

**Module4 resource admission audit.** Independent full resource_guard2341/resource_preflight563/
resource_receipt322/training_resource_receipt517 and3371direct/integration test lines reviewed.
Retain advisory draft preview versus current authoritative start admission and distinct receipts;
exact scope/TTL/capacity/consume-before-start and actual Agent/Application/Qt paths remain protected.
OS/GPU/MNE isolation is justified, not a deletion target. 4C measured and removed the duplicate GPU
estimate (two model constructions/data reads become one), preserving the cancellation observation
between RAM and GPU queries. No draft-preview reuse or persistent cache was introduced.

**Documentation evidence limitation.** Consolidated plan passed audit_agent_guidance check (ok=true,
no errors). Strict MkDocs build could not start in the existing Windows interpreter: No module named
mkdocs. No environment/dependency installed. Final exact-source docs CI remains required; current
source-only consolidation is not a successful docs-site build or final handoff.

**Module4 main presentation audit (not closure).** Full MetricTab332/history497/modeldialog702/
optimizerdialog212/devicedialog94, metric tests155/history412 read. 4G retired test-only update_plot
and the history forwarder after protecting the actual set_series/reset/repopulate path.
Model dialog async provider, stable recovery identity and pretrained-weight handoff remain live;
Direct modelselection429, training setting1242/direct1321 and full panel/sidebar source/direct tests
are reviewed. 4H removed inert settings remnants, retaining actual saved-split recommendation evidence.
Model settings/identity and cross-module main-window obligations remain pending, not whole UI closure.

**Pending visible-state decision — zero validation metrics.** Actual offscreen TrainingHistoryTable
fed validationloss0.0/accuracy0.0 renders both cells N/A. Zero is a valid result, distinct from missing.
User asynchronously asked to authorize0.0000/0.00% with N/A only for absent metrics; no reply yet.
No product edit made. Continue internal cleanup; do not silently treat this visible issue as fixed.

**Pending visible-state decision — device recommendation adapter.** Independent recommendation owner604/
direct314 audit retained metadata-only formula/cache/provenance and all scope keys. Unused
cached_for_context is a separate deletion candidate. Real Sidebar device recommendation passes
prospective_device, while concrete _StudyApplicationUiRuntime/TrainingQueryPort omit it although
backend supports it. Real application_ui_runtime over Study reproduced the TypeError in Windows;
no signature mock or product file change. User asynchronously asked to authorize the visible device
workflow repair; no reply yet. ApplicationUiRuntime itself is the Protocol, not the concrete adapter.

Completed4I–4N and5A–5D/5G are indexed below; actual source, review and focused evidence
remain traceable in their small commits. Remaining decisions/audit gaps follow.




**Module5 entry audit / next declaration.** Independent full evaluator477/EvalRecord1344 and direct
evaluator173/eval352/metrics155/context532/integrity608/safe-store889 reviewed. Retain real torch
metrics/final evaluation/recompute and safe JSON+NPZ, identity/context/integrity/sealed publication;
real tampered artifact and MNE montage tests are necessary. Coupled renderer/visualizer/TrainingPlan
saliency paths were only sampled, so whole module5 remains open. Concrete candidates are unused
export_csv, standalone export_saliency and five saliency getter conveniences; each requires its
own plan/baseline and exact exclusive test disposition before deletion. Existing canonical EvalRecord
export/load and dynamic figures stay. No unknown-script compatibility or new artifact format.



**Module4 additional completed audits.** Independent full training_history417/direct159 retained as
sole detached JSON-safe projection. Full first-party model/requirements/holder plus direct tests
retain supported catalog/identity/minimum-input/real forward+optimizer boundaries. Full
training_contract9/reset30/submission65/synchronous_lifecycle365/publication_lifecycle582 and direct
reset60/contract32/synchronous574/publication597 retain exact reset ordering, typed host submission,
unlocked waits/locked final verification, retry/dedupe/supersession/close. Secure output paths518 and
safe-store889 were already fully reviewed; don't repeat reads as new coverage. Preview coordinator,
remaining training integration/script entries and final inventory still require completion.

**Module5 render owner audit (not closure).** Independent full evaluation_render1369/work139,
direct1267/205 and UI publication_refresh935 retain immutable DTO copies, exact selected identity
fences and shared owned-work claim/cancel/retry. Copies have a concrete isolation purpose; no new
cache or measured redundant allocation established. UI timer/worker tests use mock ports and do not
prove full native GUI acceptance. Two separate future candidates: unused _final_unavailable_error,
and legacy build_evaluation_model_summary string forward (migrate three test/helper calls to typed
result.text before deleting). Actual typed model-summary preparation/result stays. Full Evaluation/
Visualization UI audit is ongoing; sampled main-window/renderer paths remain incomplete.




**Pending explicit import-risk decision5E — provenance compatibility re-exports.** Independent full provenance925/
integrity872 plus exact-hash270/ownership138/integrity81/contextconsumer190 retain bounded exact
logical-C hashes, immutable sealing, schema/producer validation and surrounding cancellation fences.
No redundant SHA claim. Eight eval.py noqa-F401 aliases have no real caller; only architecture
compatibility tests and a guard requirement demand them. Remove those eight imports, exclusive
re-export identity test and the guard's must-re-export block only. Preserve actual three context/
producer class imports, domain owner's required definitions, forbidden record-local definitions and
mandatory direct-owner production imports. Rename misleading compatibility fixture/local constant
to record terminology and model minimal actual three imports in its fixture. Main reviewed exact
guard body; worker may own eval.py/tests architecture helper/directtest only after baseline.
Baseline ownership/exact-hash and actual record context before, same retained after with all negative
ownership tests intact, Ruff and independent actualdiff review. No runtime schema/cancellation/
publication behavior change; production-8, zero new owner/compatibility shell or new source guard.
Baseline39passed8.09s (ownership/exact-hash/current context). Edit safety review rejected both initial
attempt and one retry supplying the user's approved no-unknown-external-convenience policy; no files
changed. Gate requires a fresh explicit decision after disclosure that external imports from eval.py
would fail. User asked asynchronously; no reply yet. Preserve aliases and matching guard until then.
Do not bypass the gate with a different editing tool. Continue independent authorized module work.


**Pending explicit lifecycle-risk decision5F — dormant automatic saliency scheduler.** Main and independent caller audit
prove PostTrainingSaliencyAutomation is instantiated but never armed by production; its only active
arm calls are exclusive compatibility tests. Remove the220line class, exclusive imports/service
construction/callback/cancel/wait wiring and shutdown cancellation port; remove the dev native-stress
script's dormant idle probe, retaining actual job/terminal-delivery waits. Owner delta is one legacy
scheduler removed, zero new owner; no replacement shell. Preserve PostCommandSaliencyNotificationBoundary,
explicit SaliencyCommand, PostTrainingSaliencyTarget and scoped target context, runtime cancellation,
terminal publication/ack/retry/discard and timeout budgeting. Existing architecture already requires
explicit Compute Saliency as sole product admission; no UI/public command/schema change is intended.
First complete affected test reads and passing baseline. Remove only13 exclusive scheduler unit cases,
armed-only observer case, submission-only timeout case and automatic-thread-start failure integration
case. Migrate shared shutdown failure test to a live runtime cancellation failure and shared wait
assertions to remaining real runtime/delivery owners; preserve explicit-command startup/cancel/stale
and normal observer lifetime coverage. Approximate production-260, three production files plus one
script; main final diff/LOC and independent non-author lifecycle review before commit. Focused same
retained notification/observer/service/background/publication integration plus script evidence, Ruff
and source call-site sweep are required. No automatic closure of module5 or handoff claim.

5F original baseline448passed34.01s; migrated retained429passed33.60s against unchanged production.
The19 removed collected cases are15 scheduler-only parametrizations, one armed observer, one
submission-only wait and two automatic-thread failure cases. Live runtime cancellation failure now
proved close still discards delivery. Source deletion was rejected by edit safety review before
mutation: explicit approval is required after disclosing that external/manual service.post_training_saliency.arm
calls would fail. User asked asynchronously; no reply. Main restored all five worker-owned test/script
changes to HEAD so retained source keeps its protection. No source deletion or dummy replacement;
do not bypass the gate. Resume the tested migration only after approval. The now-exclusive runtime
submission-failure forwarding chain and manager helper are additional retirement dependencies for that
same decision, not grounds to silently delete the underlying live target/publication contracts.


**Completed bounded5H — no-op 3D scene internals.** Independent full base1548/head269/3Dview1749 and
direct baseasync896/cache391/time264/worker1273 audit plus main fullhead269 confirms definition-only
CHECKBOX_KWARGS/CHECKBOX_TEXT_KWARGS, empty _setup_scene/sole constructor call and unread self.save/
param[save]. Remove only those internals and the fixture's unused save key; sample_index routing,
actors/orientation/camera/control behavior stay. UI-internal behavior-preserving changes are explicitly
authorized; no visible change, owner addition or native lifecycle rewrite. Worker owns only head.py
and time-slider test after fullthree3D test baseline; main actualdiff/lint/after and independent
nonauthor review. Roughly-25productionLOC, oneUIfile; no screenshot equivalence/native3D acceptance
claim from controlled PyVista tests. Base/3D worker, cache, weakrefs and verified teardown are retained.
Same43passed6.74s before/6.50s after; main nonauthor actualdiff approved and Ruffpassed. Actual one
production file+1/-21/net-20; test+1/-1. No sample-index/control behavior or native ownership changed.

**Completed bounded5I — actual Saliency estimator-to-receipt evidence.** Full resource817/direct244 and
Analysis618/direct1409 audits found receipt tests patch preflight; integration confirmation402 covers
import/training only. Add one case to existing analysis test module: allocated tiny NumPy epoch data,
real torch Linear parameters and actual estimator produce a RAM warning (only OS telemetry isolated),
then exact challenge/confirmed consume/readback/replay. Reuse actual TrainingManager and
VisualizationStateService receiver, asserting no initial mutation, one confirmed notification and no
replay mutation. Prove each attempt rechecks current RAM before receipt authorization. The manager has
no trainer to avoid attribution: this is Analysis estimator/receipt/configuration wiring, not a whole
ApplicationService/GUI/training-compute journey. No production change or additional receipt owner.
Worker owns only test_analysis_service.py after existing analysis/resource baseline; fullsameafter,
bounded in-memory admission-bypass fault, Ruff and main nonauthor actualdiff review before commit.
Original41passed0.48s; new42passed2.70s. Admission-bypass in-memory fault fails at the initial challenge
(DIDNOTRAISE,1fail2.15s), no faulty source persisted. Main made the allocated fixture type explicit,
matched Linear input to32flattened features and asserted264real parameter bytes; final combined42+5J38
passed80in6.00s. Ruffpassed. Main nonauthor review approves real receiver/probe/readback evidence, not
a training job. Test-only+116/-3/net+113; existing receipt isolation tests remain useful and retained.

**Completed bounded5J — reuse owned normalized arrays in direct render query.** Main full SaliencyRenderPublisher1420/
work176 and direct733/317 found single-run normalize=True allocates normalized arrays, then copies
them again in DTO construction. An actual Windows publisher probe measured two extra copies/128bytes
for128bytes of output; raw also copies128bytes, which is required to detach source. Current GUI variant
preparation already uses the owned-array path, so this is direct query cleanup, not measured GUI speedup.
Reuse existing adopt_saliency_store only for newly normalized single-run arrays; raw source remains
copied, cancellation checkpoints/read-only flags/identity fences unchanged. No new cache/owner/buffer
type. Add normal/zero and raw/normalized source-isolation/dtype/value tests, establish passing baseline,
then one-line production reuse +stable copy regression/identical focused render/work/normalization
tests. Repeat probe, independent actualdiff review and Ruff before commit. DTO read-only arrays remain
trusted detached renderer data, distinct from immutable bytes-backed authoritative EvalRecord stores.
Do not claim measured RSS/latency gains or strengthen immutability through unnecessary extra copies.
Four new normal/zero/raw/normalized characterization cases and full render/work/normalization38passed
5.65s before reuse. Sole production+1 passes already-reviewed adopt flag only after fresh normalization;
independent actualdiff review approved. Same38after passed within80combined6.00s; repeated exact
probe shows normalized extra copies2/128bytes→0/0, output stays128bytes; raw remains2/128bytes.
Changed-file Ruffpassed. Production+1/testsnet+50, no owner or visible behavior change.

**Completed bounded5K — retire unused coverage forwarding shell.** Full main482source/294tests and independent
caller/guard audit find three compatibility functions plus _DEFAULT_PROJECTOR used only by one
direct test. Migrate that case to the actual SaliencyCoverageProjector methods, keeping all label/
method/complete assertions; passing baseline before deleting shell and its three exports. Keep
project_method/project_run/label projection and all coverage/context/integrity policy unchanged.
Architecture guard must require only the actual projector definition while still forbidding retired
names in UI imports/calls and state-service policy: retain COMPATIBILITY_NAMES and union it with
PUBLIC_NAMES for negative import detection. Do not weaken tests or the specialized visualization
guard. One production file roughly-40LOC, zero owner/public Command/query/EEG/visible UI change;
three scoped files only (coverage owner/directtest/architecture helper). Full direct coverage +actual
state architecture +negative architecture tests before/after, Ruff and main nonauthor review.
5E provenance aliases and5F scheduler remain unchanged pending explicit decisions.
Same258passed36.69s before/36.50s after, including full architecture negative tests and actual
state boundaries. Ruffpassed; main nonauthor actualdiff approved. Production-39, zero owner change;
all label/method/complete assertions retained. Retired-name negative UI import/call guards stay active.

**Module5 full source/test audit additions.** Backend visualizers2332source/direct2526 retain exact
class identity, scientific color/time/geometry semantics, actual STFT and cache single-flight/clear/
failure fanout/LRU; native mesh IO isolation is justified. All4602visualization redesign tests read
contiguously to EOF: typed receipt/terminal/request identity and state behavior remain valuable.
TrainingPlan prepared publication1–150/953–1348 +fullEvaluator477 +directtests1516–2399 retain atomic
multi-record replacement, captured identity/stale/cancel fences, selected-method batching and final CPU
release. Captum inner calls remain cooperatively cancellable only between protected boundaries;
no stronger interruption promise or measured end-user speed improvement. Direct tests of successful
temporary-model CPU cleanup need tracing before any cleanup-semantics change.

Independent full manager724–2413/directsaliencylifecycle1882 and actual-method accumulation275
retain explicit command target admission, terminal generation/notification/retry, unlocked callbacks,
stale/CAS fences, atomic recompute and actual safe reload. Full publication integration2773 (not the
earlier approximate2430) includes real MNE/EEGNet multi-fold commands, actual Qt close, render barriers,
live-model/mask/metadata mutation rejection and recovered publication. Narrow compute/thread/queue
fault seams are justified, not mock-only duplicates. Its one manually armed dormant scheduler case
remains protected pending5F; similarly named explicit-command scheduler/target tests must stay.
Seven compact read-side/UI/label/FIF tests1277 were fully source-reviewed, not executed native GUI
acceptance. Capture walkthrough/script test audit and final inventory review remain unfinished.

**Module4 preview coordinator full audit.** Main read439source/341directtests: retain single-flight
same-request sharing, latest queued draft replacement, exact generation/receipt refinement, shared
OwnedWork cancellation, non-daemon worker admission/failure/close/retry and nonblocking diagnostics.
Real threads/Events/registry assertions give direct evidence; model estimate callback is a justified
external seam. Retained cache has one bounded completed result, not a second policy owner. No measured
unnecessary waiting; waits are explicit ticket/lifecycle boundaries. The worker_thread property is
used by actual UI tests to check non-daemon identity and is retained. A possible dead None branch
requires control-flow disposition before closure; do not infer deletion from a text-only search.

Completed2X–2AC are indexed below; their full scope/evidence remains in Git history.
2AC found an existing shared-environment source hazard: Windows .pth adds the original checkout
to sys.path, making scripts.dev a two-checkout namespace. For subsequent native validation, remove
only that exact oldroot from the process search path before imports, then call unchanged
assert_active_checkout_import(Path.cwd()). Do not edit the environment/.pth or weaken the gate.
The first2AC run had two expected root failures plus this separate origin failure; isolated rerun
had only two expected failures, then allsix passed after the resolver fix. No real fixture ran.


- Main fully read load_labels_step462 and wizard preview4850; independent reviewer fully read
  label_placement_step2179 and coupled caller/test ranges. Independent workers fully read all7,359
  original direct preview test lines in two contiguous halves; real Qt controls/signals/serialized
  choices are useful UI evidence, not actual backend workflow evidence.
  ReviewImportStep1556 and InternalEventStep879 full independent audits are complete. No whole-family
  closure yet; confirmed remaining candidates and UI decision items still need disposition.
- Independent coordinator audit fully read recipe reload431/payload126/ActionCoordinator2400 and
  all4660 lines of direct async-flow tests across explicit non-overlapping ranges. Retain
  generation-bound apply, modal cleanup, live Cancel, exact
  warning-receipt retry, real QThread heartbeat/cleanup and shared operation presenter ownership.
- Independent integration audit completed external-label preview71, semantic render539/safety365,
  BIDS epoch duration414 and shared support55. Retain real file/recipe/atomicity evidence; render tests
  synthesize training records and do not prove actual training. Several standalone ApplicationService
  fixtures lack finally-close; no global autouse service close exists. This is an advisory hygiene
  candidate, not a demonstrated leak or permission to rewrite these fixtures during 2X.
- Remaining UI family source fullreads: subject chooser241/loading302/normalizer28, smart parser1035/
  channel chooser183/source chooser298, event editor644; direct tests237/63/407/109/125/431 retained.
  Actual BIDS editor157 integration proves real file -> Qt choices -> backend recheck -> confirmed Apply.
  Actions678/panel991/sidebar860 source read; import/review/recipe facets reviewed, other domain tests
  remain partial: panel450–620, sidebar1–75/514–644/945–963, minimal51. Preserve live public façade.
- Main fully read receipt authority153 (distinct from deleted label receipt), real receipt integration99,
  event-value workflow290, metadata111, optional BIDS montage130/public480/multisubject416/
  responsiveness165, Assistant exact-review cancellation130. Retain one-shot/semantic/atomic paths;
  Assistant cancellation seeds pending handoff directly and does not close actual model-attempt gap.
  External-label real Qt/GDF/MAT workflow934 is fully reviewed, including async remove/re-add andrecipe.
- Coverage routing found module2 consumers hidden by initial keyword mapping: Data Import capture/
  replay/report scripts and their tests and wizard harness617 still require body audits; module8
  infrastructure ownership does not make them out ofscope. Main fully read shared DataManager244/
  direct206: retain copy-on-preprocess, channel-undo deep backup, force-clean guards and invalidation;
  MagicMock dataset fixtures do not prove actual training transitions (module3/4 remain open).
- Independent full audits: wizard harness617 uses real Study/Qt/application runtime, visible modal
  controls and terminal fail/stop paths; retain. Format matrix2953/direct639/UI integration248
  retain real commands, fixed requirements, strict failure/artifact exit and honest generated-vs-public
  claim boundaries. Dataset matrix781/direct453 retains fixed denominator/diversity and lifecycle
  checks as a renderer, not a new command owner. Teacher1259/unit430/integration197 retains actual
  command/epoch/digest contracts, sidecar nonpromotion and explicit best-effort raw/service cleanup.
  Replay1329/direct572 retains live command/widget capture, geometry/artifact/identity guards and
  explicit noncanonical claim boundary. Its persistent-visible close timeout lacks a direct test;
  declare that focused evidence improvement separately before authoring. Script cleanup
  findings do not authorize shrinking existing evidence inventory or relaxing fail-closed outcomes.
- Confirmed backend candidates: two definition-only tabular multiplier aliases; CommandService
  pure pending-receipt/scope forwarders and raw-presence double-copy convenience. The preflight
  path-set method has two actual consumers and transforms/validates diagnostics; retain it rather
  than treating it as a one-call alias. Declare exact coherent scope/baseline before further edits.
  Actual memory multipliers/maps, preflight policy, receipts and candidate scope must remain.
- Coordinator payload wrappers and wizard source/state copies remain candidates, not approved changes.
  Trace dynamic bindings and real widget lifecycle before removal. Do not move large classes merely
  to improve file-size numbers or introduce another UI/backend owner.

**Pending visible-state decision — interval onset preview.** Placement source972/direct429 and
downstream candidate/event-code/interval tests were read. A real TSV with two labels, one nonnumeric
onset and two numeric durations currently overwrites time-field needs_review with ready; atomic apply
then rejects the nonnumeric onset without mutation. The matching-count interval and event-code
ready/repeated/conflict cases exist, but partial-onset preview evidence is missing. A visible-state
correction needs user approval, requested asynchronously; no reply yet. Do not silently change
readiness/UI behavior. Continue all independent authorized cleanup while awaiting that decision.

**Pending visible-UI decision — floating remap confirmation.** Main traced parentless confirmation_label
construction and its setVisible call. A read-only in-memory pytest profile of the actual recipe remap
widget test passed and observed parentWidget=None, isWindow=True, isVisible=True with replacement-file
confirmation text. This confirms an extra top-level Qt label, not Windows window-manager acceptance.
User approval requested asynchronously to contain the text in the wizard; no source/UI change yet.
Keep this separate from dead-helper removal and continue independent authorized cleanup.

**Recently closed source/test audits — retain reasons.**

- Candidate1348/choice-schema303, candidate tests2518/56 cases and event-value candidate342:
  retain source/scope/remap/identity/class choices and external reader isolation. 2P removed only
  the confirmed one-use missing-files forwarder; shared actual missing-path policy remains.
- Scan1493/direct1245/38 cases: retain explicit-vs-recursive discovery, admitted payload materialization,
  shared budget, identity/link guards and indexed BIDS traversal. No confirmed deletion.
- Main ApplyService1479/CommandService2309, apply preparation230/discovery142/public projection124
  and projection tests253; independent service tests2464/BIDS1375/event-value apply447/timestamp279:
  retain detached staging/rollback, one-shot command receipts, per-run EEG semantics, bounded/public
  projections and Windows freshness. DatasetState1877/direct1055 retains revision/generation,
  one-shot staging/checkpoints and legacy mutation invalidation; domain UI closure remains separate.
- EEGLAB preflight962/label estimator360/direct EEGLAB522 are fully read. Resource-guard tests were
  read only at190–275/480–535/570–815/840–890 of1632. Preserve pre-MNE bounded MAT parsing, compressed
  budgets, exact FDT shape/size/path checks and shared multi-file MAT budget. Real savemat/read-counter,
  parser-denial and pandas/tracemalloc tests are useful, not final source-diverse certification.
- Montage preparation1282/coordinator460/lifecycle355, their direct tests809/630 and fixture130:
  preserve geometry/resource admission, generation/manual precedence and publication as distinct
  responsibilities. 2Q adds failed-refresh retry protection at the coordinator level, not an extra
  service-level integrated claim.
- Module 8 full reads include run_tests961/direct1174, attestation195/direct185, required-wrapper260/
  direct409, Windows bootstrap881/direct436, run.py370 and startup test bodies, WSL launcher276/cmd42,
  setup ps1/cmd, ci_change_scope109 and artifact verifier216. Whole CI925, all Poe/dependency entries,
  other scripts and handoff/dashboard adapters remain open. Actual CI aggregation already installs
  only lock-derived coverage, not a duplicate product environment; retain non-equivalent gates.
  No measured unnecessary startup/CI wait was established.

**Recent evidence limitations.** 2T's unedited native baseline had two geometry assertion failures:
the intended150px minimum exceeded natural143px layout hint, legitimately adding footer surplus.
Tests now allow only that derived surplus plus existing rounding and explicitly require minimum150;
no product geometry change. 2U's first fixture migration failed two obsolete session.load diagnostic
assertions although generic forbidden-import checks already rejected the unsafe UI. Automated safety
review rejected deleting the specific gate, so all existing checks were retained and extended to
actual direct/symbol/module-alias factories; assertions were not removed. 2W's first sandboxed Windows
launch failed before collection; required escalated interop succeeded without restarting/installing.
Native Qt unit runs are offscreen, not Windows window-manager/DPI/manual acceptance.

After closing each scoped edit/review, continue the unfinished module audit immediately. Modules3–9
and same-source final integration gates remain required. A commit, context recovery or pending CI
is not an endpoint.

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
| 2N / `2a61245b` | Unused metadata readers/budget alias; production -30 | Native27 original/migrated/after; admitted cache/budget behavior retained |
| 2O / `f485c36f` | Reuse ordered path projection and target routing; +8/-23/net -15 | Same80 original/strengthened/after; duplicates/blanks/None recipe paths preserve exact output |
| 2P / `e78f9a78` | Remove missing-path forwarder and marker no-op branch; +1/-22/net -21 | 59 -> real FIF annotation/stim characterization61 before/after; upstream MNE warning |
| 2Q / `5155f913` | Coordinator failed-refresh -> pending -> retry -> no duplicate publication; tests only | Native18; missing-retention in-memory fault detected; not service-level dispatch evidence |
| 2R / `aaf64d41` | Actual duration evidence and mapped label owner replace test/single-call forwards; +8/-35/net -27 | Same101 original/migrated/after; per-run/time/atomic behavior intact |
| 2S / `5b97abfd` | Unread filename dependency across three constructors; production -8 | Native126 plus selected actual ApplicationService30 before/after; live snapshot filename retained |
| 2T baseline / `b67d24f8` | Correct two geometry bounds for intended minimum-height surplus; tests only | Original44 pass/2 fail -> strengthened46 pass; explicit150px floor, no layout edit |
| 2T / `92a7cc38` | Unused montage smart_match and three exclusive tests; +2/-50/net -48 | Retained native43; safe/reviewed mapping and all current lifecycle cases unchanged |
| 2U / `20c139b3` | Dead label admission/receipt/specs chain; production -258 | Native289 original ->290 migrated ->289 after one obsolete case; seven actual receipt/SHA neighbors; all safety gates retained |
| 2V / `1e28068c` | Discarded full label payload hash/state; +4/-119/net -115 | Real1MiB admission stream1,048,576 ->0 bytes; actual524,288 labels unchanged;64 safety cases before/65 after; identity probes/early descriptor/final SHA intact |
| 2W / `bb5a27e0` | Unused wizard legacy review fallbacks/target/clear_skip; production -172 | Native28 ->27; full target/empty metadata assertions preserved, main focused1; main nonauthor review; no separately strengthened pre-delete run |
| 2X / `bf1a14e6` | Wait for real cancelled-review terminal delivery; tests only | Same native5 before/after, Ruff; in-memory late delivery detected1!=0; finally releases on assertion failure |
| 2Y / `26b8c054` | Remove16 unused wizard-private helpers acrossfourfiles; production -224 | Native130 ->128, exactlytwoexclusivecases removed; real sidecar field retained; independentreview and Ruff |
| 2Z / `4e317328` | Removeignored tree-sizing inputs and equivalent row-count aliases; +4/-21/net-17 | Native10 geometry/rescan cases, Ruff; independent arithmetic/caller review; no visible geometry change |
| 2AA / `11125166` | Merge duplicate rescan case while preserving all assertions; tests net-34 | Strengthened3before ->retained2after, Ruff; main nonauthorreview |
| 2AB / `fca0ac35` | Deleteunused fuzzy montage chain/module; production -102 | Native59 ->52, nine new no-mock actualnormalizer cases; sevenexclusiveold removed; same18upstreamwarnings; independentreview/Ruff |
| 2AC / `36b2de7e` | TwoOpenNeuro integration roots reuse configured storage; tests only | Isolated red2fail/4pass ->6pass; runpyactualconsumer definitions, no downloads; independentreview/Ruff |
| 2AD / `27c525c6` | Remove four Coordinator payload forwarders; +20/-39/net-19 | Native80 before/after; migrated assertions6focused before deletion; independentreview/Ruff |
| 2AE / `20b05f75` | Remove unused loader lookup/commented rejection; production -17 | Strengthened23 before/after, no-publication fault detected; real Apply neighbors, independentreview/Ruff |
| 2AF / `4df0c36e` | Remove preflight forwards/list copy and unused multiplier aliases; +8/-40/net-32 | Same20 native before/after; receipt/scope/BIDS fallback review and Ruff; policies unchanged |
| 8C / `e8ed6d4b` | Retire duplicate placement capture entrypoint; script +1/-76/net-75 | Canonicalcapture32 before/after, mainnonauthorreview/Ruff; actual factories unchanged |
| 2AG / `528322e7` | Remove empty wizard footer instance and exclusion forward; +1/-9/net-8 | Same13 native rendering/removal/geometry before/after, independentreview/Ruff |
| 8D / `aeb53bf4` | Real Qt persistent-visible timeout evidence; tests+36 | Originalsuccess1 ->success/timeout2pass; in-memory wrong-success fault detected; mainnonauthorreview/Ruff |
| 8E / `b7ed74ab` | Remove unused review-state capture fixture; script-63 | Same32 native before/after, mainnonauthorreview/Ruff; canonical factories/inventory unchanged |
| 3B / `7fb9fcc9` | Retire unused MAT Export/module/export tests; production-57/tests-98 | Native78 ->73, exactlyfive obsoletecases; same17upstreamwarnings; independentreview/Ruff |
| 3A / `07881c8d` | Two unused DrawRegion APIs removed; production-23/testsnet-16 | Original22 ->stronger23 ->retained18; wrongoverlapfaultdetected; actualcanvas/strategycases and mainnonauthorreview/Ruff |
| 3C / `c628be38` | Remove unreachable ordinary preprocess handler branches/helpers; production-76/testsnet+37 | Real ordinary/admission characterization before deletion, retained42pass; cancellation/stale/rollback/epoch safety retained, independentreview/Ruff |
| 3D / `036cb1cc` | Remove unused split to_thread no-op; production-3/tests+87 | Native direct16 before/after; both omitted-guard faults detected; independentreview/Ruff; distinct offscreen font/native-center limitations remain tracked |
| 3E / `63f691b2` | Real epoch boundary workflow replaces two summary mocks; testsnet+43 | Exact1%, above1%, multirecord counts/atomicity; threshold fault detected; combined3E/3G291pass, independentreview/Ruff |
| 3F / `f234a5ea` | Synchronous plotter/fallback/alias cleanup; productionnet-29/testsnet-1 | Real curves/current+overlay/time+PSD; direct25pass and native8cycle stress; wrong-frequency fault, independentreview/Ruff |
| 3G / `d86efa15` | Retire unused Epochs picker chain; production-538 | 307 obsolete collected cases removed (corrected actual parametrization count), actual manual Generator retained; combined291pass, independentreview/Ruff |
| 3H / `3e556a98` | Actual RAM-before-deepcopy test replaces exclusive fake; testsnet-7 | Direct/adjacent37 retained; strengthened actual-copy node1pass and omitted-check fault caught; independentreview/Ruff |
| 3I / `db4670d7` | Normalize/validate split command once; productionnet-10/testsnet+30 | Real defaultNone vs explicitempty replacement; retained47pass; exact public message, independentreview/Ruff |
| 3J / `e77e389c` | Dialogs reuse inherited geometry owner; dead reference aliases removed; productionnet-22 | Same24 Windows QPA windows cases before/after, no visible change; main nonauthorreview/Ruff |
| 3K / `0b7d77ef` | Retire test-only dataset metadata conveniences; production-49/testsnet-11 | Missing mask assertion restored;113before112retained, exactlyone duplicate removed; independentreview/Ruff |
| 3L / `81e0dfb6` | Real BIDS receipt scope and same/changed-context reimport; testsnet+69 |45before40retained; four stale-acceptance faults caught; main nonauthorreview/Ruff |
| 3M / `a7b1ad2c` | Export supported lazy dialog targets only; productionnet-6/tests+13 | Missing-class red,12green; independentreview/Ruff |
| 3N / `96366558` | Remove ignored preprocess error-prefix plumbing; production-6/tests-2 | Same28before/after; main nonauthorreview/Ruff |
| 3O / `9ddb204c` | Actual alias-to-epoch labels/counts and unknown list/dict atomic rejection; testsnet+87 | Real3new plusneighbors40pass before handler retirement; main nonauthorreview/Ruff |
| 3Q / `e8cf3260` | Real Qt controls/signals replace timer-rewired mocks; testsnet-19 | Old2→combined4→retained2+15neighbors17; omitted-signal faults detected; independentreview/Ruff |
| 3P / `7e6007c1` | Retire synchronous epoch duplicate and callback chain; productionnet-122/testsnet-502 |17obsolete nodes retired after real migration; integrated3P/R89pass; main nonauthorreview/Ruff |
| 3R / `8ff29e95` | Six unused state-service apply conveniences/protocol entries removed; productionnet-93 | Same10direct before/migrated,89integrated after; independentreview/Ruff |
| 8F / `161b5a33` | Retire orphan synthetic epoch capture/test/optional scan path; script-726,totalnet-825 |7before6retained, oneexclusivecase removed; main nonauthorreview/Ruff |
| 3S / `731e28d5` | Three duplicate adapter tests and unused helpers retired; testsnet-123 |43before40retained; real metadata/row identity/receipt/wiring preserved; independentreview/Ruff |

| 4A / `31ca6ed1` | Unused TestOnlyOption/export retirement; production-195/tests-99 |162before140retained;22exclusive obsolete cases; main nonauthorreview/Ruff |
| 3U / `b1c0b902` | Direct shared preprocess query, no panel forward; productionnet-14/testsnet+10 |27before/migrated/recoveredafter; actual panel context/minimum rate retained; independentreview/Ruff |
| 4B / `210ea1f3` | Real completed Trainer retirement/startup restore; tests+58 |237combined; in-memory omitted restore fails; exact record identities/full snapshot; main nonauthorreview |
| 4C / `e19967d6` | Single estimate per preflight; productionnet-24/testsnet+93 |131baseline/133final; measured GPU models/data reads2→1; cancellation before GPU retained after fault; independentreview/Ruff |
| 4D / `12e389be` | Unused model metadata/optimizer conveniences; production-25 |Same125before/after; canonical schemas/dynamic catalog unchanged; independentreview/Ruff |
| 4E / `45aae45d` | Actual training persistence, shared safe-load assertion; testsnet-2 |5before/after; migrated A01T1pass; omitted-save fault fails; A01T100784bytes/retry100750bytes; no GUI restart claim |
| 4F / `893e4ad0` | Unused Trainer name lookup; production-22/tests-21 |Retained Trainer/real rollback/optimizer stop47pass;4obsolete cases; independentreview/Ruff |
| 4G / `eac27aad` | Live bulk metric/history rendering only; productionnet-26/testsnet-46 |35baseline→42final incl7retained presentation neighbors;2obsolete append cases retired after historical9pass; independentreview/Ruff |
| 4H / `05da6d88` | Inert settings fields/note/helper removed; productionnet-22/tests-1 |Same45before/after incl real saved-split recommendation; main nonauthorreview/Ruff; no visible change |
| 4I / `77fc31c2` | Orphan record wrappers/exclusive suite removed; production-82/tests-59 |70before65retained;5obsolete cases; negative architecture boundary retained; independentreview |
| 4J / `4e9deb3a` | Unused TrainRecord summary/append API; production-57/tests-72 |67migrated before;62retained+4K25=87after; actual update gapfill and omitted-gap fault retained |
| 4K / `e90be669` | Unused recommendation cache accessor; production-13 |Same25before/after within87; cache/invalidation/policy unchanged; independentreview |
| 4L / `2ab22913` | Unused ModelHolder description; production-18/tests-2 |Same232 real model/catalog construction+gradient cases; no test case removed; independentreview |
| 5A / `6558bd06` | Unused EvalRecord CSV export; production-21/tests-15 |35before34retained; current JSON/NPZ reading unchanged; independentreview |
| 5B / `5c33337d` | Unread standalone saliency export retired; production-83/tests-76 |101before93retained;8obsolete cases;8POSIX-only skips still CI obligations; main nonauthorreview |
| 4M / `bf24db3f` | Mock-only output uniqueness replaced by real frozen-clock records; testsnet-98 |32before31retained/4POSIXskips; duplicateUUID fails real exclusive output creation; independentreview |
| 5C / `cdeb3175` | Unused saliency getters removed; production-100/testsnet-67 |93migrated before88after;6actual-validator bypass faults fail; invalid/old/producer checks migratednotremoved |
| 5D / `ae7c8d62` | Dead render error/string forwards; production-19/testsnet-10 |Same50before/after incl real trainer typed summary; no cases removed; independentreview |
| 4N / `33a7ad8b` | Real persistence in synthetic training integration; testsnet-41 |Same27before/after;122files/723462bytes; omitted-save exactcase fails safe load; main nonauthorreview/Ruff |
| 5G / `0839dcc2` | Unused policy/holder/render conveniences + duplicate assertion; productionnet-61/testsnet-8 |235migrated before234after; strict invalid-method/default state/vectorized interpolation retained; independentreview/Ruff |
| 5H / `cef27766` | Inert 3D setup/state removed; productionnet-20 |Same43before/after; control/sample identity/lifecycle unchanged; main nonauthorreview/Ruff |
| 5I / `75bd4047` | Real Saliency estimator/receipt/receiver evidence; testsnet+113 |42after within80combined; admission-bypass fault fails; not an attribution journey |
| 5J / `848d3356` | Reuse newly normalized detached arrays; production+1 |Same38before/after; normalized extra copies128→0bytes, raw copy retained; independentreview/Ruff |
| 5K / `e3c57cd9` | Retire unused coverage forwards; production-39 |Same258before/after; all assertions and negative UI boundaries retained; main nonauthorreview/Ruff |

| 8G / `4f352cab` | Preserve caller-owned capture output root; script-3/test+61 | Red4 then76passed; real nested sentinel/rerun/exit evidence, not native rendering |
| 6A / `296af917` | Orphan command-to-panel route removed; production-80/test-18 |342before339retained; exactly3exclusive cases; actual navigation retained |
| 6C / `3d498c51` | Orphan backend class registry removed; production-101/testnet-36 |74before71retained; actual18-tool registration unchanged |
| 6D / `f4c060c5` | Unreachable empty-schema override; productionnet-15/test+23 |72before/after; exact schema assertions and empty-schema fault detected |
| 6B / `5afdb10d` | Real confirmation card → reset/replay/cancel/stale mutation; testnet+291 |21before24after; omitted-reset fault detected; real raw identity/256Hz/file bytes, model/runtime transport isolated |
| 6F / `65cd3519` | Eight test-only RAG probes removed; production-51/testnet+10 |12original/strengthened,271combinedafter; captured actual thread non-daemon fault detected; live shutdown query retained |
| 6H / `42cc98a4` | Shared settings-path owner and orphan cache alias; productionnet-90 |Same94before/after,21exact path combinations; no user settings written |
| 6I / `a2b21efc` | Real metrics tracker replaces synthetic capture fixture |Same17before/after; omitted-finish fault detected; no production/count change |
| 6J / `3831a483` | Dormant RAG initialize/publish/helper paths; productionnet-46/test-1 |89before/after,2POSIX-only skips; lease/closed fence/local-only/corpus policy retained |
| 6K / `965bc97e` | Sole-subclass backend shell/ignored-mode helper; productionnet-50/test-60 |116before110retained48.65s;6exclusive cases removed; first lost after ending not counted |
| 6L / `f44d3e0e` | Real RAG quota fixture10.1GB→101bytes; testsnet+9 |89after/2POSIXskips; omitted current-target guard fails; actual9.41GiB fake file removed, real caches untouched |
| 6M / `ef161994` | Four giant model quota fixtures →105/206/302/300bytes; tests only |77retained8.61s,4omitted-quota faults fail; baseline Windows expected-path mismatch corrected; defaults unchanged |
| 6P / `ec4eeeda` | Exact capture UTF8 writes on Windows; productionnet0/testnet+12 |3red/10pass→452combinedgreen23.50s; real LF/CRLF/Unicode bytes+SHA, strict validator retained |
| 6N / `92d6a091` | Unused tolerant parser chain; productionnet-136/testnet-9 |403retained21.31s;57exact-result digest; omittedtypeguard2fail; strict grammar unchanged |
| 6O / `b6d596d4` | Ignored downloader arg/cleanup message alias; productionnet-7 |Same23before6.89s/after6.78s; lifecycle/public-message protection retained |
| 7A / `e6aa7d44` | CP950/ASCII console encoding fallback; productionnet+22/test+63 |4red/2pass→58green8POSIXskips4.47s;6final1.30s; both sink orders/privacy/UTF8 intact |
| 6Q / `0181b233` | Unused snapshot serialization; productionnet-70/testnet-27 |39before37retained5.74s;5omitted-validation faults fail; typed/device/activation intact |
| 6R / `f3b850d7` | Real processing widget state +2duplicate tests retired; testnet+9 |150before22.79s/148after22.63s; noop forwarding fault fails; no production change |
| 6S / `f7632053` | Unused conversation convenience chain; production-33/testnet-23 |19before7.54s/15retained7.38s; wrong-end window2faults fail6.12s; exact list semantics |
| 6T / `f4d2884a` | Suggestion row churn +unused render helpers/arg; productionnet-33/testnet+27 |213before9.09s,3red1.01s,216after9.34s;3width geometry equal,15+15calls→0+0 |
| 6U / `5cf7a6df` | Unused private command list normalizer; production-7 |Same25before6.38s/after6.36s; no tests/contract changes |
| 6V / `337d94e7` | Approved dormant recovery-feedback chain; production-131/tests-102 |403before/400after,3exclusive cases retired;14prompt parity digest above; privacy review |
| 6W / `5132d43e` | Discarded footer input/list; production-4/tests-5 |35before/after, copy unchanged; independent review |
| 6X / `a6e3d7e9` | Stateless names/byte alias indirection; production-14 |104before/after; prompts/scoring/8192byte cap unchanged |
| 6Y / `6c66f2a0` | Owned runtime init only; production-13/tests+99 |110before/after;2failed-close faults fail; independent lifecycle review |
| 7B / `c089d7a8` | Unused UI query forwards; production-63 |52before/after; backend queries/variant lifecycle retained |
| 7C / `deb4a3cf` | Four orphan widgets/lazy exports/styles; production-660/tests-227 |70before/50retained,20exclusive cases retired; architecture/import/lint pass |
| 7D / `0aa9fa6c` | Aggregate renderer unused Study/marker; production-2 |42before/after; real rows/empty widget and weakref fault; architecture/review pass |
| 7E / `48b9f880` | Unused summary measurement/notifications; production-33/tests-2 |48before/after, no cases removed; all geometry/value assertions retained |
| 7F / `36a23137` | Orphan EventBus and unconnected worker/window signals; production-59/tests-75 |52before/43after,9exclusive cases retired; independent caller review |
| 7G / `e89291f9` | Unused modal facade/ignored error argument; production-14/tests-3 |42nativebefore/after; privacy review; INFORMATION severity retained |
| 8H / `f54e3c4f` | Real installer SHA/HTTPS/size/noexec evidence; tests+92 |20before/23after;SHA-bypass1fail/2pass; no network/install; independent review |
| 9A / `d7003752` | Direct Windows offscreen installed-font default; tests/config+87 |48after incl original42+4child cases; finalbootstrap+fixture29pass/Ruff; no production change |


### Evidence qualifications that remain relevant

- Use a fresh unique PYTHONPYCACHEPREFIX plus -B for Windows tests of WSL-edited source: -B alone
  prevents writes, not stale reads. The earlier ambiguous 1B run was superseded by fresh-cache 84.
  That earlier lookup was abandoned. During2X a worker mistakenly invoked Poetry and created a
  separate empty Windows environment. Main verified its exact newly-created path,7,235,691 bytes,
  no using process and sole internal file symlink, then removed only that accidental environment
  xbrainlab-urV89cf7-py3.12 from the Windows Poetry cache. Original Windows Python remains present;
  the invalid attempt supplied no test evidence. Further runs use the explicit existing interpreter.
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
