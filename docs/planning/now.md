# XBrainLab Now

最後更新：`2026-09-09`

## Active — integrated quality-hardening validation and one manual handoff

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
for the families below; the replacement head's complete integrated gates remain outstanding.
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
