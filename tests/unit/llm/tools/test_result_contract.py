"""Security contract for unexpected assistant-tool failures."""

from __future__ import annotations

import ast
import logging
from pathlib import Path

import pytest

from XBrainLab.backend.application.results import ChangedState, CommandResult
from XBrainLab.llm.tools.result_contract import (
    SAFE_UNEXPECTED_FAILURE_CODE,
    SAFE_UNEXPECTED_FAILURE_MESSAGE,
    ToolResult,
    public_safe_result_projection,
    recover_authoritative_failure_state,
    redact_public_text,
    safe_unexpected_failure,
    tool_result_from_command,
)

PROJECT_ROOT = Path(__file__).resolve().parents[4]
PUBLIC_LOG_BOUNDARIES = (
    "XBrainLab/llm/agent/tool_execution_coordinator.py",
    "XBrainLab/llm/agent/tool_attempt_coordinator.py",
    "XBrainLab/llm/agent/verifier.py",
    "XBrainLab/llm/agent/controller.py",
    "XBrainLab/llm/agent/worker.py",
    "XBrainLab/llm/agent/parser.py",
    "XBrainLab/llm/agent/rag_lifecycle.py",
    "XBrainLab/llm/core/engine.py",
    "XBrainLab/debug/tool_executor.py",
    "XBrainLab/debug/tool_debug_mode.py",
    "XBrainLab/llm/tools/__init__.py",
    "XBrainLab/llm/tools/real/dataset_real.py",
    "XBrainLab/ui/components/assistant_runtime_lifecycle.py",
    "XBrainLab/ui/components/agent_manager.py",
)
PUBLIC_EXCEPTION_TYPE_BOUNDARIES = (
    "XBrainLab/backend/utils/public_diagnostics.py",
    "XBrainLab/backend/utils/public_diagnostic_projection.py",
    "XBrainLab/backend/utils/logger.py",
    "XBrainLab/backend/application/service.py",
    "XBrainLab/llm/tools/result_contract.py",
    "XBrainLab/ui/components/assistant_command_dispatcher.py",
    "XBrainLab/ui/dialogs/dataset/data_splitting_preview_dialog.py",
    "scripts/dev/run_application_command.py",
)
_SENSITIVE_LOG_NAMES = frozenset(
    {
        "detail",
        "diagnostic",
        "directory",
        "dispatched",
        "error",
        "error_message",
        "exc",
        "message",
        "model_id",
        "model_name",
        "parameter_keys",
        "payload",
        "request",
        "result",
        "tool_name",
        "validation_error",
        "view_mode",
    }
)
_SENSITIVE_LOG_ATTRIBUTES = frozenset(
    {
        "authorization_text",
        "directory",
        "error",
        "message",
        "model_id",
        "params",
        "path",
        "paths",
        "reason",
        "selection_detail",
        "tool_name",
        "view_mode",
    }
)
_CENTRAL_REDACTORS = frozenset(
    {
        "redact_developer_error_detail",
        "redact_public_text",
    }
)


def _unsafe_exception_exposures(path: Path) -> list[tuple[int, str]]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    findings: list[tuple[int, str]] = []
    for handler in (
        node for node in ast.walk(tree) if isinstance(node, ast.ExceptHandler)
    ):
        if not handler.name:
            continue
        for node in (
            child for statement in handler.body for child in ast.walk(statement)
        ):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id == "str"
                and node.args
                and isinstance(node.args[0], ast.Name)
                and node.args[0].id == handler.name
            ):
                findings.append((node.lineno, "str(exception)"))
            if (
                isinstance(node, ast.FormattedValue)
                and isinstance(node.value, ast.Name)
                and node.value.id == handler.name
            ):
                findings.append((node.lineno, "formatted exception"))
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr == "exception"
            ):
                findings.append((node.lineno, "unredacted exception log"))
    return findings


def _unsafe_dynamic_type_name_reads(path: Path) -> list[int]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    findings: list[int] = []
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Attribute) and node.attr == "__name__"):
            continue
        owner = node.value
        if (isinstance(owner, ast.Attribute) and owner.attr == "__class__") or (
            isinstance(owner, ast.Call)
            and isinstance(owner.func, ast.Name)
            and owner.func.id == "type"
        ):
            findings.append(node.lineno)
    return findings


