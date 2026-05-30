"""Type-only host events shared by Data Import wizard step mixins."""

from __future__ import annotations

from typing import Any, Protocol

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


class DataImportWizardStepHostProtocol(DataImportWizardHostProtocol, Protocol):
    """Transitional PyQt mixin host type.

    The step mixins are composed into ``DataInterpretationPreviewDialog`` and
    still access many Qt widgets that are created by sibling step builders.
    Keep the public host event contract narrow above; this dynamic attribute
    boundary is a named compatibility exception for the remaining mixin split.
    """

    def __getattr__(self, name: str) -> Any:
        raise AttributeError(name)
