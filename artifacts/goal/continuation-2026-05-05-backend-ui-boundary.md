# XBrainLab Continuation: Backend / UI Boundary Cleanup

Date: `2026-05-05`

Use this as the next-run handoff for the product-completion work. Do not treat
the goal as complete.

## Current Branch

`codex/stabilization-autopilot`

Recent local commits:

- `e5c12fb architecture: extract data interpretation format boundaries`
- `fdbfb85 architecture: route training cleanup through commands`
- `8ca9a34 architecture: close ui service fallback bypasses`
- `2c5f1df architecture: split state query services`
- `6bfd9a7 architecture: split preprocess command service`
- `102ddd3 architecture: split data table command service`

Do not push.

## Protected / User Changes Left Unstaged

Leave these alone unless the user explicitly asks:

- `.agents/skills/README.md`
- `.vscode/settings.json`
- root `settings.json`
- untracked `.agents/skills/*` additions from the user

## What Changed In This Handoff Slice

Backend command boundary cleanup:

- `ApplicationService` is now mostly dispatch / capability-confirmation gate /
  result envelope.
- Data-table, preprocess, state/query services were already split before this
  handoff.
- Data Interpretation format capability taxonomy moved to
  `XBrainLab/backend/application/data_interpretation_formats.py`.

UI runtime bypass cleanup:

- Dataset direct file import no longer calls controller import after successful
  `LoadDataCommand`.
- Preprocess reset now uses `ResetPreprocessCommand`; controller fallback only
  remains for mock / legacy `None` adapter paths.
- Training sidebar re-split cleanup now uses `ClearDatasetsCommand`.
- Training Clear History now asks confirmation and uses
  `ClearTrainingHistoryCommand`.

Docs updated:

- `docs/current.md`
- `docs/architecture/backend.md`
- `docs/planning/now.md`
- `docs/planning/roadmap.md`
- `docs/records/implementation_log.md`
- `docs/records/worklog.md`
- `docs/validation/README.md`

## Validation Already Run

Latest successful gates from the completed slices:

```bash
poetry run ruff check .
poetry run basedpyright
poetry run python tests/architecture_compliance.py
poetry run mkdocs build --strict
git diff --check
poetry run pytest --capture=sys tests/unit/backend/application -q
poetry run pytest --capture=sys tests/unit/ui/test_sidebars_and_components.py::TestTrainingSidebar tests/unit/ui/training/test_training_sidebar.py tests/unit/ui/training/test_training_panel.py -q
poetry run pytest --capture=sys tests/unit/ui/test_ui_misc.py::TestDatasetActionHandler tests/unit/ui/test_sidebars_and_components.py::TestPreprocessSidebar tests/unit/ui/preprocess/test_preprocess_panel.py tests/unit/ui/dataset/test_panel.py -q
```

Observed results:

- backend application unit suite: `80 passed`
- training UI focused suite: `40 passed`
- dataset/preprocess UI focused suite: `85 passed`
- full basedpyright: `0 errors, 0 warnings, 0 notes`
- architecture compliance: `Architecture compliant!`
- MkDocs strict: pass with existing Material warning

## Next Recommended Work

1. Continue UI mutating-path audit.
   - Remaining `controller.*` hits are mostly read-only or `None` fallback, but
     verify Dataset sidebar channel selection / clear dataset, Dataset panel
     metadata edits, smart parse, remove files, Visualization saliency, and
     AgentManager montage against service-success no-fallback tests.

2. Continue Data Interpretation internal boundary cleanup.
   - `data_interpretation.py` is still about `1131` lines.
   - Best next slice: extract metadata resolution or recipe serialization into a
     focused module after adding red tests.
   - Do not break public imports from `XBrainLab.backend.application`.

3. Keep product closure blockers explicit.
   - Mature import wizard editor, raw trigger selector, complex MAT/GDF anchor
     reconciliation, XDF / LSL stream parser, Windows human desktop acceptance,
     long-running ChatPanel workflow, and MCP long-running boundaries remain
     unfinished.

Do not mark product complete until those blockers have real evidence.