def _contains_sensitive_log_value(node: ast.AST) -> bool:
    return any(
        (isinstance(child, ast.Name) and child.id in _SENSITIVE_LOG_NAMES)
        or (
            isinstance(child, ast.Attribute) and child.attr in _SENSITIVE_LOG_ATTRIBUTES
        )
        for child in ast.walk(node)
    )


def _uses_central_redactor(node: ast.AST) -> bool:
    return bool(
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id in _CENTRAL_REDACTORS
    )


def _unsafe_logger_values(path: Path) -> list[tuple[int, str]]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    findings: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if not (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and isinstance(node.func.value, ast.Name)
            and node.func.value.id == "logger"
            and node.func.attr
            in {"debug", "info", "warning", "error", "critical", "exception"}
        ):
            continue
        if node.func.attr == "exception":
            findings.append((node.lineno, "unredacted exception traceback"))
        values = (
            node.args[1:]
            if node.args and isinstance(node.args[0], ast.Constant)
            else node.args
        )
        findings.extend(
            (node.lineno, "unredacted dynamic log value")
            for value in values
            if _contains_sensitive_log_value(value)
            and not _uses_central_redactor(value)
        )
        if any(
            keyword.arg == "exc_info"
            and (
                not isinstance(keyword.value, ast.Constant)
                or keyword.value.value is not False
            )
            for keyword in node.keywords
        ):
            findings.append((node.lineno, "unredacted exception traceback"))
    return findings


def test_unexpected_failure_boundaries_have_no_raw_exception_exposure() -> None:
    findings = {
        relative_path: _unsafe_exception_exposures(PROJECT_ROOT / relative_path)
        for relative_path in PUBLIC_LOG_BOUNDARIES
    }

    assert findings == {relative_path: [] for relative_path in findings}


def test_public_log_boundaries_use_the_central_redactor() -> None:
    findings = {
        relative_path: _unsafe_logger_values(PROJECT_ROOT / relative_path)
        for relative_path in PUBLIC_LOG_BOUNDARIES
    }

    assert findings == {relative_path: [] for relative_path in findings}


def test_public_boundaries_do_not_read_dynamic_type_names() -> None:
    findings = {
        relative_path: _unsafe_dynamic_type_name_reads(PROJECT_ROOT / relative_path)
        for relative_path in PUBLIC_EXCEPTION_TYPE_BOUNDARIES
    }

    assert findings == {relative_path: [] for relative_path in findings}


def test_arbitrary_compatibility_namespace_escape_hatch_is_removed() -> None:
    source = (PROJECT_ROOT / "XBrainLab/llm/tools/application_surface.py").read_text(
        encoding="utf-8"
    )

    assert "COMPATIBILITY_TOOL_NAMESPACE" not in source


def test_unexpected_failure_factory_redacts_developer_log_and_public_fields(
    caplog,
) -> None:
    private_path = "/home/alice/private/subject-17/events.tsv"
    private_email = "alice@example.test"
    private_token = "token=" + "hf_super_secret"
    error = RuntimeError(f"{private_path} {private_email} {private_token}")
    logger = logging.getLogger("tests.safe-unexpected-failure")

    with caplog.at_level(logging.ERROR, logger=logger.name):
        failure = safe_unexpected_failure(
            logger,
            error,
            boundary="tool_execution_coordinator",
            operation="query_state",
        )

    assert failure.message == SAFE_UNEXPECTED_FAILURE_MESSAGE
    assert failure.error_code == SAFE_UNEXPECTED_FAILURE_CODE
    assert failure.error_type == "runtime"
    assert failure.recovery_action == "refresh_application_state"
    assert failure.recoverable is False
    assert failure.incident_id

    public_values = " ".join(
        (
            failure.message,
            failure.error_code,
            failure.recovery_action,
            failure.incident_id,
        )
    )
    assert private_path not in public_values
    assert private_email not in public_values
    assert private_token not in public_values

    developer_log = "\n".join(record.getMessage() for record in caplog.records)
    assert failure.incident_id in developer_log
    assert "RuntimeError" in developer_log
    assert private_path not in developer_log
    assert private_email not in developer_log
    assert private_token not in developer_log
    assert "[REDACTED_PATH]" in developer_log
    assert "[REDACTED_EMAIL]" in developer_log
    assert "[REDACTED_SECRET]" in developer_log


