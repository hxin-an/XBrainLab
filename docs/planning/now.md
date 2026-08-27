# XBrainLab Now

最後更新：`2026-08-27`

## Active: Assistant precision and clarification recovery campaign

**Branch / base / dependency:** `fix/assistant-precision-electrode-stack-v1` is stacked from the
exact Electrode final `a0d2b4c97b10767eb1fb44ce160b24706449b6cc` (whose `main` base is
`2c51d7b1e6ff83475f285f0db331becd3f87f5c1`). Assistant precision commits are applied above that
final Dataset-owned Electrode flow; they must not be handed off or merged independently of it. This
integration branch owns no additional Qt layout, theme, Dataset dialog, or root `settings.json`
changes.

**Integration checkpoint.** This stack does not reopen the completed Electrode slice: the final
Dataset-owned Electrode route is a fixed dependency beneath the Assistant target/evidence and L2
admission work. Any cross-branch semantic failure is a blocker for this combined candidate, not
authority to edit that UI path from the Assistant slice.

### Problem and outcome

The current Granite 4.0 Micro candidate can select an unsafe substitute action for negated,
ambiguous, or multi-mutation prompts, and does not reliably recover a direct preprocessing action
after the user supplies a missing parameter on a later turn. The required outcome is a product
admission path that preserves one-action, parameter-origin, publication, capability, confirmation,
and execution boundaries while making the approved typed clarification receipt reachable from real
model proposals. `set_montage` must be published according to the same authoritative
`ApplyMontageCommand` mutation capability that decides whether it can change state, while its name,
zero-parameter schema, GUI confirmation, and terminal semantics remain unchanged.

### Baseline and claim boundary

The candidate must first rebind these historical checkpoint figures to an exact clean source,
model/revision, prompt/context hash, generation policy, evaluator and case-pack hash; they are not
yet a claim about this branch:

- positive `36/36`; direct parameter origin `10/10`; missing-parameter host guard `5/5`;
  bilingual no-action precision `20/24`; clarification trajectories `0/7`.
- Current primary model is `ibm-granite/granite-4.0-micro` revision
  `56111ae135df9c53a78c99028e7bc24035a9e979`; no new model, model download, model fallback, or
  change to the catalog is in scope.
- Raw first-generation decisions, strict-envelope recovery, host composed product outcome, receipt
  creation, and any execution boundary outcome are reported separately. A safe host rejection or
  receipt must never be presented as raw-model accuracy.

### Approved treatment ladder

**L0 — freeze evidence.** An independent evidence custodian first creates and holds a 48-case
bilingual development pack and a separately held 32-case holdout with content/case hashes before
repair. The development pack covers negation, general questions, ambiguity, multi-mutation,
blocked stages, all five missing direct-preprocess parameters, generic action selection, partial
parameter accumulation, format recovery, cancellation, different-tool and stale-generation paths.
The tracked holdout is process-blinded and finalist-only, not a technical secret: the product repair
builder must not inspect its wording, and progress/reporting must not expose holdout wording.

**L0 evidence checkpoint (2026-08-27).** The trusted historical preflight artifact is
`/tmp/xbrainlab-ui-health-stable-preflight.json`, produced at source
`f9b8595f2a0644d1caa57ed3f4aa3530825644a7` using Granite 4.0 Micro revision
`56111ae135df9c53a78c99028e7bc24035a9e979`, deterministic structured-decision policy
(`max_new_tokens=512`, `do_sample=false`, two format recoveries). Its frozen v8 case hashes are:
positive `a4311b63165c2f4fb1c68d88c1ed8c81ecb9ae3beb1760bf1c2e52cda57f31bc`; challenge
`df300230c11b0ca014b1320e20ec80f2529766d2cbb2d50cd38adbe78ba2405b`; precision
`1b9d03bf0eb6802313f69cff955dab8bc39058fccb58667a2903fbab8a3e16f6`; clarification
`de3bb8e1f41cd820ead690a1f9767ab7d47cf0142568c5dda8f25405a5a97087`. That artifact does
not bind a scorer or prompt hash, so its historical figures remain a checkpoint only.

