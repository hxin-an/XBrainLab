# Backend architecture

最後更新：`2026-09-12`

這份文件說明目前 source 的 backend 邊界與責任，不是功能清單、歷史改造紀錄或本次施工的
驗收紀錄。可對外宣稱的產品能力以 [current.md](../current.md) 為準；正在施工的範圍、
next step 與 stop condition 以 [planning/now.md](../planning/now.md) 為準；exact-source
evidence、CI 與手測的含義以 [validation README](../validation/README.md) 為準。

## Boundary in short

```text
Desktop UI / Local Assistant / approved scripts
                 |
          typed Command and query API
                 |
 ApplicationService: admission, command envelope, lifecycle, publication
                 |
 Study-owned domain ports and focused application services
                 |
 dataset, preprocessing, split/training, results and visualization state
```

`ApplicationService` 是 GUI、Assistant 與受支援 scripts 共用的產品 command spine。它不是第二
個 dataset 或 training state owner：`Study` 的 domain ports 仍保存可變資料與 domain operations，
而 application layer 決定 command 是否可進入、如何以同一 error/result envelope 回覆，以及何時
把一致的 view publication 交給外界。lower-level `Study`/manager tests 可以直接建構 domain
objects，但產品 UI mutation 不能繞過這條 spine。

產品入口不得建立自己的 capability policy、confirmation authority、async lifecycle 或可變 state。
Assistant 的 tool contract 也只能經過相同 command/query boundary；已退役的 MCP executable
surface 不在 current architecture 內。

## Current responsibilities

| Area | Current owner and boundary |
| --- | --- |
| Command admission and result envelope | `backend/application/service.py:ApplicationService` serializes product commands, maps failures to `CommandResult`, owns confirmation/admission boundaries and exposes read APIs. Its command handlers compose focused services instead of duplicating their mutations. |
| State, capabilities and publication | `StateSnapshotService` builds serializable state from domain ports; `ApplicationViewCoordinator` commits coherent revisions; `ApplicationPublicationLifecycle` and `ApplicationViewEventPublisher` publish them. `get_state()` takes the command lock and strictly rebuilds state; `get_capabilities()` reads the effective policy from a publication; `get_view_publication()` returns committed truth and may only recover an unusable publication when a safe try-lock permits it. |
| Query-only access | `ApplicationService` owns the non-blocking published `state` and `data_summary` fast paths. `QueryStateCommandService` handles the other typed queries (lists, label targets, diagnostics, suggestions and history) after the command spine obtains its try-lock; a busy mutable-object query returns a recoverable retry result, never an independent UI cache. |
| Import and data interpretation | `DataInterpretationCommandService` owns scan, review, preview, validation, recipe and apply orchestration; `DataInterpretationApplyService` performs reviewed metadata/label application. `DataInterpretationSessionState` carries the staged review session, while the command spine retains admission and result policy. |
| Preprocess, epoch and montage | `PreprocessCommandService` owns preprocessing commands and pipeline invalidation. `BidsMontagePreparationCoordinator` prepares BIDS montage promotion and only commits through the application publication boundary. |
| Split and training | Dataset generation first materializes and audits a saved split as an unpublished candidate. Training then admits resources for that candidate, commits the verified split and starts training; failures preserve or restore the earlier publication. Training configuration, preview receipts and terminal lifecycle stay scoped to this workflow. |
| Evaluation, visualization and saliency | `AnalysisCommandService` owns those analysis commands. Detached render publishers/work controllers publish only against an admitted, current training/publication boundary. |
| Reset, close and cancellation | `LifecycleCommandService`, `ApplicationShutdownLifecycleCoordinator`, `OwnedWorkRegistry` and the synchronous-training coordinator own reset/close/terminal-delivery seams. No view owns worker lifetime. |

Epoch dialog setup and command execution share the validated setup builder in `PreprocessCommandService`.
Interpretation, dataset generation and training command services are cached lazily on first use;
handler bindings and state/reset callbacks do not materialize those owners during cold queries.
There is no method-by-method lazy proxy layer.