@pytest.mark.parametrize(
    ("private_value", "expected_marker"),
    [
        (
            "Authorization: Bearer hf_super_secret",
            "[REDACTED_SECRET]",
        ),
        (
            r"\\research-nas\patient-share\subject-17\events.tsv",
            "[REDACTED_PATH]",
        ),
        (
            "/home/alice/private/subject-17/events.tsv",
            "[REDACTED_PATH]",
        ),
        (
            r"C:\Users\Alice\private\subject-17\events.tsv",
            "[REDACTED_PATH]",
        ),
        ("OPENAI_API_KEY=sk-super-secret", "[REDACTED_SECRET]"),
        ("access-token: private-access-value", "[REDACTED_SECRET]"),
        ("hf_token = hf_private_value", "[REDACTED_SECRET]"),
        (
            "client_secret='private-client-value'",  # pragma: allowlist secret
            "[REDACTED_SECRET]",
        ),
        ("private-key: private-key-value", "[REDACTED_SECRET]"),
        ("API key: private-api-value", "[REDACTED_SECRET]"),
        ('{"token":"private-json-token"}', "[REDACTED_SECRET]"),
        (r"{\"token\":\"private-escaped-json-token\"}", "[REDACTED_SECRET]"),
        ("{'access_token':'private-json-token'}", "[REDACTED_SECRET]"),
        ("token%3Dhf_super_secret", "[REDACTED_SECRET]"),
        ("$HOME/private/subject-17/events.tsv", "[REDACTED_PATH]"),
        (r"%USERPROFILE%\private\subject-17\events.tsv", "[REDACTED_PATH]"),
        (
            r"C:\Users\Alice\private/D:\research\subject-17\events.tsv",
            "[REDACTED_PATH]",
        ),
    ],
)
def test_public_redactor_covers_secret_and_path_variants(
    private_value: str,
    expected_marker: str,
) -> None:
    redacted = redact_public_text(f"Action failed for {private_value}; choose another.")

    assert private_value not in redacted
    assert expected_marker in redacted
    assert "Action failed for" in redacted
    assert "choose another" in redacted


def test_public_redactor_preserves_ordinary_https_url_exactly() -> None:
    public_url = "https://docs.example.test/product/guide"

    assert redact_public_text(public_url) == public_url


def test_public_safe_result_projection_redacts_every_feedback_surface() -> None:
    private_path = r"\\research-nas\patient-share\subject-17\events.tsv"
    private_token = "Authorization: Bearer hf_super_secret"  # noqa: S105
    private_message = f"Could not open {private_path}; {private_token}"

    projection = public_safe_result_projection(
        message=private_message,
        blocked_reason=private_message,
        raw_result={
            "status": "failed",
            "message": private_message,
            "diagnostics": {"api_key": "sk-private-value"},  # pragma: allowlist secret
        },
        state={"last_error": {"message": private_message}},
        capability={"reasons": [private_message]},
        diagnostics={"detail": private_message, "access_token": "private-token"},
    )

    serialized = repr(projection)
    for private_value in (
        private_path,
        private_token,
        "hf_super_secret",
        "sk-private-value",
        "private-token",
    ):
        assert private_value not in serialized
    assert projection.message.startswith("Could not open")
    assert "[REDACTED_PATH]" in projection.message
    assert "[REDACTED_SECRET]" in projection.message


def test_success_tool_result_keeps_internal_message_until_public_projection() -> None:
    private_path = "/srv/private/sub-P001/session.edf"
    result = ToolResult(ok=True, message=f"Loaded {private_path}")

    projection = public_safe_result_projection(message=result.message)

    assert private_path in result.message
    assert private_path not in projection.message
    assert "session.edf" in projection.message
    assert "[REDACTED_PATH]" in projection.message


def test_public_projection_rejects_unknown_objects_fail_closed() -> None:
    class PrivateObject:
        def __str__(self) -> str:
            raise AssertionError("Unknown public values must not be rendered.")

        def __repr__(self) -> str:
            return "PrivateObject(/srv/clinical/sub-P001/session.edf, topsecret)"

    private_object = PrivateObject()

    projection = public_safe_result_projection(
        message="failed",
        raw_result=private_object,
        diagnostics={"detail": private_object},
    )

    assert projection.raw_result == "[UNSUPPORTED_VALUE]"
    assert projection.diagnostics == {"detail": "[UNSUPPORTED_VALUE]"}
    assert "/srv/clinical" not in repr(projection)
    assert "topsecret" not in repr(projection)


