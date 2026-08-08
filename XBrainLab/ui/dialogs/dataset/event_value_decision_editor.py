"""Compact editor for per-value semantics in external label carriers."""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QComboBox,
    QFrame,
    QGridLayout,
    QLabel,
    QLineEdit,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

_ROLE_CHOICES = (
    ("Choose role", ""),
    ("Stimulus", "stimulus"),
    ("Response", "response"),
    ("Artifact", "artifact"),
    ("Boundary", "boundary"),
    ("System", "system"),
    ("Annotation", "annotation"),
    ("Other", "unknown"),
)

_USE_CHOICES = (
    ("Choose use", ""),
    ("Training class", "class"),
    ("Keep as EEG event", "event"),
    ("Do not use", "ignore"),
)


class _ElidingValueLabel(QLabel):
    """Render a raw event value without clipping its accessible full text."""

    def __init__(self, text: str, parent: QWidget | None = None) -> None:
        super().__init__(text, parent)
        self._full_text = text
        self.setAccessibleName(text)

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        self._fit_text()

    def showEvent(self, event) -> None:  # noqa: N802
        super().showEvent(event)
        self._fit_text()

    def _fit_text(self) -> None:
        available = max(self.contentsRect().width(), 1)
        rendered = self.fontMetrics().elidedText(
            self._full_text,
            Qt.TextElideMode.ElideRight,
            available,
        )
        if self.text() != rendered:
            self.setText(rendered)


@dataclass(frozen=True)
class _Occurrence:
    carrier_key: str
    carrier_name: str
    raw_value: str
    decision: dict[str, Any]


@dataclass
class _DecisionRow:
    occurrences: tuple[_Occurrence, ...]
    role_selector: QComboBox
    use_selector: QComboBox
    class_name_editor: QLineEdit
    coverage_label: QLabel
    evidence_label: QLabel

    @property
    def raw_value(self) -> str:
        return self.occurrences[0].raw_value


