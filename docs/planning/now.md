# XBrainLab Now

最後更新：`2026-09-09`

## Active — repair manual-test Preprocess re-reference regression in #131

### Problem, outcome and authorization

The user accepted the prior cleanup (#130), merged at `8306a649`, but requested a further
comprehensive pass on overdesign, historical residue, weak coverage and mock-heavy tests.
Draft #131 is the single delivery vehicle; construction commits are not intermediate handoffs.

The authorized outcome is a smaller canonical product path with real state/workflow evidence,
followed by complete exact-head validation and one live manual-test version. The user explicitly
allows this stage to exceed the normal production-LOC PR limit; each construction slice remains
independently reviewable and reversible. UI internal cleanup is authorized only while preserving
visible layout, copy, interactions and behavior. No merge before the user's new acceptance of
the final product source and explicit merge approval.

### Construction closure and retained evidence

Production construction and the integration-discovered test/lifecycle repairs are implemented
for the families below. Head `0b3825d0` passed exact-head CI and was opened for Windows native
manual testing, which exposed the re-reference regression described below. Those earlier passes
do not certify its repair or establish that every UI entry point was covered.
The construction commits hold the detailed history. Inventory counts are not claims that every
tracked file was deeply read, and passing tests do not establish defect-free architecture.

| Family | Implemented boundary / evidence |
| --- | --- |
| Import, labels and recipes | Canonical scan/review/apply replaces the retired direct-import/post-load-label commands, opt-in and hidden UI route. Real FIF/BIDS workflows, reviewed mapping, historical JSON label recipe replay and atomic failure tests preserve supported data semantics. |
| Preprocess and epoch | Unused EEG controller forwarding is removed. Real commands protect filter/resample/epoch/reset, event identity and all-dropped epoch rollback. |
| Split, training, stop/retry and results | Training uses explicit application query/publication/action/transient ports. Real training and OOM/terminal-delivery tests protect retry, history, cancellation and result/saliency delivery; snapshot tests protect stale publication and selection. |
| Evaluation, Saliency and Visualization | Existing query/publication owners remain. Settings use snapshots, including pending-option precedence and unavailable-query handling; real workflow and applicable native/public-data gates protect integrated result consumption. |
| Assistant | Stale retired alias references are removed; the 18-tool registry and command spine remain unchanged. Real product diagnostic/confirmation paths and long-session lifecycle evidence replace alias residue, not model-quality evaluation. |
| MainWindow and shared UI | Empty controller slots, indirect controller context resolution, observer refresh suppression/router and unused helpers are removed. Explicit runtime/parent resolution, real publication delivery and native QObject deletion protect ownership and unsubscribe behavior. |
| Dataset UI | Row actions require revisioned selections; rendering consumes published metadata. Test-only synchronous dispatch, unversioned selectors and live metadata reconstruction are removed. Real inline edits, row replacement/reordering and asynchronous review/apply tests protect the current product path. |
| Scripts, fixtures, docs and CI | Gate selectors and capture fixtures use current boundaries. Training captures own and close their real runtime. Coverage collection keeps the existing denominator, enforces 85% lines and records branches separately; Poe uses the same aggregate verifier. |

The primary behavioral evidence lives in current tests, including:
`tests/integration/workflows/`, `tests/integration/`,
`tests/unit/backend/`, `tests/unit/ui/dataset/`, Training/Saliency/publication test families,
and `tests/unit/scripts/`. Deleted forwarding/mock choreography is not counted as lost product
protection where the retained replacement exercises the actual state transition or side effect.
Mocks remain for external generation, resource failure and nondeterministic/native seams, not
as proof that mocked product workflows execute.

### Ownership review and retention decisions

- ApplicationService remains the shared admission, publication and owned-work authority.
  Domain services retain authoritative data/training mutations. Its size alone does not justify
  another facade, state machine or receipt owner; cancellation, publication and two-phase
  validation guards are not compatibility residue.
- Study's unused Dataset/Preprocess/Training controller factory/cache and the three forwarding
  controllers are removed. ChatController remains an active Assistant boundary.
- MainWindow owns Qt construction, navigation and shutdown; LLMController owns Assistant
  turns and leases. Neither gains a second workflow/control layer.
- The internal raw-mutation lifecycle coordinator still invalidates interpretation state after
  current metadata, smart-parse and remove-file commands. Its historical name does not make
  this live consistency protection removable.
- Lazy imports preserve the measured/import-tested heavy-dependency boundary.
  Internal label-plan/recipe records remain where canonical replay still consumes them.
- Supported model catalog, settings, recipes/results, English Assistant behavior and EEG
  semantics remain in scope for preservation. No visible redesign, prompt/model/RAG experiment,
  unknown-external API shim, legacy directory or generic inventory platform is introduced.

### Measured CI aggregation change

Successful reference run `34250604747` spent 96 seconds in Linux aggregation: Poetry install
12 seconds, full venv cache restore 50 seconds, sync 1 second and combine/verification 19 seconds.
Only that aggregation job now installs lock-pinned coverage; provenance and shard verification
have a tested stdlib-only import closure. Exact-source sidecars, complete shard evidence,
coverage denominator/85% line floor and artifacts remain mandatory.
Compare the final run's actual timing with this observation; one sample is not a general
performance guarantee. Other job environments and gates are unchanged.

### Remaining execution plan and validation

#### Current manual-test repair

On 2026-09-09, Windows manual testing reported that Preprocess → Re-reference presents an
unexpected error. The traceback identifies `_preprocessed_channel_names_for_rereference` passing
the retired `refresh` keyword through a dictionary to `execute_application_command`. Its existing
test replaces that adapter with a permissive stale fake, so it does not detect the signature error.

Expected outcome: the real button opens the reference chooser with current channels; cancelling
leaves data unchanged, and applying runs the existing preprocessing command. Publication-generation
checks must continue to reject stale review. This is an internal repair under the existing UI
authorization; no visible layout/copy redesign, restored compatibility keyword or new owner.

1. Add a failing regression through the real UI command adapter and application runtime, with
   real channel data and dialog interaction; preserve observable apply/cancel/stale protection.
2. Remove the obsolete caller keyword and inspect directly related adapter calls, including
   dictionary expansion. Replace or correct the stale fake only after stronger evidence exists.
3. Run the focused regression, directly adjacent preprocess/state tests and changed-file static
   checks. Review the actual diff and preserve the failing reproduction.
4. Push the repair to the existing #131 and require new exact-head applicable CI before a replacement
   handoff. Ask for re-testing re-reference and adjacent preprocess operations, not the entire
   previous manual checklist. Do not replace source beneath the live Windows application or discard
   its loaded data; coordinate replacement after the user can close/save it.

The separate PickMontageDialog Windows geometry warning is diagnostic-only in this repair:
trace the contradictory size constraints, but do not change visible layout without confirmation.
Stop at a verified replacement handoff, or an explicit user decision needed to replace the live
application safely. No merge without updated manual acceptance and approval.

The repair is implemented: explicit generation forwarding replaces the obsolete keyword dictionary,
with no command contract or owner change (production +1/-6 lines). The real-button regression first
reproduced the exact `TypeError`; its cancel/average/selected/stale cases now pass, along with the
autospecced generation contract (5 cases). Directly related UI/adapter/dialog/preprocess checks pass
203 cases; Ruff and locked Basedpyright pass with zero diagnostics. Inspection of synchronous adapter
callers, including Training's dictionary forwarding, found no other retired `refresh` argument;
the similarly named source-identity script options are valid and unchanged.

Next: push this repair and verify its new CI. On 2026-09-09 the user reported that the rest of their GUI
test found no further issue and requested the repaired Windows GUI plus AI Assistant and a reusable
launch command. The old native application has exited and its worktree is clean. Reuse that isolated
worktree only after verifying it remains unused; open a single PowerShell console for application
stdout/log, not a separate log-viewer GUI. This report is not acceptance of the changed product source
or merge approval. Assistant stays on the supported existing local model/settings without experiments.

#### Previous integration failures and validation requirements

Integrated run `34304758779` exposed missed test consumers of retired dialog/controller/refresh
contracts and an outdated CI installer count. These consumers and their same-class Training,
Dataset, shared-sidebar and Visualization mock residue are now migrated. Focused tests preserve
current command/publication/confirmation, detached data, error outcome and log-redaction evidence.
No production fallback or weaker dependency policy was restored. Preserve the failed run and
shard artifacts; the repaired tests still require replacement-head integrated validation.

The final integration-rest shard timed out in the real no-model contract-failure walkthrough's
shutdown. Its pre-timeout stack places the command thread inside `_ControllerShutdownBridge._finish`
at `controller.moveToThread(gui_thread)` while the GUI waits for runtime CLOSED.
The bounded same-process coverage reproduction also hangs locally. Native debugger evidence
(`build/assistant-shutdown-native-stack.txt`) shows the command thread holding the Python GIL
inside `QObject.moveToThread` while waiting for a Qt mutex, and the worker thread holding a Qt
destruction/connection lock while waiting for the GIL in `sipQThread.disconnectNotify`.
`QThread.finished` precedes deferred deletion; it is not a completed native-cleanup fence.
The deterministic native finished-callback barrier test failed on early successful shutdown
before the repair. The existing controller owner/retry timer now requires a nonblocking
`QThread.wait(0)` completion probe before terminal publication, including the already-not-running
entry. The source guard still rejects blocking waits and nested loops; only the literal zero-time
probe is permitted. Independent lifecycle review found no blocking issue; the focused controller/
dispatcher tests, repeated real diagnostic walkthrough and adjacent controller/runtime tests pass.
Do not lengthen timeouts, skip this walkthrough, or infer a model/prompt problem. This is required
integrated evidence, not a reason to hand off an incomplete candidate.

1. Freeze and push the single integration head to #131. Verify exact base/head and every
   applicable non-skipped CI check using actual GitHub conclusions and artifacts.
2. Require the complete Linux test aggregation, at least 85% line coverage, separate branch
   baseline, source-diverse required public data, platform/native and applicable UI gates.
   Earlier green heads cannot substitute. Reuse equivalent same-head CI evidence rather than
   running a duplicate local full manifest.
3. Diagnose and repair any direct integrated failure, preserve its evidence, and validate the
   changed final head again. Pending CI is not a stopping point.
4. Once all applicable gates pass, launch that exact isolated version and a live log, verify
   responsiveness, and deliver one workflow-oriented manual checklist. Do not monitor the
   user's subsequent operation or merge without acceptance.

Local focused evidence covers canonical dataset workflows, revisioned Dataset UI and async
review/apply, preprocessing/epoch rollback, Training state/lifecycle, application boundaries,
script contracts, Ruff and architecture/type checks. Those passes are construction evidence;
they do not yet satisfy the final exact-head CI/Windows/source-diverse handoff contract.

### Stop condition and assumptions

Stop only at the single live, validated manual-test handoff, a user pause, or a genuine missing
authority/resource that cannot be resolved through safe in-scope work. Keep the original dirty
worktree, user settings, shared environment, original data and existing applications untouched.
The final candidate uses an isolated runtime and log. New source changes invalidate its prior
manual acceptance; #130's acceptance does not approve #131.

Do not claim architecture perfection, complete model reliability, native Windows acceptance from
offscreen captures, or handoff-ready from partial/pending evidence. Merge and post-merge worktree
cleanup remain subsequent user-approved actions.
