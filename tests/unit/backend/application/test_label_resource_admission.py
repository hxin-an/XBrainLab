"""Canonical external-label resource admission contracts."""

from __future__ import annotations

from pathlib import Path

import pytest

from XBrainLab.backend.application import (
    data_interpretation_path_identity as path_identity_module,
)
from XBrainLab.backend.application import (
    label_resource_admission as label_admission_module,
)
from XBrainLab.backend.application.commands import LabelImportPlan
from XBrainLab.backend.application.label_resource_admission import specs_from_paths
from XBrainLab.backend.application.resource_guard import check_import_resource_preflight
from XBrainLab.backend.application.resource_label_estimation import (
    LABEL_CARRIER_FILE_SIZE_MULTIPLIERS,
    SUPPORTED_EXTERNAL_LABEL_EXTENSIONS,
)


def test_label_specs_preserve_spelling_while_matching_windows_case_variants(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    label_path = (tmp_path / "ExternalLabels" / "A01T.mat").resolve()
    config_path = str(label_path).swapcase()
    windows_path = type(
        "WindowsPathOps",
        (),
        {"normcase": staticmethod(lambda value: str(value).casefold())},
    )()
    windows_os = type("WindowsOs", (), {"path": windows_path})()
    monkeypatch.setattr(label_admission_module, "os", windows_os)
    monkeypatch.setattr(path_identity_module, "os", windows_os, raising=False)

    specs = specs_from_paths(
        [str(label_path)],
        configs={config_path: {"label_field": "classlabel"}},
    )

    assert specs[0].path == str(label_path)
    assert specs[0].label_field == "classlabel"


def test_reviewed_label_session_reports_each_real_resource_checkpoint(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    first = tmp_path / "first.csv"
    second = tmp_path / "second.csv"
    first.write_text("label\n1\n", encoding="utf-8")
    second.write_text("label\n2\n", encoding="utf-8")
    paths = [str(first), str(second)]
    preflight = check_import_resource_preflight(paths)
    stages: list[tuple[str, int | None, int | None]] = []
    monkeypatch.setattr(
        label_admission_module,
        "owned_work_checkpoint",
        lambda stage, completed=None, total=None, **_kwargs: stages.append(
            (stage, completed, total)
        ),
    )

    session = label_admission_module.session_from_resource_preflight(
        specs_from_paths(paths),
        preflight,
    )

    assert len(session.specs) == 2
    assert stages == [
        ("Normalizing reviewed label resource scope", None, None),
        ("Inspecting reviewed label resource 1 of 2", 0, 2),
        ("Inspecting reviewed label resource 2 of 2", 1, 2),
        ("Binding reviewed label resource reader", None, None),
        ("Verifying reviewed label resource 1 of 2", 0, 2),
        ("Verifying reviewed label resource 2 of 2", 1, 2),
        ("Reviewed label resources admitted", 2, 2),
    ]


def test_public_label_import_plan_cannot_accept_prematerialized_payloads() -> None:
    with pytest.raises(TypeError, match="label_map"):
        LabelImportPlan(label_map={"labels.csv": [1, 2]})  # type: ignore[call-arg]


def test_label_resource_formats_and_estimator_thresholds_have_one_owner() -> None:
    assert (
        frozenset(LABEL_CARRIER_FILE_SIZE_MULTIPLIERS)
        == SUPPORTED_EXTERNAL_LABEL_EXTENSIONS
    )
    assert {".mat", ".csv", ".tsv", ".txt", ".npy"} <= (
        SUPPORTED_EXTERNAL_LABEL_EXTENSIONS
    )