class EventValueDecisionEditor(QWidget):
    """Edit event role and supervised-class use without losing file identity."""

    decisions_changed = pyqtSignal()

    def __init__(
        self,
        carrier_plans: list[dict[str, Any]],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("EventValueDecisionEditor")
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._carrier_count = 0
        self._rows: list[_DecisionRow] = []
        self._advanced_visible = False
        self._advanced_widgets: list[QWidget] = []
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(0, 2, 0, 0)
        self._layout.setSpacing(7)
        self.set_carrier_plans(carrier_plans)

    def set_carrier_plans(self, carrier_plans: list[dict[str, Any]]) -> None:
        """Replace the observed values while preserving only backend-owned truth."""
        self._rows.clear()
        self._advanced_widgets.clear()
        self._clear_layout()
        occurrences = self._occurrences(carrier_plans)
        self._carrier_count = len(
            {occurrence.carrier_key for occurrence in occurrences}
        )
        if not occurrences:
            self.setVisible(False)
            return

        self.setVisible(True)
        title = QLabel("Event value decisions")
        title.setObjectName("DataImportSubsectionTitle")
        detail = QLabel(
            "Choose what each observed value means and whether it becomes a "
            "training class. Suggested names remain editable."
        )
        detail.setObjectName("DataImportSourceDetail")
        detail.setWordWrap(True)
        self._layout.addWidget(title)
        self._layout.addWidget(detail)

        table = QFrame()
        table.setObjectName("DataImportValueDecisionTable")
        grid = QGridLayout(table)
        grid.setContentsMargins(10, 8, 10, 9)
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(7)
        headers = (
            "Label value",
            "Use as",
            "Class name",
            "Occurrences",
            "Event role",
            "Source evidence",
        )
        for column, header in enumerate(headers):
            label = QLabel(header)
            label.setObjectName("DataImportPairingHeaderLabel")
            grid.addWidget(label, 0, column)
            if column >= 4:
                self._advanced_widgets.append(label)

        grouped_occurrences = self._group_occurrences(occurrences)
        grouped_value_counts = Counter(
            grouped[0].raw_value for grouped in grouped_occurrences
        )
        for row_index, grouped in enumerate(grouped_occurrences, start=1):
            row = self._build_row(grouped)
            self._rows.append(row)
            value_cell = self._value_cell(
                grouped,
                show_source=grouped_value_counts[grouped[0].raw_value] > 1,
            )
            grid.addWidget(value_cell, row_index, 0)
            grid.addWidget(row.use_selector, row_index, 1)
            grid.addWidget(row.class_name_editor, row_index, 2)
            grid.addWidget(row.coverage_label, row_index, 3)
            grid.addWidget(row.role_selector, row_index, 4)
            grid.addWidget(row.evidence_label, row_index, 5)
            self._advanced_widgets.extend((row.role_selector, row.evidence_label))

        grid.setColumnStretch(0, 5)
        grid.setColumnStretch(1, 3)
        grid.setColumnStretch(2, 3)
        grid.setColumnStretch(3, 2)
        grid.setColumnStretch(4, 3)
        grid.setColumnStretch(5, 4)
        self._layout.addWidget(table)
        self.set_advanced_visible(self._advanced_visible)
        self.updateGeometry()

    def has_rows(self) -> bool:
        return bool(self._rows)

    def row_count(self) -> int:
        return len(self._rows)

    def is_complete(self) -> bool:
        return bool(self._rows) and all(self._row_complete(row) for row in self._rows)

    def unresolved_values(self) -> list[str]:
        return sorted(
            {row.raw_value for row in self._rows if not self._row_complete(row)},
            key=str.casefold,
        )

    def coverage_text(self, raw_value: str) -> str:
        matching = [
            str(
                row.coverage_label.property("fullCoverageText")
                or row.coverage_label.text()
            )
            for row in self._rows
            if row.raw_value == str(raw_value)
        ]
        return " · ".join(matching)

    def set_advanced_visible(self, visible: bool) -> None:
        """Show backend role and source evidence only on explicit request."""
        self._advanced_visible = bool(visible)
        for widget in self._advanced_widgets:
            widget.setVisible(self._advanced_visible)
        self.updateGeometry()

    def set_value_decision(
        self,
        raw_value: str,
        *,
        role: str,
        use: str,
        class_name: str = "",
        carrier_key: str | None = None,
    ) -> None:
        """Set one visible value decision, optionally for a single carrier."""
        matched = False
        for row in self._rows:
            if row.raw_value != str(raw_value):
                continue
            if carrier_key is not None and not any(
                occurrence.carrier_key == carrier_key for occurrence in row.occurrences
            ):
                continue
            self._set_combo_data(row.role_selector, role)
            self._set_combo_data(row.use_selector, use)
            if class_name:
                row.class_name_editor.setText(class_name)
                row.class_name_editor.setCursorPosition(0)
            self._sync_class_name_editor(row)
            matched = True
        if not matched:
            raise KeyError(f"Unknown event value decision: {raw_value}")
        self.decisions_changed.emit()

    def changed_decisions_by_carrier(self) -> dict[str, dict[str, dict[str, Any]]]:
        """Return only user-edited semantic choices, keyed by carrier and value."""
        changed: dict[str, dict[str, dict[str, Any]]] = {}
        for row in self._rows:
            current_semantics = self._current_semantics(row)
            for occurrence in row.occurrences:
                if current_semantics == self._initial_semantics(occurrence.decision):
                    continue
                changed.setdefault(occurrence.carrier_key, {})[occurrence.raw_value] = (
                    self._choice_payload(row, occurrence)
                )
        return changed

    def _build_row(self, occurrences: tuple[_Occurrence, ...]) -> _DecisionRow:
        representative = occurrences[0].decision
        role_selector = QComboBox(self)
        role_selector.setObjectName("EventValueRoleSelector")
        role_selector.setMinimumWidth(100)
        role_selector.setSizePolicy(
            QSizePolicy.Policy.Ignored,
            QSizePolicy.Policy.Fixed,
        )
        role_selector.addItems([display for display, _value in _ROLE_CHOICES])
        for index, (_display, value) in enumerate(_ROLE_CHOICES):
            role_selector.setItemData(index, value)

        use_selector = QComboBox(self)
        use_selector.setObjectName("EventValueUseSelector")
        use_selector.setMinimumWidth(90)
        use_selector.setSizePolicy(
            QSizePolicy.Policy.Ignored,
            QSizePolicy.Policy.Fixed,
        )
        use_selector.addItems([display for display, _value in _USE_CHOICES])
        for index, (_display, value) in enumerate(_USE_CHOICES):
            use_selector.setItemData(index, value)

        initial = self._initial_editor_state(representative)
        self._set_combo_data(role_selector, initial["role"])
        self._set_combo_data(use_selector, initial["use"])

        class_name_editor = QLineEdit(self)
        class_name_editor.setObjectName("EventValueClassNameEditor")
        class_name_editor.setPlaceholderText("Required for class labels")
        class_name_editor.setMinimumWidth(135)
        class_name_editor.setSizePolicy(
            QSizePolicy.Policy.Ignored,
            QSizePolicy.Policy.Fixed,
        )
        class_name_editor.setText(initial["class_name"])
        class_name_editor.setCursorPosition(0)
        class_name_editor.setToolTip(initial["class_name"])

        count = sum(
            self._safe_count(item.decision.get("count")) for item in occurrences
        )
        file_count = len({item.carrier_key for item in occurrences})
        total_files = max(self._carrier_count, 1)
        full_coverage_text = f"{count} occurrences · {file_count}/{total_files} files"
        coverage_label = QLabel(f"{count} · {file_count}/{total_files}")
        coverage_label.setObjectName("DataImportValueDecisionCoverage")
        coverage_label.setProperty("fullCoverageText", full_coverage_text)
        coverage_label.setToolTip(full_coverage_text)
        coverage_label.setWordWrap(True)
        coverage_label.setSizePolicy(
            QSizePolicy.Policy.Ignored,
            QSizePolicy.Policy.Preferred,
        )

        evidence = str(
            representative.get("provenance")
            or representative.get("decision_source")
            or "No source evidence"
        ).strip()
        evidence_label = QLabel(evidence)
        evidence_label.setObjectName("DataImportValueDecisionEvidence")
        evidence_label.setWordWrap(True)
        evidence_label.setToolTip(evidence)
        evidence_label.setSizePolicy(
            QSizePolicy.Policy.Ignored,
            QSizePolicy.Policy.Preferred,
        )

        row = _DecisionRow(
            occurrences=occurrences,
            role_selector=role_selector,
            use_selector=use_selector,
            class_name_editor=class_name_editor,
            coverage_label=coverage_label,
            evidence_label=evidence_label,
        )
        self._sync_class_name_editor(row)
        role_selector.currentIndexChanged.connect(self._emit_change)
        use_selector.currentIndexChanged.connect(
            lambda _index, current=row: self._use_changed(current)
        )
        class_name_editor.textChanged.connect(self._emit_change)
        class_name_editor.textChanged.connect(class_name_editor.setToolTip)
        class_name_editor.editingFinished.connect(
            lambda current=class_name_editor: current.setCursorPosition(0)
        )
        return row

    def _use_changed(self, row: _DecisionRow) -> None:
        if not row.role_selector.currentData():
            default_role = {
                "class": "stimulus",
                "event": "annotation",
                "ignore": "unknown",
            }.get(str(row.use_selector.currentData() or ""))
            if default_role:
                self._set_combo_data(row.role_selector, default_role)
        self._sync_class_name_editor(row)
        self._emit_change()

    def _emit_change(self, *_args: Any) -> None:
        self.decisions_changed.emit()

    @staticmethod
    def _sync_class_name_editor(row: _DecisionRow) -> None:
        row.class_name_editor.setReadOnly(row.use_selector.currentData() != "class")

    @staticmethod
    def _row_complete(row: _DecisionRow) -> bool:
        role = str(row.role_selector.currentData() or "")
        use = str(row.use_selector.currentData() or "")
        if not role or not use:
            return False
        return use != "class" or bool(row.class_name_editor.text().strip())

    @staticmethod
    def _current_semantics(row: _DecisionRow) -> dict[str, Any]:
        role = str(row.role_selector.currentData() or "")
        use = str(row.use_selector.currentData() or "")
        semantics: dict[str, Any] = {
            "role": role,
            "keep_event": None,
            "use_as_class": None,
            "class_name": "",
        }
        if use == "class":
            semantics.update(
                keep_event=True,
                use_as_class=True,
                class_name=row.class_name_editor.text().strip(),
            )
        elif use == "event":
            semantics.update(keep_event=True, use_as_class=False)
        elif use == "ignore":
            semantics.update(keep_event=False, use_as_class=False)
        return semantics

    def _choice_payload(
        self,
        row: _DecisionRow,
        occurrence: _Occurrence,
    ) -> dict[str, Any]:
        semantics = self._current_semantics(row)
        payload: dict[str, Any] = {"role": semantics["role"]}
        if isinstance(semantics["keep_event"], bool):
            payload["keep_event"] = semantics["keep_event"]
        if isinstance(semantics["use_as_class"], bool):
            payload["use_as_class"] = semantics["use_as_class"]
        if semantics["class_name"]:
            payload["class_name"] = semantics["class_name"]
        suggestion = str(occurrence.decision.get("suggested_name") or "").strip()
        if suggestion:
            payload["suggested_name"] = suggestion
        payload["decision_source"] = "user_choice"
        payload["provenance"] = "ui_event_value_editor"
        return payload

    @staticmethod
    def _initial_semantics(decision: dict[str, Any]) -> dict[str, Any]:
        state = EventValueDecisionEditor._initial_editor_state(decision)
        semantics: dict[str, Any] = {
            "role": state["role"],
            "keep_event": None,
            "use_as_class": None,
            "class_name": "",
        }
        if state["use"] == "class":
            semantics.update(
                keep_event=True,
                use_as_class=True,
                class_name=state["class_name"],
            )
        elif state["use"] == "event":
            semantics.update(keep_event=True, use_as_class=False)
        elif state["use"] == "ignore":
            semantics.update(keep_event=False, use_as_class=False)
        return semantics

    @staticmethod
    def _initial_editor_state(decision: dict[str, Any]) -> dict[str, str]:
        resolved = str(decision.get("decision") or "") == "resolved"
        source = str(decision.get("decision_source") or "")
        explicit_incomplete = source.startswith("user_choice")
        role = (
            str(decision.get("role") or "") if resolved or explicit_incomplete else ""
        )
        keep_event = decision.get("keep_event")
        use_as_class = decision.get("use_as_class")
        use = ""
        if isinstance(keep_event, bool) and isinstance(use_as_class, bool):
            if not keep_event:
                use = "ignore"
            elif use_as_class:
                use = "class"
            else:
                use = "event"
        class_name = str(
            decision.get("class_name") or decision.get("suggested_name") or ""
        ).strip()
        return {"role": role, "use": use, "class_name": class_name}

    @staticmethod
    def _occurrences(carrier_plans: list[dict[str, Any]]) -> list[_Occurrence]:
        occurrences: list[_Occurrence] = []
        for carrier in carrier_plans:
            if not isinstance(carrier, dict):
                continue
            carrier_key = str(carrier.get("path") or carrier.get("name") or "").strip()
            decisions = carrier.get("value_decisions")
            if not carrier_key or not isinstance(decisions, dict):
                continue
            carrier_name = str(carrier.get("name") or Path(carrier_key).name)
            for raw_value, raw_decision in decisions.items():
                value = str(raw_value).strip()
                if not value or not isinstance(raw_decision, dict):
                    continue
                occurrences.append(
                    _Occurrence(
                        carrier_key=carrier_key,
                        carrier_name=carrier_name,
                        raw_value=value,
                        decision=dict(raw_decision),
                    )
                )
        return sorted(
            occurrences,
            key=lambda item: (item.raw_value.casefold(), item.carrier_name.casefold()),
        )

    @classmethod
    def _group_occurrences(
        cls,
        occurrences: list[_Occurrence],
    ) -> list[tuple[_Occurrence, ...]]:
        by_value: dict[str, list[_Occurrence]] = defaultdict(list)
        for occurrence in occurrences:
            by_value[occurrence.raw_value].append(occurrence)
        grouped: list[tuple[_Occurrence, ...]] = []
        for raw_value in sorted(by_value, key=str.casefold):
            value_occurrences = by_value[raw_value]
            by_signature: dict[tuple[Any, ...], list[_Occurrence]] = defaultdict(list)
            for occurrence in value_occurrences:
                by_signature[cls._decision_signature(occurrence.decision)].append(
                    occurrence
                )
            if len(by_signature) == 1:
                grouped.append(tuple(value_occurrences))
            else:
                grouped.extend(tuple(group) for group in by_signature.values())
        return grouped

    @staticmethod
    def _decision_signature(decision: dict[str, Any]) -> tuple[Any, ...]:
        state = EventValueDecisionEditor._initial_editor_state(decision)
        return (
            state["role"],
            state["use"],
            state["class_name"],
            str(decision.get("suggested_name") or ""),
        )

    def _value_cell(
        self,
        occurrences: tuple[_Occurrence, ...],
        *,
        show_source: bool,
    ) -> QWidget:
        cell = QWidget(self)
        cell.setObjectName("DataImportValueDecisionCell")
        layout = QVBoxLayout(cell)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        raw_value = occurrences[0].raw_value
        tooltip = self._value_tooltip(occurrences)
        value_label = _ElidingValueLabel(raw_value, cell)
        value_label.setObjectName("DataImportValueDecisionValue")
        value_label.setToolTip(f"{tooltip}\nValue: {raw_value}".strip())
        value_label.setWordWrap(False)
        value_label.setMinimumWidth(
            min(value_label.fontMetrics().horizontalAdvance(raw_value) + 4, 180)
        )
        value_label.setSizePolicy(
            QSizePolicy.Policy.Ignored,
            QSizePolicy.Policy.Preferred,
        )
        layout.addWidget(value_label)
        if show_source:
            source_label = QLabel(self._source_display(occurrences), cell)
            source_label.setObjectName("DataImportSourceDetail")
            source_label.setProperty("eventValueSource", True)
            source_label.setToolTip(tooltip)
            layout.addWidget(source_label)
        cell.setToolTip(tooltip)
        cell.setSizePolicy(
            QSizePolicy.Policy.Ignored,
            QSizePolicy.Policy.Preferred,
        )
        return cell

    @staticmethod
    def _source_display(occurrences: tuple[_Occurrence, ...]) -> str:
        source_names = list(
            dict.fromkeys(occurrence.carrier_name for occurrence in occurrences)
        )
        source_label = "Source" if len(source_names) == 1 else "Sources"
        extra_count = len(source_names) - 1
        extra_text = f" +{extra_count}" if extra_count else ""
        return f"{source_label}: {source_names[0]}{extra_text}"

    @staticmethod
    def _value_tooltip(occurrences: tuple[_Occurrence, ...]) -> str:
        sources = ", ".join(item.carrier_name for item in occurrences)
        return f"Observed in: {sources}" if sources else ""

    @staticmethod
    def _safe_count(value: Any) -> int:
        try:
            return max(int(value), 0)
        except (TypeError, ValueError):
            return 0

    @staticmethod
    def _set_combo_data(selector: QComboBox, value: str) -> None:
        index = selector.findData(value)
        selector.setCurrentIndex(index if index >= 0 else 0)

    def _clear_layout(self) -> None:
        while self._layout.count():
            item = self._layout.takeAt(0)
            if item is None:
                continue
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
