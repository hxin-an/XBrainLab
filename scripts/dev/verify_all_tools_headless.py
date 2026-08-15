import argparse
import json
import os
import sys
from collections import Counter
from collections.abc import Sequence
from dataclasses import asdict, dataclass, field
from typing import Any, cast

# Setup paths
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.append(PROJECT_ROOT)

from XBrainLab.backend.study import Study
from XBrainLab.debug.tool_executor import DebugExecutionEvidence, ToolExecutor
from XBrainLab.llm.action_contracts import AGENT_ACTION_CONTRACTS, AgentExecutionKind
from XBrainLab.llm.tools import get_all_tools
from XBrainLab.llm.tools.application_surface import ToolCommandResult
from XBrainLab.llm.tools.result_contract import UiRequest

EXPECTED_TOOL_NAMES = tuple(tool.name for tool in get_all_tools("real"))
EXPECTED_TOOL_NAME_SET = frozenset(EXPECTED_TOOL_NAMES)
_SAFETY_DIAGNOSTIC_DOMAINS = frozenset(
    {
        "authorization",
        "capability",
        "confirmation",
        "path",
        "policy",
        "provenance",
        "refresh",
        "reliability",
        "safety",
        "state",
        "view",
    }
)
_SAFETY_DIAGNOSTIC_STATES = frozenset(
    {
        "authorized",
        "bypass",
        "bypassed",
        "override",
        "reliable",
        "required",
        "skipped",
        "stale",
        "unknown",
    }
)
if len(EXPECTED_TOOL_NAMES) != 30 or len(EXPECTED_TOOL_NAME_SET) != 30:
    raise RuntimeError(
        "Canonical Real tool surface must contain exactly 30 unique tools."
    )


@dataclass(frozen=True)
class _VerifiedCall:
    tool_name: str
    params: dict[str, Any]
    confirmed: bool
    expected_ok: bool
    expected_error_type: str | None
    expected_command_name: str | None
    expected_changed_state: dict[str, bool]
    expected_state: dict[str, Any]
    expected_raw_result_contains: tuple[Any, ...]
    expected_ui_request_kind: str | None
    expected_ui_params: dict[str, Any]
    expected_diagnostics: dict[str, bool] = field(default_factory=dict)


def _default_script_path() -> str:
    return os.path.join(
        PROJECT_ROOT,
        "scripts/agent/debug/all_tools.json",
    )


def _is_canonical_script(script_path: str) -> bool:
    return os.path.realpath(script_path) == os.path.realpath(_default_script_path())


def _resolve_existing_script_paths(value: Any) -> Any:
    """Resolve existing repo-relative paths authored in the debug script."""
    if isinstance(value, dict):
        return {
            key: _resolve_existing_script_paths(item) for key, item in value.items()
        }
    if isinstance(value, list):
        return [_resolve_existing_script_paths(item) for item in value]
    if not isinstance(value, str) or os.path.isabs(value):
        return value
    candidate = os.path.abspath(os.path.join(PROJECT_ROOT, value))
    return candidate if os.path.exists(candidate) else value


def _result_payload(result: ToolCommandResult | UiRequest) -> dict[str, Any]:
    if isinstance(result, ToolCommandResult):
        return result.to_payload()
    return asdict(result)


def _path_value(value: Any, path: str) -> tuple[bool, Any]:
    current = value
    for part in path.split("."):
        if isinstance(current, dict) and part in current:
            current = current[part]
            continue
        return False, None
    return True, current


def _contains_value(container: Any, expected: Any) -> bool:
    if isinstance(container, dict):
        return expected in container or any(
            _contains_value(value, expected) for value in container.values()
        )
    if isinstance(container, (list, tuple, set)):
        return expected in container or any(
            _contains_value(value, expected) for value in container
        )
    return container == expected


