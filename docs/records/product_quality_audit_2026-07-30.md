# Product Quality Audit - 2026-07-30

This record is the evidence ledger for the product-quality closure goal. It is
not a replacement for `docs/current.md`; current truth must be copied back to
the canonical documents after each validated slice.

Baseline:

- branch: `ux/assistant-product-v1`
- commit: `3869aaef73acf3fb30ce95d15868c2abcf17c6f5`
- baseline worktree: clean and pushed
- protected local files: repo-root `settings.json`, `.vscode/settings.json`
- excluded parallel work: dirty `stabilize/windows-public-beta` worktree

Status meanings:

- `open`: reproduced or source-verified and not fixed
- `in progress`: owned by the active closure goal
- `verified`: fixed and protected by focused plus regression evidence
- `external acceptance`: automated closure is complete but Windows human
  acceptance remains

## Architecture

| ID | Severity | Finding and evidence | Required closure | Status |
| --- | --- | --- | --- | --- |
| ARCH-01 | P0 | `QtObserverBridge._dispatch()` reports success without checking whether the consumer rendered the publication. `AgentManager` also drops the renderer's false result. A terminal training event can therefore be released before the corresponding revision is visible. | Acknowledgement-requiring consumers return an explicit boolean; only `True` acknowledges the revision. Protect no-render, delayed-render and exactly-once terminal delivery. | open |
| ARCH-02 | P1 | Application code still constructs controller adapters through `Study.get_controller()`, so the nominal application layer depends on an outer UI/controller layer. | Move one command family at a time to manager/domain ports. Controllers become outer adapters only. Add an import/source guard. | open |
| ARCH-03 | P1 | Product `CommandResult.runtime` / `local_payload` can expose live Raw, Epoch or generator objects across application and Qt/thread boundaries. | Replace product object payloads with immutable detached query/render DTOs. Remove product `include_objects` paths. | open |
| ARCH-04 | P1 | State-changing UI refresh can arrive through command-result refresh, controller observers and revisioned application publication. Suppression ledgers mask multiple truths. | Make revisioned application publication the single state-changing refresh truth. Keep progress as transient events only. | open |
| ARCH-05 | P1 | Product panels still require broad controller bundles instead of narrow query/publication/action ports. | Convert panels incrementally and keep compatibility only outside the product path. | open |
| ARCH-06 | P2 | `ApplicationService`, `LLMController`, `AgentManager`, Data Import and Dataset actions are large responsibility aggregators. | Extract lifecycle, dispatch, runtime and presentation slices behind behavioral tests; do not refactor by line count alone. | open |
| ARCH-07 | P1 | Legacy load/label commands remain available in the default automation catalog. | Exclude legacy commands by default; compatibility requires an explicit opt-in and cannot become readiness fallback. | open |
| ARCH-08 | P1 | Some readiness/capability paths can fall back when application publication is absent. | Real Study product contexts fail closed when publication or capability truth is missing. | open |

## Security, Privacy and Resources

| ID | Severity | Finding and evidence | Required closure | Status |
| --- | --- | --- | --- | --- |
| SEC-01 | P0 | Training/evaluation persistence uses `torch.load(..., weights_only=False)` before validating the loaded type. | Introduce a versioned safe artifact format: JSON manifest/scalars, NPZ numeric arrays with `allow_pickle=False`, and `weights_only=True` state dicts. Product rejects legacy unsafe records with a clear migration boundary. | open |
| SEC-02 | P0 | Free-form subject metadata can become part of a training output path. | Preserve display metadata separately; create a filesystem-safe slug plus stable short hash, reject separators/control/dot segments/reserved names, and verify the resolved output remains under the authorized root. | open |
| SEC-03 | P1 | RAG can initialize an unpinned embedding model without first-run consent, quota preflight or offline-only runtime. Vector data is stored under the package tree. | Pin `sentence-transformers/all-MiniLM-L6-v2@1110a243fdf4706b3f48f1d95db1a4f5529b4d41`, use the Granite consent/cache policy, run with `local_files_only=True`, and store vectors in the user data/cache directory. Missing cache disables RAG without breaking Assistant. | open |
| SEC-04 | P1 | Local model loading has no final RAM/VRAM admission despite catalog estimates. | Run centralized resource admission before `from_pretrained`; blocking results prevent load, OOM returns a recoverable UI state and releases cache. | open |
| SEC-05 | P1 | Assistant Markdown link activation can pass arbitrary URL schemes, including local-file-like targets. | Allow HTTPS with host confirmation. File artifacts require a typed host-created action. Reject `file:`, `data:`, `javascript:` and custom schemes. | open |
| SEC-06 | P1 | Lexical path validation may be bypassed by POSIX symlinks or Windows junction/reparse points. | Resolve final identity consistently and reject or containment-check links/reparse targets under the selected root. | open |
| SEC-07 | P1 | Logs and exception paths can expose complete private EEG paths and subject identifiers. | Add centralized redaction, basename/hash path display, opt-in detailed diagnostics, retention and permissions policy. | open |
| SEC-08 | P2 | Directory enumeration and model downloads do not have complete bounded-consumption controls. | Use bounded `os.scandir`, deadline/cancel/truncation, staged downloads, streaming quota/free-space checks and partial cleanup. | open |
| SEC-09 | P1 | Product model choices retain legacy Phi entries, including a `trust_remote_code` path. | Product selection becomes exact Granite 3.3 2B only. Existing protected settings receive a migration message; no silent fallback and no automatic rewrite. | open |
| SEC-10 | P1 | RAG/context data are not consistently encoded as untrusted data. | Use bounded structured data with source labels; strip control characters/private paths and keep data outside instruction/policy fields. Add injection regressions. | open |

