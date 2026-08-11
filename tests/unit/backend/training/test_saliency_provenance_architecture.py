from pathlib import Path

from tests.architecture_compliance import (
    check_saliency_provenance_ownership,
)
from XBrainLab.backend.training import saliency_provenance
from XBrainLab.backend.training.record import eval as eval_module

_OWNER_SOURCE = """
SALIENCY_CONTEXT_SCHEMA_VERSION = 3
SALIENCY_PRODUCER_SCHEMA_VERSION = 2

class SaliencyContextError(ValueError):
    pass

class SaliencyProducerIdentity:
    pass

class SaliencyArtifactContext:
    pass

def fingerprint_saliency_epoch_data(value):
    return value

def fingerprint_saliency_model_state(value):
    return value

def fingerprint_saliency_split_mask(value):
    return value
"""

_COMPATIBILITY_SOURCE = """
from ..saliency_provenance import (
    SALIENCY_CONTEXT_SCHEMA_VERSION as SALIENCY_CONTEXT_SCHEMA_VERSION,
    SALIENCY_PRODUCER_SCHEMA_VERSION as SALIENCY_PRODUCER_SCHEMA_VERSION,
    SaliencyArtifactContext as SaliencyArtifactContext,
    SaliencyContextError as SaliencyContextError,
    SaliencyProducerIdentity as SaliencyProducerIdentity,
    fingerprint_saliency_epoch_data as fingerprint_saliency_epoch_data,
    fingerprint_saliency_model_state as fingerprint_saliency_model_state,
    fingerprint_saliency_split_mask as fingerprint_saliency_split_mask,
)

class EvalRecord:
    pass
"""


def _write(root: Path, relative_path: str, source: str) -> None:
    path = root / relative_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(source, encoding="utf-8")


def _write_valid_owners(root: Path) -> None:
    _write(
        root,
        "XBrainLab/backend/training/saliency_provenance.py",
        _OWNER_SOURCE,
    )
    _write(
        root,
        "XBrainLab/backend/training/record/eval.py",
        _COMPATIBILITY_SOURCE,
    )


def test_guard_rejects_provenance_definitions_in_eval(tmp_path: Path) -> None:
    _write_valid_owners(tmp_path)
    eval_path = tmp_path / "XBrainLab/backend/training/record/eval.py"
    eval_path.write_text(
        _COMPATIBILITY_SOURCE
        + """

def _bounded_array_descriptor(value):
    return value

class SaliencyArtifactContext:
    pass
""",
        encoding="utf-8",
    )

    violations = check_saliency_provenance_ownership(tmp_path)

    assert len(violations) == 1
    assert "_bounded_array_descriptor" in violations[0]
    assert "SaliencyArtifactContext" in violations[0]


def test_guard_rejects_product_imports_from_compatibility_module(
    tmp_path: Path,
) -> None:
    _write_valid_owners(tmp_path)
    _write(
        tmp_path,
        "XBrainLab/backend/visualization/base.py",
        "from XBrainLab.backend.training.record.eval import SaliencyArtifactContext\n",
    )

    violations = check_saliency_provenance_ownership(tmp_path)
    normalized = violations[0].replace("\\", "/")

    assert len(violations) == 1
    assert "visualization/base.py" in normalized
    assert "must import saliency provenance" in violations[0]


def test_guard_allows_explicit_re_exports_and_direct_domain_imports(
    tmp_path: Path,
) -> None:
    _write_valid_owners(tmp_path)
    _write(
        tmp_path,
        "XBrainLab/backend/visualization/base.py",
        "from XBrainLab.backend.training.saliency_provenance import "
        "SaliencyArtifactContext\n",
    )
    _write(
        tmp_path,
        "XBrainLab/backend/visualization/saliency_3d_engine.py",
        "from XBrainLab.backend.training.record.eval import EvalRecord\n"
        "from XBrainLab.backend.training.saliency_provenance import "
        "SaliencyArtifactContext\n",
    )

    assert check_saliency_provenance_ownership(tmp_path) == []


def test_repository_saliency_provenance_boundary() -> None:
    root_dir = Path(__file__).resolve().parents[4]

    assert check_saliency_provenance_ownership(root_dir) == []


def test_eval_module_compatibility_re_exports_owner_symbols() -> None:
    for name in saliency_provenance.__all__:
        assert getattr(eval_module, name) is getattr(saliency_provenance, name)
