import ast
import inspect
from types import SimpleNamespace
from unittest.mock import MagicMock

from XBrainLab.backend.application.commands import QueryStateCommand
from XBrainLab.ui.panels.dataset.actions import (
    DatasetActionHandler,
    DatasetTableRowIdentity,
    DatasetTableSelection,
)
from XBrainLab.ui.panels.dataset.external_label_import_coordinator import (
    ExternalLabelImportBindings,
    ExternalLabelImportCoordinator,
    LabelImportTarget,
)


def _unused_dialog_factory():
    raise AssertionError("dialog factory should not be used by this contract test")


def test_label_plan_preserves_reviewed_preview_and_target_identity() -> None:
    host = SimpleNamespace(panel=object())
    coordinator = ExternalLabelImportCoordinator(
        host,
        event_filter_dialog_class=_unused_dialog_factory,
        import_label_dialog_class=_unused_dialog_factory,
        label_mapping_dialog_class=_unused_dialog_factory,
    )
    coordinator._remember_target_file_indices([2, 5])
    selection = SimpleNamespace(
        preview_id="preview-17",
        label_paths=("labels-a.csv", "labels-b.csv"),
        label_configs={
            "labels-a.csv": {"column": "classlabel"},
            "labels-b.csv": {"column": "classlabel"},
        },
    )

    plan = coordinator.build_label_import_plan(
        selection,
        mapping={"classlabel": "label"},
        mode="batch",
        file_mapping={"subject-01.edf": "labels-a.csv"},
        selected_event_names={"770", "769"},
    )

    assert plan.preview_id == "preview-17"
    assert plan.target_indices == [2, 5]
    assert plan.selected_event_names == ["769", "770"]
    assert plan.label_paths == ["labels-a.csv", "labels-b.csv"]
    assert plan.file_mapping == {"subject-01.edf": "labels-a.csv"}