def _validated_bool_mapping(
    value: Any,
    *,
    field_name: str,
    call_index: int,
) -> dict[str, bool] | None:
    if not isinstance(value, dict):
        print(
            f"Invalid script: expected.{field_name} for call {call_index} must be an object."
        )
        return None
    if not all(
        isinstance(key, str) and isinstance(item, bool) for key, item in value.items()
    ):
        print(
            f"Invalid script: expected.{field_name} for call {call_index} "
            "must map string keys to booleans."
        )
        return None
    return cast(dict[str, bool], value)


def _validated_calls(
    data: Any,
) -> list[_VerifiedCall] | None:
    if not isinstance(data, dict):
        print("Invalid script: top-level JSON value must be an object.")
        return None

    raw_calls = data.get("calls")
    if not isinstance(raw_calls, list) or not raw_calls:
        print("Invalid script: calls must be a non-empty JSON array.")
        return None

    calls: list[_VerifiedCall] = []
    declared_tools: list[str] = []
    for index, raw_call in enumerate(raw_calls, start=1):
        if not isinstance(raw_call, dict):
            print(f"Invalid script: call {index} must be a JSON object.")
            return None
        tool_name = raw_call.get("tool")
        params = raw_call.get("params", {})
        confirmed = raw_call.get("confirmed", False)
        expected = raw_call.get("expected")
        if not isinstance(tool_name, str) or not tool_name.strip():
            print(f"Invalid script: call {index} has no valid tool name.")
            return None
        if not isinstance(params, dict):
            print(f"Invalid script: params for call {index} must be a JSON object.")
            return None
        if not isinstance(confirmed, bool):
            print(f"Invalid script: confirmed for call {index} must be a boolean.")
            return None
        if not isinstance(expected, dict) or not expected:
            print(
                f"Invalid script: expected for call {index} must be a non-empty object."
            )
            return None
        expected_ok = expected.get("ok")
        expected_error_type = expected.get("error_type")
        expected_command_name = expected.get("command_name")
        expected_changed_state = _validated_bool_mapping(
            expected.get("changed_state", {}),
            field_name="changed_state",
            call_index=index,
        )
        expected_state = expected.get("state", {})
        expected_raw_result_contains = expected.get("raw_result_contains", [])
        expected_ui_request_kind = expected.get("ui_request_kind")
        expected_ui_params = expected.get("ui_params", {})
        expected_diagnostics = _validated_bool_mapping(
            expected.get("diagnostics", {}),
            field_name="diagnostics",
            call_index=index,
        )
        if expected_changed_state is None or expected_diagnostics is None:
            return None
        if not isinstance(expected_ok, bool):
            print(f"Invalid script: expected.ok for call {index} must be a boolean.")
            return None
        if expected_error_type is not None and not isinstance(
            expected_error_type,
            str,
        ):
            print(
                f"Invalid script: expected.error_type for call {index} "
                "must be a string."
            )
            return None
        if expected_command_name is not None and not isinstance(
            expected_command_name,
            str,
        ):
            print(
                f"Invalid script: expected.command_name for call {index} "
                "must be a string."
            )
            return None
        if not isinstance(expected_state, dict) or not all(
            isinstance(path, str) and path for path in expected_state
        ):
            print(
                f"Invalid script: expected.state for call {index} "
                "must map non-empty paths to expected values."
            )
            return None
        if not isinstance(expected_raw_result_contains, list):
            print(
                f"Invalid script: expected.raw_result_contains for call {index} "
                "must be an array."
            )
            return None
        if expected_ui_request_kind is not None and not isinstance(
            expected_ui_request_kind,
            str,
        ):
            print(
                f"Invalid script: expected.ui_request_kind for call {index} "
                "must be a string."
            )
            return None
        if not isinstance(expected_ui_params, dict) or not all(
            isinstance(path, str) and path for path in expected_ui_params
        ):
            print(
                f"Invalid script: expected.ui_params for call {index} "
                "must map non-empty paths to expected values."
            )
            return None

        normalized_name = tool_name.strip()
        contract = AGENT_ACTION_CONTRACTS.contract_for(normalized_name)
        if contract is None:
            print(
                f"Invalid script: call {index} tool '{normalized_name}' "
                "has no canonical action contract."
            )
            return None
        if expected_ok is False:
            if not expected_error_type:
                print(
                    f"Invalid script: blocked call {index} must declare "
                    "expected.error_type."
                )
                return None
        elif contract.execution_kind is AgentExecutionKind.UI_REQUEST:
            if not expected_ui_request_kind:
                print(
                    f"Invalid script: UI call {index} must declare "
                    "expected.ui_request_kind."
                )
                return None
        else:
            if (
                contract.execution_kind is AgentExecutionKind.APPLICATION_COMMAND
                and expected_command_name
                != (
                    contract.capability_command.value
                    if contract.capability_command is not None
                    else None
                )
            ):
                print(
                    f"Invalid script: call {index} has an incorrect or missing "
                    "expected.command_name."
                )
                return None
            if not (
                expected_changed_state or expected_state or expected_raw_result_contains
            ):
                print(
                    f"Invalid script: successful call {index} must declare "
                    "state, changed_state, or raw_result evidence."
                )
                return None

        declared_tools.append(normalized_name)
        calls.append(
            _VerifiedCall(
                tool_name=normalized_name,
                params=cast(dict[str, Any], params),
                confirmed=confirmed,
                expected_ok=expected_ok,
                expected_error_type=expected_error_type,
                expected_command_name=expected_command_name,
                expected_changed_state=expected_changed_state,
                expected_state=cast(dict[str, Any], expected_state),
                expected_raw_result_contains=tuple(expected_raw_result_contains),
                expected_ui_request_kind=expected_ui_request_kind,
                expected_ui_params=cast(dict[str, Any], expected_ui_params),
                expected_diagnostics=expected_diagnostics,
            )
        )

    counts = Counter(declared_tools)
    duplicate_tools = sorted(name for name, count in counts.items() if count != 1)
    declared_tool_set = set(declared_tools)
    missing_tools = sorted(EXPECTED_TOOL_NAME_SET - declared_tool_set)
    unknown_tools = sorted(declared_tool_set - EXPECTED_TOOL_NAME_SET)
    if missing_tools:
        print(
            f"Invalid script: missing canonical Real tools: {', '.join(missing_tools)}"
        )
    if unknown_tools:
        print(
            f"Invalid script: unknown canonical Real tools: {', '.join(unknown_tools)}"
        )
    if duplicate_tools:
        print(
            "Invalid script: each canonical Real tool must appear exactly once; "
            f"invalid counts for: {', '.join(duplicate_tools)}"
        )
    if missing_tools or unknown_tools or duplicate_tools:
        return None

    print(
        "Validated complete canonical Real surface: "
        f"{len(EXPECTED_TOOL_NAMES)} tools, exactly one call each."
    )
    return calls


