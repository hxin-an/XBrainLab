"""Verify all approved DEV initial states and oracles without model inference."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import time
from pathlib import Path


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bank", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args(argv)
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

    from scripts.dev.assistant_dev_context import PROJECTION_ID, DevContextAssembler
    from scripts.dev.assistant_pilot_bank import build_dev_selection, load_bank
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
    bank = load_bank(args.bank, drop_review_status=True)
    selection = build_dev_selection(bank)
    cases = [case for case in bank["cases"] if case["split"] == "DEV"]
    for case in cases:
        score_decision(case, None)  # Validate oracle; no fabricated model response.
    registry = ToolRegistry()
    for tool in get_all_tools():
        registry.register(tool)
    report = {
        "schema": "xbrainlab.assistant_dev_fixture_preflight.v1",
        "bank_sha256": bank["source"]["sha256"],
        "source": source_identity(),
        "selection": selection,
        "projection": PROJECTION_ID,
        "scope": "66 real initial states / 264 oracle schemas; no model accuracy evidence",
        "fixtures": [],
        "complete": False,
    }
    _write(output / "preflight.json", report)
    for fid in sorted({case["fixture_id"] for case in cases}):
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
            assembler = DevContextAssembler(registry, study)
            messages = assembler.get_messages([])
            entry.update(
                ok=True,
                evidence=evidence,
                actual_host_generation=assembler.latest_tool_publication.backend_generation,
                model_state_messages=messages,
                model_state_sha256=hashlib.sha256(
                    json.dumps(messages, sort_keys=True).encode()
                ).hexdigest(),
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
    report["complete"] = len(report["fixtures"]) == 66 and all(
        item["ok"] and item["cleanup_ok"] and item.get("stop_ok", True)
        for item in report["fixtures"]
    )
    _write(output / "preflight.json", report)
    return 0 if report["complete"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
