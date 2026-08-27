#!/usr/bin/env python3
"""Capture the shared acknowledgement-alert presentation surfaces.

The generated files are development evidence only. They show the three
acknowledgement severities plus the long-text and narrow-width layouts; native
WSLg acceptance remains a separate human gate.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Iterable
from pathlib import Path

from PyQt6.QtWidgets import QApplication

from scripts.dev.chatpanel_guided_boundary.artifact_integrity import (
    collect_source_identity,
    inspect_screenshot_artifact,
)
from XBrainLab.ui.components.modal_presentation import AlertSeverity, ModalAlertDialog

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUTPUT_DIR = ROOT / "build" / "dev-artifacts" / "modal-alert-presentation"
EVIDENCE_FILENAME = "modal-alert-presentation-evidence.json"
_LONG_MESSAGE = "Review this detail before continuing.\n" * 40


def _cases() -> Iterable[tuple[str, AlertSeverity, str, str, int | None]]:
    yield (
        "information.png",
        AlertSeverity.INFORMATION,
        "Project saved",
        "Your project was saved successfully.",
        None,
    )
    yield (
        "warning.png",
        AlertSeverity.WARNING,
        "Review import settings",
        "One or more imported values need your review.",
        None,
    )
    yield (
        "error.png",
        AlertSeverity.CRITICAL,
        "Import could not finish",
        "The file could not be imported. Review the detail and try again.",
        None,
    )
    yield (
        "long-text.png",
        AlertSeverity.WARNING,
        "Detailed import report",
        _LONG_MESSAGE,
        None,
    )
    yield (
        "narrow.png",
        AlertSeverity.WARNING,
        "Review import settings",
        "One or more imported values need your review before continuing.",
        420,
    )


def _capture_case(
    app: QApplication,
    output_dir: Path,
    *,
    filename: str,
    severity: AlertSeverity,
    title: str,
    message: str,
    width: int | None,
) -> None:
    dialog = ModalAlertDialog(severity=severity, title=title, message=message)
    try:
        if width is not None:
            dialog.resize(width, dialog.height())
        dialog.show()
        app.processEvents()
        output_path = output_dir / filename
        if not dialog.grab().save(str(output_path), "PNG"):
            raise RuntimeError(f"Could not save {filename}.")
    finally:
        dialog.close()
        dialog.deleteLater()
        app.processEvents()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    args = parser.parse_args(argv)
    output_dir = args.output_dir.expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / EVIDENCE_FILENAME).unlink(missing_ok=True)

    source_at_start = collect_source_identity(ROOT, refresh=True)
    app = QApplication.instance() or QApplication([sys.argv[0]])
    app.setStyle("Fusion")
    captured_names: list[str] = []
    for filename, severity, title, message, width in _cases():
        _capture_case(
            app,
            output_dir,
            filename=filename,
            severity=severity,
            title=title,
            message=message,
            width=width,
        )
        captured_names.append(filename)
    source_at_end = collect_source_identity(ROOT, refresh=True)
    if source_at_start.get("source_digest") != source_at_end.get("source_digest"):
        raise RuntimeError("Product source changed during modal alert capture.")

    screenshots = {
        filename: inspect_screenshot_artifact(output_dir / filename)
        for filename in captured_names
    }
    if not all(item.get("readable") for item in screenshots.values()):
        raise RuntimeError("Modal alert capture produced an unreadable PNG.")
    evidence = {
        "artifact_type": "xbrainlab.modal_alert_presentation",
        "source_identity": source_at_end,
        "capture_environment": {
            "qt_platform": QApplication.platformName(),
            "qt_style": app.style().objectName(),
        },
        "screenshots": screenshots,
        "claim_boundary": (
            "Automated Qt layout evidence; not WSLg or Windows human acceptance."
        ),
    }
    (output_dir / EVIDENCE_FILENAME).write_text(
        json.dumps(evidence, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(output_dir / EVIDENCE_FILENAME)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
