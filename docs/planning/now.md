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

**Post-candidate repair, 2026-09-13:** frozen candidate 8122d2ad completed the full native portable
campaign with 132/134 passed and two failures, so it is not a handoff version despite all 24 applicable
CI checks passing. Preserve `portable-full-8122d2ad-v2` and the earlier v1 Git-path admission failure.
Native Git needs process-local Windows GIT_DIR/GIT_WORK_TREE for this WSL-created worktree;
the exact candidate/main identities were verified, with no shared Git configuration change.

- Thielen2021 applies 37,800 labels but Save recipe exceeds the existing 1 MiB cap. Diagnose the
  serialized field sizes, add a focused red regression, and bound only proven regenerable evidence
  through the existing recipe serializer. Preserve all replay choices/content identity and the byte
  cap; no UI edit, guessed classes or case removal. Require fresh Thielen Commands and recipe replay.
  Repair is now implemented in the existing serializer: only derived anchor/duration value-count
  histograms are omitted. The two new regression cases failed before repair; all 19 directly related
  tests passed afterward, with no skips. Native `thielen-dense-recipe-replay-v1/result.json` passed
  actual Commands/save/fresh replay with 37,800 events, zero waveform error and a 52,513-byte recipe.
  Independent persistence review found no blocker; these focused results do not certify a new full run.
- Yi2025's portable draft omitted the label carriers and eight explicit class decisions present in
  its exact historical recipe; its empty expected-event list is also wrong. Rebuild only that case
  from the hash-bound saved choices and independent selected-run events, publish a new immutable
  manifest and update its binding after focused portable replay. Preserve old manifest/failure.
  Do not weaken product admission or replace labels with skip_labels.
  The repaired local draft passed focused replay (eight explicit classes, five events each), but
  publication is blocked by auto-review requiring explicit confirmation for the exact E write.
  The create-only target is
  `E:\XBrainLabData\datasets\manifests\import-cases-v1\Yi2025-09895cbabb7f.json`.
  Read-only preflight confirmed that target absent, the parent a normal directory, and the old
  `Yi2025-ba7340b85652.json` unchanged. Re-review with the approved plan and these checks was also
  denied. Do not retry or route through another tool; request the user's explicit publication approval.
  No new E manifest or catalog binding was written. Existing data and failure evidence are untouched.
- The historical 82,138,516-byte Thielen2021 recipe is required provenance but exceeds the general
  small-artifact selector. Review and preserve this exact hash-bound large file explicitly during
  evidence packaging; never silently omit it or raise the product recipe input cap.
  The task-local packager now selects only this exact size/SHA-bound large artifact explicitly;
  the general 32 MB file and 500 MB aggregate bounds remain. Packaging has not executed.
- After focused tests and independent data/persistence review, commit/freeze the repaired candidate
  and rerun the complete 134-case campaign plus exact-head CI/native wizard. Prior-head passes are
  history, not the new candidate's full evidence. Then finish the already prepared source/evidence
  copies and single Windows handoff. UI modification remains unauthorized.

The task branch owns the implementation; Git is the authority for exact source and dirty state.
No new product/UI source changed in the recurring-catalog/storage slices. Earlier focused evidence:
59 native tests together, then the real internal-alias defect reproduced and all 13 conformance tests
passed after correction. Internal raw markers and per-recording class aliases remain distinct.
Those runs do not replace the outstanding frozen full portable campaign.

Completed and protected:

- Initial 127 BIDS roots and case manifests copied/verified. Completion binds plan
  `636aaf45bf7d21ff8b478e56f711c068a2de4c2ddcf05fb70fb3bab505995cc1` and exactly 127 IDs.
  First attempt timed out at 14,400 seconds after 94 roots; preserve its failure receipt and
  incomplete `staging/relocate-trk3nem2` (3.936 GB by metadata) and older staging. Continuation
  session 73965 completed with exit 0; all six owned native processes were confirmed absent.
- BNCI2016 v1 failed with the original loader's KeyError because the instance captured its callable
  before replacement. Preserve v1 source/driver/failure; v2 constructs after binding and asserts
  identity. BNCI2016, BNCI2022 and Yang fresh conversions and D actual imports/replays then passed.
  BNCI2022 is explicitly no-label: 1,152 structural markers, not supervised difficulty classes.
  Yang checks three sessions but complete application replay selects the first recording.
- All seven new portable roots/manifests copied and replayed with actual Commands, complete
  selected-run waveform/channel/event checks and fresh recipes. New plan SHA-256
  `e7adf335e4ff6bca18aae94b7e0a6d395c891bad70bbebe14b9086190183b7bf`;
  `relocated-new-probe-v1/summary.json` binds every successful result.
  Preserve the unexecuted three-case predecessor plan and all original/failed data.
- The candidate catalog now binds all 134 required cases and promotes only the seven proved new
  entries. Nine rights entries and four remaining blockers stay visible. Preparation checked both
  completions, exact seven results and all actual E manifest hashes before tracked integration.
  The human inventory is generated from that catalog; this is not full campaign PASS.
- Required public fixtures copied from retained D to `E:\XBrainLabData\datasets\public-fixtures`.
  `public-fixture-copy-completed-v1.json` binds the copy plan and successful before/after
  `required-ci` and `teacher-preflight` checks. The optional `all` profile's missing P300
  sub-002 is retained as a distinct non-required finding; no repeated download or all-profile claim.

