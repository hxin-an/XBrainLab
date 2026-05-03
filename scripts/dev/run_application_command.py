#!/usr/bin/env python3
"""Run ApplicationService commands from JSON in a headless process."""

from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path
from typing import Any

from XBrainLab.backend.application import (
    ApplicationService,
    command_specs,
    execute_automation_payload,
    mcp_tool_specs,
)
from XBrainLab.backend.study import Study


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
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
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    logging.getLogger("XBrainLab").setLevel(logging.WARNING)
    service = ApplicationService(Study())

    if args.list_schemas:
        print(
            json.dumps(
                [spec.to_dict() for spec in command_specs(service)],
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0

    if args.mcp_tools:
        print(json.dumps(mcp_tool_specs(service), ensure_ascii=False, indent=2))
        return 0

    payloads = _load_payloads(args)
    executions = [
        execute_automation_payload(service, payload).to_dict() for payload in payloads
    ]
    print(json.dumps(executions, ensure_ascii=False, indent=2))
    return 0 if all(item["accepted"] for item in executions) else 1


def _load_payloads(args: argparse.Namespace) -> list[dict[str, Any]]:
    if args.payload:
        data = json.loads(args.payload)
    elif args.payload_file:
        data = json.loads(args.payload_file.read_text(encoding="utf-8"))
    else:
        raise SystemExit(
            "Provide --payload, --payload-file, --list-schemas, or --mcp-tools."
        )

    if isinstance(data, dict):
        return [data]
    if isinstance(data, list) and all(isinstance(item, dict) for item in data):
        return data
    raise SystemExit("Payload must be a JSON object or a list of JSON objects.")


if __name__ == "__main__":
    raise SystemExit(main())
