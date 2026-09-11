"""Canonical external-label resource admission contracts."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from XBrainLab.backend.application import (
    label_resource_admission as label_admission_module,
)
from XBrainLab.backend.application import label_resource_reader
from XBrainLab.backend.application.commands import LabelImportPlan
from XBrainLab.backend.application.errors import PreconditionError
from XBrainLab.backend.application.label_resource_admission import (
    LabelResourceSpec,
)
from XBrainLab.backend.application.resource_guard import check_import_resource_preflight
from XBrainLab.backend.application.resource_label_estimation import (
    LABEL_CARRIER_FILE_SIZE_MULTIPLIERS,
    SUPPORTED_EXTERNAL_LABEL_EXTENSIONS,
)
from XBrainLab.backend.load_data import label_loader


def test_reviewed_label_session_does_not_read_payload_before_actual_load(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    label_path = tmp_path / "labels.txt"
    label_path.write_bytes(b"1 2\n" * (256 * 1024))
    preflight = check_import_resource_preflight([str(label_path)])
    payload_bytes = 0
    original_read = label_resource_reader._BoundedBinaryReader.read

    def counted_read(reader: Any, size: int = -1) -> bytes:
        nonlocal payload_bytes
        payload = original_read(reader, size)
        payload_bytes += len(payload)
        return payload

    monkeypatch.setattr(
        label_resource_reader._BoundedBinaryReader, "read", counted_read
    )
    session = label_admission_module.session_from_resource_preflight(
        [LabelResourceSpec(path=str(label_path))], preflight
    )
    admission_payload_bytes = payload_bytes

    loaded = session.load(str(label_path))

    assert loaded.shape == (512 * 1024,)
    assert (loaded[0::2] == 1).all()
    assert (loaded[1::2] == 2).all()
    assert payload_bytes > admission_payload_bytes
    # Identity probes remain; this counts only the bounded full-payload stream.
    assert admission_payload_bytes == 0


@pytest.mark.parametrize("mutation_phase", ["during_admission", "before_load"])
def test_reviewed_label_session_rejects_changed_file_before_parser_entry(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    mutation_phase: str,
) -> None:
    label_path = tmp_path / "labels.txt"
    label_path.write_bytes(b"1 2\n")
    preflight = check_import_resource_preflight([str(label_path)])
    original_checkpoint = label_admission_module.owned_work_checkpoint
    original_parser = label_loader._load_label_source
    parser_calls = 0

    def checkpoint(stage: str, **kwargs: Any) -> None:
        original_checkpoint(stage, **kwargs)
        if mutation_phase == "during_admission" and stage.startswith(
            "Verifying reviewed label resource"
        ):
            label_path.write_bytes(b"3 4\n")

    def parser(*args: Any, **kwargs: Any) -> Any:
        nonlocal parser_calls
        parser_calls += 1
        return original_parser(*args, **kwargs)

    monkeypatch.setattr(label_admission_module, "owned_work_checkpoint", checkpoint)
    monkeypatch.setattr(label_loader, "_load_label_source", parser)
    with pytest.raises(PreconditionError) as rejected:
        session = label_admission_module.session_from_resource_preflight(
            [LabelResourceSpec(path=str(label_path))], preflight
        )
        if mutation_phase == "before_load":
            label_path.write_bytes(b"3 4\n")
        session.load(str(label_path))

    assert rejected.value.diagnostics["code"] == (
        "interpretation_resource_changed_after_admission"
    )
    assert rejected.value.diagnostics["parse_started"] is False
    assert parser_calls == 0


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
        [LabelResourceSpec(path=path) for path in paths],
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
