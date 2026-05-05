# XBrainLab Continuation: Backend / UI Boundary Cleanup

Date: `2026-05-05`

Use this as the next-run handoff for the product-completion work. Do not treat
the goal as complete.

## Current Branch

`codex/stabilization-autopilot`

Recent local commits:

- `backend: gate train confirmation in command layer` (current handoff slice)
- `assistant: filter legacy rag examples` (current handoff slice)
- `0e36405 assistant: neutralize legacy tool labels`
- `6e289ed ui: prefer interpretation next step`
- `27d3920 test: gate walkthrough resource smoke`
- `6bfd9a7 architecture: split preprocess command service`
- `2c5f1df architecture: split state query services`
- `8ca9a34 architecture: close ui service fallback bypasses`
- `fdbfb85 architecture: route training cleanup through commands`
- `e5c12fb architecture: extract data interpretation format boundaries`

Do not push.

## Protected / User Changes Left Unstaged

Leave these alone unless the user explicitly asks:

- `.agents/skills/README.md`
- `.vscode/settings.json`
- root `settings.json`
- untracked `.agents/skills/*` additions from the user

## What Changed In This Handoff Slice

Backend command boundary cleanup already completed before this continuation:

- `ApplicationService` is now mostly dispatch / capability-confirmation gate /
  result envelope.
- Data-table, preprocess, state/query services were already split before this
  handoff.
- Data Interpretation format capability taxonomy moved to
  `XBrainLab/backend/application/data_interpretation_formats.py`.

UI runtime / product-language cleanup:

- Dataset direct file import no longer calls controller import after successful
  `LoadDataCommand`.
- Preprocess reset now uses `ResetPreprocessCommand`; controller fallback only
  remains for mock / legacy `None` adapter paths.
- Training sidebar re-split cleanup now uses `ClearDatasetsCommand`.
- Training Clear History now asks confirmation and uses
  `ClearTrainingHistoryCommand`.
- Consolidated automated human-like walkthrough now gates close-time resource
  smoke. The latest artifact passes `26 / 26` phases, `20` screenshots,
  resource smoke `passed=True`, RSS growth `231628 KB` / limit `600000 KB`,
  Qt active thread `0`.
- ChatPanel / AgentManager visible next-step language now uses Data
  Interpretation as the data-entry main path: empty state shows
  `Scan data source`, raw-loaded state no longer suggests legacy
  `attach_labels`, and ChatPanel status rendering filters `load_data` /
  `attach_labels` / `import_labels`.
- Legacy compatibility tool fallback labels are neutralized to `Import data` /
  `Add labels to loaded data`; assistant visible summaries no longer say
  `Load EEG data` / `Attach labels`.
- RAG prompt context now shares the product data-entry boundary. `RAGIndexer`,
  `BM25Index`, and `RAGRetriever` filter examples containing `load_data`,
  `attach_labels`, or `import_labels`, including old Qdrant candidates that
  still exist in a user's local collection.
- Long-running `train` confirmation is now enforced by the backend command
  gate, not only by UI / agent convention. `TrainCommand` carries
  `confirmed`, unready train still returns precondition reasons, and
  backend-ready unconfirmed train returns `confirmation_required` without
  calling the training controller.

Docs updated:

- `docs/current.md`
- `docs/architecture/agent.md`
- `docs/architecture/backend.md`
- `docs/planning/now.md`
- `docs/planning/roadmap.md`
- `docs/records/implementation_log.md`
- `docs/records/worklog.md`
- `docs/validation/README.md`
- `artifacts/goal/continuation-2026-05-05-backend-ui-boundary.md`

## Validation Already Run

Latest successful gates from the completed slices:

