"""Architecture guards for application state module ownership."""

from __future__ import annotations

from pathlib import Path

from tests.architecture_compliance import check_application_state_module_boundaries


def _write_product_file(root: Path, relative_path: str, source: str) -> None:
    path = root / relative_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(source, encoding="utf-8")


def test_guard_rejects_saliency_coverage_policy_in_state_service(
    tmp_path: Path,
) -> None:
    _write_product_file(
        tmp_path,
        "XBrainLab/backend/application/state_service.py",
        "def _saliency_classes(record): return []\n",
    )

    violations = check_application_state_module_boundaries(tmp_path)

    assert any(
        "state_service.py defines saliency coverage policy" in item
        for item in violations
    )


def test_guard_rejects_ui_projector_imports_and_compatibility_calls(
    tmp_path: Path,
) -> None:
    _write_product_file(
        tmp_path,
        "XBrainLab/ui/panels/visualization/demo.py",
        """from XBrainLab.backend.application.saliency_coverage import SaliencyCoverageProjector
from XBrainLab.backend.application.state_service import saliency_method_coverage

projector = SaliencyCoverageProjector()
coverage = saliency_method_coverage(record, \"Gradient\")
run = projector.project_run(record, plan_index=0, run_index=0)
""",
    )

    violations = check_application_state_module_boundaries(tmp_path)

    assert any(
        "UI must consume published saliency coverage" in item for item in violations
    )
    assert any("saliency_method_coverage" in item for item in violations)
    assert any("project_run" in item for item in violations)


def test_guard_rejects_query_service_ownership_drift(tmp_path: Path) -> None:
    _write_product_file(
        tmp_path,
        "XBrainLab/backend/application/state_service.py",
        "class QueryStateCommandService: pass\n",
    )
    _write_product_file(
        tmp_path,
        "XBrainLab/backend/application/service.py",
        "from .state_service import QueryStateCommandService\n",
    )

    violations = check_application_state_module_boundaries(tmp_path)

    assert any("QueryStateCommandService is owned by" in item for item in violations)
    assert any("imports QueryStateCommandService from" in item for item in violations)


def test_repository_application_state_module_boundaries_are_clean() -> None:
    root = Path(__file__).resolve().parents[4]

    assert check_application_state_module_boundaries(root) == []
