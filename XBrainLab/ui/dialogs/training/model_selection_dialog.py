"""Searchable model selection with catalog defaults and pretrained weights."""

import os
from typing import Any

from PyQt6.QtCore import QEvent, QObject, Qt, QTimer
from PyQt6.QtGui import QKeyEvent
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from XBrainLab.backend import model_base
from XBrainLab.backend.model_base.model_catalog import (
    BraindecodeProviderStatus,
    ModelSpec,
    braindecode_provider_status,
    default_model_id,
    discover_model_specs,
    get_model_spec,
)
from XBrainLab.backend.training import ModelHolder
from XBrainLab.ui.application_capabilities import (
    TrainingQueryPort,
    get_training_model_signal_context,
)
from XBrainLab.ui.components.user_error_presentation import (
    UnexpectedErrorContext,
    present_unexpected_error,
)
from XBrainLab.ui.core.base_dialog import BaseDialog
from XBrainLab.ui.core.worker import PythonThreadWorker
from XBrainLab.ui.styles.theme import Theme


class ModelSelectionDialog(BaseDialog):
    """Dialog for selecting a deep learning model architecture.

    Uses reviewed catalog defaults and supports loading pretrained weights.

    Attributes:
        controller: Application controller for data access.
        pretrained_weight_path: Path to pretrained weight file, or None.
        model_holder: Configured ModelHolder after acceptance.
        search_input: Search field for narrowing the model catalog.
        model_results: Searchable list of model architectures.
    """

    def __init__(
        self,
        parent,
        controller,
        initial_model_name: str | None = None,
        *,
        provider_status: BraindecodeProviderStatus | None = None,
        query_port: TrainingQueryPort | None = None,
    ):
        self.controller = controller
        self._query_port = query_port

        self.pretrained_weight_path: str | None = None
        self.model_holder: ModelHolder | None = None

        # UI Elements
        self.search_input: QLineEdit | None = None
        self.model_results: QListWidget | None = None
        self.provider_banner: QLabel | None = None
        self.no_match_label: QLabel | None = None
        self.confirm_btn: QPushButton | None = None
        self.weight_label: QLabel | None = None
        self.weight_btn: QPushButton | None = None
        self.content_scroll: QScrollArea | None = None
        self._provider_worker: PythonThreadWorker | None = None
        self._provider_status = provider_status
        self._signal_context = self._read_signal_context()
        self._selected_model_id: str | None = None
        self._applying_catalog = False
        self._selection_changed_while_pending = False
        self._provider_check_pending = provider_status is None

        # Render a cheap metadata projection immediately. A checked provider
        # snapshot replaces it asynchronously after the dialog is visible.
        self.model_specs = discover_model_specs(
            model_base,
            signal_context=self._signal_context,
        )
        self._spec_by_id = {spec.model_id: spec for spec in self.model_specs}
        self.initial_model_id = self._canonical_model_id(initial_model_name)

        super().__init__(parent, title="Model Selection")
        self.setMinimumSize(600, 360)

        self._apply_catalog(self.model_specs, preserve_id=self.initial_model_id)
        if provider_status is None:
            QTimer.singleShot(0, self._start_provider_preflight)
        else:
            self._apply_provider_status(provider_status)
        self.fit_to_content(
            minimum_width=640,
            minimum_height=452,
            maximum_height=620,
        )
        QTimer.singleShot(0, self._focus_search_input)

    def _canonical_model_id(self, model_name: str | None) -> str | None:
        if not isinstance(model_name, str):
            default_id = default_model_id()
            return default_id if default_id in self._spec_by_id else None
        requested_name = model_name.strip().casefold()
        if requested_name.startswith(("braindecode.", "legacy.braindecode.")):
            return requested_name
        for spec in self.model_specs:
            factory_name = getattr(spec.factory, "__name__", "").casefold()
            if requested_name in {
                spec.model_id.casefold(),
                spec.display_name.casefold(),
                factory_name,
            }:
                return spec.model_id
        default_id = default_model_id()
        return default_id if default_id in self._spec_by_id else None

    def init_ui(self):
        """Initialize the searchable model catalog."""
        self.setObjectName("ModelSelectionDialog")
        self.setStyleSheet(self._dialog_style())
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 18, 18, 14)
        layout.setSpacing(12)

        content = QWidget()
        content.setObjectName("ModelSelectionContent")
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(12)
        content_layout.setAlignment(Qt.AlignmentFlag.AlignTop)

        content_scroll = QScrollArea()
        self.content_scroll = content_scroll
        content_scroll.setObjectName("ModelSelectionContentScroll")
        content_scroll.setWidgetResizable(True)
        content_scroll.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff,
        )
        content_scroll.setVerticalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAsNeeded,
        )
        content_scroll.setFrameShape(QFrame.Shape.NoFrame)
        content_scroll.setWidget(content)

        # Model setup
        setup_frame = QFrame()
        setup_frame.setObjectName("ModelSection")
        setup_frame.setFrameShape(QFrame.Shape.NoFrame)
        setup_frame.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Maximum,
        )
        setup_layout = QGridLayout(setup_frame)
        setup_layout.setContentsMargins(12, 12, 12, 12)
        setup_layout.setHorizontalSpacing(12)
        setup_layout.setVerticalSpacing(10)
        setup_title = QLabel("Model setup")
        setup_title.setObjectName("SectionTitle")
        setup_layout.addWidget(setup_title, 0, 0, 1, 3)

        provider_banner = QLabel("Checking Braindecode 1.6.1 availability…")
        self.provider_banner = provider_banner
        provider_banner.setObjectName("ModelProviderBanner")
        provider_banner.setWordWrap(True)
        setup_layout.addWidget(provider_banner, 1, 0, 1, 3)

        setup_layout.addWidget(QLabel("Search models"), 2, 0)
        search_input = QLineEdit()
        self.search_input = search_input
        search_input.setObjectName("ModelSearchInput")
        search_input.setPlaceholderText("Search by name, family, task, or model ID")
        search_input.setClearButtonEnabled(True)
        search_input.installEventFilter(self)
        search_input.textChanged.connect(self.filter_models)
        setup_layout.addWidget(search_input, 2, 1, 1, 2)

        model_results = QListWidget()
        self.model_results = model_results
        model_results.setObjectName("ModelSearchResults")
        model_results.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        model_results.setAlternatingRowColors(True)
        model_results.setTextElideMode(Qt.TextElideMode.ElideRight)
        model_results.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        model_results.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        model_results.setMinimumHeight(150)
        model_results.setMaximumHeight(230)
        model_results.currentItemChanged.connect(self._on_result_changed)
        model_results.itemDoubleClicked.connect(lambda _item: self.accept())
        setup_layout.addWidget(model_results, 3, 0, 1, 3)

        no_match_label = QLabel("No models match this search.")
        self.no_match_label = no_match_label
        no_match_label.setObjectName("ModelNoMatchLabel")
        no_match_label.setVisible(False)
        setup_layout.addWidget(no_match_label, 4, 0, 1, 3)

        setup_layout.addWidget(QLabel("Pretrained weight"), 5, 0)
        weight_label = QLabel("None")
        self.weight_label = weight_label
        weight_label.setObjectName("PretrainedWeightLabel")
        weight_label.setMinimumHeight(28)
        weight_label.setWordWrap(False)
        setup_layout.addWidget(weight_label, 5, 1)
        weight_btn = QPushButton("Load")
        self.weight_btn = weight_btn
        weight_btn.setFixedWidth(76)
        weight_btn.clicked.connect(self.load_pretrained_weight)
        setup_layout.addWidget(weight_btn, 5, 2)
        setup_layout.setColumnStretch(1, 1)
        content_layout.addWidget(setup_frame)

        layout.addWidget(content_scroll, stretch=0)

        # Buttons
        action_layout = QHBoxLayout()
        action_layout.addStretch(1)
        confirm_btn = QPushButton("Confirm")
        self.confirm_btn = confirm_btn
        confirm_btn.setObjectName("PrimaryConfirmButton")
        confirm_btn.clicked.connect(self.accept)
        action_layout.addWidget(confirm_btn)
        layout.addLayout(action_layout)

    @staticmethod
    def _dialog_style() -> str:
        return f"""
        QDialog#ModelSelectionDialog {{
            background: {Theme.BACKGROUND_DARK};
            color: {Theme.TEXT_PRIMARY};
        }}
        QDialog#ModelSelectionDialog QLabel {{
            color: {Theme.TEXT_PRIMARY};
            background: transparent;
        }}
        QDialog#ModelSelectionDialog QFrame#ModelSection {{
            color: {Theme.TEXT_PRIMARY};
            border: none;
            border-radius: 6px;
            background: {Theme.BACKGROUND_MID};
        }}
        QDialog#ModelSelectionDialog QLabel#SectionTitle {{
            color: {Theme.TEXT_SECONDARY};
            background: transparent;
            font-weight: 700;
        }}
        QDialog#ModelSelectionDialog QLineEdit#ModelSearchInput {{
            background: {Theme.METRICS_TABLE_BG};
            color: {Theme.TEXT_PRIMARY};
            border: 1px solid {Theme.METRICS_TABLE_BORDER};
            border-radius: 4px;
            padding: 5px 8px;
            min-height: 22px;
        }}
        QDialog#ModelSelectionDialog QListWidget#ModelSearchResults {{
            background: {Theme.METRICS_TABLE_BG};
            alternate-background-color: {Theme.BACKGROUND_MID};
            color: {Theme.TEXT_PRIMARY};
            border: 1px solid {Theme.METRICS_TABLE_BORDER};
            border-radius: 4px;
            padding: 2px;
        }}
        QDialog#ModelSelectionDialog QListWidget#ModelSearchResults::item {{
            padding: 7px 8px;
            border-radius: 3px;
        }}
        QDialog#ModelSelectionDialog QListWidget#ModelSearchResults::item:selected {{
            background: {Theme.TABLE_SELECTION};
            color: {Theme.TEXT_PRIMARY};
        }}
        QDialog#ModelSelectionDialog QLabel#ModelProviderBanner {{
            background: {Theme.METRICS_TABLE_BG};
            color: {Theme.TEXT_SECONDARY};
            border: 1px solid {Theme.METRICS_TABLE_BORDER};
            border-radius: 4px;
            padding: 7px 9px;
        }}
        QDialog#ModelSelectionDialog QLabel#ModelProviderBanner[recovery="true"] {{
            color: #f0c36b;
            border-color: #8a6d2f;
            background: #332b1d;
        }}
        QDialog#ModelSelectionDialog QLabel#ModelNoMatchLabel {{
            color: {Theme.TEXT_MUTED};
            padding: 4px 2px;
        }}
        QDialog#ModelSelectionDialog QLabel#PretrainedWeightLabel {{
            background: {Theme.METRICS_TABLE_BG};
            color: {Theme.TEXT_SECONDARY};
            border: 1px solid {Theme.METRICS_TABLE_BORDER};
            border-radius: 4px;
            padding: 5px 8px;
        }}
        QDialog#ModelSelectionDialog QScrollArea#ModelSelectionContentScroll {{
            border: none;
            background: {Theme.BACKGROUND_DARK};
        }}
        QDialog#ModelSelectionDialog QScrollArea#ModelSelectionContentScroll > QWidget,
        QDialog#ModelSelectionDialog QWidget#ModelSelectionContent {{
            background: {Theme.BACKGROUND_DARK};
        }}
        QDialog#ModelSelectionDialog QScrollBar:vertical {{
            background: transparent;
            width: 8px;
            margin: 0;
            border: none;
        }}
        QDialog#ModelSelectionDialog QScrollBar::handle:vertical {{
            background: {Theme.BACKGROUND_LIGHT};
            border-radius: 5px;
            min-height: 28px;
        }}
        QDialog#ModelSelectionDialog QScrollBar::handle:vertical:hover {{
            background: {Theme.TEXT_MUTED};
        }}
        QDialog#ModelSelectionDialog QScrollBar::add-line:vertical,
        QDialog#ModelSelectionDialog QScrollBar::sub-line:vertical {{
            height: 0;
            background: transparent;
        }}
        QDialog#ModelSelectionDialog QScrollBar::add-page:vertical,
        QDialog#ModelSelectionDialog QScrollBar::sub-page:vertical {{
            background: transparent;
        }}
        QDialog#ModelSelectionDialog QPushButton {{
            background: {Theme.BACKGROUND_MID};
            color: {Theme.TEXT_PRIMARY};
            border: 1px solid {Theme.BACKGROUND_LIGHT};
            border-radius: 4px;
            padding: 6px 12px;
        }}
        QDialog#ModelSelectionDialog QPushButton:hover {{
            background: #32363b;
        }}
        QDialog#ModelSelectionDialog QPushButton:default {{
            background: {Theme.BLUE_PRIMARY};
            border-color: {Theme.BLUE_HOVER};
            font-weight: 700;
        }}
        QDialog#ModelSelectionDialog QPushButton#PrimaryConfirmButton {{
            min-width: 128px;
            padding: 7px 12px;
            border-radius: 4px;
            border: 1px solid #0a7fc7;
            background: #0069a8;
            color: {Theme.TEXT_PRIMARY};
            font-weight: 700;
        }}
        QDialog#ModelSelectionDialog QPushButton#PrimaryConfirmButton:hover {{
            background: #0a7fc7;
        }}
        """

    def _start_provider_preflight(self) -> None:
        if self._provider_worker is not None:
            return
        worker = PythonThreadWorker(
            braindecode_provider_status,
            name="xbrainlab-braindecode-provider-check",
            daemon=True,
        )
        self._provider_worker = worker
        worker.signals.result.connect(self._apply_provider_status)
        worker.signals.error.connect(self._provider_preflight_failed)
        worker.start()

    def _provider_preflight_failed(self, _error: object) -> None:
        self._apply_provider_status(
            BraindecodeProviderStatus(
                available=False,
                installed_version=None,
                reason="Braindecode provider readiness could not be verified.",
                checked=True,
            )
        )

    def _apply_provider_status(self, status: object) -> None:
        if not isinstance(status, BraindecodeProviderStatus) or not status.checked:
            self._provider_preflight_failed(status)
            return
        self._provider_status = status
        preserve_id = (
            self._selected_model_id
            if self._selection_changed_while_pending
            else self.initial_model_id
        )
        specs = list(
            discover_model_specs(
                model_base,
                provider_status=status,
                signal_context=self._signal_context,
            )
        )
        if (
            status.available
            and preserve_id
            and preserve_id.startswith("legacy.braindecode.")
        ):
            try:
                persisted = get_model_spec(
                    preserve_id,
                    provider_status=status,
                    signal_context=self._signal_context,
                )
            except ValueError:
                persisted = None
            if persisted is not None:
                specs.append(persisted)
        self._provider_check_pending = False
        self._apply_catalog(
            tuple(specs),
            preserve_id=preserve_id,
            fallback_to_first=preserve_id is None,
        )
        if self.provider_banner is not None:
            recovery = status.checked and not status.available
            self.provider_banner.setProperty("recovery", recovery)
            if status.available:
                self.provider_banner.clear()
                self.provider_banner.setVisible(False)
            else:
                self.provider_banner.setText(
                    "Braindecode 1.6.1 is unavailable. Showing reviewed local "
                    "recovery models; no model identity was changed automatically."
                )
                self.provider_banner.setVisible(True)
            style = self.provider_banner.style()
            if style is not None:
                style.unpolish(self.provider_banner)
                style.polish(self.provider_banner)
            self._resize_dialog_to_content()

    def _read_signal_context(self) -> dict[str, Any] | None:
        return get_training_model_signal_context(
            self.controller,
            runtime=self._query_port,
        )

    def _apply_catalog(
        self,
        specs: tuple[ModelSpec, ...],
        *,
        preserve_id: str | None,
        fallback_to_first: bool = True,
    ) -> None:
        self.model_specs = specs
        self._spec_by_id = {spec.model_id: spec for spec in specs}
        if self.model_results is None:
            return
        self.model_results.blockSignals(True)
        self.model_results.clear()
        selected_item: QListWidgetItem | None = None
        first_available: QListWidgetItem | None = None
        for spec in specs:
            detail = f"{spec.family} · {spec.task} · {spec.model_id}"
            if not spec.available:
                detail = f"Unavailable — {spec.unavailable_reason}"
            item = QListWidgetItem(f"{spec.display_name}\n{detail}")
            item.setData(Qt.ItemDataRole.UserRole, spec.model_id)
            item.setData(
                Qt.ItemDataRole.UserRole + 1,
                " ".join(
                    (
                        spec.display_name,
                        spec.model_id,
                        *spec.aliases,
                        spec.family,
                        spec.task,
                    )
                ).casefold(),
            )
            item.setToolTip(spec.unavailable_reason or detail)
            if not spec.available:
                item.setFlags(
                    item.flags()
                    & ~Qt.ItemFlag.ItemIsEnabled
                    & ~Qt.ItemFlag.ItemIsSelectable
                )
            elif first_available is None:
                first_available = item
            if spec.model_id == preserve_id and spec.available:
                selected_item = item
            self.model_results.addItem(item)
        self.model_results.blockSignals(False)
        chosen = selected_item or (first_available if fallback_to_first else None)
        if chosen is not None:
            self._applying_catalog = True
            try:
                self.model_results.setCurrentItem(chosen)
                self._select_spec(self._spec_for_item(chosen))
            finally:
                self._applying_catalog = False
        else:
            self.model_results.setCurrentItem(None)
            self._selected_model_id = None
            if self.confirm_btn is not None:
                self.confirm_btn.setEnabled(False)
        self.filter_models(self.search_input.text() if self.search_input else "")

    def filter_models(self, text: str) -> None:
        if self.model_results is None:
            return
        query = " ".join(str(text).casefold().split())
        visible_count = 0
        current_visible = False
        for index in range(self.model_results.count()):
            item = self.model_results.item(index)
            if item is None:
                continue
            search_text = str(item.data(Qt.ItemDataRole.UserRole + 1) or "")
            visible = not query or all(token in search_text for token in query.split())
            item.setHidden(not visible)
            if visible:
                visible_count += 1
                if item.data(Qt.ItemDataRole.UserRole) == self._selected_model_id:
                    current_visible = True
        if self.no_match_label is not None:
            self.no_match_label.setVisible(visible_count == 0)
        if self.confirm_btn is not None:
            selected = self._selected_spec()
            self.confirm_btn.setEnabled(
                bool(selected is not None and selected.available and current_visible)
            )

    def eventFilter(  # noqa: N802
        self,
        watched: QObject | None,
        event: QEvent,
    ) -> bool:
        if (
            watched is self.search_input
            and isinstance(event, QKeyEvent)
            and event.type() == QEvent.Type.KeyPress
        ):
            key = event.key()
            if key in (Qt.Key.Key_Down, Qt.Key.Key_Up):
                self._move_result_selection(1 if key == Qt.Key.Key_Down else -1)
                return True
            if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
                if self._current_result_is_actionable():
                    self.accept()
                else:
                    self._move_result_selection(1)
                return True
        return super().eventFilter(watched, event)

    def _move_result_selection(self, direction: int) -> None:
        if self.model_results is None:
            return
        candidates: list[int] = []
        for index in range(self.model_results.count()):
            item = self.model_results.item(index)
            if item is None:
                continue
            if not item.isHidden() and bool(item.flags() & Qt.ItemFlag.ItemIsEnabled):
                candidates.append(index)
        if not candidates:
            return
        current = self.model_results.currentRow()
        if current not in candidates:
            target = candidates[0 if direction > 0 else -1]
        else:
            offset = candidates.index(current) + direction
            target = candidates[max(0, min(offset, len(candidates) - 1))]
        self.model_results.setCurrentRow(target)

    def _on_result_changed(
        self,
        current: QListWidgetItem | None,
        _previous: QListWidgetItem | None,
    ) -> None:
        if self._provider_check_pending and not self._applying_catalog:
            self._selection_changed_while_pending = True
        self._select_spec(self._spec_for_item(current))

    def _focus_search_input(self) -> None:
        if self.search_input is not None:
            self.search_input.setFocus(Qt.FocusReason.OtherFocusReason)

    def _spec_for_item(self, item: QListWidgetItem | None) -> ModelSpec | None:
        if item is None:
            return None
        return self._spec_by_id.get(str(item.data(Qt.ItemDataRole.UserRole)))

    def _selected_spec(self) -> ModelSpec | None:
        if self._selected_model_id is None:
            return None
        return self._spec_by_id.get(self._selected_model_id)

    def _current_result_is_actionable(self) -> bool:
        if self.model_results is None:
            return False
        item = self.model_results.currentItem()
        spec = self._spec_for_item(item)
        return bool(
            item is not None
            and not item.isHidden()
            and item.flags() & Qt.ItemFlag.ItemIsEnabled
            and item.flags() & Qt.ItemFlag.ItemIsSelectable
            and spec is not None
            and spec.available
            and spec.model_id == self._selected_model_id
            and self.confirm_btn is not None
            and self.confirm_btn.isEnabled()
        )

    def _select_spec(self, spec: ModelSpec | None) -> None:
        if spec is None or not spec.available:
            if self.confirm_btn is not None:
                self.confirm_btn.setEnabled(False)
            return
        self._selected_model_id = spec.model_id
        self.filter_models(self.search_input.text() if self.search_input else "")

    def _resize_dialog_to_content(self) -> None:
        """Resize normal content high enough so the scroll area is not a gutter."""
        self.fit_to_content(
            minimum_width=640,
            minimum_height=452,
            maximum_height=620,
        )

    def load_pretrained_weight(self):
        """Open a file dialog to load or clear pretrained model weights."""
        if not self.weight_label or not self.weight_btn:
            return

        if self.pretrained_weight_path:
            self.pretrained_weight_path = None
            self.weight_label.setText("None")
            self.weight_btn.setText("Load")
            return

        filepath, _ = QFileDialog.getOpenFileName(
            self,
            "Select Pretrained Weight",
            filter="Model Weights (*)",
        )
        if filepath:
            self.pretrained_weight_path = filepath
            self.weight_label.setText(os.path.basename(filepath))
            self.weight_btn.setText("Clear")

    def accept(self):
        """Build the ModelHolder from current selections and accept."""
        if not self._current_result_is_actionable():
            return

        spec = self._selected_spec()
        if spec is None or not spec.available:
            if self.confirm_btn is not None:
                self.confirm_btn.setEnabled(False)
            return
        model_params_map = {
            parameter.key: parameter.default
            for parameter in spec.parameters
            if parameter.default is not None
        }

        try:
            self.model_holder = ModelHolder(
                spec.factory,
                model_params_map,
                self.pretrained_weight_path,
                model_id=spec.model_id,
                display_name=spec.display_name,
                provider=spec.provider,
                source_revision=spec.source_revision,
            )
            super().accept()

        except Exception:
            present_unexpected_error(
                self,
                UnexpectedErrorContext.TRAINING_MODEL_SETTINGS,
            )

    def get_result(self):
        """Return the configured ModelHolder.

        Returns:
            ModelHolder instance with selected model and parameters, or None.

        """
        return self.model_holder
