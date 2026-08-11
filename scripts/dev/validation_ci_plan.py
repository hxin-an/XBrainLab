#!/usr/bin/env python3
"""Translate a canonical validation plan into existing CI execution capabilities."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path

from scripts.dev.ci_gate_ownership import CI_GATE_OWNERS
from scripts.dev.ci_test_command_catalog import (
    LINUX_CI_COMMANDS,
    PLATFORM_CI_COMMANDS,
)
from scripts.dev.handoff_gate_spec import HANDOFF_GATE_SPECS
from scripts.dev.validation_control_plane import Layer, ValidationPlan

_GIT_SHA = re.compile(r"^(?:[0-9a-f]{40}|[0-9a-f]{64})$")


def _required_bool(payload: dict[str, object], key: str) -> bool:
    value = payload.get(key)
    if not isinstance(value, bool):
        raise ValueError(f"CI validation plan field {key!r} must be a boolean")
    return value


@dataclass(frozen=True, slots=True)
class CiValidationPlan:
    """Bounded CI capabilities selected from one source validation plan."""

    plan_digest: str
    source_sha: str
    selected_gate_ids: tuple[str, ...]
    gate_owners: tuple[tuple[str, str], ...]
    required_owners: tuple[str, ...]
    run_lint: bool
    run_product: bool
    run_docs: bool
    run_focused: bool
    run_ui: bool
    run_native: bool
    run_public_data: bool
    run_platform: bool
    linux_commands: tuple[str, ...]
    platform_commands: tuple[str, ...]

    def __post_init__(self) -> None:
        if not _GIT_SHA.fullmatch(self.source_sha):
            raise ValueError("CI plan source SHA must be a lowercase Git hash")
        if not re.fullmatch(r"[0-9a-f]{64}", self.plan_digest):
            raise ValueError("CI plan digest must be lowercase SHA-256")
        if len(self.selected_gate_ids) != len(set(self.selected_gate_ids)):
            raise ValueError("CI plan repeats selected gate IDs")
        if tuple(gate_id for gate_id, _owner in self.gate_owners) != (
            self.selected_gate_ids
        ):
            raise ValueError("CI plan gate owners do not cover selected gates exactly")
        stale_owners = tuple(
            gate_id
            for gate_id, owner in self.gate_owners
            if CI_GATE_OWNERS.get(gate_id) != owner
        )
        if stale_owners:
            raise ValueError(
                "CI plan gate ownership differs from the source registry: "
                + ", ".join(stale_owners)
            )
        owners = tuple(sorted({owner for _gate_id, owner in self.gate_owners}))
        if owners != self.required_owners:
            raise ValueError("CI plan required owners do not match gate ownership")
        expected_flags = {
            "lint": self.run_lint,
            "product": self.run_product,
            "docs": self.run_docs,
            "focused": self.run_focused,
            "ui": self.run_ui,
            "native": self.run_native,
            "public-data": self.run_public_data,
        }
        inconsistent = tuple(
            owner
            for owner, enabled in expected_flags.items()
            if enabled != (owner in self.required_owners)
        )
        if inconsistent:
            raise ValueError(
                "CI plan execution flags differ from required owners: "
                + ", ".join(inconsistent)
            )

    def to_json(self) -> str:
        return json.dumps(
            {
                "schema_version": 1,
                "plan_digest": self.plan_digest,
                "source_sha": self.source_sha,
                "selected_gate_ids": list(self.selected_gate_ids),
                "gate_owners": [list(item) for item in self.gate_owners],
                "required_owners": list(self.required_owners),
                "run_lint": self.run_lint,
                "run_product": self.run_product,
                "run_docs": self.run_docs,
                "run_focused": self.run_focused,
                "run_ui": self.run_ui,
                "run_native": self.run_native,
                "run_public_data": self.run_public_data,
                "run_platform": self.run_platform,
                "linux_commands": list(self.linux_commands),
                "platform_commands": list(self.platform_commands),
            },
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )

    def digest(self) -> str:
        return hashlib.sha256(self.to_json().encode("utf-8")).hexdigest()

    @classmethod
    def from_json(cls, value: str) -> CiValidationPlan:
        payload = json.loads(value)
        if not isinstance(payload, dict) or payload.get("schema_version") != 1:
            raise ValueError("unsupported CI validation plan schema version")
        return cls(
            plan_digest=str(payload["plan_digest"]),
            source_sha=str(payload["source_sha"]),
            selected_gate_ids=tuple(map(str, payload["selected_gate_ids"])),
            gate_owners=tuple(
                (str(item[0]), str(item[1])) for item in payload["gate_owners"]
            ),
            required_owners=tuple(map(str, payload["required_owners"])),
            run_lint=_required_bool(payload, "run_lint"),
            run_product=_required_bool(payload, "run_product"),
            run_docs=_required_bool(payload, "run_docs"),
            run_focused=_required_bool(payload, "run_focused"),
            run_ui=_required_bool(payload, "run_ui"),
            run_native=_required_bool(payload, "run_native"),
            run_public_data=_required_bool(payload, "run_public_data"),
            run_platform=_required_bool(payload, "run_platform"),
            linux_commands=tuple(map(str, payload["linux_commands"])),
            platform_commands=tuple(map(str, payload["platform_commands"])),
        )

    def gate_ids_for_owner(self, owner: str) -> tuple[str, ...]:
        owned = {
            gate_id for gate_id, gate_owner in self.gate_owners if gate_owner == owner
        }
        return tuple(gate_id for gate_id in HANDOFF_GATE_SPECS if gate_id in owned)

    def github_outputs(self) -> dict[str, str]:
        """Return strings safe for direct append to ``GITHUB_OUTPUT``."""

        risk_owners = tuple(
            owner
            for owner in ("ui", "native", "public-data")
            if owner in self.required_owners
        )
        return {
            "plan_digest": self.plan_digest,
            "source_sha": self.source_sha,
            "run_lint": str(self.run_lint).casefold(),
            "run_product": str(self.run_product).casefold(),
            "run_docs": str(self.run_docs).casefold(),
            "run_focused": str(self.run_focused).casefold(),
            "run_ui": str(self.run_ui).casefold(),
            "run_native": str(self.run_native).casefold(),
            "run_public_data": str(self.run_public_data).casefold(),
            "run_platform": str(self.run_platform).casefold(),
            "risk_owners": json.dumps(list(risk_owners), separators=(",", ":")),
            "linux_commands": json.dumps(
                list(self.linux_commands), separators=(",", ":")
            ),
            "platform_commands": json.dumps(
                list(self.platform_commands), separators=(",", ":")
            ),
        }


def build_ci_validation_plan(
    plan: ValidationPlan,
    *,
    source_sha: str,
) -> CiValidationPlan:
    """Map semantic risks to CI matrices without duplicating leaf test paths."""

    if not plan.ready:
        raise ValueError("CI refuses a blocked validation plan")
    if plan.source_sha is None or plan.base_sha is None:
        raise ValueError("CI refuses a plan not bound to exact source")
    if not _GIT_SHA.fullmatch(source_sha):
        raise ValueError("CI source SHA must be a lowercase 40- or 64-digit hash")
    if source_sha != plan.source_sha:
        raise ValueError("CI source SHA differs from the bound plan source SHA")
    selected = tuple(plan.execution_ids)
    unowned = tuple(gate_id for gate_id in selected if gate_id not in CI_GATE_OWNERS)
    if unowned:
        raise ValueError(
            "Selected gates have no CI execution owner: " + ", ".join(unowned)
        )
    gate_owners = tuple((gate_id, CI_GATE_OWNERS[gate_id]) for gate_id in selected)
    required_owners = tuple(sorted({owner for _gate_id, owner in gate_owners}))
    run_product = "product" in required_owners
    run_docs = "docs" in required_owners
    run_public_data = "public-data" in required_owners
    run_platform = bool(
        {
            Layer.DEPENDENCY,
            Layer.NATIVE_LIFECYCLE,
            Layer.PLATFORM_PACKAGING,
        }.intersection(plan.layers)
    )
    return CiValidationPlan(
        plan_digest=plan.digest(),
        source_sha=source_sha,
        selected_gate_ids=selected,
        gate_owners=gate_owners,
        required_owners=required_owners,
        run_lint="lint" in required_owners,
        run_product=run_product,
        run_docs=run_docs,
        run_focused="focused" in required_owners,
        run_ui="ui" in required_owners,
        run_native="native" in required_owners,
        run_public_data=run_public_data,
        run_platform=run_platform,
        linux_commands=LINUX_CI_COMMANDS if run_product else (),
        platform_commands=PLATFORM_CI_COMMANDS if run_platform else (),
    )


def _write_json(path: Path, payload: str) -> None:
    destination = path.expanduser().resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(payload + "\n", encoding="utf-8")


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--source-sha", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--github-output", type=Path)
    return parser


def main() -> int:
    args = _build_parser().parse_args()
    try:
        plan = ValidationPlan.from_json(
            args.plan.expanduser().resolve(strict=True).read_text(encoding="utf-8")
        )
        ci_plan = build_ci_validation_plan(plan, source_sha=args.source_sha)
        _write_json(args.output, ci_plan.to_json())
        if args.github_output is not None:
            output_lines = "".join(
                f"{name}={value}\n" for name, value in ci_plan.github_outputs().items()
            )
            with (
                args.github_output.expanduser()
                .resolve()
                .open("a", encoding="utf-8") as handle
            ):
                handle.write(output_lines)
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(str(error))
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
