import ast
import weakref
from dataclasses import replace
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from PyQt6 import sip
from PyQt6.QtCore import QObject

from XBrainLab.backend.study import Study
from XBrainLab.ui.components.info_panel_service import InfoPanelService


@pytest.fixture
def study() -> Study:
    return Study()


@pytest.fixture
def service(study):
    return InfoPanelService(study)


def test_service_initialization(service, study):
    assert service.study == study
    assert service._observes_controller_events is False
    assert service._latest_publication is None
    assert not hasattr(service, "dataset_bridge")
    assert not hasattr(service, "preprocess_bridge")


def test_register_and_notify_fail_closed_before_first_publication(service):
    panel_mock = MagicMock()

    service.register(panel_mock)
    assert panel_mock in service._listeners
    service.notify_all()

    assert panel_mock.update_info.call_count == 2
    panel_mock.update_info.assert_called_with(
        loaded_data_list=[], preprocessed_data_list=[]
    )


def test_notify_all_replays_latest_publication_without_second_state_query():
    from XBrainLab.backend.application.service import ApplicationService

    study = Study()
    application_service = ApplicationService(study)
    publication = replace(
        application_service.get_view_publication(),
        data_summary_rows=({"filename": "publication.edf"},),
    )
    service = InfoPanelService(study)
    panel = MagicMock()
    service._listeners.add(panel)

    try:
        assert service.render_publication(publication) is True
        panel.update_info.reset_mock()

        service.notify_all()

        panel.update_info.assert_called_once_with(
            loaded_data_list=[{"filename": "publication.edf"}],
            preprocessed_data_list=[],
        )
    finally:
        application_service.close()


def test_missing_publication_rows_fail_closed_without_second_state_query():
    from XBrainLab.backend.application.service import ApplicationService

    study = Study()
    application_service = ApplicationService(study)
    publication = replace(
        application_service.get_view_publication(),
        data_summary_rows=None,
    )
    service = InfoPanelService(study)
    panel = MagicMock()
    service._listeners.add(panel)

    try:
        assert service.render_publication(publication) is True

        panel.update_info.assert_called_once_with(
            loaded_data_list=[],
            preprocessed_data_list=[],
        )
    finally:
        application_service.close()


def test_absent_publication_fails_closed_without_state_query():
    study = Study()
    study.get_controller = MagicMock(
        side_effect=AssertionError("missing publication must not read controller truth")
    )
    service = InfoPanelService(study)
    panel = MagicMock()

    service.register(panel)
    service.notify_all()

    study.get_controller.assert_not_called()
    assert panel.update_info.call_count == 2
    panel.update_info.assert_called_with(
        loaded_data_list=[],
        preprocessed_data_list=[],
    )


def test_deleted_qobject_runtime_error_is_terminal_cleanup():
    from XBrainLab.backend.application.service import ApplicationService

    class DeletedAggregatePanel(QObject):
        def update_info(self, **_kwargs) -> None:
            self.objectName()

    study = Study()
    application_service = ApplicationService(study)
    service = InfoPanelService(study)
    publication = application_service.get_view_publication()
    panel = DeletedAggregatePanel()
    service._listeners.add(panel)
    sip.delete(panel)

    try:
        assert sip.isdeleted(panel) is True
        assert service.render_publication(publication) is True
    finally:
        application_service.close()


def test_product_info_publication_has_one_owner_and_no_state_query_fallback():
    repo_root = Path(__file__).resolve().parents[4]
    main_window_source = (repo_root / "XBrainLab/ui/main_window.py").read_text(
        encoding="utf-8"
    )
    info_service_source = (
        repo_root / "XBrainLab/ui/components/info_panel_service.py"
    ).read_text(encoding="utf-8")

    main_tree = ast.parse(main_window_source)
    info_tree = ast.parse(info_service_source)
    class_names = [
        node.name
        for tree in (main_tree, info_tree)
        for node in ast.walk(tree)
        if isinstance(node, ast.ClassDef)
    ]
    publication_owner_classes = [
        node.name
        for tree in (main_tree, info_tree)
        for node in ast.walk(tree)
        if isinstance(node, ast.ClassDef)
        and {"register", "notify_all", "render_publication"}.issubset(
            {child.name for child in node.body if isinstance(child, ast.FunctionDef)}
        )
    ]
    data_list_queries = [
        node
        for tree in (main_tree, info_tree)
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "QueryStateCommand"
        and any(
            keyword.arg == "query"
            and isinstance(keyword.value, ast.Constant)
            and keyword.value.value == "data_lists"
            for keyword in node.keywords
        )
    ]
    product_owner_assignments = [
        node
        for node in ast.walk(main_tree)
        if isinstance(node, ast.Assign)
        and any(
            isinstance(target, ast.Attribute)
            and isinstance(target.value, ast.Name)
            and target.value.id == "self"
            and target.attr == "info_service"
            for target in node.targets
        )
    ]
    info_names = {node.id for node in ast.walk(info_tree) if isinstance(node, ast.Name)}

    assert class_names.count("InfoPanelService") == 1
    assert "_StartupInfoPanelService" not in class_names
    assert publication_owner_classes == ["InfoPanelService"]
    assert len(product_owner_assignments) == 1
    assert data_list_queries == []
    assert {
        "execute_application_command",
        "get_controller_for_compatibility_context",
        "QtObserverBridge",
    }.isdisjoint(info_names)


def test_weak_ref_cleanup(service):
    """Test that service doesn't hold strong refs to panels."""

    class MockPanel:
        def update_info(self, **kwargs):
            pass

    panel = MockPanel()
    service.register(panel)

    assert panel in service._listeners

    del panel
    # Force gc if needed, but WeakSet should handle it
    # note: locally 'panel' is gone, but we can't easily assert weakref collection in simple sync test without gc.collect()
    # But we can check that it IS a WeakSet
    assert isinstance(service._listeners, weakref.WeakSet)


@pytest.mark.parametrize(
    "relative_path",
    [
        "XBrainLab/ui/components/info_panel_service.py",
        "XBrainLab/ui/dialogs/dataset/data_splitting_dialog.py",
        "XBrainLab/ui/panels/dataset/sidebar.py",
    ],
)
def test_product_ui_runtime_contracts_do_not_import_unittest_mock(
    relative_path: str,
) -> None:
    repo_root = Path(__file__).resolve().parents[4]

    source = (repo_root / relative_path).read_text(encoding="utf-8")

    assert "unittest.mock" not in source
