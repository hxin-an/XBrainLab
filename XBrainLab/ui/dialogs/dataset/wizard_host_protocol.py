"""Type-only host events shared by Data Import wizard step mixins."""

from __future__ import annotations

from typing import Protocol

from XBrainLab.ui.dialogs.dataset.wizard_state import (
    DataImportWizardState,
    WizardStateChange,
)


class DataImportWizardHostProtocol(Protocol):
    """Minimal cross-step notification surface.

    Step mixins render view fragments, but they do not own downstream refresh
    rules. They report state changes to the host, which routes updates to the
    affected panels.
    """

    _wizard_state: DataImportWizardState

    def _notify_wizard_state_changed(self, change: WizardStateChange) -> None: ...