One heavy E task at a time. The bounded Wu2020 diagnostic completed with exit 0: the unchanged
1,458,751,813-byte input took 26.23 seconds (12.84 copy, 13.34 tree verification), with a 137.73 MB
peak working set. Existing copy owner/lock/full source and staging hashes remained enabled.
Preserve `staging/copy-buffer-probe-v1` and its diagnostic receipt for separately approved exact
cleanup. The old observed operation took roughly 26 minutes; cache/antivirus/external load were
uncontrolled, so no causal/general speedup claim. Use the measured 64 MiB buffer only in the
task-local source-copy process, retaining the same verification/publication owner. No D relay or
shared Python/product change. Source hash-planning session 10766 completed successfully.
`combined-source-copy-plan-v1.json` binds 53 source mappings, 49 unique tree operations and three
archives, requiring 102,748,932,711 additional bytes. Its SHA-256 is
`aabcf60fb5233b27a32f9a9dc5f8e5b9c0fdc5577369c04fea078b5976eb9b27`.
No bulk original-source copy has started. The focused Thielen process also exited successfully;
there is no remaining owned heavy task. Resolve the explicit E-publication authority blocker above
before switching the Yi binding or starting final campaign/storage publication.

Next, in order:

1. Independent review found no blocker in actual catalog/docs promotion semantics and seven
   content-bound replay receipts; all 16 focused catalog tests passed natively with no skips.
   The secret hook flags new public evidence checksums; only scanner-reported, reviewed values in
   the seven promoted entries are added as individual false positives, with no filter/exclusion change.
   Original-source hashing is complete; use the hash-bound combined plan rather than rerunning
   `plan_eside_source_copy.py`. It combines
   `dside-source-copy-plan-v2.json` (16 trees and three archives, 41.62 GB) with verified physical
   E roots. Include mixed `moabb-ten-20260913/{source,forenzo-source,kojima-source,liu2024-source}`
   and `zhang-source/MNE-Zhang2025-data`; exclude Zhang's generated BIDS sibling. Aliases
   `a-cache`, `a-source`, `guttmann-loader-root`, `brandl-loader-source`, `legacy-mi-staging`
   are not extra physical copies. Deduplicate only identical complete name/size/hash maps; native
   BIDS originals may reuse verified canonical BIDS with original-prefix provenance preserved.
2. Render the passive folder guide using `render_portable_locations.py`, from bound manifests
   only. Freeze/commit the candidate and fetch origin/main. Do not modify tracked source during
   formal evidence collection: the runner fingerprints all tracked files, source and environment.
   Run every one of the 134 required cases with `run_moabb_import_conformance.py` against E,
   a fresh output, one worker and existing case/gate bounds. Missing/failed/timeout cases fail closed.
   Run representative native Windows wizard evidence and use same-head CI for equivalent
   source-diverse/regression/platform/docs gates. Do not reuse old-head green checks.
3. Complete original-source bulk copies through `apply_source_copy_plan.py` and the existing
   verified-copy owner/lock; whole-E usage plus overlap stays below 500,000,000,000 bytes.
   Formal import evidence precedes long source copying to expose product defects earlier;
   this sequence does not waive consolidation before handoff. No original deletion/move.
   Preserve `retained_failures`, Jeong's acquisition fragment and incomplete Yang output.
4. Package required historical success/failure evidence and recipes with `stage_import_provenance.py`
   after catalog/source completion and a clean tracked candidate. It retains original bytes and
   mappings, exact runner/catalog/lock source, task-local prerequisites and historical receipts.
   Apply its evidence-copy plan with the same owner/lock, verify, and keep original recipes unchanged.
5. After exact-source applicable gates succeed and source/evidence mappings are complete, prepare
   the final manual checkout, open native Windows GUI with PowerShell as the sole live log, confirm
   responsiveness and provide a rerun command plus focused integrated handtest checklist.
   Never call a slice, copy completion, compaction or CI pending the requested endpoint.
   User manual acceptance and explicit merge approval are still required.

Artifact entry points are below this task's ignored `build/dev-artifacts`, unless E is explicit.
`portable-case-relocation-plan.json` and its completion own initial inputs;
`portable-new-relocation-plan.json`, its completion and `relocated-new-probe-v1` own the seven
new copies/replays. `portable-catalog-candidate-v1` retains preparation identity. `remaining-eleven`
retains exact originals, acquisition failures, source/conversion fidelity and task-local repairs.
`receipt-index.json`, `receipt-snapshots` and `saved-choice-index.json` retain historical evidence.
These are evidence/migration records, not a second product state or blanket cleanup authorization.

Remaining dispositions: defer Shin2017A/B, EPFLP300, Lee2024 AC/BS/DL/EL/TV and Liu2020BETA rights.
Martinez original subject URL sequence 11 times out; Rozado official archive and metadata return 403.
Triana lacks authoritative fiducials; BNCI2019 EOG stored units remain unresolved. No invented
coordinates/classes/scaling, bypassed access or automatic terms acceptance. NEMAR nm000239 is a
metadata-only alternative lead related to Martinez, not the pinned original-loader archive; it has
not been acquired or substituted and requires a provenance/scope decision before doing so.
Optional alternate-SSD or exact E-in-place move questions are unanswered, not blockers: continue
approved copy/hash/preserve-originals, not unapproved moves, repeated downloads or duplicate deletion.
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