At the current base source, the scorer runner SHA-256 is
`c04bf392a2603c7022009b9196927bce7931ba605766dd7b74408e2d65df73f9`; fixed prompt-policy
SHA-256 is `3215cd2106baa022e64a07ad1c10a15e6a730bb10f76d9b9b2394ebd58e4133a`; context
assembler SHA-256 is `eba7a9b58925bea46bdd1cf37cd1ce72a5c070061ecb9b756137a3e07ffea1da`.
The v4 tracked development corpus is 48 cases with SHA-256
`13b5a4434781d7be89f6e5618395232e854376ac1020500b55d228cabb46be94`; the separately named
32-case holdout corpus SHA-256 is
`4919e5db805e34851ec32eeea199915a453316d0d68ca46b214d7dda1f0eca55`. Every user turn now
contains its before-turn publication-generation event, one exact boundary (`respond`,
`typed_receipt`, or `verified_execute`), exact direct tool or `null`, exact parameters, and either
the complete receipt missing/verified-value evidence or `null`. Only stale cases may advance
generation; no-action, cancellation, unrelated/different-tool, and stale-clear turns declare a
`respond` expectation. This is only a machine-loadable composed-boundary oracle/schema: no
production controller or scorer consumes it yet, so it does not demonstrate product execution,
zero mutation, receipt lifecycle, format recovery, or any model score. `format_recovery` only locks
the static final composed expectation; a future runner must separately record raw primary/repair
taxonomy and observed final outcome.

The lightweight loader holds an explicit pinned experiment snapshot of the five direct-tool schemas:
resampling remains an integer, normalization keeps its registered enum, and reference retains its
registered string type without an invented enum. It is a frozen L0 corpus baseline, not a second
authoritative runtime policy. Full-product CI lazily imports the real registry and
`ToolSchemaValidator` for exact schema and representative validation parity; the module's `-S`
subprocess proof hashes and loads without site-packages, Torch, MNE, or `XBrainLab` imports. Tests
mutate missing/unknown/type/enum values (including fractional rates, invalid normalization values,
and invalid reference types), schema/step drift, and corpus content drift. Development/holdout exact
digests and the frozen-v8 source identity
`f9b8595f2a0644d1caa57ed3f4aa3530825644a7` plus all four frozen corpus digests are pinned in the
loader; any update requires an approved corpus-baseline decision, updating the explicit pin and
this checkpoint together. Tests also lock the 81 frozen v8 denominator, two corpora's
counts/taxonomy/bilingual balance, no shared IDs/trajectories, and no verbatim frozen turn or
trajectory. A later candidate must recompute its own identities on a clean exact SHA before any
score comparison or claim.

**L1 — prompt/context/output treatments.** Test at most four pre-registered hypotheses: decision
ordering, compact canonical examples, the placement/shape of bounded active-receipt context, and
strict output/decoder recovery. Treatments may not add a semantic Host router, infer values, change
tool membership, or encode individual expected answers into the prompt.

**L2 — existing typed receipt completion.** Reuse `ToolAttemptCoordinator`,
`PendingInteractionCoordinator`, `AssistantToolInputReceipt`, controller generation binding, and
the existing parameter-origin verifier; do not add an owner, state machine, receipt type, or
compatibility path. When exactly one currently published direct-preprocess proposal has a valid
shape but fails only because values cannot be proven from latest user text, create a zero-execution
receipt only if that exact tool occurs in the same proposal generation's immutable callable-schema
publication actually used for the model prompt. This is prompt-time membership evidence only, not a
live readiness lookup and never changes origin-before-live-capability ordering. The receipt contains
only exact tool ID, actual missing fields, latest-user-verified values, fixed question evidence,
publication generation, and two parameter reply attempts. A follow-up must again propose that same
exact tool; then re-run schema, origin, publication, capability, confirmation, and one-action
checks. Cancel/new chat/stale publication/different tool/topic/third reply clear the receipt with
zero execution.

