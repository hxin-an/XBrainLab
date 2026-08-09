"""Regressions for the application-owned training lifecycle event boundary."""

from __future__ import annotations

from pathlib import Path

from tests import architecture_compliance
from XBrainLab.backend.application import ApplicationService
from XBrainLab.backend.study import Study


def _write_product_file(root: Path, relative_path: str, source: str) -> None:
    path = root / relative_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(source, encoding="utf-8")


def test_application_controller_guard_rejects_controller_dependencies(
    tmp_path: Path,
) -> None:
    _write_product_file(
        tmp_path,
        "XBrainLab/backend/application/service.py",
        """
from XBrainLab.backend.controller.training_controller import TrainingController
from .controller_adapters import TrainingControllerAdapter


class ApplicationService:
    def __init__(self, study):
        self.training = TrainingControllerAdapter(study)
        self.controller = study.get_controller("training")
""",
    )

    violations = architecture_compliance.check_application_controller_boundary(
        tmp_path,
    )

    assert any("controller module" in item for item in violations)
    assert any("TrainingControllerAdapter" in item for item in violations)
    assert any("get_controller" in item for item in violations)


def test_repository_publication_lifecycle_uses_application_owned_port() -> None:
    root_dir = Path(__file__).resolve().parents[4]

    assert (
        architecture_compliance.check_application_publication_lifecycle_port_boundary(
            root_dir,
        )
        == []
    )


def test_application_service_does_not_reexport_publication_lifecycle_internals() -> (
    None
):
    compatibility_delegates = {
        "_observer_finalizer",
        "_saliency_notification_boundary",
        "_discard_pending_saliency_terminal",
        "_publish_training_live_state",
        "_deliver_training_terminal_publication",
        "_terminal_training_publication_event",
        "_publish_post_training_saliency_terminal_state",
        "_commit_post_training_saliency_terminal_state",
        "_remember_pending_saliency_terminal",
        "_pending_saliency_terminal",
        "_clear_pending_saliency_terminal",
        "_reconcile_pending_saliency_terminal",
        "_plan_saliency_terminal_delivery",
        "_notify_saliency_publication_changed",
        "_visualization_batch_generation",
    }

    assert compatibility_delegates.isdisjoint(ApplicationService.__dict__)


def test_real_study_service_construction_does_not_resolve_training_controller() -> None:
    study = Study()

    service = ApplicationService(study)

    assert service.training is study.training_state_service
    assert service.training_lifecycle_events is study.training_state_service
    assert "training" not in study._controllers
    assert service.get_view_publication().state.training.progress_message is None

    service.close()
    assert "training" not in study._controllers
    assert "training" not in study._controller_event_subscriptions


def test_product_lifecycle_observer_precedes_later_controller_observers() -> None:
    study = Study()
    service = ApplicationService(study)
    delivery_order: list[str] = []
    service.publication_lifecycle.publish_training_live_state = (
        lambda *_args, **_kwargs: delivery_order.append("application")
    )

    controller = study.get_controller("training")
    controller.subscribe(
        "training_updated",
        lambda: delivery_order.append("later-controller-observer"),
    )

    study.training_state_service.notify("training_updated")

    assert delivery_order == ["application", "later-controller-observer"]
    service.close()
