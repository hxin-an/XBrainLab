"""Event filter dialog for selecting GDF events to retain.

Provides a checkable list of event names with persistent selection memory,
context menu, and toggle functionality for efficient event filtering.
"""

from PyQt6.QtCore import QSettings, Qt
from PyQt6.QtWidgets import (
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QPushButton,
    QVBoxLayout,
)

from XBrainLab.ui.core.base_dialog import BaseDialog


class EventFilterDialog(BaseDialog):
    """Dialog for filtering GDF events by selecting which events to keep.

    Provides a checkable list with Select All/Deselect All, toggle, and
    context menu support. Persists the last selection using QSettings.

    Attributes:
        event_names: Sorted list of available event name strings.
        selected_names: List of event names selected by the user.
        settings: QSettings instance for persisting selection state.
        list_widget: QListWidget displaying checkable event names.
        btn_all: Button to select all events.
        btn_none: Button to deselect all events.
        btn_toggle: Button to toggle selected items.

    """

    def __init__(self, parent, event_names):
        self.event_names = event_names  # Already sorted list of strings
        self.selected_names = []
        self.settings = QSettings("XBrainLab", "EventFilter")

        # UI
        self.list_widget = None
        self.btn_all = None
        self.btn_none = None
        self.btn_toggle = None

        super().__init__(parent, title="Filter GDF Events")
        self.resize(300, 400)

    def init_ui(self):
        """Initialize the dialog UI with event list and control buttons."""
        layout = QVBoxLayout(self)

        layout.addWidget(QLabel("Select events to KEEP for synchronization:"))

        # Load last selection
        last_selected = self.settings.value("last_selected_events", [], type=list)
        # Ensure it's a list of strings (QSettings might return list of QVariant)
        last_selected = [str(x) for x in last_selected]

        self.list_widget = QListWidget()
        self.list_widget.setSelectionMode(QListWidget.SelectionMode.ExtendedSelection)
        self.list_widget.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.list_widget.customContextMenuRequested.connect(self.show_context_menu)

        for name in self.event_names:
            item = QListWidgetItem(str(name))
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)

            # Check if it was selected last time OR if no history (default all checked)
            if not last_selected or str(name) in last_selected:
                item.setCheckState(Qt.CheckState.Checked)
            else:
                item.setCheckState(Qt.CheckState.Unchecked)

            self.list_widget.addItem(item)

        layout.addWidget(self.list_widget)

        # Select All / None
        btn_layout = QHBoxLayout()
        self.btn_all = QPushButton("Select All")
        self.btn_all.clicked.connect(lambda: self.set_all_checked(True))
        self.btn_none = QPushButton("Deselect All")
        self.btn_none.clicked.connect(lambda: self.set_all_checked(False))
        btn_layout.addWidget(self.btn_all)
        btn_layout.addWidget(self.btn_none)

        self.btn_toggle = QPushButton("Toggle Selected")
        self.btn_toggle.clicked.connect(self.toggle_selected)
        btn_layout.addWidget(self.btn_toggle)

        layout.addLayout(btn_layout)

        # Buttons
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel,
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def set_all_checked(self, checked):
        """Set the check state for all event items.

        Args:
            checked: If True, check all items; otherwise uncheck all.

        """
        if self.list_widget is None:
            return
        state = Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked
        for i in range(self.list_widget.count()):
            item = self.list_widget.item(i)
            if item:
                item.setCheckState(state)

    def toggle_selected(self):
        """Toggle the check state of all currently selected items."""
        if self.list_widget is None:
            return
        selected_items = self.list_widget.selectedItems()
        if not selected_items:
            return

        # Toggle based on the first item's state
        first_state = selected_items[0].checkState()
        new_state = (
            Qt.CheckState.Unchecked
            if first_state == Qt.CheckState.Checked
            else Qt.CheckState.Checked
        )

        for item in selected_items:
            item.setCheckState(new_state)

    def show_context_menu(self, pos):
        """Display a context menu with check/uncheck/toggle actions.

        Args:
            pos: Position where the context menu was requested.

        """
        if self.list_widget is None:
            return
        menu = QMenu(self)
        action_check = menu.addAction("Check Selected")
        action_uncheck = menu.addAction("Uncheck Selected")
        action_toggle = menu.addAction("Toggle Selected")

        action = menu.exec(self.list_widget.mapToGlobal(pos))

        selected_items = self.list_widget.selectedItems()
        if not selected_items:
            return

        if action == action_check:
            for item in selected_items:
                item.setCheckState(Qt.CheckState.Checked)
        elif action == action_uncheck:
            for item in selected_items:
                item.setCheckState(Qt.CheckState.Unchecked)
        elif action == action_toggle:
            self.toggle_selected()

    def keyPressEvent(self, event):  # noqa: N802
        """Handle key press events, mapping Space to toggle.

        Args:
            event: The key press event.

        """
        if event.key() == Qt.Key.Key_Space:
            self.toggle_selected()
        else:
            super().keyPressEvent(event)

    def accept(self):
        """Collect checked events, persist selection, and accept dialog."""
        if self.list_widget is not None:
            self.selected_names = []
            for i in range(self.list_widget.count()):
                item = self.list_widget.item(i)
                if item and item.checkState() == Qt.CheckState.Checked:
                    self.selected_names.append(item.text())

            # Save to settings
            self.settings.setValue("last_selected_events", self.selected_names)

        super().accept()

    def get_selected_ids(self):
        """Return the list of selected event names.

        Returns:
            List of checked event name strings.

        """
        return self.selected_names

    def get_result(self):
        """Return the list of selected event names.

        Returns:
            List of checked event name strings.

        """
        return self.get_selected_ids()

    def set_selection(self, names):
        """Programmatically set the checked events.

        Unchecks all items first, then checks only those matching the
        provided names.

        Args:
            names: List of event name strings to check.

        """
        # Uncheck all first? Or just check the ones in names?
        # Smart filter implies "These are the ones you want".
        # So let's uncheck all, then check names.
        self.set_all_checked(False)

        if self.list_widget is None:
            return

        for i in range(self.list_widget.count()):
            item = self.list_widget.item(i)
            if item and item.text() in names:
                item.setCheckState(Qt.CheckState.Checked)
