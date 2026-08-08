"""Product behavior for external label/event value decisions."""

from __future__ import annotations

from PyQt6.QtWidgets import QComboBox, QFrame, QLabel, QLineEdit, QScrollArea

from XBrainLab.ui.dialogs.dataset.event_value_decision_editor import (
    EventValueDecisionEditor,
)


def _unresolved(value: str, *, count: int = 1) -> dict[str, object]:
    return {
        "role": "unknown",
        "keep_event": None,
        "use_as_class": None,
        "suggested_name": value.replace("_", " ").title(),
        "decision": "unresolved",
        "decision_source": "unresolved",
        "provenance": "observed:BIDS events:trial_type",
        "count": count,
    }


def _carrier(path: str, decisions: dict[str, dict[str, object]]) -> dict[str, object]:
    return {
        "path": path,
        "name": path.rsplit("/", 1)[-1],
        "format": "BIDS events",
        "selected_label_field": "trial_type",
        "value_decisions": decisions,
    }


def test_editor_requires_explicit_role_and_use_before_complete(qtbot) -> None:
    editor = EventValueDecisionEditor(
        [_carrier("/data/run-01_events.tsv", {"left_hand": _unresolved("left_hand")})]
    )
    qtbot.addWidget(editor)

    assert editor.has_rows()
    assert editor.is_complete() is False
    assert editor.unresolved_values() == ["left_hand"]

    editor.set_value_decision(
        "left_hand",
        role="stimulus",
        use="class",
        class_name="Left hand",
    )

    assert editor.is_complete()
    assert editor.unresolved_values() == []
    assert editor.changed_decisions_by_carrier() == {
        "/data/run-01_events.tsv": {
            "left_hand": {
                "role": "stimulus",
                "keep_event": True,
                "use_as_class": True,
                "class_name": "Left hand",
                "suggested_name": "Left Hand",
                "decision_source": "user_choice",
                "provenance": "ui_event_value_editor",
            }
        }
    }


def test_editor_round_trips_boundary_and_system_as_distinct_roles(qtbot) -> None:
    editor = EventValueDecisionEditor(
        [
            _carrier(
                "/data/run-01_events.tsv",
                {
                    "boundary": _unresolved("boundary"),
                    "start_experiment": _unresolved("start_experiment"),
                },
            )
        ]
    )
    qtbot.addWidget(editor)

    role_selector = editor.findChildren(QComboBox, "EventValueRoleSelector")[0]
    role_choices = {
        role_selector.itemText(index): role_selector.itemData(index)
        for index in range(role_selector.count())
    }
    assert role_choices["Boundary"] == "boundary"
    assert role_choices["System"] == "system"
    assert role_choices["Stimulus"] == "stimulus"

    editor.set_value_decision("boundary", role="boundary", use="event")
    editor.set_value_decision("start_experiment", role="system", use="event")

    decisions = editor.changed_decisions_by_carrier()["/data/run-01_events.tsv"]
    assert decisions["boundary"]["role"] == "boundary"
    assert decisions["start_experiment"]["role"] == "system"
    assert editor.is_complete()


def test_class_editor_returns_to_the_start_after_editing_finishes(qtbot) -> None:
    editor = EventValueDecisionEditor(
        [_carrier("/data/run-01_events.tsv", {"ignore": _unresolved("ignore")})]
    )
    qtbot.addWidget(editor)
    editor.show()
    class_editor = editor.findChildren(QLineEdit, "EventValueClassNameEditor")[0]
    assert class_editor.cursorPosition() == 0
    editor.set_value_decision(
        "ignore",
        role="system",
        use="class",
        class_name="Ignore - not a real event",
    )
    assert class_editor.cursorPosition() == 0
    assert class_editor.toolTip() == "Ignore - not a real event"
    class_editor.setCursorPosition(len(class_editor.text()))

    class_editor.editingFinished.emit()

    assert class_editor.cursorPosition() == 0


def test_editor_groups_identical_values_across_files_and_preserves_output(
    qtbot,
) -> None:
    editor = EventValueDecisionEditor(
        [
            _carrier("/data/run-01_events.tsv", {"left": _unresolved("left", count=3)}),
            _carrier("/data/run-02_events.tsv", {"left": _unresolved("left", count=4)}),
        ]
    )
    qtbot.addWidget(editor)

    assert editor.row_count() == 1
    assert "7 occurrences" in editor.coverage_text("left")
    assert "2/2 files" in editor.coverage_text("left")
    assert [
        label.text()
        for label in editor.findChildren(QLabel, "DataImportValueDecisionValue")
    ] == ["left"]
    assert not any(
        label.property("eventValueSource") is True
        for label in editor.findChildren(QLabel)
    )

    editor.set_value_decision(
        "left",
        role="stimulus",
        use="class",
        class_name="Left hand",
    )

    decisions = editor.changed_decisions_by_carrier()
    assert set(decisions) == {
        "/data/run-01_events.tsv",
        "/data/run-02_events.tsv",
    }
    assert (
        decisions["/data/run-01_events.tsv"]["left"]
        == decisions["/data/run-02_events.tsv"]["left"]
    )