def test_dataset_action_handler_keeps_external_label_entrypoints_as_delegates() -> None:
    tree = ast.parse(inspect.getsource(DatasetActionHandler))
    handler = next(node for node in tree.body if isinstance(node, ast.ClassDef))
    methods = {
        node.name: node
        for node in handler.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    delegate_names = {
        "import_label",
        "_execute_label_import_async",
        "_offer_label_recipe_save",
        "_get_target_files_for_import",
        "_target_files_from_table_rows",
        "_build_label_import_plan",
        "_filter_events_for_import",
        "_smart_filter_suggestions_for_import",
        "_target_index_for_filter_suggestion",
    }
    control_flow = (ast.If, ast.For, ast.While, ast.Try, ast.With, ast.Match)

    for name in delegate_names:
        method = methods[name]
        assert not any(isinstance(node, control_flow) for node in ast.walk(method)), (
            f"{name} regrew workflow control flow in DatasetActionHandler"
        )
        assert any(
            isinstance(node, ast.Attribute)
            and isinstance(node.value, ast.Attribute)
            and isinstance(node.value.value, ast.Name)
            and node.value.value.id == "self"
            and node.value.attr == "_external_label_import"
            for node in ast.walk(method)
        ), f"{name} no longer delegates to ExternalLabelImportCoordinator"


def test_product_label_targets_are_detached_from_generation_bound_backend_rows() -> (
    None
):
    generation = 17
    selection = DatasetTableSelection(
        publication_generation=generation,
        rows=(
            DatasetTableRowIdentity(
                canonical_filepath="/data/sub-01_raw.fif",
                rendered_row=0,
            ),
        ),
    )
    panel = SimpleNamespace(
        table=SimpleNamespace(
            item=MagicMock(
                side_effect=AssertionError("Qt item payload must not be read"),
            ),
        ),
        capture_table_selection=MagicMock(return_value=selection),
        resolve_table_selection=MagicMock(return_value=[0]),
    )
    host = SimpleNamespace(
        panel=panel,
        _compatibility_target_files_from_controller=MagicMock(
            side_effect=AssertionError("product runtime must not use controller"),
        ),
    )
    warnings = MagicMock()
    commands: list[tuple[object, int | None]] = []

    def _execute(_panel, command, **kwargs):
        commands.append((command, kwargs.get("expected_publication_generation")))
        return SimpleNamespace(
            failed=False,
            diagnostics={
                "payload_type": "label_import_targets",
                "target_count": 1,
                "targets": [
                    {
                        "index": 0,
                        "filepath": "/data/sub-01_raw.fif",
                        "filename": "sub-01_raw.fif",
                        "is_raw": True,
                        "event_names": ["768", "769"],
                        "suggested_event_names": [],
                        "event_read_error": None,
                    },
                ],
            },
        )

    bindings = ExternalLabelImportBindings(
        message_box=lambda: SimpleNamespace(warning=warnings),
        get_command_review_context=lambda *_args, **_kwargs: None,
        get_command_capability=lambda *_args, **_kwargs: None,
        has_real_application_context=lambda *_args, **_kwargs: True,
        blocked_reason=lambda *_args, **_kwargs: "blocked",
        execute_application_command=_execute,
        is_stale_publication_result=lambda _result: False,
        present_unexpected_error=lambda *_args, **_kwargs: None,
    )
    coordinator = ExternalLabelImportCoordinator(
        host,
        event_filter_dialog_class=_unused_dialog_factory,
        import_label_dialog_class=_unused_dialog_factory,
        label_mapping_dialog_class=_unused_dialog_factory,
        bindings=bindings,
    )

    targets = coordinator.target_files_from_table_rows([0])

    assert targets is not None
    assert len(targets) == 1
    target = targets[0]
    assert type(target).__name__ == "LabelImportTarget"
    assert target.index == 0
    assert target.filepath == "/data/sub-01_raw.fif"
    assert target.filename == "sub-01_raw.fif"
    assert target.event_names == ("768", "769")
    assert target.publication_generation == generation
    assert coordinator.selection_snapshot().target_indices == (0,)
    assert len(commands) == 1
    command, expected_generation = commands[0]
    assert isinstance(command, QueryStateCommand)
    assert command.query == "label_import_targets"
    assert command.params == {"target_indices": [0], "target_count": 0}
    assert expected_generation == generation
    panel.table.item.assert_not_called()
    host._compatibility_target_files_from_controller.assert_not_called()
    warnings.assert_not_called()


def test_product_sequence_label_event_review_uses_detached_backend_evidence() -> None:
    generation = 23
    initial_target = LabelImportTarget(
        index=2,
        filepath="/data/sub-03_raw.fif",
        filename="sub-03_raw.fif",
        raw=True,
        event_names=("768", "769", "1023"),
        suggested_event_names=(),
        event_read_error=None,
        publication_generation=generation,
    )
    panel = object()
    host = SimpleNamespace(panel=panel)
    commands: list[tuple[object, int | None]] = []
    warnings = MagicMock()

    def _execute(_panel, command, **kwargs):
        commands.append((command, kwargs.get("expected_publication_generation")))
        return SimpleNamespace(
            failed=False,
            diagnostics={
                "payload_type": "label_import_targets",
                "target_count": 1,
                "targets": [
                    {
                        "index": 2,
                        "filepath": "/data/sub-03_raw.fif",
                        "filename": "sub-03_raw.fif",
                        "is_raw": True,
                        "event_names": ["768", "769", "1023"],
                        "suggested_event_names": ["769"],
                        "event_read_error": None,
                    }
                ],
            },
        )

    class _EventDialog:
        def __init__(self, parent, event_names):
            assert parent is panel
            assert event_names == ["1023", "768", "769"]
            self.suggested: list[str] = []

        def set_selection(self, event_names):
            self.suggested = list(event_names)
            assert self.suggested == ["769"]

        def exec(self):
            return True

        def get_selected_ids(self):
            return {"769"}

    bindings = ExternalLabelImportBindings(
        message_box=lambda: SimpleNamespace(warning=warnings),
        get_command_review_context=lambda *_args, **_kwargs: None,
        get_command_capability=lambda *_args, **_kwargs: None,
        has_real_application_context=lambda *_args, **_kwargs: True,
        blocked_reason=lambda *_args, **_kwargs: "blocked",
        execute_application_command=_execute,
        is_stale_publication_result=lambda _result: False,
        present_unexpected_error=lambda *_args, **_kwargs: None,
    )
    coordinator = ExternalLabelImportCoordinator(
        host,
        event_filter_dialog_class=lambda: _EventDialog,
        import_label_dialog_class=_unused_dialog_factory,
        label_mapping_dialog_class=_unused_dialog_factory,
        bindings=bindings,
    )
    target_files: list[object] = [initial_target]

    selected = coordinator.filter_events_for_import(target_files, 288)

    assert selected == {"769"}
    assert len(target_files) == 1
    refreshed = target_files[0]
    assert isinstance(refreshed, LabelImportTarget)
    assert refreshed.suggested_event_names == ("769",)
    assert len(commands) == 1
    command, expected_generation = commands[0]
    assert isinstance(command, QueryStateCommand)
    assert command.query == "label_import_targets"
    assert command.params == {"target_indices": [2], "target_count": 288}
    assert expected_generation == generation
    warnings.assert_not_called()
