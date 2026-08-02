#!/usr/bin/env python3
"""Run ApplicationService commands from JSON in a headless process."""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path
from typing import Any, NoReturn

from XBrainLab.backend.application import (
    command_specs,
    execute_automation_payload,
    get_application_service,
    mcp_tool_specs,
)
from XBrainLab.backend.study import Study
from XBrainLab.backend.utils.public_diagnostics import (
    DiagnosticTextLayout,
    public_diagnostic_text,
)

PUBLIC_CLI_MAX_PAYLOAD_BYTES = 1024 * 1024
PUBLIC_CLI_MAX_COMMANDS = 64
PUBLIC_CLI_MAX_OUTPUT_BYTES = 1024 * 1024
PUBLIC_CLI_MAX_DIAGNOSTIC_BYTES = 1024
_TOP_LEVEL_FAILURE_MESSAGE = "XBrainLab command runner could not complete the request."
_PAYLOAD_TOO_LARGE_ERROR = (
    "payload_too_large",
    "Payload exceeds the command runner input limit.",
)
_TOO_MANY_COMMANDS_ERROR = (
    "too_many_commands",
    "Payload contains too many commands.",
)
_OUTPUT_TOO_LARGE_ERROR = (
    "output_too_large",
    "Command output exceeds the command runner output limit.",
)


class _CliArgumentError(Exception):
    """Signal an invalid CLI shape without retaining private argument text."""


class _CliLimitError(Exception):
    """Carry only a stable public limit failure contract."""

    def __init__(self, error: tuple[str, str]) -> None:
        super().__init__()
        self.code, self.public_message = error


class _PublicArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> NoReturn:
        del message
        raise _CliArgumentError


def parse_args() -> argparse.Namespace:
    parser = _PublicArgumentParser(
        description="Execute XBrainLab ApplicationService commands headlessly.",
    )
    parser.add_argument(
        "--payload",
        help="JSON object with command/command_name and arguments.",
    )
    parser.add_argument(
        "--payload-file",
        type=Path,
        help="Path to a JSON object or list of command payloads.",
    )
    parser.add_argument(
        "--list-schemas",
        action="store_true",
        help="Print command schemas with current capability/autonomy policy.",
    )
    parser.add_argument(
        "--mcp-tools",
        action="store_true",
        help="Print MCP-shaped tool schemas backed by ApplicationService commands.",
    )
    parser.add_argument(
        "--include-legacy-compatibility",
        action="store_true",
        help=(
            "Explicitly expose and allow deprecated direct load/label commands "
            "for migration tooling."
        ),
    )
    return parser.parse_args()


def main() -> int:
    product_logger = logging.getLogger("XBrainLab")
    original_level = product_logger.level
    product_logger.setLevel(logging.WARNING)
    try:
        try:
            return _run(parse_args())
        except SystemExit as error:
            if type(error) is SystemExit and error.code in (None, 0):
                raise
            return _emit_public_error(
                code="application_command_failed",
                message=_TOP_LEVEL_FAILURE_MESSAGE,
            )
        except Exception:
            return _emit_public_error(
                code="application_command_failed",
                message=_TOP_LEVEL_FAILURE_MESSAGE,
            )
    finally:
        product_logger.setLevel(original_level)


def _run(args: argparse.Namespace) -> int:
    if args.list_schemas:
        service = get_application_service(Study())
        return _emit_public_json(
            [
                spec.to_dict()
                for spec in command_specs(
                    service,
                    include_legacy_compatibility=args.include_legacy_compatibility,
                )
            ],
            exit_code=0,
        )

    if args.mcp_tools:
        service = get_application_service(Study())
        return _emit_public_json(
            mcp_tool_specs(
                service,
                include_legacy_compatibility=args.include_legacy_compatibility,
            ),
            exit_code=0,
        )

    try:
        payloads = _load_payloads(args)
    except _CliLimitError as error:
        return _emit_public_error(
            code=error.code,
            message=error.public_message,
        )
    except FileNotFoundError:
        return _emit_payload_error("Payload file could not be found.")
    except PermissionError:
        return _emit_payload_error(
            "Payload file could not be read because permission was denied."
        )
    except UnicodeDecodeError:
        return _emit_payload_error("Payload file must contain valid UTF-8 text.")
    except json.JSONDecodeError:
        return _emit_payload_error("Payload must contain valid JSON.")
    except OSError:
        return _emit_payload_error("Payload file could not be read.")
    service = get_application_service(Study())
    executions = [
        execute_automation_payload(
            service,
            payload,
            allow_legacy_compatibility=args.include_legacy_compatibility,
        ).to_public_dict()
        for payload in payloads
    ]
    exit_code = 0 if all(item["accepted"] for item in executions) else 1
    return _emit_public_json(executions, exit_code=exit_code)


