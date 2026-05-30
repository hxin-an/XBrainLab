"""State and change events shared by Data Import wizard steps."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class WizardStateChange(str, Enum):
    """Named UI state changes that the wizard host can route to affected steps."""

    LABEL_SOURCES = "label_sources"


@dataclass
class LabelSourceState:
    """Mutable label-source choices owned by the wizard workflow, not one step."""

    initial_sources: list[str] = field(default_factory=list)
    extra_sources: list[str] = field(default_factory=list)
    excluded_carriers: list[str] = field(default_factory=list)
    skip_labels: bool = False

    @classmethod
    def from_initial_sources(cls, sources: list[str]) -> LabelSourceState:
        initial = list(sources)
        return cls(initial_sources=initial, extra_sources=list(initial))

    def label_sources_changed(self) -> bool:
        return self.extra_sources != self.initial_sources

    def clear_skip(self) -> None:
        self.skip_labels = False

    def mark_skip(self) -> None:
        self.skip_labels = True

    def exclude_carrier(self, carrier_path: str) -> bool:
        carrier = str(carrier_path).strip()
        if not carrier or carrier in self.excluded_carriers:
            return False
        self.excluded_carriers.append(carrier)
        return True


@dataclass
class DataImportWizardState:
    """Workflow state shared by the Data Import wizard host and step views."""

    label_sources: LabelSourceState

    @classmethod
    def from_label_sources(cls, sources: list[str]) -> DataImportWizardState:
        return cls(label_sources=LabelSourceState.from_initial_sources(sources))