**L3 — bounded rejection-only verifier.** Only if L1/L2 leave measured no-action residuals, update
the already user-authorized target decision before source work, then experiment with one same-model
extra generation. It may receive only latest user text, the exact primary proposal/schema, and the
current publication, and may return only `allow_primary` or `reject_to_response`. It may not repair
format, handle an active receipt, select/replace a tool, infer a parameter, create a receipt,
request confirmation, issue a GUI handoff, or execute. Timeout, parse failure, uncertainty, or
stale state fail closed to response. Remove this treatment if it does not meet all gates.

### `set_montage` public-contract prerequisite

Before source work changes model-facing membership, update `docs/target/agent.md`; the user has
already authorized this target delta. Dataset UI remains a view/configure entry when EEG exists,
whereas Assistant `set_montage` is published only when the immutable ApplicationService publication
says the authoritative montage mutation is enabled. Raw/preprocessed/epoch/dataset-ready stages
publish it only when unlocked; training/retained-trainer lock leaves the UI viewable but hides the
mutation tool. The tool requests the existing GUI workflow; confirm/cancel and command-boundary
TOCTOU revalidation remain unchanged.

**Target-first checkpoint (2026-08-27):** this prerequisite is now recorded in
`docs/target/agent.md`: `set_montage` remains zero-parameter, GUI-handoff and confirmation-based,
but its model-facing membership is the enabled `apply_montage` mutation capability from the same
immutable ApplicationService publication. The target stage table no longer implies an epoch-only
Assistant rule. The same target document now records the L3 verifier as a residual-only,
same-model, one-extra-generation rejection path with fail-closed `reject_to_response`; it cannot
repair, infer, select, hand off, confirm or execute, and adds no owner.

**Root contract calibration (2026-08-27):** verification now explicitly orders direct
parameter-origin before ApplicationService capability and confirmation. A missing or unverified
required direct parameter creates its typed receipt in zero execution and ends that turn; it is
never deferred until after capability or confirmation.

**L2 / `set_montage` implementation checkpoint (2026-08-27):** root and the independent source
reviewer accepted the product-source commit
`f66eb5516539c694ac7971aa79376a273490450c`, the Electrode-stacked integration of
`3cab532e8b8cb7f65f1910395ce285548f3a957b`. It reuses the existing receipt/controller owners,
binds direct receipt admission to prompt-time immutable publication, preserves partial
user-verified values, fails closed for cancellation/different/stale/expired replies, and projects
`set_montage` from the authoritative `apply_montage` capability. The integrated contract keeps the
Electrode no-data reason `Load EEG data before configuring electrode layout.` and additionally
blocks running or retained trainers. This is reviewed source and focused-test evidence only: it is
not raw-model accuracy, product acceptance, or handoff approval.

**Integration validation checkpoint:** the final Electrode branch contained an older expectation
that a retained trainer could make one first montage mutation. That contradicts the approved
retained-trainer lock above. The directly affected ApplicationService test must instead assert
capability rejection, the reset-session reason, and zero raw/epoch/effective-layout mutation. The
normal error-only publication/state delta advances generation (1→2 in the characterized test). A
no-trainer first attach remains a separate success path. No UI or production policy expansion is
authorized by this test alignment.

**Development-evaluator blocker:** the development evaluator still uses policy-bearing unbound
harness methods rather than the controller's actual terminal lifecycle. It cannot certify receipt
clearance, zero execution, or verified execution until that duplication is removed; no development
score or product claim may use it in its current form.

### Owners, deletion candidates, and complexity guard

Owners before and after are unchanged: `ApplicationService` owns authoritative mutation and
capability publication; `ToolAttemptCoordinator` owns proposal/admission;
`PendingInteractionCoordinator` owns bounded pending receipt lifecycle; the existing GUI handoff
registry owns presentation/correlation. No new authoritative owner, state machine, or receipt is
authorized.

Deletion candidates to verify by caller inventory before removal are the legacy
`UiRequestKind.CONFIRM_MONTAGE` branch/feedback and any Agent-provided default montage suggestion;
the formal `WORKFLOW_HANDOFF` remains. Record production `+/-/net LOC`, changed production file
count, owner delta, and an explicit split proposal before crossing any AGENTS complexity trigger.

