# XBrainLab Now

最後更新：`2026-08-27`

## Active: Assistant precision and clarification recovery campaign

**Branch / base / dependency:** `fix/assistant-precision-electrode-stack-v1` is stacked from the
exact Electrode final `a0d2b4c97b10767eb1fb44ce160b24706449b6cc` (whose `main` base is
`2c51d7b1e6ff83475f285f0db331becd3f87f5c1`). Assistant precision commits are applied above that
final Dataset-owned Electrode flow; they must not be handed off or merged independently of it. This
integration branch owns no additional Qt layout, theme, Dataset dialog, or root `settings.json`
changes.

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
The subsequent product repair builder does not inspect the holdout wording.

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
The new tracked development corpus is 48 cases with SHA-256
`7cebb1c5b6e32efa4279c0a53e20c3015aaddc6d98c1c22106004a25a20c49cf`; the separately named
32-case holdout corpus SHA-256 is
`b17a7461884708c4afd358af47fb253e8db6343f587dcd5ce56389ec3a9a1c95`. Loader tests lock the
81 frozen v8 denominator, two corpora's counts/taxonomy/bilingual balance, strict schema, no shared
IDs/trajectories, and no verbatim frozen trajectory. A later candidate must recompute all identities
on its own clean exact SHA before any score comparison or claim.

**L1 — prompt/context/output treatments.** Test at most four pre-registered hypotheses: decision
ordering, compact canonical examples, the placement/shape of bounded active-receipt context, and
strict output/decoder recovery. Treatments may not add a semantic Host router, infer values, change
tool membership, or encode individual expected answers into the prompt.

**L2 — existing typed receipt completion.** Reuse `ToolAttemptCoordinator`,
`PendingInteractionCoordinator`, `AssistantToolInputReceipt`, controller generation binding, and
the existing parameter-origin verifier; do not add an owner, state machine, receipt type, or
compatibility path. When exactly one currently published direct-preprocess proposal has a valid
shape but fails only because values cannot be proven from latest user text, create a zero-execution
receipt containing only exact tool ID, actual missing fields, latest-user-verified values, fixed
question evidence, publication generation, and two parameter reply attempts. A follow-up must
again propose that same exact tool; then re-run schema, origin, publication, capability,
confirmation, and one-action checks. Cancel/new chat/stale publication/different tool/topic/third
reply clear the receipt with zero execution.

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
or safety rule. Do not commit until root approves this active plan.
