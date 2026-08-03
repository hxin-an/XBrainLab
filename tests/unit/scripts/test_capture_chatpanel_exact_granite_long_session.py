from __future__ import annotations

import ast
import hashlib
import inspect
from pathlib import Path

import pytest

from scripts.dev.capture_chatpanel_exact_granite_long_session import main
from scripts.dev.chatpanel_long_session.cli import (
    DEFAULT_TIMEOUT_SECONDS,
    MAX_TIMEOUT_SECONDS,
    isolated_capture_write_environment,
    parse_args,
    prepare_capture_output,
)
from XBrainLab.llm.core.model_catalog import PRIMARY_LOCAL_MODEL_ID


def test_cli_requires_output_and_a_registered_cache_source(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("XBRAINLAB_MODEL_CACHE_DIR", raising=False)
    with pytest.raises(SystemExit):
        parse_args([])

    output_dir = tmp_path / "environment-evidence"
    cache_dir = tmp_path / "environment-models"
    monkeypatch.setenv(
        "XBRAINLAB_MODEL_CACHE_DIR",
        str(cache_dir),
    )
    environment_args = parse_args(["--output-dir", str(output_dir)])

    assert environment_args.cache_dir == cache_dir

    args = parse_args(
        [
            "--output-dir",
            str(tmp_path / "evidence"),
            "--cache-dir",
            str(tmp_path / "models"),
        ]
    )

    assert args.model == PRIMARY_LOCAL_MODEL_ID
    assert args.timeout_seconds == DEFAULT_TIMEOUT_SECONDS
    assert args.cache_dir == tmp_path / "models"


def test_cli_rejects_wrong_model_and_unbounded_timeout(tmp_path: Path) -> None:
    common = [
        "--output-dir",
        str(tmp_path / "evidence"),
        "--cache-dir",
        str(tmp_path / "models"),
    ]

    with pytest.raises(SystemExit):
        parse_args([*common, "--model", "microsoft/Phi-4-mini-instruct"])
    with pytest.raises(SystemExit):
        parse_args([*common, "--timeout-seconds", str(MAX_TIMEOUT_SECONDS + 1)])
    assert MAX_TIMEOUT_SECONDS == 600
    with pytest.raises(SystemExit):
        parse_args([*common, "--timeout-seconds", "1800"])


def test_cli_accepts_explicit_bounded_handoff_gate_contract(tmp_path: Path) -> None:
    cache_dir = tmp_path / "model-cache"
    args = parse_args(
        [
            "--output-dir",
            str(tmp_path / "evidence"),
            "--cache-dir",
            str(cache_dir),
            "--model",
            PRIMARY_LOCAL_MODEL_ID,
            "--timeout-seconds",
            "600",
        ]
    )

    assert args.cache_dir == cache_dir
    assert args.model == PRIMARY_LOCAL_MODEL_ID
    assert args.timeout_seconds == MAX_TIMEOUT_SECONDS


def test_capture_output_must_be_empty_and_separate_from_model_cache(
    tmp_path: Path,
) -> None:
    cache_dir = tmp_path / "models"
    cache_dir.mkdir()
    output_dir = prepare_capture_output(tmp_path / "evidence", cache_dir=cache_dir)

    assert output_dir == (tmp_path / "evidence").resolve()
    (output_dir / "stale.json").write_text("{}", encoding="utf-8")

    with pytest.raises(ValueError, match="empty"):
        prepare_capture_output(output_dir, cache_dir=cache_dir)
    with pytest.raises(ValueError, match="overlap"):
        prepare_capture_output(cache_dir / "evidence", cache_dir=cache_dir)


def test_mutable_runtime_paths_are_isolated_below_output_dir(tmp_path: Path) -> None:
    output_dir = tmp_path / "evidence"
    cache_dir = tmp_path / "models"
    output_dir.mkdir()
    cache_dir.mkdir()

    with isolated_capture_write_environment(output_dir, cache_dir=cache_dir) as root:
        import os

        mutable_names = (
            "XBRAINLAB_CONFIG_DIR",
            "XBRAINLAB_DATA_DIR",
            "XBRAINLAB_CACHE_DIR",
            "XBRAINLAB_LOG_DIR",
            "XBRAINLAB_RAG_CACHE_DIR",
            "XDG_CONFIG_HOME",
            "XDG_CACHE_HOME",
            "XDG_DATA_HOME",
            "XDG_STATE_HOME",
            "MPLCONFIGDIR",
            "HF_HOME",
            "TORCH_HOME",
            "CUDA_CACHE_PATH",
        )
        for name in mutable_names:
            Path(os.environ[name]).resolve().relative_to(output_dir.resolve())
        assert Path(os.environ["XBRAINLAB_MODEL_CACHE_DIR"]).resolve() == (
            cache_dir.resolve()
        )
        assert os.environ["HF_HUB_OFFLINE"] == "1"
        assert os.environ["TRANSFORMERS_OFFLINE"] == "1"
        assert os.environ["PYTHONDONTWRITEBYTECODE"] == "1"
        assert root.parent == output_dir.resolve()

    assert not root.exists()


def test_entrypoint_is_thin_and_does_not_import_heavy_runtime_at_module_load() -> None:
    module = inspect.getmodule(main)
    assert module is not None
    source = inspect.getsource(module)
    tree = ast.parse(source)
    functions = [node for node in tree.body if isinstance(node, ast.FunctionDef)]

    assert [node.name for node in functions] == ["main"]
    assert "PyQt6" not in source
    assert "torch" not in source
    assert "mne" not in source.lower()
    assert "chatpanel_long_session.runtime" not in source
    assert "sys.dont_write_bytecode = True" in source


@pytest.mark.parametrize(
    "callback_name",
    (
        "_wait_for_ready",
        "_wait_for_turn_terminal",
        "_wait_for_external_publication",
    ),
)
def test_deferred_poll_callbacks_stop_after_driver_finishing(
    callback_name: str,
) -> None:
    from scripts.dev.chatpanel_long_session.runtime import _LongSessionDriver

    driver = object.__new__(_LongSessionDriver)
    driver._finishing = True

    getattr(driver, callback_name)()


def test_driver_records_authoritative_query_state_result() -> None:
    from scripts.dev.chatpanel_long_session.runtime import _LongSessionDriver
    from XBrainLab.llm.tools.application_surface import ToolCommandResult

    driver = object.__new__(_LongSessionDriver)
    driver._finishing = False
    driver._active_turn_index = 2
    driver.application_command_results = []

    driver._record_application_command_result(
        ToolCommandResult(
            ok=True,
            tool_name="query_state",
            command_name="query_state",
            message="No data loaded. Next: Scan data source.",
            state={"pipeline_stage": "empty"},
            diagnostics={
                "publication_generation": 5,
                "publication_revision": 9,
            },
        )
    )

    assert driver.application_command_results == [
        {
            "sequence": 1,
            "turn_index": 2,
            "tool_name": "query_state",
            "command_name": "query_state",
            "ok": True,
            "publication_generation": 5,
            "publication_revision": 9,
            "pipeline_stage": "empty",
            "message_sha256": hashlib.sha256(
                b"No data loaded. Next: Scan data source."
            ).hexdigest(),
        }
    ]
