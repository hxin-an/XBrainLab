from pathlib import Path

from tests.architecture_compliance import (
    check_saliency_artifact_integrity_ownership,
)

_OWNER_SOURCE = """
class SaliencyArtifactIntegrityError(Exception):
    pass

class SaliencyIntegrityReason:
    pass

def build_saliency_artifact_manifest():
    pass

def normalize_saliency_method_parameters():
    pass

def verify_saliency_artifact_manifest():
    pass
"""


def _write(root: Path, relative_path: str, source: str) -> None:
    path = root / relative_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(source, encoding="utf-8")


def _write_owner(root: Path) -> None:
    _write(
        root,
        "XBrainLab/backend/training/saliency_artifact_integrity.py",
        _OWNER_SOURCE,
    )


def test_guard_rejects_integrity_policy_in_ui_and_state_service(
    tmp_path: Path,
) -> None:
    _write_owner(tmp_path)
    _write(
        tmp_path,
        "XBrainLab/ui/panels/visualization/panel.py",
        "saliency_integrity_manifest = {}\n",
    )
    _write(
        tmp_path,
        "XBrainLab/backend/application/state_service.py",
        "from XBrainLab.backend.training.saliency_artifact_integrity import "
        "SaliencyIntegrityReason\n",
    )

    violations = check_saliency_artifact_integrity_ownership(tmp_path)
    normalized = [item.replace("\\", "/") for item in violations]

    assert len(violations) == 3
    assert any("visualization/panel.py" in item for item in normalized)
    assert any("state_service.py" in item for item in normalized)


def test_guard_rejects_non_persistence_imports(tmp_path: Path) -> None:
    _write_owner(tmp_path)
    _write(
        tmp_path,
        "XBrainLab/backend/study.py",
        "from XBrainLab.backend.training.saliency_artifact_integrity import "
        "build_saliency_artifact_manifest\n",
    )

    violations = check_saliency_artifact_integrity_ownership(tmp_path)

    assert len(violations) == 1
    assert "outside the training persistence domain" in violations[0]


def test_repository_saliency_artifact_integrity_boundary() -> None:
    root_dir = Path(__file__).resolve().parents[4]

    assert check_saliency_artifact_integrity_ownership(root_dir) == []
