"""Canonical agent action contracts and compatibility projections."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from enum import Enum

from XBrainLab.backend.application.commands import CommandName


class AgentUiAction(str, Enum):
    """Agent actions fulfilled by UI or read-only adapters, not backend commands."""

    BROWSE_FILES = "browse_files"
    QUERY_STATE = "query_state"
    NAVIGATE = "navigate"


class AgentExecutionKind(str, Enum):
    """How the runtime must execute one canonical assistant tool."""

    APPLICATION_COMMAND = "application_command"
    UI_REQUEST = "ui_request"
    READ_ONLY = "read_only"


@dataclass(frozen=True, slots=True)
class AgentActionContract:
    """One canonical tool's backend/UI action and intent projection metadata."""

    canonical_tool: str
    action: CommandName | AgentUiAction
    taxonomy: str
    execution_kind: AgentExecutionKind = AgentExecutionKind.APPLICATION_COMMAND
    capability_command: CommandName | None = None
    intent_aliases: tuple[str, ...] = ()
    ui_decision_fields: tuple[str, ...] = ()
    direct_action: bool = False
    model_facing: bool = True

    def __post_init__(self) -> None:
        if self.capability_command is None and isinstance(self.action, CommandName):
            object.__setattr__(self, "capability_command", self.action)

    @property
    def command(self) -> CommandName | None:
        """Return the capability command used by the backend policy."""
        return self.capability_command

    @property
    def action_name(self) -> str:
        """Return the stable action key used by prompt policy."""
        return self.action.value


@dataclass(frozen=True, slots=True)
class AgentActionContractRegistry:
    """Validated immutable source for agent action compatibility views."""

    contracts: tuple[AgentActionContract, ...]

    def __post_init__(self) -> None:
        tool_names = [contract.canonical_tool for contract in self.contracts]
        duplicate_tools = _duplicates(tool_names)
        if duplicate_tools:
            raise ValueError(
                "Agent action contracts contain duplicate canonical tools: "
                f"{', '.join(duplicate_tools)}"
            )

        intent_aliases = [
            alias for contract in self.contracts for alias in contract.intent_aliases
        ]
        duplicate_aliases = _duplicates(intent_aliases)
        if duplicate_aliases:
            raise ValueError(
                "Agent action contracts contain duplicate intent aliases: "
                f"{', '.join(duplicate_aliases)}"
            )

        for contract in self.contracts:
            if not contract.canonical_tool or contract.canonical_tool.strip() != (
                contract.canonical_tool
            ):
                raise ValueError("Canonical tool names must be non-empty and trimmed.")
            if not contract.taxonomy or contract.taxonomy.strip() != contract.taxonomy:
                raise ValueError("Tool taxonomies must be non-empty and trimmed.")
            if (
                contract.execution_kind is AgentExecutionKind.APPLICATION_COMMAND
                and not isinstance(contract.action, CommandName)
            ):
                raise ValueError(
                    "Application-command tools must declare a CommandName action: "
                    f"{contract.canonical_tool}"
                )
            if (
                contract.execution_kind is AgentExecutionKind.APPLICATION_COMMAND
                and contract.capability_command is None
            ):
                raise ValueError(
                    "Application-command tools require a capability command: "
                    f"{contract.canonical_tool}"
                )
            if (
                contract.execution_kind is AgentExecutionKind.READ_ONLY
                and contract.capability_command is not None
            ):
                raise ValueError(
                    "Read-only direct tools cannot declare a mutation capability: "
                    f"{contract.canonical_tool}"
                )
            if (
                contract.execution_kind is not AgentExecutionKind.APPLICATION_COMMAND
                and contract.intent_aliases
            ):
                raise ValueError(
                    "Only application-command tools can map backend intent aliases: "
                    f"{contract.canonical_tool}"
                )
            if any(
                not alias or alias.strip() != alias for alias in contract.intent_aliases
            ):
                raise ValueError("Intent aliases must be non-empty and trimmed.")
            if (
                contract.ui_decision_fields
                and contract.execution_kind is not AgentExecutionKind.UI_REQUEST
            ):
                raise ValueError(
                    "Only UI-request tools can declare UI decision fields: "
                    f"{contract.canonical_tool}"
                )
            if len(set(contract.ui_decision_fields)) != len(
                contract.ui_decision_fields
            ) or any(
                not field or field.strip() != field
                for field in contract.ui_decision_fields
            ):
                raise ValueError(
                    "UI decision fields must be unique, non-empty, and trimmed."
                )

    def tool_names(self) -> frozenset[str]:
        """Return every canonical tool name exposed by this registry."""
        return frozenset(contract.canonical_tool for contract in self.contracts)

    def model_tool_names(self) -> frozenset[str]:
        """Return the canonical tools that may be published to the model."""
        return frozenset(
            contract.canonical_tool
            for contract in self.contracts
            if contract.model_facing
        )

    def contract_for(self, tool_name: str) -> AgentActionContract | None:
        """Return the canonical contract for ``tool_name`` when registered."""
        return next(
            (
                contract
                for contract in self.contracts
                if contract.canonical_tool == tool_name
            ),
            None,
        )

    def contracts_for_kind(
        self,
        execution_kind: AgentExecutionKind,
    ) -> tuple[AgentActionContract, ...]:
        """Return contracts executed through one explicit runtime boundary."""
        return tuple(
            contract
            for contract in self.contracts
            if contract.execution_kind is execution_kind
        )

    def tool_names_for_kind(
        self,
        execution_kind: AgentExecutionKind,
    ) -> frozenset[str]:
        """Return canonical tools assigned to ``execution_kind``."""
        return frozenset(
            contract.canonical_tool
            for contract in self.contracts_for_kind(execution_kind)
        )

    def taxonomy(self) -> dict[str, str]:
        """Project prompt taxonomy from the canonical contracts."""
        return {
            contract.canonical_tool: contract.taxonomy for contract in self.contracts
        }

    def validate_registered_tool_names(self, tool_names: list[str]) -> None:
        """Fail closed when a real/mock runtime drifts from this registry."""
        duplicates = _duplicates(tool_names)
        if duplicates:
            raise ValueError(
                "Tool runtime contains duplicate registrations: "
                f"{', '.join(duplicates)}"
            )
        registered = frozenset(tool_names)
        expected = self.tool_names()
        if registered != expected:
            missing = sorted(expected - registered)
            unknown = sorted(registered - expected)
            details: list[str] = []
            if missing:
                details.append(f"missing={','.join(missing)}")
            if unknown:
                details.append(f"unknown={','.join(unknown)}")
            raise ValueError(
                "Tool runtime does not match canonical action contracts ("
                + "; ".join(details)
                + ")."
            )

    def tool_to_command(self) -> dict[str, CommandName]:
        """Project the historical tool-to-command mapping."""
        return {
            contract.canonical_tool: command
            for contract in self.contracts
            if (command := contract.command) is not None
        }

    def intent_to_command(self) -> dict[str, CommandName]:
        """Project the historical intent-to-command mapping."""
        return {
            alias: command
            for contract in self.contracts
            if (command := contract.command) is not None
            for alias in contract.intent_aliases
        }

    def direct_action_tool_names(self) -> dict[str, frozenset[str]]:
        """Project direct action names to every canonical tool implementing them."""
        action_tools: dict[str, set[str]] = {}
        for contract in self.contracts:
            if contract.direct_action:
                action_tools.setdefault(contract.action_name, set()).add(
                    contract.canonical_tool
                )
        return {
            action_name: frozenset(tool_names)
            for action_name, tool_names in action_tools.items()
        }


