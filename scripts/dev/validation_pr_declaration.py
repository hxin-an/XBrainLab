#!/usr/bin/env python3
"""Build a reviewed validation descriptor from one GitHub event payload."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.dev.validation_control_plane import (
    ChangeDescriptor,
    ChangeIntent,
    ClaimLevel,
    Layer,
    RiskLevel,
)

_FIELD_PREFIX = "Validation-"
_KNOWN_FIELDS = frozenset({"Intent", "Risk", "Layers", "Rules"})


def _event_object(event_path: Path) -> dict[str, object]:
    payload = json.loads(event_path.expanduser().resolve(strict=True).read_text())
    if not isinstance(payload, dict):
        raise ValueError("GitHub event payload must be a JSON object")
    return payload


def _declaration_fields(body: str) -> dict[str, str]:
    fields: dict[str, str] = {}
    for raw_line in body.splitlines():
        line = raw_line.strip()
        if not line.startswith(_FIELD_PREFIX):
            continue
        name, separator, value = line.partition(":")
        field = name.removeprefix(_FIELD_PREFIX)
        if not separator or field not in _KNOWN_FIELDS:
            raise ValueError(f"unknown validation declaration field: {name}")
        if field in fields:
            raise ValueError(f"duplicate validation declaration field: {name}")
        clean_value = value.strip()
        if not clean_value:
            raise ValueError(f"validation declaration field is empty: {name}")
        fields[field] = clean_value
    return fields


def _comma_values(value: str | None) -> tuple[str, ...]:
    if value is None:
        return ()
    values = tuple(item.strip() for item in value.split(","))
    if any(not item for item in values):
        raise ValueError("validation declaration contains an empty list item")
    return values


def descriptor_from_github_event(
    event_name: str,
    event_path: Path,
) -> ChangeDescriptor:
    """Return PR-declared semantics; direct pushes use a critical CI floor."""

    event = _event_object(event_path)
    if event_name != "pull_request":
        return ChangeDescriptor(
            intent=ChangeIntent.CI,
            claim_level=ClaimLevel.PRODUCT_PR,
            declared_risk=RiskLevel.CRITICAL,
        )

    pull_request = event.get("pull_request")
    if not isinstance(pull_request, dict):
        raise ValueError("pull_request event payload is missing pull_request")
    body = pull_request.get("body")
    fields = _declaration_fields(body if isinstance(body, str) else "")
    if "Intent" not in fields:
        raise ValueError("pull request body requires Validation-Intent")
    try:
        intent = ChangeIntent(fields["Intent"])
    except ValueError as error:
        raise ValueError("invalid validation intent") from error
    try:
        risk = RiskLevel[fields.get("Risk", "low").upper()]
    except KeyError as error:
        raise ValueError("invalid validation risk") from error
    try:
        layers = frozenset(
            Layer(value) for value in _comma_values(fields.get("Layers"))
        )
    except ValueError as error:
        raise ValueError("invalid validation layer") from error
    return ChangeDescriptor(
        intent=intent,
        claim_level=ClaimLevel.PRODUCT_PR,
        declared_layers=layers,
        declared_risk=risk,
        required_rule_ids=frozenset(_comma_values(fields.get("Rules"))),
    )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--event-name", required=True)
    parser.add_argument("--event-path", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser


def main() -> int:
    args = _build_parser().parse_args()
    try:
        descriptor = descriptor_from_github_event(args.event_name, args.event_path)
        output = args.output.expanduser().resolve()
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(descriptor.to_json() + "\n", encoding="utf-8")
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(str(error), file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
