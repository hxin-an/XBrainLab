"""Resource-lifecycle regressions for Data Interpretation readers."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from XBrainLab.backend.application import (
    data_interpretation_internal_events,
    data_interpretation_scan,
    resource_guard,
)


class _FailingCloseableMneObject:
    def __init__(self) -> None:
        self.closed = False

    @property
    def annotations(self) -> Any:
        raise RuntimeError("annotation metadata failed")

    def close(self) -> None:
        self.closed = True
        raise RuntimeError("cleanup failed")


class _FailingHeaderRaw:
    def __init__(self) -> None:
        self.closed = False

    @property
    def ch_names(self) -> Any:
        raise RuntimeError("header metadata failed")

    def close(self) -> None:
        self.closed = True
        raise RuntimeError("cleanup failed")


class _FailingCloseableDirectoryIterator:
    def __init__(self) -> None:
        self.closed = False

    def __iter__(self) -> _FailingCloseableDirectoryIterator:
        return self

    def __next__(self) -> Path:
        raise OSError("directory changed during scan")

    def close(self) -> None:
        self.closed = True
        raise RuntimeError("cleanup failed")


def test_source_discovery_closes_directory_iterator_when_scan_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    iterator = _FailingCloseableDirectoryIterator()
    real_iterdir = Path.iterdir

    def _iterdir(path: Path):
        return iterator if path == tmp_path else real_iterdir(path)

    monkeypatch.setattr(Path, "iterdir", _iterdir)

    scope = data_interpretation_scan.discover_source_preflight_scope(
        source_path=str(tmp_path),
    )

    assert any(
        "directory changed during scan" in warning
        for warning in scope.discovery_warnings
    )
    assert iterator.closed is True


def test_import_preflight_closes_raw_when_header_metadata_read_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "recording.edf"
    source.write_bytes(b"header")
    raw = _FailingHeaderRaw()
    fake_mne = SimpleNamespace(
        io=SimpleNamespace(read_raw_edf=lambda *_args, **_kwargs: raw),
    )
    monkeypatch.setattr(resource_guard, "import_module", lambda _name: fake_mne)
    monkeypatch.setattr(
        resource_guard.ResourceChecker,
        "get_system_ram_status",
        staticmethod(
            lambda: {
                "available_bytes": 10**12,
                "total_bytes": 10**12,
                "used_bytes": 0,
            }
        ),
    )

    preflight = resource_guard.check_import_resource_preflight([str(source)])

    [file_diagnostics] = preflight.to_diagnostics()["files"]
    assert file_diagnostics["estimate_source"] == "file_size_fallback"
    assert raw.closed is True


def test_internal_event_preview_closes_reader_when_metadata_read_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = tmp_path / "recording.edf"
    reader = _FailingCloseableMneObject()
    monkeypatch.setattr(
        data_interpretation_internal_events,
        "_read_mne_object",
        lambda _path, _mne: reader,
    )

    preview = data_interpretation_internal_events.build_internal_event_preview(
        [str(source)],
    )

    assert preview["event_count"] == 0
    assert "annotation metadata failed" in preview["scan_warnings"][0]
    assert "cleanup failed" not in preview["scan_warnings"][0]
    assert reader.closed is True
