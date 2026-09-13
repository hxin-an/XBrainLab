# XBrainLab Now

最後更新：`2026-09-13`

## Active — Repeatable release import conformance and durable dataset storage

### Approved outcome and source

User approved implementation of the combined plan: consolidate dataset locations, make full import
conformance a recurring major-stage/key-change gate, and investigate the 11 non-rights blockers.
The fixed MOABB 1.5.0 / 140809d8c48bdf2be953951ff75f688122edee34 denominator remains 147 exports.
Initial evidence is 127 representative BIDS routes passed, nine rights entries deferred and eleven
technical/acquisition/source-semantic blockers. These are not 147 independent complete cohorts.

PR #141 remains open. Commit 4522bbe6681147b2bb4d78e176fc37323edacff9 has all 24 applicable CI
checks successful and four native Windows changed-import cases passed. The exact manual checkout
was launched with PowerShell PID 38336 and XBrainLab PID 36344; verify live use, never terminate it.
User has not accepted or authorized merging this PR. Keep that checkout untouched while it is used.
Continue the import task branch with independently revertible slices; new candidate source requires
fresh applicable evidence and acceptance. Preserve unrelated root settings/UI/test changes.

### Scope and defaults

- Major-stage integrated acceptance and changes to import/label contracts or reader/converter
  dependencies require full representative backend conformance plus representative Windows GUI.
  Ordinary PRs retain focused tests and existing CI; no equivalent full local reruns while CI runs.
- Keep all 147 statuses visible. The nine rights entries are deferred: no terms acceptance, new
  acquisition or author contact. A previously passed baseline cannot silently become an allowed blocker.
- Durable data root is E:\\XBrainLabData, using the existing datasets/source, bids, public-fixtures,
  manifests and quarantine hierarchy, with sibling evidence and staging. Models/shared Python stay put.
- Retain unique original sources, reproduction-required extraction, validated BIDS and necessary
  success/failure evidence. Duplicate/intermediate deletion requires an exact reviewed deletion list
  and separate confirmation. No original data, live source, user output or broad worktree deletion.
- Copy first, hash verify, rerun from destination, then switch references. Never rewrite historical
  recipes/receipts. Data IDs resolve relative paths beneath an explicit root, not worktree/date paths
  or permanent junctions. Account for copy overlap within the authorized 500,000,000,000-byte E budget.
- Reuse the existing command spine, dataset resolver and gate registry. No new product owner,
  compatibility layer, UI layout/flow changes, shared-model changes or extra environment.
  Any necessary visible UI fix needs explicit confirmation before implementation.
- Technical work may check/install only a separately reviewed compatible prerequisite; no silent
  upgrade of the shared environment. Sosulski's minimum 4.58 GB archive may be considered after
  source/license/space preflight; Yang's 65.6 GB full corpus is not a default acquisition.
- Independent lanes may proceed while one needs external authority. At most two disjoint workers;
  primary owns catalog/storage/integration. No agent writes another lane's files.

### Implementation sequence

1. Inventory actual receipts, original/converted selections, paths, hashes and live use. Resolve the
   D-side E- sanitizer fallout and shared physical recordings; do not classify duplicates by filenames.
2. Consolidate the necessary task scripts into a tracked import-only runner using real
   Scan/Preview/Validate/Apply, waveform/channel/type/sample/class checks and fresh-service recipe replay.
   Preserve the existing three-case training/showcase contract rather than forcing all exports to train.
3. Establish one executable 147-entry catalog with pinned versions, selections, relative paths,
   identities, conversion settings, explicit choices, numeric tolerance and expected status.
   Generate the human inventory from this authority; no parallel hand-written current-status list.
4. Batch copy verified sources and formal BIDS into the durable hierarchy. Quarantine unknown identity.
   Keep manifests/provenance explicit for retained conversions whose original options/logs are missing.
   Run from new paths before updating formal references; no historical evidence rewriting.
5. Investigate Rozado2015/Zhang2017/Tavakolan2017 prerequisites, Martinez acquisition, Sosulski/Yang
   sampling, BNCI2015_006/BNCI2016_002/BNCI2022_001 loader failures, Triana fiducials and BNCI2019 units.
   Reproduce pinned failures, prefer attributable upstream fixes, do not guess events/coordinates/units.
   Newly resolved entries join the required baseline only after full actual verification.
6. Bind the recurring requirement to docs/validation/README.md and the existing
   scripts/dev/handoff_gate_spec.py mechanism. Normal CI tests catalog/runner/failure semantics;
   the corpus gate runs natively against retained Windows data without repeated public downloads.
