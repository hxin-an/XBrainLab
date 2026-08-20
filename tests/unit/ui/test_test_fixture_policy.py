"""Contracts for explicit Qt modal policy in the shared test harness."""

from __future__ import annotations

import pytest
from PyQt6.QtWidgets import QDialog, QMessageBox


def test_undeclared_blocking_modal_fails_fast() -> None:
    with pytest.raises(AssertionError, match="Unexpected blocking Qt modal"):
        QMessageBox.information(None, "Title", "Message")


def test_component_test_can_explicitly_accept_modals(
    auto_accept_modals: None,
    qtbot,
) -> None:
    del auto_accept_modals, qtbot
    assert (
        QMessageBox.question(None, "Question", "Continue?")
        == QMessageBox.StandardButton.Yes
    )
    assert QDialog().exec() == QDialog.DialogCode.Accepted
