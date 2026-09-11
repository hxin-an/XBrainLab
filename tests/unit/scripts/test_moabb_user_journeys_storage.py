from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from scripts.dev.moabb_user_journeys.cli import build_parser
from scripts.dev.moabb_user_journeys.registry import load_registry
from scripts.dev.moabb_user_journeys.storage import (
    build_plan,
    load_validated_plan,
    validate_plan_cache,
    write_json_atomic,
)


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


def test_atomic_json_is_valid_and_complete(tmp_path: Path) -> None:
    path = tmp_path / "receipt.json"
    write_json_atomic(path, {"serial": True, "count": 3})

    assert json.loads(path.read_text(encoding="utf-8")) == {
        "count": 3,
        "serial": True,
    }


@pytest.mark.parametrize(
    ("content", "error", "message"),
    [
        (b"abc", None, ""),
        (None, FileNotFoundError, "Cached dataset file is missing"),
        (b"abcd", ValueError, "Cached size mismatch"),
        (b"xyz", ValueError, "Checksum mismatch"),
    ],
    ids=["valid", "missing", "wrong-size", "wrong-checksum"],
)
def test_cache_validation_requires_exact_existing_bytes(
    tmp_path: Path, content: bytes | None, error, message: str
) -> None:
    path = tmp_path / "source.edf"
    if content is not None:
        path.write_bytes(content)
    digest = hashlib.sha256(b"abc").hexdigest()
    plan = {
        "plan_id": "selected-plan",
        "registry_sha256": "registry-digest",
        "files": [
            {
                "cache_path": str(path),
                "url": "https://physionet.org/files/example.edf",
                "size_bytes": 3,
                "checksum": {"algorithm": "sha256", "value": digest},
            }
        ],
    }

    if error is not None:
        with pytest.raises(error, match=message):
            validate_plan_cache(plan)
    else:
        receipt = validate_plan_cache(plan)
        assert receipt["plan_id"] == plan["plan_id"]
        assert receipt["registry_sha256"] == plan["registry_sha256"]
        assert receipt["files"][0]["sha256"] == digest
        assert receipt["files"][0]["path"] == str(path.resolve())
    assert path.read_bytes() == content if content is not None else not path.exists()


@pytest.mark.parametrize(
    "argv",
    [["plan"], ["validate", "--files-only"], ["run-resume", "--run-id", "audit"]],
)
def test_existing_cache_workflow_commands_remain_available(argv: list[str]) -> None:
    args = build_parser().parse_args(argv)

    assert args.action == argv[0]


def test_one_time_fetch_command_is_not_available() -> None:
    parser = build_parser()

    with pytest.raises(SystemExit) as exc:
        parser.parse_args(["fetch"])

    assert exc.value.code == 2
    assert "fetch" not in parser.format_help()