def _is_safety_diagnostic_name(name: str) -> bool:
    parts = frozenset(part for part in name.lower().split("_") if part)
    return bool(
        parts.intersection(_SAFETY_DIAGNOSTIC_DOMAINS)
        and parts.intersection(_SAFETY_DIAGNOSTIC_STATES)
    )


def _truthy_safety_diagnostics(
    diagnostics: dict[str, Any],
    *,
    prefix: str = "",
) -> list[tuple[str, Any]]:
    findings: list[tuple[str, Any]] = []
    for name, value in diagnostics.items():
        path = f"{prefix}.{name}" if prefix else name
        if isinstance(value, dict):
            findings.extend(_truthy_safety_diagnostics(value, prefix=path))
        elif bool(value) and _is_safety_diagnostic_name(name):
            findings.append((path, value))
    return findings


def _matches_expected(
    call: _VerifiedCall, result: ToolCommandResult | UiRequest
) -> list[str]:
    mismatches: list[str] = []
    if isinstance(result, UiRequest):
        if call.expected_ok is not True:
            mismatches.append("received a UI request for an expected failure")
        if result.kind.value != call.expected_ui_request_kind:
            mismatches.append(
                f"ui_request_kind={result.kind.value!r}, "
                f"expected {call.expected_ui_request_kind!r}"
            )
        for path, expected in call.expected_ui_params.items():
            found, actual = _path_value(result.params, path)
            if not found or actual != expected:
                mismatches.append(f"ui_params.{path}={actual!r}, expected {expected!r}")
        return mismatches

    if result.ok is not call.expected_ok:
        mismatches.append(f"ok={result.ok}, expected {call.expected_ok}")
    if (
        call.expected_error_type is not None
        and result.error_type != call.expected_error_type
    ):
        mismatches.append(
            f"error_type={result.error_type!r}, expected {call.expected_error_type!r}"
        )
    if (
        call.expected_command_name is not None
        and result.command_name != call.expected_command_name
    ):
        mismatches.append(
            f"command_name={result.command_name!r}, "
            f"expected {call.expected_command_name!r}"
        )
    for name, expected in call.expected_changed_state.items():
        actual = result.changed_state.get(name, False)
        if actual is not expected:
            mismatches.append(f"changed_state.{name}={actual!r}, expected {expected!r}")
    for name, actual in result.changed_state.items():
        if name not in call.expected_changed_state and bool(actual):
            mismatches.append(f"unexpected truthy changed_state.{name}={actual!r}")
    raw_changed_state = (
        result.raw_result.get("changed_state")
        if isinstance(result.raw_result, dict)
        else None
    )
    if isinstance(raw_changed_state, dict):
        for name, actual in raw_changed_state.items():
            if name not in call.expected_changed_state and bool(actual):
                mismatches.append(
                    f"unexpected truthy raw_result.changed_state.{name}={actual!r}"
                )
    for path, expected in call.expected_diagnostics.items():
        found, actual = _path_value(result.diagnostics, path)
        if not found or actual is not expected:
            mismatches.append(f"diagnostics.{path}={actual!r}, expected {expected!r}")
    for path, actual in _truthy_safety_diagnostics(result.diagnostics):
        if path not in call.expected_diagnostics:
            mismatches.append(f"unexpected truthy diagnostics.{path}={actual!r}")
    raw_diagnostics = (
        result.raw_result.get("diagnostics")
        if isinstance(result.raw_result, dict)
        else None
    )
    if isinstance(raw_diagnostics, dict):
        for path, actual in _truthy_safety_diagnostics(raw_diagnostics):
            if path not in call.expected_diagnostics:
                mismatches.append(
                    f"unexpected truthy raw_result.diagnostics.{path}={actual!r}"
                )
    for path, expected in call.expected_state.items():
        found, actual = _path_value(result.state, path)
        if not found or actual != expected:
            mismatches.append(f"state.{path}={actual!r}, expected {expected!r}")
    for expected in call.expected_raw_result_contains:
        if not _contains_value(result.raw_result, expected):
            mismatches.append(f"raw_result does not contain {expected!r}")
    return mismatches


