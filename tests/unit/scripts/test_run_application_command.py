"""Public diagnostic tests for the headless application command runner."""

from __future__ import annotations

import argparse
import json
import logging
from collections.abc import Callable
from pathlib import Path

import pytest

from scripts.dev import run_application_command
from XBrainLab.backend.application import AutomationExecution


def _payload_file_args(path: Path) -> argparse.Namespace:
    return argparse.Namespace(
        payload=None,
        payload_file=path,
        list_schemas=False,
        include_legacy_compatibility=False,
    )


def _inline_payload_args(
    payload: str = '{"command":"query_state"}',
) -> argparse.Namespace:
    return argparse.Namespace(
        payload=payload,
        payload_file=None,
        list_schemas=False,
        include_legacy_compatibility=False,
    )


def _run_payload_file(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    path: Path,
) -> tuple[int, str, str]:
    monkeypatch.setattr(
        run_application_command,
        "parse_args",
        lambda: _payload_file_args(path),
    )
    monkeypatch.setattr(
        run_application_command,
        "get_application_service",
        lambda _study: object(),
    )
    monkeypatch.setattr(run_application_command, "Study", object)

    return_code = run_application_command.main()
    captured = capsys.readouterr()
    return return_code, captured.out, captured.err


def _assert_public_cli_error(
    result: tuple[int, str, str],
    *,
    code: str,
    message: str,
) -> None:
    return_code, stdout, stderr = result

    assert return_code == 2
    assert stdout == ""
    assert len(stderr.encode("utf-8")) <= (
        run_application_command.PUBLIC_CLI_MAX_DIAGNOSTIC_BYTES
    )
    assert json.loads(stderr) == {
        "ok": False,
        "error": {
            "code": code,
            "message": message,
        },
    }


def _assert_safe_payload_file_failure(
    result: tuple[int, str, str],
    *,
    private_values: tuple[str, ...],
) -> None:
    return_code, stdout, stderr = result

    assert return_code == 2
    assert stdout == ""
    assert stderr.strip()
    assert len(stderr.encode("utf-8")) <= 1024
    assert "Traceback" not in stderr
    payload = json.loads(stderr)
    assert payload == {
        "ok": False,
        "error": {
            "code": "invalid_payload",
            "message": payload["error"]["message"],
        },
    }
    for private_value in private_values:
        assert private_value not in stderr


def test_cli_resource_limits_are_centralized_and_stable() -> None:
    assert run_application_command.PUBLIC_CLI_MAX_PAYLOAD_BYTES == 1024 * 1024
    assert run_application_command.PUBLIC_CLI_MAX_COMMANDS == 64
    assert run_application_command.PUBLIC_CLI_MAX_OUTPUT_BYTES == 1024 * 1024
    assert run_application_command.PUBLIC_CLI_MAX_DIAGNOSTIC_BYTES == 1024