### Authorized next slice: private LLMController terminal-lifecycle evaluator seam

After this stack is clean, the only root-authorized follow-up is a private extraction inside the
existing `LLMController` (roughly one production file). Both the worker callback and development
evaluator must drive the same real terminal lifecycle; delete the policy-bearing unbound harness methods
rather than adding a public class, owner, state machine, receipt, compatibility path, prompt, or
tool. Test first: cancellation, different-tool, and stale publication must clear a receipt with zero
execution; the evaluator execution sentinel may observe only the already verified execute boundary
without mutation. Focused validation is the red/green controller and evaluator trajectory tests,
the direct receipt/capability tests, ruff, architecture compliance, and `git diff --check`; no
model/GPU or holdout access is allowed. Stop and return to root if this requires a public contract,
additional owner, L3 verifier, prompt/UI change, or any semantic policy beyond the existing terminal
lifecycle.

### Experiment budget and promotion gates

Maximum GPU processes: four 12-case sentinels, four 48-case development runs, two finalist
32-case holdouts, one frozen canonical strict run, and one exact-source confirmation rerun. A
sentinel immediately eliminates a treatment if it allows unrequested confirmation, GUI handoff,
ApplicationService/ToolExecutor execution, or mutation. Holdout runs are only for finalists.

Promotion requires: canonical strict suite fully passing; `36/36`, `10/10`, `5/5`, `24/24`, and
`7/7` category gates; no development or holdout safety failure; no positive/valid continuation
regression through blanket response; and production-controller trajectories that create actual
receipts rather than evaluator-synthesized state. This work cannot claim raw LLM accuracy,
Assistant-ready, Stable promotion, or handoff-ready until the canonical validation and manual gates
close on one exact source.

### Tests and evidence

Follow the TDD bug loop: write the smallest red reproduction for each reachable defect, implement
the bounded repair, then rerun the same test plus direct adjacent evidence. Focused coverage must
include strict envelope, publication/generation staleness, parameter-origin, receipt creation and
expiry, latest-value precedence, partial accumulation, cancellation/different-tool/new-chat,
zero-execution missing/precision outcomes, GUI handoff/confirmation separation, and exact
`set_montage` capability membership. Use low-mock controller integration for actual receipt
trajectories and preserve raw model outputs/taxonomy in ignored development artifacts.

Before any user handoff, select commands from `scripts/dev/handoff_gate_spec.py` and run the
canonical manifest on the same clean/explained exact commit. Model/native validation uses explicit
timeout and `prlimit --core=0`. Automated evidence is a checkpoint only; WSLg manual acceptance and
explicit merge approval remain required after source changes.

### Roles, checkpoints, and stop conditions

- **Root coordinator:** sole scope, branch/base, integration, PR/CI and final exact-SHA evidence
  owner; independently inspects diff/artifacts and does not merge while the user is away.
- **Builder:** owns only this branch and submits exact head, base, dirty state, LOC/owner delta,
  focused evidence, artifact paths and known risks; never reads the hidden holdout or changes UI.
- **Evidence reviewer:** independently owns frozen/holdout scoring and audits denominators, raw vs
  composed outcomes, mocks, GPU traces and exact-SHA identity; read-only and may block only direct
  contract/safety/evidence failures.
- **Contract reviewer:** independently traces target/current membership, receipt expiry, TOCTOU,
  command spine and rejection-only verifier constraints; read-only, with at most three advisory
  follow-ups outside scope.

Each checkpoint needs builder focused evidence, an independent reviewer report, and root exact-SHA
verification. CI pending/flakes do not stop unrelated work; a failed required gate leaves this
branch at `checkpoint`. Stop the affected treatment for a required new public target decision,
new owner/state machine, model/download change, destructive operation, exhausted pre-registered
budget, or unavailable mandatory resource; report the residual rather than weakening a denominator
or safety rule. Root has reviewed the L2 / `set_montage` source above and authorized only the
private `LLMController` terminal-lifecycle evaluator seam described here; all other product,
evaluator behavior, prompt, UI and holdout work remains out of scope.
