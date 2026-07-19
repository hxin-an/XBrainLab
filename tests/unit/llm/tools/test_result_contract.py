"""Security contract for unexpected assistant-tool failures."""

from __future__ import annotations

import ast
import logging
from pathlib import Path

import pytest

from XBrainLab.llm.tools.result_contract import (
    SAFE_UNEXPECTED_FAILURE_CODE,
    SAFE_UNEXPECTED_FAILURE_MESSAGE,
    public_safe_result_projection,
    redact_public_text,
    safe_unexpected_failure,
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
    "XBrainLab/llm/agent/product_turn_policy.py",
    "XBrainLab/llm/core/engine.py",
    "XBrainLab/debug/tool_executor.py",
    "XBrainLab/debug/tool_debug_mode.py",
    "XBrainLab/llm/tools/__init__.py",
    "XBrainLab/llm/tools/real/dataset_real.py",
    "XBrainLab/ui/components/assistant_runtime_lifecycle.py",
    "XBrainLab/ui/components/agent_manager.py",
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
