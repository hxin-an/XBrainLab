from __future__ import annotations

from pathlib import Path

from tests.architecture_compliance import (
    check_evaluation_publication_refresh_boundary,
    check_mutable_object_boundaries,
)

ROOT = Path(__file__).resolve().parents[2]


def _write_source(root: Path, relative_path: str, source: str) -> None:
    path = root / relative_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(source, encoding="utf-8")


def test_evaluation_product_ui_has_no_mutable_object_boundary_debt() -> None:
    violations = check_mutable_object_boundaries(ROOT)

    assert not [
        violation
        for violation in violations
        if "XBrainLab/ui/panels/evaluation/" in violation
    ]


def test_evaluation_read_side_does_not_reintroduce_controller_dependencies() -> None:
    service_source = (ROOT / "XBrainLab/backend/application/service.py").read_text(
        encoding="utf-8"
    )
    adapters_path = ROOT / "XBrainLab/backend/application/controller_adapters.py"
    bootstrap_path = ROOT / "XBrainLab/ui/controller_compatibility_bootstrap.py"
    panel_source = (ROOT / "XBrainLab/ui/panels/evaluation/panel.py").read_text(
        encoding="utf-8"
    )
    main_window_source = (ROOT / "XBrainLab/ui/main_window.py").read_text(
        encoding="utf-8"
    )

    assert "EvaluationControllerAdapter" not in service_source
    assert not adapters_path.exists()
    assert not bootstrap_path.exists()
    assert "local_result_payload" not in panel_source
    assert "PooledRecordWrapper" not in panel_source
    assert "TrainingPlanHolder" not in panel_source
    assert "TrainRecord" not in panel_source
    evaluation_spec = main_window_source.split(
        '"evaluation_panel"',
        maxsplit=1,
    )[1].split("),", maxsplit=1)[0]
    assert '"evaluation"' not in evaluation_spec
    assert '"training"' not in evaluation_spec
    assert "training_controller" not in panel_source
    assert "preprocess_controller" not in panel_source
    assert "_create_refresh_bridge" not in panel_source


def test_evaluation_long_work_has_one_owned_python_worker_path() -> None:
    panel_source = (ROOT / "XBrainLab/ui/panels/evaluation/panel.py").read_text(
        encoding="utf-8"
    )
    work_source = (ROOT / "XBrainLab/backend/application/evaluation_work.py").read_text(
        encoding="utf-8"
    )
    service_source = (ROOT / "XBrainLab/backend/application/service.py").read_text(
        encoding="utf-8"
    )
    main_window_source = (ROOT / "XBrainLab/ui/main_window.py").read_text(
        encoding="utf-8"
    )
    render_source = (
        ROOT / "XBrainLab/backend/application/evaluation_render.py"
    ).read_text(encoding="utf-8")

    assert "QThreadPool.globalInstance" not in panel_source
    assert "Worker(self._load_evaluation_render" not in panel_source
    assert "PythonThreadWorker(" in panel_source
    assert "begin_evaluation_render_operation(" in panel_source
    assert "cancel_application_operation(" in panel_source
    assert "get_evaluation_render_publication" not in panel_source
    assert "EvaluationWorkController(" in service_source
    assert "registry=self.owned_work" in service_source
    assert "OwnedWorkRegistry()" not in work_source
    assert "Thread(" not in work_source
    assert "threading" not in work_source
    assert "evaluation_background_work_snapshot" in main_window_source
    assert "begin_evaluation_render_shutdown" in main_window_source
    assert "build_saliency_producer_identity" in render_source
    assert "producerModelFingerprints" in panel_source
    assert "hashlib" not in panel_source


def test_evaluation_publication_refresh_architecture_guard_is_clean() -> None:
    assert check_evaluation_publication_refresh_boundary(ROOT) == []


def test_evaluation_guard_rejects_implicit_main_window_construction(
    tmp_path: Path,
) -> None:
    _write_source(
        tmp_path,
        "XBrainLab/ui/panels/evaluation/panel.py",
        """
class EvaluationPanel:
    def __init__(
        self,
        parent=None,
        *,
        query_port: EvaluationQueryPort | None = None,
        publication_port: ApplicationPublicationSubscriptionPort | None = None,
        action_port: EvaluationActionPort | None = None,
    ):
        self._query_port = query_port
        self._publication_port = publication_port
        self._action_port = action_port

    def _on_application_view_publication_changed(self, publication):
        if publication.revision <= self._last_application_revision:
            return True

    def _subscribe(self):
        self._create_bridge(
            self._publication_port,
            APPLICATION_VIEW_PUBLICATION_CHANGED_EVENT,
            self._on_application_view_publication_changed,
        )
""",
    )
    _write_source(
        tmp_path,
        "XBrainLab/ui/main_window.py",
        """
_PANEL_SPECS = (
    _PanelSpec(
        "evaluation_panel",
        "Evaluation",
        "evaluation",
        "EvaluationPanel",
        (),
    ),
)

class MainWindow:
    def _materialize_panel(self, index):
        spec = _PANEL_SPECS[index]
        if spec.attr == "evaluation_panel":
            return EvaluationPanel(self)
""",
    )
    _write_source(
        tmp_path,
        "XBrainLab/ui/controller_compatibility_bootstrap.py",
        "class CompatibilityWorkflowControllers:\n    pass\n",
    )
    _write_source(
        tmp_path,
        "XBrainLab/ui/refresh_coordinator.py",
        """
def _panel_names_for(panel_name):
    if panel_name != "evaluation_panel":
        return (panel_name,)
    return ()
""",
    )

    violations = check_evaluation_publication_refresh_boundary(tmp_path)

    assert any(
        "MainWindow Evaluation construction must inject query_port" in item
        for item in violations
    )
    assert any(
        "MainWindow Evaluation construction must inject publication_port" in item
        for item in violations
    )
    assert any(
        "MainWindow Evaluation construction must inject action_port" in item
        for item in violations
    )