def _duplicates(values: list[str]) -> tuple[str, ...]:
    return tuple(sorted(value for value, count in Counter(values).items() if count > 1))


AGENT_ACTION_CONTRACTS = AgentActionContractRegistry(
    contracts=(
        AgentActionContract(
            "switch_panel",
            AgentUiAction.NAVIGATE,
            taxonomy="UI Routing",
            execution_kind=AgentExecutionKind.UI_REQUEST,
            direct_action=True,
        ),
        AgentActionContract(
            "import_eeg_data",
            CommandName.SCAN_SOURCE,
            taxonomy="GUI Completion",
            execution_kind=AgentExecutionKind.UI_REQUEST,
            direct_action=True,
        ),
        AgentActionContract(
            "select_channels",
            CommandName.PREPROCESS,
            taxonomy="GUI Completion",
            execution_kind=AgentExecutionKind.UI_REQUEST,
            ui_decision_fields=("channels",),
            direct_action=True,
        ),
        AgentActionContract(
            "set_montage",
            CommandName.APPLY_MONTAGE,
            taxonomy="GUI Completion",
            execution_kind=AgentExecutionKind.UI_REQUEST,
            direct_action=True,
        ),
        AgentActionContract(
            "create_epochs",
            CommandName.CREATE_EPOCH,
            taxonomy="GUI Completion",
            execution_kind=AgentExecutionKind.UI_REQUEST,
            direct_action=True,
        ),
        AgentActionContract(
            "configure_dataset_split",
            CommandName.CONFIGURE_DATASET_SPLIT,
            taxonomy="GUI Completion",
            execution_kind=AgentExecutionKind.UI_REQUEST,
            direct_action=True,
        ),
        AgentActionContract(
            "select_model",
            CommandName.CONFIGURE_TRAINING,
            taxonomy="GUI Completion",
            execution_kind=AgentExecutionKind.UI_REQUEST,
            ui_decision_fields=("model",),
            direct_action=True,
        ),
        AgentActionContract(
            "configure_training",
            CommandName.CONFIGURE_TRAINING,
            taxonomy="GUI Completion",
            execution_kind=AgentExecutionKind.UI_REQUEST,
            ui_decision_fields=("training_options",),
            direct_action=True,
        ),
        AgentActionContract(
            "apply_bandpass_filter",
            CommandName.PREPROCESS,
            taxonomy="Data Transform",
            direct_action=True,
        ),
        AgentActionContract(
            "apply_notch_filter",
            CommandName.PREPROCESS,
            taxonomy="Data Transform",
            direct_action=True,
        ),
        AgentActionContract(
            "resample_data",
            CommandName.PREPROCESS,
            taxonomy="Data Transform",
            direct_action=True,
        ),
        AgentActionContract(
            "set_reference",
            CommandName.PREPROCESS,
            taxonomy="Data Transform",
            direct_action=True,
        ),
        AgentActionContract(
            "normalize_data",
            CommandName.PREPROCESS,
            taxonomy="Data Transform",
            direct_action=True,
        ),
        AgentActionContract(
            "start_training",
            CommandName.TRAIN,
            taxonomy="Execution",
            direct_action=True,
        ),
        AgentActionContract(
            "stop_training",
            CommandName.STOP_TRAINING,
            taxonomy="Execution",
            direct_action=True,
        ),
        AgentActionContract(
            "reset_preprocessing",
            CommandName.RESET_PREPROCESS,
            taxonomy="Lifecycle",
            direct_action=True,
        ),
        AgentActionContract(
            "clear_training_history",
            CommandName.CLEAR_TRAINING_HISTORY,
            taxonomy="Lifecycle",
            direct_action=True,
        ),
    )
)