def _matches_execution_evidence(
    call: _VerifiedCall,
    result: ToolCommandResult | UiRequest,
    evidence: object,
) -> list[str]:
    if not isinstance(evidence, DebugExecutionEvidence):
        return ["missing typed canonical execution evidence"]

    mismatches: list[str] = []
    expected_counts = {
        "dispatch_count": 1,
        "publication_read_count": 1,
        "runtime_command_invocation_count": 0,
        "adapter_invocation_count": 0,
        "ui_adapter_invocation_count": 0,
    }
    contract = AGENT_ACTION_CONTRACTS.contract_for(call.tool_name)
    if contract is None:
        return ["missing canonical action contract for execution evidence"]

    blocked = bool(
        isinstance(result, ToolCommandResult)
        and not result.ok
        and result.error_type in {"confirmation_required", "input", "precondition"}
    )
    if not blocked and call.expected_ok:
        if contract.execution_kind is AgentExecutionKind.APPLICATION_COMMAND:
            expected_counts["runtime_command_invocation_count"] = 1
        elif contract.execution_kind is AgentExecutionKind.READ_ONLY:
            expected_counts["adapter_invocation_count"] = 1
            if call.tool_name == "get_dataset_info":
                expected_counts["runtime_command_invocation_count"] = 1
        elif contract.execution_kind is AgentExecutionKind.UI_REQUEST:
            expected_counts["adapter_invocation_count"] = 1
            expected_counts["ui_adapter_invocation_count"] = 1

    if evidence.tool_name != call.tool_name:
        mismatches.append(
            f"evidence.tool_name={evidence.tool_name!r}, expected {call.tool_name!r}"
        )
    for field_name, expected in expected_counts.items():
        actual = getattr(evidence, field_name)
        if actual != expected:
            mismatches.append(f"evidence.{field_name}={actual}, expected {expected}")
    return mismatches