def test_public_projection_shares_one_budget_across_envelope_fields() -> None:
    shared = ["subject_id=Private-17"] * 32

    projection = public_safe_result_projection(
        message="failed",
        raw_result=shared,
        state={"shared": shared},
        capability={"shared": shared},
        diagnostics={"shared": shared},
    )

    assert isinstance(projection.raw_result, list)
    assert projection.state == {"shared": "[SHARED]"}
    assert projection.capability == {"shared": "[SHARED]"}
    assert projection.diagnostics == {"shared": "[SHARED]"}


def test_public_projection_and_tool_result_reject_hostile_truth_protocols() -> None:
    class HostileDiagnostics(dict[str, object]):
        def __bool__(self) -> bool:
            raise AssertionError("diagnostic truth protocol must not execute")

        def items(self):
            raise AssertionError("diagnostic mapping protocol must not execute")

    class HostileTruth:
        def __bool__(self) -> bool:
            raise AssertionError("tool result truth protocol must not execute")

    projection = public_safe_result_projection(
        message="failed",
        diagnostics=HostileDiagnostics({"detail": "private"}),
    )
    tool_result = ToolResult(ok=HostileTruth(), message="failed")  # type: ignore[arg-type]

    assert projection.diagnostics == {}
    assert tool_result.ok is False
    assert tool_result.message == "failed"


def test_tool_command_adapter_uses_only_public_command_result_projection() -> None:
    private_path = "/srv/clinical/subject-17/events.tsv"
    command_result = CommandResult.success_result(
        command_name="query_state",
        message="ready",
        state={"source_path": private_path},
        changed_state=ChangedState(),
        diagnostics={"source_path": private_path},
    )

    tool_result = tool_result_from_command(command_result)
    serialized = repr(tool_result)

    assert private_path not in serialized
    assert "[REDACTED_PATH]" in serialized


def test_failed_tool_result_projects_every_public_feedback_field() -> None:
    private_path = "/srv/clinical/subject-17/events.tsv"

    result = ToolResult(
        ok=False,
        message=f"Could not read {private_path}",
        payload={"source_path": private_path},
        state={"source_path": private_path},
        capability={"reasons": [f"Review {private_path}"]},
        diagnostics={"source_path": private_path},
    )

    serialized = repr(result)
    assert private_path not in serialized
    assert "[REDACTED_PATH]" in serialized


def test_failure_state_recovery_contains_hostile_publication_baseexception(
    caplog,
) -> None:
    class HostileBoundarySignal(BaseException):
        pass

    class HostilePublication:
        @property
        def usable(self) -> bool:
            raise HostileBoundarySignal("/srv/clinical/sub-P001/events.tsv")

    class Runtime:
        def get_view_publication(self) -> HostilePublication:
            return HostilePublication()

    logger = logging.getLogger("tests.hostile-publication")
    with caplog.at_level(logging.ERROR, logger=logger.name):
        recovery = recover_authoritative_failure_state(
            Runtime(),
            logger,
            operation="query_state",
            boundary="assistant_state_recovery",
        )

    assert recovery.state is None
    assert recovery.changed_state == {"state_unknown": True}
    assert recovery.diagnostics["refresh_required"] is True
    assert "/srv/clinical" not in "\n".join(
        record.getMessage() for record in caplog.records
    )


def test_unexpected_failure_does_not_execute_hostile_exception_metaclass(
    caplog,
) -> None:
    class HostileMeta(type):
        def __getattribute__(cls, name: str) -> object:
            if name == "__name__":
                raise AssertionError("hostile metaclass name access executed")
            return super().__getattribute__(name)

    class HostileError(Exception, metaclass=HostileMeta):
        def __str__(self) -> str:
            raise AssertionError("hostile exception string protocol executed")

    logger = logging.getLogger("tests.hostile-unexpected-failure")
    with caplog.at_level(logging.ERROR, logger=logger.name):
        failure = safe_unexpected_failure(
            logger,
            HostileError("/srv/Clinical Records/Mary Example"),
            boundary="assistant_tool",
            operation="query_state",
        )

    rendered = "\n".join(record.getMessage() for record in caplog.records)
    assert failure.error_code == SAFE_UNEXPECTED_FAILURE_CODE
    assert "exception_type=Exception" in rendered
    assert "Mary Example" not in rendered
