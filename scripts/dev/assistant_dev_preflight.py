"""Verify frozen experiment states and oracles without model inference."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import time
from pathlib import Path


def selected_cases(
    bank: dict, config_path: Path | dict | None = None
) -> tuple[dict, list]:
    """Use the runner's population contract; repeats do not duplicate fixtures."""
    from scripts.dev.assistant_experiment_config import build_selection
    from scripts.dev.assistant_pilot_bank import build_dev_selection

    config = (
        json.loads(config_path.read_text(encoding="utf-8"))
        if isinstance(config_path, Path)
        else config_path
    )
    selection = (
        build_dev_selection(bank) if config is None else build_selection(bank, config)
    )
    identifiers = set(selection["case_ids"])
    return selection, [case for case in bank["cases"] if case["case_id"] in identifiers]


def model_contexts(
    registry, study, cases: list[dict], *, config: dict | None = None
) -> dict:
    """Capture the actual research assembly for every model and current request.

    No model is loaded and no retrieval is performed here. Separate replay of
    saved RAG captures checks reference retention and native tokenizer limits.
    """
    from scripts.dev.assistant_dev_context import DevContextAssembler
    from scripts.dev.assistant_experiment_config import (
        MODELS,
        TEST_ABLATIONS,
        ablation_policy,
        experiment_identity,
    )

    if config is not None:
        experiment_identity(config)
    aliases = (
        MODELS if config is None else [model["alias"] for model in config["models"]]
    )
    is_test = config is not None and config["split"] == "TEST"
    contexts = {}
    profiles = [
        (alias, ablation)
        for alias in aliases
        for ablation in (TEST_ABLATIONS if is_test else ("full",))
    ]
    for alias, ablation in profiles:
        model_id = MODELS[alias]
        policy = ablation_policy(ablation)
        assembler = DevContextAssembler(
            registry,
            study,
            model_id=model_id,
            tool_filter_enabled=policy["tool_filter_enabled"],
        )
        captures = []
        for case in cases:
            messages = assembler.get_messages(
                [{"role": "user", "content": case["input"]}]
            )
            publication = assembler.latest_tool_publication
            captures.append(
                {
                    "case_id": case["case_id"],
                    "model_id": model_id,
                    "condition_policy": policy,
                    "messages": messages,
                    "actual_host_generation": publication.backend_generation,
                    "workflow_stage": publication.workflow_stage,
                    "tool_names": sorted(publication.tool_names),
                    "blocked_reasons": dict(publication.blocked_reasons),
                    "rag_allowed_tool_names": sorted(
                        assembler.rag_allowed_tool_names()
                    ),
                    "message_utf8_bytes": sum(
                        len(message["content"].encode("utf-8")) for message in messages
                    ),
                    "messages_sha256": hashlib.sha256(
                        json.dumps(messages, sort_keys=True).encode()
                    ).hexdigest(),
                }
            )
        contexts[f"{alias}-{ablation}" if is_test else model_id] = captures
    return contexts


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bank", required=True, type=Path)
    parser.add_argument(
        "--config", type=Path, help="Frozen experiment config; default: full DEV"
    )
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args(argv)
    config = None
    if args.config is not None:
        from scripts.dev.assistant_experiment_config import experiment_identity

        config = json.loads(args.config.read_text(encoding="utf-8"))
        experiment_identity(config)  # Validate TEST opt-in before reading any bank.
    output = args.output.absolute()
    output.mkdir()
    for name, directory in (
        ("XBRAINLAB_CONFIG_DIR", "config"),
        ("XBRAINLAB_LOG_DIR", "logs"),
        ("XBRAINLAB_CACHE_DIR", "cache"),
        ("XBRAINLAB_DATA_DIR", "data"),
    ):
        os.environ[name] = str(output / directory)
    os.environ["QT_QPA_PLATFORM"] = "offscreen"

    from scripts.dev.assistant_pilot_case import _write, bootstrap_case_checkout

    bootstrap_case_checkout()

    import torch
    from PyQt6.QtWidgets import QApplication

    from scripts.dev.assistant_dev_context import PROJECTION_ID
    from scripts.dev.assistant_pilot_bank import load_bank
    from scripts.dev.assistant_pilot_fixture import prepare_fixture
    from scripts.dev.assistant_pilot_scoring import score_decision
    from scripts.dev.run_assistant_pilot import source_identity
    from XBrainLab.backend.application import (
        StopTrainingCommand,
        get_application_service,
    )
    from XBrainLab.backend.study import Study
    from XBrainLab.llm.tools import get_all_tools
    from XBrainLab.llm.tools.tool_registry import ToolRegistry

    torch.set_num_threads(1)
    app = QApplication.instance() or QApplication([])
    app.setQuitOnLastWindowClosed(False)
    bank = load_bank(
        args.bank, allow_test=config is not None and config["split"] == "TEST"
    )
    selection, cases = selected_cases(bank, config)
    fixture_ids = sorted({case["fixture_id"] for case in cases})
    for case in cases:
        score_decision(case, None)  # Validate oracle; no fabricated model response.
    registry = ToolRegistry()
    for tool in get_all_tools():
        registry.register(tool)
    report = {
        "schema": "xbrainlab.assistant_dev_fixture_preflight.v2",
        "bank_sha256": bank["source"]["sha256"],
        "source": source_identity(),
        "selection": selection,
        "projection": PROJECTION_ID,
        "scope": f"{len(fixture_ids)} real states / {len(cases)} oracles / selected prompt conditions; no inference or retrieval",
        "fixtures": [],
        "complete": False,
    }
    _write(output / "preflight.json", report)
    for fid in fixture_ids:
        study = Study()
        service = get_application_service(study)
        entry = {"fixture_id": fid, "ok": False}
        started = time.monotonic()
        try:
            evidence = prepare_fixture(
                study,
                bank["fixtures"][fid],
                output / fid,
                running_training_epochs=10_000,
            )
            entry.update(
                ok=True,
                evidence=evidence,
                model_contexts=model_contexts(
                    registry,
                    study,
                    [case for case in cases if case["fixture_id"] == fid],
                    config=config,
                ),
            )
        except Exception as exc:  # Preserve each actual failed initial state.
            entry["error"] = f"{type(exc).__name__}: {exc}"
        finally:
            if service.get_state().training.is_running:
                stopped = service.execute(StopTrainingCommand(wait_timeout=10))
                entry["stop_ok"] = stopped.ok
            entry["cleanup_ok"] = service.wait_for_background_tasks(timeout=10)
            service.close()
            app.processEvents()
        entry["seconds"] = time.monotonic() - started
        report["fixtures"].append(entry)
        _write(output / "preflight.json", report)
        print(
            json.dumps(
                {"fixture": fid, "ok": entry["ok"], "error": entry.get("error")}
            ),
            flush=True,
        )
    report["complete"] = len(report["fixtures"]) == len(fixture_ids) and all(
        item["ok"] and item["cleanup_ok"] and item.get("stop_ok", True)
        for item in report["fixtures"]
    )
    _write(output / "preflight.json", report)
    return 0 if report["complete"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