```bash
git diff --check
timeout 300s poetry run ruff check .
timeout 300s poetry run basedpyright
timeout 300s poetry run mkdocs build --strict
timeout 300s poetry run python tests/architecture_compliance.py
poetry run pytest --capture=sys tests/unit/scripts/test_capture_human_like_product_walkthrough.py -q
poetry run pytest --capture=sys tests/unit/ui/chat/test_chat_panel.py tests/unit/ui/components/test_agent_manager.py tests/integration/ui/test_product_walkthrough.py -q
poetry run pytest --capture=sys tests/unit/llm/agent/test_controller.py::TestPipelineGate::test_legacy_load_summary_uses_neutral_product_language tests/unit/ui/chat/test_chat_panel.py::TestChatPanelCallbacks::test_product_status_updates_empty_state_and_chips tests/integration/ui/test_product_walkthrough.py::test_assistant_product_click_through_layout -q
poetry run pytest --capture=sys tests/unit/llm/rag/test_example_policy.py tests/unit/test_llm_backend.py tests/unit/llm/agent/test_assembler_stage.py -q
poetry run pytest --capture=sys tests/unit/backend/application/test_application_service.py::test_train_command_blocked_until_backend_ready tests/unit/backend/application/test_application_service.py::test_train_command_requires_confirmation_before_long_running_start -q
poetry run pytest --capture=sys tests/unit/llm/tools/test_application_surface.py::test_start_training_surface_preserves_backend_confirmation_boundary tests/unit/llm/agent/test_controller.py::TestOnUserConfirmed::test_approved_executes_and_finalises tests/unit/llm/agent/test_controller.py::TestOnUserConfirmed::test_approved_failure_triggers_retry tests/unit/ui/test_sidebars_and_components.py::TestTrainingSidebar::test_start_training_service_success_does_not_fallback_to_controller -q
poetry run pytest --capture=sys tests/unit/backend/application -q
poetry run pytest --capture=sys tests/unit/llm/agent tests/unit/llm/tools -q
poetry run pytest --capture=sys tests/unit/ui/test_sidebars_and_components.py::TestTrainingSidebar tests/unit/ui/training/test_training_sidebar.py tests/unit/ui/training/test_training_panel.py -q
timeout 420s env QT_QPA_PLATFORM=offscreen poetry run python scripts/dev/capture_human_like_product_walkthrough.py
```

Observed results:

- human-like walkthrough script tests: `11 passed`
- ChatPanel / AgentManager / product walkthrough focused suite: `75 passed`
- legacy label summary focused gate: `3 passed`
- RAG example policy focused gate: `5 passed`
- broader RAG / assembler focused gate: `31 passed`
- backend train confirmation focused gate: `2 passed`
- agent/application surface/UI confirmation adapter gate: `4 passed`
- backend application suite: `102 passed`
- agent/tool suite: `470 passed`
- training UI focused suite: `42 passed`
- consolidated walkthrough artifact: status `passed`, `26 / 26` phases,
  `20` screenshots, human desktop acceptance `not performed`
- full ruff: pass
- full basedpyright: `0 errors, 0 warnings, 0 notes`
- architecture compliance: `Architecture compliant!`
- MkDocs strict: pass with existing Material warning
- git diff check: pass

Known validation note:

- Focused basedpyright on the whole legacy
  `tests/unit/ui/components/test_agent_manager.py` file still reports
  pre-existing mock/QMainWindow typing debt. Full project basedpyright is clean.

## Next Recommended Work

1. Continue UI mutating-path audit.
   - Remaining `controller.*` hits are mostly read-only or `None` fallback, but
     verify Dataset sidebar channel selection / clear dataset, Dataset panel
     metadata edits, smart parse, remove files, Visualization saliency, and
     AgentManager montage against service-success no-fallback tests.

2. Continue legacy data-entry containment.
   - `load_data` / `attach_labels` should remain compatibility coverage, not
     product UI / agent mental model.
   - RAG prompt injection is now filtered, but the old gold-set content still
     needs a real rewrite into Data Interpretation positive / blocked /
     recovery examples.
   - Next useful audit: legacy real-tool tests, parser / verifier compatibility
     paths, and any visible transcript labels.

3. Continue Data Interpretation product work.
   - Mature import wizard editor, raw trigger selector, complex MAT/GDF anchor
     reconciliation, XDF / LSL stream parser, and real-data manual
     certification remain unfinished.

4. Keep product closure blockers explicit.
   - Windows human desktop acceptance, dual-monitor / DPI behavior, long real
     local-model desktop sessions, long-running ChatPanel workflow, interactive
     desktop 3D, and MCP HTTP / long-running job progress / cancel / recovery
     boundaries remain unfinished.

Do not mark product complete until those blockers have real evidence.