## Functional Correctness and Validation

| ID | Severity | Finding and evidence | Required closure | Status |
| --- | --- | --- | --- | --- |
| FUNC-01 | P0 | Stop can interrupt after an optimizer step without advancing the current holder. A later Start clears the interrupt and can resume the cancelled plan before the new plan. | Define Stop as terminal cancel. Mark the admitted plan's current/remaining holders cancelled and advance the queue. Resume is not implicit. | open |
| FUNC-02 | P1 | Training plan IDs use second resolution and output directories use `exist_ok=True`, allowing collisions and stale result reuse. | Use timestamp plus UUID and exclusive directory creation. No implicit resume without a future complete manifest/state protocol. | open |
| FUNC-03 | P1 | The nominal full-pipeline test constructs epochs/splits directly and mocks persistence, so it does not prove the user workflow it claims. | Rename the existing scope and add a real ApplicationService FIF import-to-visualization smoke without persistence mocking. | open |
| FUNC-04 | P1 | The dashboard can pass while required public fixtures are skipped. | Handoff/release profile validates a fixture manifest first and fails on skip, xfail or deselection. | open |
| FUNC-05 | P1 | Execution smokes do not prove event-to-label correctness, split disjointness or held-out predictions. | Add a deterministic oracle dataset with explicit semantic assertions and finite output checks. | open |
| FUNC-06 | P1 | Current UI/Granite evidence is not consistently bound to the clean candidate commit and some screenshots disagree with current source. | Regenerate exact-commit artifacts containing commit, dirty state, environment, generator, claims and limitations. | open |
| FUNC-07 | P1 | Stop/restart lacks a barrier test at the vulnerable optimizer-step boundary. | Add a deterministic barrier regression and verify only the new plan runs after Stop. | open |
| FUNC-08 | P2 | Sleep-EDF and CHB-MIT sidecars are raw-only evidence but can be overread as label support. | Keep explicit capability boundaries in reports and documentation. | open |

## Assistant and Agent

| ID | Severity | Finding and evidence | Required closure | Status |
| --- | --- | --- | --- | --- |
| AGENT-01 | P0 | Native generation timeout is published only after the worker exits, while the local backend performs an unbounded join. UI can remain `Stopping` forever. | Run Granite in a supervised subprocess. Allow a short cooperative cancel grace, terminate the worker on timeout, fence the turn, show recoverable restart-required state and bound application close. | open |
| AGENT-02 | P1 | Endpoint selection can depend on set/hash order when multiple workflow endpoints share a rank. | Choose highest workflow order, then last textual mention; ask for clarification when intent remains contradictory. Prove across hash seeds and word orders. | open |
| AGENT-03 | P1 | Conversation context keeps only a small visible suffix and transcript growth eventually hard-blocks. | Add turn-bound archive/pruning, explicit unresolved-reference clarification and a long-session soak with external GUI state changes. | open |
| AGENT-04 | P1 | Product evidence for Granite is a narrow host-assisted workflow and is stale relative to the clean source. | Re-run exact Granite, secure offline RAG, confirmation/error/retry/cancel and long-session product evidence. Do not call it thesis accuracy. | open |
| AGENT-05 | P2 | Text glyphs are used for toolbar actions and have inconsistent accessibility/DPI behavior. | Use standard icons, tooltips, accessible names and narrow/high-DPI validation. | open |
| AGENT-06 | P2 | Turn orchestration, tool attempt lifecycle, process ownership and Qt presentation are concentrated in large controller/manager classes. | Extract `TurnOrchestrator`, `ToolAttemptSession` and `RuntimeProcessOwner`; keep AgentManager as Qt adapter. | open |