`TrainingOperationMonitor` owns the physical monitor threads for admitted training and saliency work,
including exact producer-generation matching and physical-exit joins. `OwnedWorkRegistry` remains the
operation-state authority; `ApplicationService` retains admission, result decoration and background-wait
ordering. A terminal operation snapshot does not by itself prove that its monitor thread has exited.

For detached model summaries, `AnalysisCommandService` captures the exact plan/run and model inputs,
then revalidates those identities and refreshes the result catalog. `ApplicationService` retains the
two lock/admission boundaries, trainer/publication freshness, cancellation and final result envelope;
model construction/inspection runs outside the command lock. Unrelated completed folds may refresh the
catalog, but a substituted summary target cannot publish the old model text.

The existing montage coordinator normalizes and validates a manual override before selection;
`ApplicationService` retains lock/admission, trainer freeze/no-op, live Epoch projection and publication.
`DatasetStateService` owns the preprocessed-first/loaded-fallback detached summary row selection used by
initial and subsequent view publications; consumers do not rebuild that selection policy.

The table names ownership, not a promise that every class is small. `ApplicationService` remains an
integration point with substantial composition responsibility; new behavior should first reuse the
focused owner above, and must not turn it into a second policy or state layer.

## State, publication and lifecycle contracts

- A product mutation is admitted under the application command boundary. Downstream-replacing work
  captures pipeline identity and either commits a coherent replacement or restores/marks the result as
  failed; it does not expose a half-applied dataset/training transition as success.
- The view publication combines a state snapshot, training read boundary and revision/generation.
  Published state and data-summary queries consume committed truth without waiting on a mutation. Other
  object-bearing queries must acquire the command try-lock or fail recoverably; `get_state()` is the
  strict refresh API, not an interchangeable non-blocking reader.
- Detached preparation and rendering check freshness at their commit boundary. Cancellation is owned and
  cooperative: the registry can request cancellation and close waits only for defined quiescence points;
  third-party numerical work cannot be promised instantaneous interruption.
- Close is idempotent and fences further command admission before releasing observers and runtime-owned
  work. A closed service returns a stable rejection rather than silently reconstructing application state.
- Training start does not publish a merely previewed split. Candidate preparation, resource confirmation,
  materialization and rollback diagnostics preserve the distinction between a rejected candidate and a
  committed run.

## Data and result semantics

Import is a reviewed workflow, not arbitrary file mutation:

1. Source discovery and resource admission establish the selected files and bounded reader scope.
2. Preview/validation produce a reviewed interpretation candidate, including explicit label and metadata
   decisions. Content/path identity checks prevent an accepted review from being applied to changed input.
3. Apply updates admitted loaded EEG carriers and uses atomic/rollback-aware label operations. A failed
   rollback is reported as unknown state instead of being presented as a safe retry.
4. Preprocess/epoch replacement invalidates downstream training through the pipeline transaction.

Formal BIDS selection and reviewed non-BIDS mapping use the same product boundary, but this is not a full
BIDS validator and does not imply support for every proprietary format. Event, label, epoch and scientific
interpretation limits remain product limits in [current.md](../current.md), not backend guarantees.

Split planning records the allocation/audit used by Train. The train path materializes that saved
candidate before resource preflight, then commits it only when admission succeeds; it does not treat a UI
preview as a result. Each completed run persists separate inference records for non-empty training,
validation and test loaders after checkpoint selection. An evaluation/render request binds one exact
plan/run-or-aggregate/split identity: a run never borrows another run's predictions, and an aggregate pools
only the requested split across its eligible completed runs.

`TrainRecord` owns result selection rather than exposing its raw storage map. The legacy primary `eval`
record remains the held-out compatibility/saliency record; split-qualified sidecars remain distinct.
`get_saved_evaluation_record()` returns only an exact stored split, while
`get_evaluation_record_for_split()` may use a matching primary record. Training history requires the exact
saved test record; Evaluation may use a matching primary fallback. Analysis, state and render code use
these named queries, preserving both artifact format and publication ownership. Evaluation, visualization
and saliency publish detached artifacts only when their source identity is current; their numerical or
scientific validity is outside this architecture contract.

## Persistence and artifact filesystem boundary

