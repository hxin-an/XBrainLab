#!/usr/bin/env python3
"""Export one synthetic Assistant case as the exact local-model prompt dossier."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
from dataclasses import asdict
from pathlib import Path
from typing import Any

from scripts.dev.run_stable_assistant_model_eval import (
    DEFAULT_CASES,
    DEFAULT_CHALLENGES,
    DEFAULT_CLARIFICATION_CASES,
    DEFAULT_PRECISION_CASES,
    ClarificationCase,
    PrecisionCase,
    admit_clarification_receipt,
    build_case_messages,
    build_clarification_messages,
    load_challenge_cases,
    load_clarification_cases,
    load_precision_cases,
    load_target_cases,
    target_tool_registry,
)
from XBrainLab.llm.core.backends.local import LocalBackend
from XBrainLab.llm.core.config import LLMConfig
from XBrainLab.llm.core.model_catalog import local_model_spec

ROOT = Path(__file__).resolve().parents[2]


def _load_pinned_tokenizer(config: LLMConfig) -> Any:
    """Load only the pinned tokenizer; this developer tool never loads weights."""
    spec = local_model_spec(config.model_name)
    if spec is None:
        raise RuntimeError(f"No product model specification for {config.model_name!r}.")
    from transformers import AutoTokenizer

    return AutoTokenizer.from_pretrained(
        spec.repo_id,
        cache_dir=config.cache_dir,
        revision=spec.revision,
        trust_remote_code=False,
        local_files_only=True,
    )


def _source_sha() -> str:
    git = shutil.which("git")
    if git is None:
        raise RuntimeError("Git is required to bind the prompt dossier source SHA.")
    return subprocess.check_output(  # noqa: S603 - resolved Git executable and fixed argv
        [git, "rev-parse", "HEAD"], cwd=ROOT, text=True
    ).strip()


def _direct_clarification_messages(
    case: ClarificationCase,
    precision_cases: tuple[PrecisionCase, ...],
) -> list[dict[str, str]]:
    source = next(
        item for item in precision_cases if item.case_id == case.source_case_id
    )
    first_response = json.dumps(
        {
            "workflow_stage": source.workflow_stage,
            "tool_name": "respond_to_user",
            "parameters": {
                "message": "Please provide the missing parameter values.",
                "pending_action": case.expected_tool,
                "missing_inputs": sorted(case.expected_parameters),
            },
        }
    )
    registry = target_tool_registry()
    admission = admit_clarification_receipt(
        source,
        first_response,
        expected_tool=case.expected_tool,
        registry=registry,
    )
    if admission is None:
        raise RuntimeError(f"Could not construct synthetic receipt for {case.case_id}.")
    return build_clarification_messages(
        case,
        source,
        receipt=admission.receipt,
        registry=registry,
    )[0]


def _resolve_case_messages(case_id: str) -> tuple[dict[str, Any], list[dict[str, str]]]:
    """Resolve one checked-in synthetic case through the product assembler."""
    registry = target_tool_registry()
    precision_cases = load_precision_cases(DEFAULT_PRECISION_CASES)
    for case in (
        *load_target_cases(DEFAULT_CASES),
        *load_challenge_cases(DEFAULT_CHALLENGES),
        *precision_cases,
    ):
        if case.case_id == case_id:
            return asdict(case), build_case_messages(case, registry)

    for case in load_clarification_cases(
        DEFAULT_CLARIFICATION_CASES,
        precision_cases=precision_cases,
    ):
        if case.case_id != case_id:
            continue
        if case.trajectory_kind != "direct":
            raise ValueError(
                "Prompt export currently supports direct receipt continuations; "
                f"{case_id!r} is a multi-turn trajectory."
            )
        return asdict(case), _direct_clarification_messages(case, precision_cases)
    raise ValueError(f"Unknown synthetic Assistant case id: {case_id!r}.")


def _message_metrics(messages: list[dict[str, str]]) -> list[dict[str, Any]]:
    return [
        {
            "index": index,
            "role": message["role"],
            "characters": len(message["content"]),
            "utf8_bytes": len(message["content"].encode("utf-8")),
        }
        for index, message in enumerate(messages)
    ]


def _markdown(dossier: dict[str, Any]) -> str:
    def message_block(messages: list[dict[str, str]]) -> str:
        return "\n\n".join(
            f"### {index}. `{message['role']}`\n\n```text\n{message['content']}\n```"
            for index, message in enumerate(messages)
        )

    final = dossier["final_prompt"]
    return (
        "# Assistant final prompt dossier\n\n"
        f"- Source SHA: `{dossier['source_sha']}`\n"
        f"- Case: `{dossier['case_id']}`\n"
        f"- Model: `{dossier['model']['id']}@{dossier['model']['revision']}`\n"
        "- Tokenizer only: no model weights were loaded.\n\n"
        "## Synthetic scenario\n\n```json\n"
        + json.dumps(dossier["case"], ensure_ascii=False, indent=2)
        + "\n```\n\n## Raw message metrics\n\n```json\n"
        + json.dumps(dossier["raw_message_metrics"], ensure_ascii=False, indent=2)
        + "\n```\n\n## Raw messages\n\n"
        + message_block(dossier["raw_messages"])
        + "\n\n## Processed message metrics\n\n```json\n"
        + json.dumps(dossier["processed_message_metrics"], ensure_ascii=False, indent=2)
        + "\n```\n\n## Processed messages\n\n"
        + message_block(dossier["processed_messages"])
        + "\n\n## Final rendered prompt\n\n"
        + f"- Characters: {final['characters']}\n"
        + f"- UTF-8 bytes: {final['utf8_bytes']}\n"
        + f"- Tokens: {final['token_count']}\n"
        + f"- SHA-256: `{final['sha256']}`\n\n```text\n{final['content']}\n```\n"
    )


def export_prompt_dossier(case_id: str, out_path: Path) -> dict[str, Any]:
    """Write one reproducible prompt dossier without constructing a model."""
    case, raw_messages = _resolve_case_messages(case_id)
    config = LLMConfig(model_name=LLMConfig.default_local_model_id())
    spec = local_model_spec(config.model_name)
    if spec is None:  # pragma: no cover - catalog is a product invariant
        raise RuntimeError("Default local model is absent from the product catalog.")
    backend = LocalBackend(config)
    processed_messages = backend._process_messages_for_template(raw_messages)
    tokenizer = _load_pinned_tokenizer(config)
    final_prompt, token_count = backend._render_chat_template_with_token_count(
        tokenizer,
        processed_messages,
    )
    dossier = {
        "source_sha": _source_sha(),
        "case_id": case_id,
        "case": case,
        "model": {"id": spec.repo_id, "revision": spec.revision},
        "raw_messages": raw_messages,
        "raw_message_metrics": _message_metrics(raw_messages),
        "processed_messages": processed_messages,
        "processed_message_metrics": _message_metrics(processed_messages),
        "final_prompt": {
            "content": final_prompt,
            "characters": len(final_prompt),
            "utf8_bytes": len(final_prompt.encode("utf-8")),
            "token_count": token_count,
            "sha256": hashlib.sha256(final_prompt.encode("utf-8")).hexdigest(),
        },
    }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(_markdown(dossier), encoding="utf-8")
    return dossier


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case-id", required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)
    export_prompt_dossier(args.case_id, args.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