def test_missing_payload_file_emits_bounded_public_diagnostic(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    private_path = tmp_path / "patient-Jane" / "missing payload.json"

    result = _run_payload_file(monkeypatch, capsys, private_path)

    _assert_safe_payload_file_failure(
        result,
        private_values=(str(private_path), "patient-Jane"),
    )


def test_unreadable_payload_file_emits_bounded_public_diagnostic(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    private_path = tmp_path / "patient-Jane" / "protected payload.json"
    original_read_text: Callable[..., str] = Path.read_text

    def deny_private_payload(path: Path, *args, **kwargs) -> str:
        if path == private_path:
            raise PermissionError(13, "Permission denied", str(private_path))
        return original_read_text(path, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", deny_private_payload)
    result = _run_payload_file(monkeypatch, capsys, private_path)

    _assert_safe_payload_file_failure(
        result,
        private_values=(str(private_path), "patient-Jane"),
    )


def test_non_utf8_payload_file_emits_bounded_public_diagnostic(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    private_path = tmp_path / "patient-Jane-invalid-utf8.json"
    private_path.write_bytes(b'{"command":"query_state","subject":"\xff"}')

    result = _run_payload_file(monkeypatch, capsys, private_path)

    _assert_safe_payload_file_failure(
        result,
        private_values=(str(private_path), "patient-Jane"),
    )


def test_invalid_json_payload_file_emits_bounded_public_diagnostic(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    private_path = tmp_path / "patient-Jane-invalid.json"
    private_value = "/srv/private/patient-Jane/session.edf"
    private_path.write_text(
        f'{{"command":"query_state","source":"{private_value}"',
        encoding="utf-8",
    )

    result = _run_payload_file(monkeypatch, capsys, private_path)

    _assert_safe_payload_file_failure(
        result,
        private_values=(str(private_path), private_value, "patient-Jane"),
    )


def test_oversized_payload_file_is_rejected_before_json_materialization(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    private_path = tmp_path / "Clinical Records" / "Jane Doe.json"
    private_path.parent.mkdir()
    private_path.write_bytes(
        b"{" + (b"x" * run_application_command.PUBLIC_CLI_MAX_PAYLOAD_BYTES)
    )
    original_json_loads = json.loads

    def reject_json_materialization(_payload: object) -> object:
        raise AssertionError("Oversized payload must be rejected before json.loads")

    monkeypatch.setattr(
        run_application_command.json,
        "loads",
        reject_json_materialization,
    )

    result = _run_payload_file(monkeypatch, capsys, private_path)

    assert result[0] == 2
    assert result[1] == ""
    assert original_json_loads(result[2]) == {
        "ok": False,
        "error": {
            "code": "payload_too_large",
            "message": "Payload exceeds the command runner input limit.",
        },
    }
    assert str(private_path) not in result[2]
    assert "Jane Doe" not in result[2]


def test_payload_file_reader_caps_bytes_before_materialization() -> None:
    read_sizes: list[int] = []

    class BoundedReadProbe:
        def __enter__(self) -> BoundedReadProbe:
            return self

        def __exit__(self, *_args: object) -> None:
            return None

        def read(self, size: int = -1) -> bytes:
            read_sizes.append(size)
            if size < 0:
                raise AssertionError("Payload file reads must have an explicit cap")
            return b"x" * size

    class PayloadPathProbe:
        def open(self, mode: str) -> BoundedReadProbe:
            assert mode == "rb"
            return BoundedReadProbe()

    with pytest.raises(run_application_command._CliLimitError) as error:
        run_application_command._read_bounded_payload_file(PayloadPathProbe())

    assert read_sizes == [run_application_command.PUBLIC_CLI_MAX_PAYLOAD_BYTES + 1]
    assert error.value.code == "payload_too_large"
    assert error.value.public_message == (
        "Payload exceeds the command runner input limit."
    )


def test_cli_rejects_command_count_before_execution(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    payloads = [
        {"command": "query_state"}
        for _ in range(run_application_command.PUBLIC_CLI_MAX_COMMANDS + 1)
    ]
    monkeypatch.setattr(
        run_application_command,
        "parse_args",
        lambda: _inline_payload_args(json.dumps(payloads)),
    )
    monkeypatch.setattr(run_application_command, "Study", object)
    monkeypatch.setattr(
        run_application_command,
        "get_application_service",
        lambda _study: object(),
    )
    monkeypatch.setattr(
        run_application_command,
        "execute_automation_payload",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("Over-limit commands must not execute")
        ),
    )

    return_code = run_application_command.main()
    captured = capsys.readouterr()

    _assert_public_cli_error(
        (return_code, captured.out, captured.err),
        code="too_many_commands",
        message="Payload contains too many commands.",
    )


def test_cli_preserves_in_limit_batch_behavior(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    payloads = [
        {"command": "query_state"}
        for _ in range(run_application_command.PUBLIC_CLI_MAX_COMMANDS)
    ]
    execution = AutomationExecution(
        accepted=True,
        command_name="query_state",
        verification={"schema_valid": True},
        autonomy={},
        capability=None,
        result=None,
        state={"pipeline_stage": "empty"},
    )
    monkeypatch.setattr(
        run_application_command,
        "parse_args",
        lambda: _inline_payload_args(json.dumps(payloads)),
    )
    monkeypatch.setattr(run_application_command, "Study", object)
    monkeypatch.setattr(
        run_application_command,
        "get_application_service",
        lambda _study: object(),
    )
    monkeypatch.setattr(
        run_application_command,
        "execute_automation_payload",
        lambda *_args, **_kwargs: execution,
    )

    return_code = run_application_command.main()
    captured = capsys.readouterr()
    response = json.loads(captured.out)

    assert return_code == 0
    assert captured.err == ""
    assert len(response) == run_application_command.PUBLIC_CLI_MAX_COMMANDS
    assert len(captured.out.encode("utf-8")) <= (
        run_application_command.PUBLIC_CLI_MAX_OUTPUT_BYTES
    )


def test_cli_json_redacts_client_identity_variants(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    private_identities = ("Jane Doe", "Mary Example", "Bob Jones", "王小明")
    execution = AutomationExecution(
        accepted=True,
        command_name="query_state",
        verification={
            "client": private_identities[0],
            "message": "Client Mary Example failed validation. Retry.",
        },
        autonomy={"client_\u200bidentity": private_identities[2]},
        capability=None,
        result={
            "message": "客\u200b戶王小明從\u200b匯入畫面載入成功。",
        },
        state={
            "client_name": private_identities[1],
            "客\u200b户": private_identities[3],
        },
    )
    monkeypatch.setattr(run_application_command, "parse_args", _inline_payload_args)
    monkeypatch.setattr(run_application_command, "Study", object)
    monkeypatch.setattr(
        run_application_command,
        "get_application_service",
        lambda _study: object(),
    )
    monkeypatch.setattr(
        run_application_command,
        "execute_automation_payload",
        lambda *_args, **_kwargs: execution,
    )

    return_code = run_application_command.main()
    captured = capsys.readouterr()

    assert return_code == 0
    assert captured.err == ""
    assert json.loads(captured.out)[0]["accepted"] is True
    assert all(identity not in captured.out for identity in private_identities)
    assert "[SUBJECT_REF:" in captured.out


@pytest.mark.parametrize(
    ("error_message", "private_identity"),
    (
        (
            "Unsupported command: Failed to read /home/alice/Clinical Records/"
            "Jane Doe/session 01/eeg data.edf for subject Jane Doe",
            "Jane Doe",
        ),
        (
            r"Unsupported command: Could not read C:\Users\Mary Example"
            r"\EEG Studies\session 01\recording data.gdf for client Mary Example",
            "Mary Example",
        ),
        (
            r"Unsupported command: Could not read \\lab-server\Clinical Share"
            r"\Bob Jones\session 01\events data.tsv for patient Bob Jones",
            "Bob Jones",
        ),
        (
            "Unsupported command: Could not read /srv/Clinical Records/王小明/"
            "session 01/events data.tsv for subject 王小明",
            "王小明",
        ),
    ),
)
def test_cli_json_redacts_terminal_identity_in_verification_error(
    error_message: str,
    private_identity: str,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    execution = AutomationExecution(
        accepted=False,
        command_name="unknown",
        verification={"error": error_message},
        autonomy={},
        capability=None,
        result=None,
        state={},
    )
    monkeypatch.setattr(run_application_command, "parse_args", _inline_payload_args)
    monkeypatch.setattr(run_application_command, "Study", object)
    monkeypatch.setattr(
        run_application_command,
        "get_application_service",
        lambda _study: object(),
    )
    monkeypatch.setattr(
        run_application_command,
        "execute_automation_payload",
        lambda *_args, **_kwargs: execution,
    )

    return_code = run_application_command.main()
    captured = capsys.readouterr()

    assert return_code == 1
    assert captured.err == ""
    assert private_identity not in captured.out
    assert "[REDACTED_PATH]" in captured.out
    assert "[SUBJECT_REF:" in captured.out


def test_cli_rejects_oversized_execution_output_without_partial_stdout(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    private_value = "/srv/Clinical Records/Jane Doe/session.edf"

    class OversizedExecution:
        def to_public_dict(self) -> dict[str, object]:
            return {
                "accepted": True,
                "detail": private_value
                + ("x" * run_application_command.PUBLIC_CLI_MAX_OUTPUT_BYTES),
            }

    monkeypatch.setattr(run_application_command, "parse_args", _inline_payload_args)
    monkeypatch.setattr(run_application_command, "Study", object)
    monkeypatch.setattr(
        run_application_command,
        "get_application_service",
        lambda _study: object(),
    )
    monkeypatch.setattr(
        run_application_command,
        "execute_automation_payload",
        lambda *_args, **_kwargs: OversizedExecution(),
    )

    return_code = run_application_command.main()
    captured = capsys.readouterr()

    _assert_public_cli_error(
        (return_code, captured.out, captured.err),
        code="output_too_large",
        message="Command output exceeds the command runner output limit.",
    )
    assert private_value not in captured.err
    assert "Jane Doe" not in captured.err


def test_cli_bounds_schema_output(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    private_value = "/srv/Clinical Records/Mary Example/session.edf"
    oversized_text = private_value + (
        "x" * run_application_command.PUBLIC_CLI_MAX_OUTPUT_BYTES
    )
    args = argparse.Namespace(
        payload=None,
        payload_file=None,
        list_schemas=True,
        include_legacy_compatibility=False,
    )

    class OversizedSpec:
        def to_dict(self) -> dict[str, str]:
            return {"description": oversized_text}

    monkeypatch.setattr(run_application_command, "parse_args", lambda: args)
    monkeypatch.setattr(run_application_command, "Study", object)
    monkeypatch.setattr(
        run_application_command,
        "get_application_service",
        lambda _study: object(),
    )
    monkeypatch.setattr(
        run_application_command,
        "command_specs",
        lambda *_args, **_kwargs: [OversizedSpec()],
    )
    return_code = run_application_command.main()
    captured = capsys.readouterr()

    _assert_public_cli_error(
        (return_code, captured.out, captured.err),
        code="output_too_large",
        message="Command output exceeds the command runner output limit.",
    )
    assert private_value not in captured.err
    assert "Mary Example" not in captured.err


def test_main_restores_product_logger_level_after_payload_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    product_logger = logging.getLogger("XBrainLab")
    original_level = product_logger.level
    product_logger.setLevel(logging.INFO)
    try:
        result = _run_payload_file(
            monkeypatch,
            capsys,
            tmp_path / "missing.json",
        )

        assert result[0] == 2
        assert product_logger.level == logging.INFO
    finally:
        product_logger.setLevel(original_level)


def test_service_construction_failure_emits_bounded_redacted_json(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    private_path = "/srv/Clinical Records/Mary Example"
    monkeypatch.setattr(run_application_command, "parse_args", _inline_payload_args)
    monkeypatch.setattr(run_application_command, "Study", object)
    monkeypatch.setattr(
        run_application_command,
        "get_application_service",
        lambda _study: (_ for _ in ()).throw(RuntimeError(private_path)),
    )

    return_code = run_application_command.main()
    captured = capsys.readouterr()
    payload = json.loads(captured.err)

    assert return_code == 2
    assert captured.out == ""
    assert payload["ok"] is False
    assert payload["error"]["code"] == "application_command_failed"
    assert private_path not in captured.err
    assert "Mary Example" not in captured.err
    assert "Traceback" not in captured.err
    assert len(captured.err.encode("utf-8")) <= 1024


def test_argument_boundary_failure_emits_bounded_redacted_json_and_restores_logger(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    private_path = "/srv/Clinical Records/Mary Example"
    product_logger = logging.getLogger("XBrainLab")
    original_level = product_logger.level
    product_logger.setLevel(logging.INFO)
    monkeypatch.setattr(
        run_application_command,
        "parse_args",
        lambda: (_ for _ in ()).throw(RuntimeError(private_path)),
    )

    try:
        return_code = run_application_command.main()
        captured = capsys.readouterr()
        payload = json.loads(captured.err)

        assert return_code == 2
        assert captured.out == ""
        assert payload["error"]["code"] == "application_command_failed"
        assert private_path not in captured.err
        assert "Mary Example" not in captured.err
        assert "Traceback" not in captured.err
        assert len(captured.err.encode("utf-8")) <= 1024
        assert product_logger.level == logging.INFO
    finally:
        product_logger.setLevel(original_level)


def test_invalid_cli_argument_does_not_echo_private_value(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    private_path = "/srv/Clinical Records/Mary Example"
    monkeypatch.setattr(
        run_application_command.sys,
        "argv",
        ["run_application_command.py", "--unexpected", private_path],
    )

    return_code = run_application_command.main()
    captured = capsys.readouterr()
    payload = json.loads(captured.err)

    assert return_code == 2
    assert captured.out == ""
    assert payload["error"]["code"] == "application_command_failed"
    assert private_path not in captured.err
    assert "Mary Example" not in captured.err
    assert "Traceback" not in captured.err
    assert len(captured.err.encode("utf-8")) <= 1024


def test_top_level_failure_does_not_execute_hostile_exception_protocols(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    class HostileMeta(type):
        def __getattribute__(cls, name: str) -> object:
            if name == "__name__":
                raise AssertionError("hostile exception metaclass name access executed")
            return super().__getattribute__(name)

    class HostileCliError(Exception, metaclass=HostileMeta):
        def __str__(self) -> str:
            raise AssertionError("hostile exception string protocol executed")

    product_logger = logging.getLogger("XBrainLab")
    original_level = product_logger.level
    product_logger.setLevel(logging.INFO)
    monkeypatch.setattr(run_application_command, "parse_args", _inline_payload_args)
    monkeypatch.setattr(run_application_command, "Study", object)
    monkeypatch.setattr(
        run_application_command,
        "get_application_service",
        lambda _study: object(),
    )
    monkeypatch.setattr(
        run_application_command,
        "execute_automation_payload",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            HostileCliError("/srv/Clinical Records/Mary Example")
        ),
    )

    try:
        return_code = run_application_command.main()
        captured = capsys.readouterr()
        payload = json.loads(captured.err)

        assert return_code == 2
        assert captured.out == ""
        assert payload["error"]["code"] == "application_command_failed"
        assert "Mary Example" not in captured.err
        assert product_logger.level == logging.INFO
    finally:
        product_logger.setLevel(original_level)
