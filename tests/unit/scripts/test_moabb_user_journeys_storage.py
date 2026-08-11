from __future__ import annotations

import hashlib
import io
import json
from pathlib import Path

import pytest

from scripts.dev.moabb_user_journeys.registry import load_registry
from scripts.dev.moabb_user_journeys.storage import (
    build_plan,
    download_file,
    load_validated_plan,
    write_json_atomic,
)


class _Response(io.BytesIO):
    def __init__(self, content: bytes, url: str):
        super().__init__(content)
        self._url = url

    def geturl(self) -> str:
        return self._url

    def __enter__(self) -> _Response:
        return self

    def __exit__(self, *args: object) -> None:
        self.close()


def test_plan_is_no_download_serial_and_below_cap() -> None:
    registry = load_registry()

    plan = build_plan(registry)

    assert plan["validated"] is True
    assert plan["serial_downloads"] is True
    assert plan["expected_download_bytes"] == 979_833_042
    assert plan["expected_download_bytes"] <= plan["max_download_bytes"]
    assert plan["expected_download_bytes"] < 1024**3
    assert all(
        Path(item["cache_path"]).is_relative_to(Path(plan["data_root"]))
        for item in plan["files"]
    )


def test_written_plan_fails_closed_after_tampering(tmp_path: Path) -> None:
    registry = load_registry()
    plan = build_plan(registry)
    plan["expected_download_bytes"] += 1
    path = tmp_path / "plan.json"
    write_json_atomic(path, plan)

    with pytest.raises(ValueError, match="expected_download_bytes"):
        load_validated_plan(path, registry=registry)


def test_download_stream_verifies_exact_size_and_checksum(tmp_path: Path) -> None:
    content = b"official-fixture-bytes"
    destination = tmp_path / "fixture.edf"
    item = {
        "url": "https://physionet.org/files/example.edf",
        "cache_path": str(destination),
        "size_bytes": len(content),
        "checksum": {
            "algorithm": "sha256",
            "value": hashlib.sha256(content).hexdigest(),
        },
    }
    calls: list[str] = []

    def opener(request: object, **_: object) -> _Response:
        calls.append(request.full_url)  # type: ignore[attr-defined]
        return _Response(content, item["url"])

    download_file(item, opener=opener)

    assert calls == [item["url"]]
    assert destination.read_bytes() == content
    assert not destination.with_name("fixture.edf.part").exists()


def test_download_rejects_payload_larger_than_declared(tmp_path: Path) -> None:
    destination = tmp_path / "fixture.gdf"
    item = {
        "url": "https://zenodo.org/example.gdf",
        "cache_path": str(destination),
        "size_bytes": 3,
        "checksum": {
            "algorithm": "md5",
            "value": hashlib.md5(b"abc", usedforsecurity=False).hexdigest(),
        },
    }

    def opener(*_: object, **__: object) -> _Response:
        return _Response(b"abcd", item["url"])

    with pytest.raises(ValueError, match="exceeded declared size boundary"):
        download_file(item, opener=opener)

    assert not destination.exists()
    assert not destination.with_name("fixture.gdf.part").exists()


def test_atomic_json_is_valid_and_complete(tmp_path: Path) -> None:
    path = tmp_path / "receipt.json"
    write_json_atomic(path, {"serial": True, "count": 3})

    assert json.loads(path.read_text(encoding="utf-8")) == {
        "count": 3,
        "serial": True,
    }