7. Run the full baseline once with the formal runner, then fixed representative normal-wizard paths.
   Review actual data/publication/migration risks independently, complete same-source CI/native gates,
   and hand off one integrated Windows version with PowerShell log. Do not merge automatically.

### Focused validation and stop condition

- File identities and full selected-run waveforms, channel order/types, event class/sample tuples,
  fresh recipe replay; source STIM interval shifts and converter ID changes remain explicit.
- Missing input, changed hashes, dropped/retyped channels, event offset, lost recipe choice, stale
  source/environment/registry resume, timeout or unexecuted required entry must fail closed.
- Preserve a failure attempt on successful retry. Resume only under identical candidate/environment/
  catalog/input identities; source change requires current-source execution evidence.
- GUI matrix covers ordinary EEG and BIDS, internal/external/no labels, multiple subjects/sessions,
  dense events, recipe reopen, back/edit/review, cancel/retry and recovery without partial publication.
  Grounded representative classes reach epoch/small training; one-class data stays correctly blocked.
- Scope-complete requires portable verified data mappings, repeatable runner, complete disposition,
  no baseline regression and final applicable exact-source evidence. No all-corpus/scientific/Assistant
  readiness claim. Do not stop at a slice, compaction or pending CI.
- Cleanup is held until exact candidate targets are approved and no live reader references them.
  If required migration/verification needs unavailable authority, complete independent work and report
  the precise missing decision instead of bypassing safety.

### Current checkpoint / next action

Implementation is committed on the existing task branch (Git is the authority for exact SHA).
The new catalog/gate, real-command replay and copy-only helpers have 59 focused native Windows
tests passing together. Independent reviews closed promotion-downgrade, no-label verification,
root/ancestor junction and completion-receipt overwrite gaps. No product/UI code changed in these
new validation slices. None of this substitutes for the outstanding full portable corpus run.

**One heavy E task at a time.** Initial BIDS relocation session 57939 reached its 14,400-second
bound at 10:16:29 UTC (started 06:16:29 UTC), reporting wrapper code 124. Native inspection confirmed
all six owned processes absent; no child is left writing. It completed 94/127 operations (27.52 GB
of 40.19 GB); Jeong's unpublished `staging/relocate-trk3nem2` contains 61/84 files and 3.936/5.279 GB
by metadata only. Preserve it unchanged and retain `portable-case-relocation-attempt-1-timeout.json`.
The final completion receipt does not exist. This is slow-copy timeout evidence, not an import defect.
Use this idle boundary for the prepared three-case portable probe and bounded metadata inventory,
then continue the unchanged migration plan through the existing verified-copy owner/lock. Do not
disable checks, overwrite a live plan, delete partial staging or count copies as portable replay PASS.

Early portable probe v2 caught a runner-only internal-alias defect: internal import preserves raw
marker descriptions and publishes class aliases in per-recording epoch hints. The runner had compared
raw descriptions directly to semantic class names. A real-command fixture reproduced it (1 failed,
1 passed), then all 13 focused conformance tests passed after the bounded correction. Wrong aliases
still fail, excluded context stays non-class, and original annotations/waveforms must survive Apply
and fresh recipe replay. Independent review found no blocker. Fresh portable probe v3 passed
Mainsah2025_A, AlexMI and BNCI2014_001; this is shared-boundary evidence, not the full campaign.
Preserve v2 failure (its one-time probe exited zero despite the failed row; it is not a passing probe).
No product/UI behavior or expected source classes changed. The bounded mixed-source metadata
inventory is complete: original archives/extractions in `source`, `forenzo-source`, `kojima-source`,
`liu2024-source`, plus `zhang-source/MNE-Zhang2025-data` are now included in the prepared source
planner. Zhang's generated BIDS sibling stays in the separate BIDS plan. Preserve Kojima's possible
flattened duplicates until content identity is proven; no filename-based deletion. The E public-fixture
directory is absent and must be populated from the already hash-verified D cache. No native Python
writer remained at the restart preflight. Continue the unchanged migration plan with verified reuse.