def test_editor_keeps_conflicting_existing_decisions_separate(qtbot) -> None:
    class_decision = {
        "role": "stimulus",
        "keep_event": True,
        "use_as_class": True,
        "class_name": "Left hand",
        "suggested_name": "Left hand",
        "decision": "resolved",
        "count": 3,
    }
    response_decision = {
        "role": "response",
        "keep_event": True,
        "use_as_class": False,
        "suggested_name": "Left hand",
        "decision": "resolved",
        "count": 2,
    }
    editor = EventValueDecisionEditor(
        [
            _carrier("/data/run-01_events.tsv", {"left": class_decision}),
            _carrier("/data/run-02_events.tsv", {"left": response_decision}),
            _carrier("/data/run-03_events.tsv", {"left": class_decision}),
        ]
    )
    qtbot.addWidget(editor)

    assert editor.row_count() == 2
    assert len(editor.findChildren(QComboBox, "EventValueRoleSelector")) == 2
    value_labels = editor.findChildren(QLabel, "DataImportValueDecisionValue")
    assert [label.text() for label in value_labels] == ["left", "left"]
    source_labels = [
        label
        for label in editor.findChildren(QLabel)
        if label.property("eventValueSource") is True
    ]
    source_texts = [label.text() for label in source_labels]
    assert len(set(source_texts)) == 2
    assert any("run-01_events.tsv" in text for text in source_texts)
    assert any("run-02_events.tsv" in text for text in source_texts)
    assert all(label.toolTip().startswith("Observed in:") for label in value_labels)


def test_editor_uses_editable_controls_without_nested_scroll(qtbot) -> None:
    editor = EventValueDecisionEditor(
        [_carrier("/data/run-01_events.tsv", {"left": _unresolved("left")})]
    )
    qtbot.addWidget(editor)

    assert editor.findChildren(QComboBox, "EventValueRoleSelector")
    assert editor.findChildren(QComboBox, "EventValueUseSelector")
    assert editor.findChildren(QLineEdit, "EventValueClassNameEditor")
    assert editor.findChildren(QComboBox)
    assert editor.findChildren(QLineEdit)
    assert editor.findChildren(QScrollArea) == []


def test_editor_hides_internal_role_and_evidence_until_advanced(qtbot) -> None:
    editor = EventValueDecisionEditor(
        [_carrier("/data/run-01_events.tsv", {"left": _unresolved("left")})]
    )
    qtbot.addWidget(editor)
    editor.show()
    qtbot.wait(0)

    visible_headers = {
        label.text()
        for label in editor.findChildren(QLabel, "DataImportPairingHeaderLabel")
        if not label.isHidden()
    }
    role_selector = editor.findChildren(QComboBox, "EventValueRoleSelector")[0]
    assert visible_headers == {
        "Label value",
        "Use as",
        "Class name",
        "Occurrences",
    }
    assert not role_selector.isVisibleTo(editor)
    assert "Role" not in visible_headers
    assert "Evidence" not in visible_headers

    editor.set_advanced_visible(True)

    visible_headers = {
        label.text()
        for label in editor.findChildren(QLabel, "DataImportPairingHeaderLabel")
        if not label.isHidden()
    }
    assert not role_selector.isHidden()
    assert "Event role" in visible_headers
    assert "Source evidence" in visible_headers


def test_editor_fits_a_narrow_wizard_viewport_without_horizontal_clipping(
    qtbot,
) -> None:
    values = (
        "ignore",
        "noise_with_reponse",
        "oddball_with_reponse",
        "response",
        "standard_with_reponse",
    )
    editor = EventValueDecisionEditor(
        [
            _carrier(
                "/data/run-01_events.tsv",
                {value: _unresolved(value, count=100) for value in values},
            )
        ]
    )
    qtbot.addWidget(editor)
    editor.show()
    editor.adjustSize()
    editor.resize(650, editor.height())
    qtbot.wait(10)

    table = editor.findChild(QFrame, "DataImportValueDecisionTable")
    assert table is not None
    role_selector = editor.findChildren(QComboBox, "EventValueRoleSelector")[0]
    use_selector = editor.findChildren(QComboBox, "EventValueUseSelector")[0]
    class_name_editor = editor.findChildren(QLineEdit, "EventValueClassNameEditor")[0]
    assert (
        role_selector.minimumWidth()
        + use_selector.minimumWidth()
        + class_name_editor.minimumWidth()
        <= 325
    )
    assert editor.minimumSizeHint().width() <= 650
    assert editor.width() == 650
    assert all(
        control.geometry().right() <= table.contentsRect().right()
        for control in (
            *editor.findChildren(QComboBox),
            *editor.findChildren(QLineEdit),
        )
    )
    value_labels = editor.findChildren(QLabel, "DataImportValueDecisionValue")
    assert all(
        label.fontMetrics().horizontalAdvance(label.text())
        <= label.contentsRect().width()
        for label in value_labels
    )
    assert {label.accessibleName() for label in value_labels} == set(values)
    assert all("Value:" in label.toolTip() for label in value_labels)
    assert all(
        label.fontMetrics().horizontalAdvance(label.text()) <= label.width()
        for label in editor.findChildren(QLabel, "DataImportValueDecisionCoverage")
    )