## UI and Product Experience

| ID | Severity | Finding and evidence | Required closure | Status |
| --- | --- | --- | --- | --- |
| UI-01 | P1 | Opening Assistant can shrink Dataset content to an unusable width while a fixed aggregate sidebar remains visible. | Add responsive behavior: move aggregate details to a `Data Summary` tab/drawer below the breakpoint. | open |
| UI-02 | P1 | Disabled Start Training does not explain the first blocking prerequisite. | Add a compact readiness checklist for Split, Model and Settings with a direct next action. | open |
| UI-03 | P1 | Match Labels exposes internal `Role` terminology beside user-facing `Use as`. | First layer uses task language only; internal role/evidence moves to report/advanced. Recipe navigation says `Go to Match Labels`. | open |
| UI-04 | P2 | Post-import next action is only visible through low-salience status feedback. | Show one contextual `Continue to Preprocess` or `Create epochs` action after successful import. | open |
| UI-05 | P2 | Preprocess plots do not explain raw/processed/event/excluded visual encodings. | Add a compact legend without resizing the stable preview area. | open |
| UI-06 | P2 | Visualization lacks persistent dataset/model/fold/run/grouping provenance. | Add a compact provenance bar or details action without restoring the removed verbose fixed row. | open |
| UI-07 | P2 | Aggregate Information exposes engineering labels and many unavailable values. | Hide absent rows and use domain language such as EEG epochs, epoch start and high-pass filter. | open |
| UI-08 | P2 | Training epoch and EEG epoch language is ambiguous. | Apply explicit terminology in user-facing copy and reports. | open |
| UI-09 | P1 | Existing screenshots do not consistently prove narrow layout, DPI, Assistant dock and dialog geometry against exact source. | Capture full-window artifacts at required sizes and 100/125/150% scaling; main agent inspects every required image. | open |
| UI-10 | P2 | Product surfaces have inconsistent hierarchy, disabled/destructive actions, empty states and table/header/selection styling. | Introduce scoped shared product components/tokens and perform a same-class sweep; do not globally rewrite the theme. | open |

## Documentation and Repository Hygiene

| ID | Severity | Finding and evidence | Required closure | Status |
| --- | --- | --- | --- | --- |
| DOC-01 | P1 | Branch/handoff instructions disagree about the active candidate and stabilization line. | Publish one current integration/handoff rule and update all canonical entry points. | open |
| DOC-02 | P1 | Homepage/current/now disagree on whether the candidate is closed, awaiting re-audit or handoff-ready. | Separate automated candidate truth from Windows acceptance and use the same wording everywhere. | open |
| DOC-03 | P1 | Docs claim one worktree while Git has three; branch inventory and test totals are stale or contradictory. | Generate inventory/evidence from exact commit and avoid manually duplicated totals. | open |
| DOC-04 | P1 | `docs/validation/README.md` mixes current truth with dated history and contradictory static-analysis results. | Keep concise current gates and move dated evidence to records. | open |
| DOC-05 | P2 | Active queue and old goal documents still dispatch completed/MCP/legacy work. | Retain one active goal; remove stale current goal files after integrating useful constraints. Git history remains the archive. | open |
| DOC-06 | P2 | Current artifacts contain duplicate screenshot groups and an outdated index. | Keep one canonical artifact per state/viewport, regenerate the index and record provenance. | open |
| DOC-07 | P2 | MkDocs navigation surfaces huge worklog/implementation history while hiding decision-oriented content. | Keep current/architecture/validation prominent and move logs to a records/history area. | open |
| DOC-08 | P1 | Repo-local skills still mention BackendFacade/MCP as active architecture in places. | Sweep `.agents` instructions and align them with the current ApplicationService/local-only/MCP-retired truth. | open |

## Automated Exit Conditions

The active goal cannot finish while any code-controllable P0/P1 item is open.
It also requires:

1. focused regression and same-class/source guards for each repaired class;
2. real ApplicationService happy path plus deterministic oracle coverage;
3. strict fixture manifest and multi-dataset gates with zero hidden skips;
4. exact Granite plus secure offline RAG walkthrough;
5. reviewed UI artifacts at narrow/full/DPI layouts;
6. Ruff, full Basedpyright, architecture, pytest, MkDocs and quality dashboard;
7. clean and pushed integration branch with protected settings untouched.

Passing these conditions creates a Windows handoff candidate. Product completion
and merge to `main` still require user acceptance.