Evidence/artifact entry points (all beneath this task's `build/dev-artifacts` unless stated):

- `portable-case-relocation-plan.json`: all 127 initial cases, complete input hashes and choices.
  `portable-case-relocation-completed.json` appears only after every copy/hash operation and input
  manifest publication; it does not certify portable replay. Do not overwrite the occupied plan.
- `catalog-case-drafts-local/cases-v3` and `catalog-case-drafts-bound`: all 127 original bindings.
  Includes source-bound ERP/Romani choices and actual Thielen2021 recipe, not the wrong dataset alias.
  `receipt-index.json`, `receipt-snapshots` (78 cited contents), `saved-choice-index.json`
  (363 historical recipes) retain evidence. Historical recipes must not be rewritten.
- `catalog-case-drafts-new`: BNCI2015_006, Tavakolan2017, Zhang2017 and Sosulski2019 passed
  independent source/conversion checks and selected-run actual Commands plus fresh recipe replay
  on D (1734, 60, 24 and 90 events respectively). Tavakolan checks four sessions; Zhang checks 15
  runs; Sosulski checks two Run 2 trials with distinct non-60 ms SOAs. These are representative
  selections, not complete cohorts. E replay/promotion remains outstanding.
- `remaining-eleven`: original acquisition, failed attempts, exact source/conversion proofs and
  process-local repair scripts. Zhang's official archive is 1.755 GB with publisher MD5 and SHA-256.
  Sosulski's official per-subject archive is 415.77 MB with publisher SHA-256 and CC-BY-SA-4.0;
  the 4.58 GB aggregate was not acquired. Original BCI2kReader wheel works through isolated task
  sys.path; no shared install or compatibility patch was needed.
- `retained-source-roots-v2.json` and `retained-additional-source-roots-v1.json`: size-only original
  source-location inventory, not identity proof or globally complete mixed-staging coverage.
  D `a-cache`, `a-source`, `guttmann-loader-root`, `brandl-loader-source` and
  `legacy-mi-staging` are aliases, not extra physical copies. Metadata-only v1 followed root
  aliases and timed out; its counts are invalid. It never modified data.
- `dside-source-copy-plan-v2.json`: content-bound 16 physical source trees and three original
  archives, 41.62 GB. Separates Jeong's original ZIP and subject extraction from the 725 MB
  acquisition temporary file (retained in place, not promoted). Original v1 plan is historical.
  `plan_eside_source_copy.py` prepares the combined source plan after the BIDS writer is idle;
  it excludes the proven generated `legacy4-bids-route-20260913` and already canonical sources.
  `apply_source_copy_plan.py` uses the existing copy helper/lock and exclusive completion.
  Neither E source planning nor copying has run. Original/failed evidence remains protected.
  Source planning also compares full file-name/size/hash maps against the completed BIDS plan:
  native BIDS originals can share an already verified canonical BIDS tree instead of writing
  another identical source copy. Original-prefix provenance and separate export rows stay intact;
  application of the source plan rechecks both trees before accepting reuse.
- Independent source-preservation review found a concrete mapping gap: existing
  `evidence/moabb-ten-20260913/{source,forenzo-source,kojima-source,liu2024-source,zhang-source}`
  contains original archives/extractions referenced by retained fidelity receipts, but only Brandl
  was in the E plan. `retained-mixed-source-roots-v1.json` now records the bounded metadata inventory;
  the prepared source planner includes the original roots/child described above. This closes the
  planning coverage gap, not the still-outstanding hash/copy proof. No deletion or reacquisition.

Queued work, in order:

1. The three-case early portable probe v3 passed after the alias-verification repair above.
   Finish the 127 BIDS copy with verified reuse of completed destinations after the idle metadata
   check. Keep the original attempt's incomplete staging and failure record unchanged.
2. With E idle, execute `remaining-eleven/convert_retained_remaining.py` separately for
   BNCI2016_002, BNCI2022_001 and Yang2025 into fresh D outputs. The first fixes a reproduced
   marker row/column indexing error. BNCI2022 fixes lower-case trigger lookup and verifies actual
   zero-to-nonzero pulse starts against the retained 1152-segment evidence; unexpected adjacent
   nonzero transitions fail closed. These are structure/outcome events, not four difficulty labels:
   preserve annotations, use explicit no-label import and retain the supervised missing-class block.
   Yang has three CRC-verified original sessions; prior overlapping E output is incomplete despite
   a PASS receipt, is invalidated/preserved, and must not be reused.
3. Run `verify_new_dside_cases.py` with fresh output per candidate. Regenerate/apply the separate
   new-only relocation plan only when idle; portable-check newly resolved cases before promotion.
4. Complete original-source and necessary evidence consolidation within 500 GB, hash-check targets
   and preserve originals. Current source plans are not successful migration receipts. Optional
   questions about another SSD or a reviewed E-in-place move are not blockers: without a response,
   continue the approved copy/verify/preserve-original strategy, not unapproved moves/deletions.
   Also check `datasets/public-fixtures` with the existing pinned fixture verifier against retained
   D fixtures; do not assume this cache is already consolidated or download it again. The prepared
   `stage_import_provenance.py` preserves historical recipes, task-local prerequisites and exact
   runner/catalog/lock bytes. Execute this packaging only after the portable catalog is bound and
   committed (the script rejects unfinished bindings/dirty tracked source); its source-commit
   reference is not a standalone application bundle.
   Retained D fixtures passed the existing `required-ci` (205,255,918 bytes) and
   `teacher-preflight` (277,106,963 bytes) hash verifiers. The broader optional `all` profile
   stopped on missing P300 `sub-002`; preserve that distinction rather than downloading all
   profiles or calling an optional missing extra a required-gate pass.
5. Bind the final portable manifests/catalog, generate the human inventory, then freeze the candidate.
   Fetch origin/main before the full campaign. Run every required case, representative native Windows
   wizard/source-diverse gates and same-head CI without replacing them with old evidence. Keep source
   stable during the final campaign; failed attempts remain available. Final delivery is one integrated
   Windows handtest with PowerShell log, not a slice/CI/compaction checkpoint.

Remaining dispositions must stay honest: nine rights entries remain deferred (no new acquisition,
terms acceptance or contact); native Rozado archive/metadata requests return HTTP 403, and the
correct official Martinez subject URL (sequence 11) still times out
(`remaining-eleven/final-access-preflight-v1.json`). Triana official conversion remains blocked on
missing fiducials; BNCI2019 source EOG units remain unresolved. Never infer coordinates/units/classes
or reduce the pinned denominator to obtain PASS. Do not promote the four D-verified candidates
until portable evidence exists, or claim original-source consolidation from BIDS copies alone.
`remaining-eleven/bnci2019-unit-authority-review.md` retains the additional originating-lab
description/installed-loader check: shared acquisition hardware is not an explicit stored EOG
unit calibration. No additional source acquisition, rescaling or promotion followed that check.

## Closed baseline

Quality-baseline closure was accepted and merged via
[PR #140](https://github.com/hxin-an/XBrainLab/pull/140). Its implementation/evidence history stays in
Git/PR, not active dispatch. Known Assistant limitations below remain deferred.

## Candidate — Assistant reliability repair plan (not active implementation)

Goal: reliable selection and parameter-collection continuity with no unexpected workflow side effects.
LOC, static pass, literal prompt assertions or one improved score are not completion criteria.

1. **Mechanism audit before choosing a fix.** Trace baseline/retained failures from full rendered input/
   RAG through raw output, parser, capability/provenance, typed receipt, GUI terminal and visible response.
   Separate intent errors, missing clarification fields, invalid/stale admission and evaluator assumptions.
   Reproduce a bounded set through normal ChatPanel with real execution, using no patient data.
   No Host intent guessing or new model experiments in this diagnostic phase.
2. **Approve a repair boundary.** Select one evidence-backed hypothesis and existing owner. Explicitly
   decide behavior for unspecified/multiple actions, missing/partial values, correction/cancel and
   unavailable tools. Tool/schema/confirmation/visible-flow or model/RAG changes require separate
   approval; current source/tests do not ratify target. A larger model is neither proven necessary nor
   authorized. No generic evaluator platform, control plane or parallel state owner.
3. **Separate development and acceptance.** Keep frozen 81/scorer unchanged as regression evidence.
   Before implementation, define supplementary development cases and disjoint reviewer-owned holdout
   by failure family. Never tune on the holdout or shrink its denominator; disclose prior exposure to
   frozen cases. Reuse existing runners, review any necessary bounded extension, and agree a candidate/
   resource budget before execution. Do not repeatedly add two more prompt attempts after failure.
4. **Implement/review one coherent repair.** Prefer deletion/reuse; test failing observable behavior
   through actual owners, then passing behavior. Mock external inference only in unit tests; real-model/
   native evidence cannot substitute fake generation or preapproved GUI terminals. Independent reviewer
   checks mechanism, meaningful tests, complexity and scope, not only summary.
5. **One integrated acceptance.** Require 36/36 positive, 10/10 explicit origin, 5/5 missing guards,
   5/5 direct clarification admission, 24/24 product no-action and 7/7 clarification. Holdout must show
   zero unexpected execution/confirmation/navigation/mutation and correct authorized continuations.
   Separate raw-model/Host/product outcomes. Then same-source normal ChatPanel→GUI→Command journey,
   relevant cancel/stale cleanup, applicable CI and one final Windows GUI/English Assistant acceptance.
   No Stable/generalized-safety claim from bounded cases alone. Unsupported mechanism or exhausted
   budget means a documented decision checkpoint, not weaker gates or automatic extra prompt edits.

This proposal does not block the explicitly revised cleanup scope or certify Assistant readiness.
New implementation begins only after diagnostic outcome, scope and budget are approved.

其他候選方向見 [Roadmap](roadmap.md)；不宣稱 Assistant Stable 或零缺陷。