def verify_all_tools_script(
    script_path: str | None = None,
    *,
    trust_external_script: bool = False,
) -> bool:
    script_path = os.path.abspath(script_path or _default_script_path())
    if not os.path.exists(script_path):
        print(f"Script not found: {script_path}")
        return False
    canonical_script = _is_canonical_script(script_path)
    if not canonical_script and not trust_external_script:
        print(
            "Refusing external debug script without explicit "
            "trust_external_script=True authorization."
        )
        return False

    print("Loading script...")
    try:
        with open(script_path, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError) as exc:
        print(f"Could not load script: {exc}")
        return False

    calls = _validated_calls(data)
    if calls is None:
        return False

    print(f"Found {len(calls)} calls. executing headless...")

    study = Study()
    executor = ToolExecutor(study)
    failures = 0
    executed_tool_names: list[str] = []
    trust_source = (
        "Canonical repository debug script"
        if canonical_script
        else "Explicitly trusted external debug script"
    )

    for i, call in enumerate(calls):
        tool = call.tool_name
        print(f"[{i + 1}/{len(calls)}] Executing {tool}...")
        params = cast(
            dict[str, Any],
            _resolve_existing_script_paths(call.params),
        )

        try:
            execution_options: dict[str, Any] = {
                "authorization_text": (
                    f"{trust_source} call: "
                    f"{json.dumps({'tool': tool, 'params': params}, sort_keys=True)}"
                )
            }
            if call.confirmed:
                execution_options["confirmed"] = True
            executed_tool_names.append(tool)
            result = executor.execute(tool, params, **execution_options)
            payload = _result_payload(result)
            summary = {
                key: payload.get(key)
                for key in (
                    "ok",
                    "tool_name",
                    "command_name",
                    "message",
                    "error_type",
                    "changed_state",
                    "kind",
                    "params",
                )
                if key in payload
            }
            print(f"  Result: {json.dumps(summary, default=str, sort_keys=True)}")
            mismatches = _matches_expected(call, result)
            mismatches.extend(
                _matches_execution_evidence(
                    call,
                    result,
                    getattr(executor, "last_execution_evidence", None),
                )
            )
            if mismatches:
                failures += 1
                print(f"  FAILED: {'; '.join(mismatches)}")
            elif isinstance(result, ToolCommandResult) and not result.ok:
                print("  Expected blocked outcome observed.")
        except Exception as e:
            failures += 1
            print(f"  CRASHED: {e}")

    execution_counts = Counter(executed_tool_names)
    invalid_execution_counts = sorted(
        name for name in EXPECTED_TOOL_NAMES if execution_counts.get(name, 0) != 1
    )
    if invalid_execution_counts:
        failures += 1
        print(f"FAILED exact-once execution for: {', '.join(invalid_execution_counts)}")
    print(f"Completed with {failures} failed call(s).")
    return failures == 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run the complete standalone debug-tool script headlessly.",
    )
    parser.add_argument(
        "script_path",
        nargs="?",
        help="Optional debug JSON script; external paths require explicit trust.",
    )
    parser.add_argument(
        "--trust-external-script",
        action="store_true",
        help="Authorize declared paths in a caller-supplied external script.",
    )
    args = parser.parse_args(argv)
    return (
        0
        if verify_all_tools_script(
            args.script_path,
            trust_external_script=args.trust_external_script,
        )
        else 1
    )


if __name__ == "__main__":
    raise SystemExit(main())