def _load_payloads(args: argparse.Namespace) -> list[dict[str, Any]]:
    if args.payload:
        payload_text = _bounded_inline_payload(args.payload)
    elif args.payload_file:
        payload_text = _read_bounded_payload_file(args.payload_file).decode("utf-8")
    else:
        raise SystemExit(
            "Provide --payload, --payload-file, --list-schemas, or --mcp-tools."
        )

    data = json.loads(payload_text)
    if type(data) is dict:
        return [data]
    if type(data) is list:
        if len(data) > PUBLIC_CLI_MAX_COMMANDS:
            raise _CliLimitError(_TOO_MANY_COMMANDS_ERROR)
        if all(type(item) is dict for item in data):
            return data
    raise SystemExit("Payload must be a JSON object or a list of JSON objects.")


def _bounded_inline_payload(payload: str) -> str:
    if len(payload) > PUBLIC_CLI_MAX_PAYLOAD_BYTES:
        raise _CliLimitError(_PAYLOAD_TOO_LARGE_ERROR)
    if len(payload.encode("utf-8")) > PUBLIC_CLI_MAX_PAYLOAD_BYTES:
        raise _CliLimitError(_PAYLOAD_TOO_LARGE_ERROR)
    return payload


def _read_bounded_payload_file(path: Path) -> bytes:
    with path.open("rb") as stream:
        payload = stream.read(PUBLIC_CLI_MAX_PAYLOAD_BYTES + 1)
    if len(payload) > PUBLIC_CLI_MAX_PAYLOAD_BYTES:
        raise _CliLimitError(_PAYLOAD_TOO_LARGE_ERROR)
    return payload


def _emit_public_json(value: Any, *, exit_code: int) -> int:
    rendered = _bounded_public_json(value)
    if rendered is None:
        return _emit_public_error(
            code=_OUTPUT_TOO_LARGE_ERROR[0],
            message=_OUTPUT_TOO_LARGE_ERROR[1],
        )
    sys.stdout.write(f"{rendered}\n")
    return exit_code


def _bounded_public_json(value: Any) -> str | None:
    remaining_bytes = PUBLIC_CLI_MAX_OUTPUT_BYTES - 1
    chunks: list[str] = []
    encoder = json.JSONEncoder(ensure_ascii=False, indent=2)
    for chunk in encoder.iterencode(value):
        if len(chunk) > remaining_bytes:
            return None
        chunk_bytes = chunk.encode("utf-8")
        if len(chunk_bytes) > remaining_bytes:
            return None
        chunks.append(chunk)
        remaining_bytes -= len(chunk_bytes)
    return "".join(chunks)


def _emit_payload_error(message: str) -> int:
    return _emit_public_error(code="invalid_payload", message=message)


def _emit_public_error(*, code: str, message: str) -> int:
    safe_code = public_diagnostic_text(
        code,
        layout=DiagnosticTextLayout.SINGLE_LINE,
    )
    safe_message = public_diagnostic_text(
        message,
        layout=DiagnosticTextLayout.SINGLE_LINE,
    )
    payload = {
        "ok": False,
        "error": {
            "code": safe_code,
            "message": safe_message,
        },
    }
    rendered = json.dumps(
        payload,
        ensure_ascii=False,
        separators=(",", ":"),
    )
    if len(rendered.encode("utf-8")) + 1 > PUBLIC_CLI_MAX_DIAGNOSTIC_BYTES:
        payload["error"]["message"] = "Diagnostic output was truncated."
        rendered = json.dumps(
            payload,
            ensure_ascii=False,
            separators=(",", ":"),
        )
    sys.stderr.write(f"{rendered}\n")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