Training/evaluation persistence passes through `training/record/artifact_store.py`, not arbitrary object
pickles. Its versioned JSON manifest, non-pickle NPZ and tensor-only checkpoint formats are part of the
current artifact contract. The training record/result-query rules above select a record; they do not waive
artifact identity or integrity checks.

- One bounded IO operation retains and rechecks the full output-directory identity. A changed or substituted
  parent fails the operation rather than redirecting publication.
- POSIX artifact leaves are opened directory-descriptor-relative with `O_NOFOLLOW`; Windows uses native
  reparse-point-safe handles. Both reject non-regular and multi-hardlink leaves.
- Temporary leaves are exclusively created and a verified retained parent performs the atomic replacement.
  Readers use the same trusted-parent/regular-leaf checks, so a leaf substitution cannot be accepted between
  validation and publication.
- Source/training/result identity is validated before a result is considered current. This protection is
  distinct from the admission boundary for a user-selected pretrained weight or EEG source reader.
- Generated validation evidence belongs under ignored `build/` locations described in
  [validation README](../validation/README.md), not as product authority.

This is a bounded artifact filesystem contract, not a claim that Windows NTFS junction/reparse behavior has
received every real-machine acceptance scenario.

## Public diagnostic and log privacy boundary

`backend/utils/public_diagnostics.py` is the shared boundary for public logs, exception/result messages,
Assistant feedback and UI interaction outcomes. Public projection redacts full POSIX, Windows and UNC paths
to a display basename plus an opaque path reference, masks subject/participant/patient and BIDS `sub-*`
identifiers with process-local non-reversible references, removes controls/escape sequences, and bounds
recursive structured values. Product modules must not install a bypass file/stream handler or show raw
backend exceptions directly in a UI sink.

`CommandResult.to_internal_dict()` is the detached in-process projection. `to_dict()` is the compatibility
public-safe projection and delegates to `to_public_dict()`; exports, support output and Assistant payloads
must retain that public projection rather than expose internal diagnostics. Detailed disclosure is an
explicit controlled diagnostic mode, never a settings/UI toggle; it remains local-only, needs user review
before sharing, and must be removed after diagnosis. It is not an automatic-upload channel.

The default logger redacts before console/file delivery and uses bounded rotation: active `5 MiB` plus five
backups (about `30 MiB` nominal maximum). POSIX log directories/files are revalidated owner-only (`0700` /
`0600`). On Windows, the opened directory and each active/marker/backup log receive and read back a
current-user-only protected DACL; failure of owner/DACL/ACE/reparse verification disables the file sink and
keeps only redacted console logging. This does not claim protection from Administrator/SYSTEM, same-account
malware, ancestor-junction races, non-NTFS behavior or a substitute for Windows native acceptance. Detailed
logs must not be placed on shared or network locations.

## Artifact and diagnostic limits

The boundaries above prevent specified accidental disclosure/substitution paths; they do not establish
zero data leakage, a deployment security certification, or a complete platform security review.

## Current limits and change rules

- This is a desktop source baseline, not a signed installer, full clinical workflow, complete BIDS
  implementation, arbitrary-data/model guarantee or scientific certification. See
  [current.md](../current.md) for the supported product surface and limitations.
- Automated unit/source/integration evidence proves bounded contracts. It does not replace real-data
  diversity evidence, Windows native interaction, or user manual acceptance. A fresh product-source
  candidate follows the applicable exact-source process in [validation README](../validation/README.md);
  its currently pending work is recorded only in [planning/now.md](../planning/now.md).
- Existing domain controllers/adapters may remain behind `Study` ports or in low-level tests where they
  express domain operations. They are not a permitted alternate product command surface, and no retired
  facade/controller compatibility layer should be reintroduced merely for old callers.
- New backend abstractions need at least two real production callers or a necessary unsafe/external seam.
  They must remove duplicated policy in the same change and preserve the command spine, state publication,
  cancellation and privacy contracts above.

## Related architecture references

- [Architecture overview](README.md) provides the cross-layer map.
- [Data layer](data_pipeline.md) describes source/import/storage boundaries.
- [Assistant architecture](agent.md) describes the Assistant contract and its command-spine use.
- [Frontend architecture](ui.md) describes how views consume publication rather than own backend
  state.
