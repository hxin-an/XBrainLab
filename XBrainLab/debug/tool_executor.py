"""Policy-safe standalone executor for Interactive Debug Mode tools."""

from dataclasses import dataclass
from types import SimpleNamespace
from typing import Any, ClassVar

from XBrainLab.backend.utils.logger import logger
from XBrainLab.llm.action_contracts import (
    AGENT_ACTION_CONTRACTS,
    AgentExecutionKind,
)
from XBrainLab.llm.agent.execution_policy import HostExecutionPolicy
from XBrainLab.llm.agent.tool_attempt_coordinator import ToolAttemptCoordinator
from XBrainLab.llm.agent.tool_execution_coordinator import ToolExecutionCoordinator
from XBrainLab.llm.agent.verifier import PathProvenanceVerifier, VerificationLayer
from XBrainLab.llm.tools.application_surface import (
    SETTING_CHANGE_CONFIRMATION_KIND,
    TOOL_TO_COMMAND,
    ApplicationToolRuntime,
    ToolAvailability,
    ToolAvailabilityContext,
    ToolCommandResult,
    application_tool_runtime,
    assistant_edited_recommendation_fields,
    assistant_setting_change_requires_confirmation,
    get_application_context,
    setting_confirmation_params,
)
from XBrainLab.llm.tools.base import BaseTool
from XBrainLab.llm.tools.real.analysis_real import (
    RealEvaluateTool,
    RealSaliencyTool,
    RealVisualizeTool,
)
from XBrainLab.llm.tools.real.dataset_real import (
    RealApplyInterpretationTool,
    RealAttachLabelsTool,
    RealClearDatasetTool,
    RealConfigureDatasetSplitTool,
    RealGetDatasetInfoTool,
    RealListFilesTool,
    RealLoadDataTool,
    RealPreviewInterpretationTool,
    RealQueryStateTool,
    RealReloadInterpretationRecipeTool,
    RealSaveInterpretationRecipeTool,
    RealScanSourceTool,
    RealValidateInterpretationTool,
)
from XBrainLab.llm.tools.real.preprocess_real import (
    RealBandPassFilterTool,
    RealChannelSelectionTool,
    RealEpochDataTool,
    RealNormalizeTool,
    RealNotchFilterTool,
    RealRereferenceTool,
    RealResampleTool,
    RealResetPreprocessTool,
    RealSetMontageTool,
    RealStandardPreprocessTool,
)
from XBrainLab.llm.tools.real.training_real import (
    RealConfigureTrainingTool,
    RealSetModelTool,
    RealStartTrainingTool,
    RealStopTrainingTool,
)
from XBrainLab.llm.tools.real.ui_control_real import RealSwitchPanelTool
from XBrainLab.llm.tools.result_contract import (
    UiRequest,
    redact_public_text,
    safe_unexpected_failure,
)


@dataclass(frozen=True)
class _SingleToolRegistry:
    """Registry view for the one adapter admitted by this debug call."""

    tool_name: str
    tool: BaseTool

    def get_tool(self, name: str) -> BaseTool | None:
        return self.tool if name == self.tool_name else None


@dataclass(frozen=True, slots=True)
class DebugExecutionEvidence:
    """Observed canonical boundaries crossed by one standalone debug call."""

    tool_name: str
    dispatch_count: int
    publication_read_count: int
    runtime_command_invocation_count: int
    adapter_invocation_count: int
    ui_adapter_invocation_count: int


@dataclass(slots=True)
class _MutableDebugExecutionEvidence:
    tool_name: str
    dispatch_count: int = 1
    publication_read_count: int = 0
    runtime_command_invocation_count: int = 0
    adapter_invocation_count: int = 0
    ui_adapter_invocation_count: int = 0

    def freeze(self) -> DebugExecutionEvidence:
        return DebugExecutionEvidence(
            tool_name=self.tool_name,
            dispatch_count=self.dispatch_count,
            publication_read_count=self.publication_read_count,
            runtime_command_invocation_count=self.runtime_command_invocation_count,
            adapter_invocation_count=self.adapter_invocation_count,
            ui_adapter_invocation_count=self.ui_adapter_invocation_count,
        )


class _ObservedApplicationRuntime:
    """Count calls while delegating to the genuine application runtime."""

    def __init__(
        self,
        runtime: ApplicationToolRuntime,
        evidence: _MutableDebugExecutionEvidence,
    ) -> None:
        self._runtime = runtime
        self._evidence = evidence

    def get_view_publication(self) -> Any:
        self._evidence.publication_read_count += 1
        return self._runtime.get_view_publication()

    def execute(self, command: Any) -> Any:
        self._evidence.runtime_command_invocation_count += 1
        return self._runtime.execute(command)


class _ObservedToolAdapter(BaseTool):
    """Count actual direct/UI adapter invocation before delegation."""

    def __init__(
        self,
        tool: BaseTool,
        execution_kind: AgentExecutionKind,
        evidence: _MutableDebugExecutionEvidence,
    ) -> None:
        self._tool = tool
        self._execution_kind = execution_kind
        self._evidence = evidence

    @property
    def name(self) -> str:
        return self._tool.name

    @property
    def description(self) -> str:
        return self._tool.description

    @property
    def parameters(self) -> dict[str, Any]:
        return self._tool.parameters

    @property
    def requires_confirmation(self) -> bool:
        return self._tool.requires_confirmation

    def execute(self, study: Any, **kwargs: Any) -> Any:
        self._evidence.adapter_invocation_count += 1
        if self._execution_kind is AgentExecutionKind.UI_REQUEST:
            self._evidence.ui_adapter_invocation_count += 1
        return self._tool.execute(study, **kwargs)


class _SignalSink:
    def emit(self, *_args: Any) -> None:
        """Accept coordinator lifecycle events in a non-UI process."""


class _DebugExecutionHost:
    """Minimal non-UI host required by ``ToolExecutionCoordinator``."""

    def __init__(self, study: Any, registry: _SingleToolRegistry) -> None:
        self.study = study
        self.registry = registry
        self.metrics = SimpleNamespace(current_turn=None)
        self.status_update = _SignalSink()
        self.application_command_started = _SignalSink()
        self.application_command_completed = _SignalSink()


class _DebugBlockPolicy:
    @staticmethod
    def blocked_result(
        command_name: str,
        context: ToolAvailabilityContext,
    ) -> ToolCommandResult:
        return ToolAttemptCoordinator.blocked_result(command_name, context)


@dataclass(frozen=True)
class DebugToolAdmission:
    """One debug call admitted by the shared host-side policy boundary."""

    tool_name: str
    tool: BaseTool
    params: dict[str, Any]
    context: ToolAvailabilityContext


class ToolExecutor:
    """Executes tools requested by the Interactive Debug Mode.

    Maintains a class-level registry (``TOOL_MAP``) that maps short string
    names to concrete ``Real*Tool`` classes covering dataset, preprocessing,
    training, and UI-control operations.

    Attributes:
        TOOL_MAP: Class-variable mapping tool name strings to their
            corresponding ``BaseTool`` subclass types.
        study: The active :class:`Study` instance against which tools are
            executed.

    """

    TOOL_MAP: ClassVar[dict[str, type[BaseTool]]] = {
        # Dataset
        "list_files": RealListFilesTool,
        "scan_source": RealScanSourceTool,
        "preview_interpretation": RealPreviewInterpretationTool,
        "validate_interpretation": RealValidateInterpretationTool,
        "apply_interpretation": RealApplyInterpretationTool,
        "save_interpretation_recipe": RealSaveInterpretationRecipeTool,
        "reload_interpretation_recipe": RealReloadInterpretationRecipeTool,
        "load_data": RealLoadDataTool,
        "attach_labels": RealAttachLabelsTool,
        "clear_dataset": RealClearDatasetTool,
        "query_state": RealQueryStateTool,
        "get_dataset_info": RealGetDatasetInfoTool,
        "configure_dataset_split": RealConfigureDatasetSplitTool,
        # Analysis
        "evaluate": RealEvaluateTool,
        "visualize": RealVisualizeTool,
        "saliency": RealSaliencyTool,
        # Preprocess
        "apply_standard_preprocess": RealStandardPreprocessTool,
        "reset_preprocess": RealResetPreprocessTool,
        "apply_bandpass_filter": RealBandPassFilterTool,
        "apply_notch_filter": RealNotchFilterTool,
        "resample_data": RealResampleTool,
        "normalize_data": RealNormalizeTool,
        "set_reference": RealRereferenceTool,
        "select_channels": RealChannelSelectionTool,
        "set_montage": RealSetMontageTool,
        "epoch_data": RealEpochDataTool,
        # Training
        "configure_training": RealConfigureTrainingTool,
        "set_model": RealSetModelTool,
        "start_training": RealStartTrainingTool,
        "stop_training": RealStopTrainingTool,
        # UI
        "switch_panel": RealSwitchPanelTool,
    }

    def __init__(
        self,
        study: Any,
        *,
        application_runtime: ApplicationToolRuntime | None = None,
    ) -> None:
        """Initialise the executor with a study context.

        Args:
            study: The backend :class:`Study` instance that each tool
                receives as its first positional argument.
            application_runtime: Explicit command runtime for a non-Study
                headless host. Genuine ``Study`` instances resolve their
                canonical runtime automatically.

        """
        self.study = study
        self.application_runtime = (
            application_runtime
            if application_runtime is not None
            else application_tool_runtime(study)
        )
        self._active_evidence: _MutableDebugExecutionEvidence | None = None
        self._active_runtime: ApplicationToolRuntime | None = None
        self._last_execution_evidence: DebugExecutionEvidence | None = None

    @property
    def last_execution_evidence(self) -> DebugExecutionEvidence | None:
        """Return immutable boundary evidence for the most recent execute call."""
        return self._last_execution_evidence

    def execute(
        self,
        tool_name: str,
        params: dict[str, Any],
        *,
        authorization_text: str = "",
        confirmed: bool = False,
    ) -> ToolCommandResult | UiRequest:
        """Admit and execute one standalone debug tool call.

        Application-command tools always run through
        ``ToolExecutionCoordinator`` and ``ApplicationToolRuntime``. Direct
        adapter execution is limited to canonical read-only and UI-request
        tools after schema, path, capability, and confirmation checks.

        Args:
            tool_name: Key into ``TOOL_MAP`` identifying the tool to run.
            params: Proposed tool parameters.
            authorization_text: Trusted host text containing any user-approved
                filesystem paths. Path-bearing calls fail closed when their
                paths are absent from this text and backend state.
            confirmed: Explicit host confirmation for a destructive tool.
                Confirmation is separate from the tool's public parameter
                schema and defaults to denied.

        Returns:
            A structured command result, or a typed UI request for a canonical
            UI-request tool.

        """
        evidence = _MutableDebugExecutionEvidence(tool_name=tool_name)
        self._active_evidence = evidence
        self._active_runtime = (
            _ObservedApplicationRuntime(self.application_runtime, evidence)
            if self.application_runtime is not None
            else None
        )
        try:
            tool_class = self.TOOL_MAP.get(tool_name)
            if not tool_class:
                msg = "The requested debug tool is unavailable."
                logger.error("Rejected an unknown debug tool.")
                return ToolCommandResult.failure(
                    "unknown_debug_tool",
                    msg,
                    error_type="input",
                )
            admission = self.admit(
                tool_name,
                dict(params),
                authorization_text=authorization_text,
                confirmed=confirmed,
            )
            if isinstance(admission, ToolCommandResult):
                return admission
            return self._execute_admitted(admission)
        except Exception as exc:
            failure = safe_unexpected_failure(
                logger,
                exc,
                boundary="debug_tool_executor",
                operation=tool_name,
            )
            return ToolCommandResult.failure(
                tool_name,
                failure.message,
                command_name=self._mapped_command_name(tool_name),
                error_type=failure.error_type,
                error_code=failure.error_code,
                recovery_action=failure.recovery_action,
                recoverable=failure.recoverable,
                diagnostics=failure.diagnostics,
            )
        finally:
            self._last_execution_evidence = evidence.freeze()
            self._active_evidence = None
            self._active_runtime = None

    def admit(
        self,
        tool_name: str,
        params: dict[str, Any],
        *,
        authorization_text: str = "",
        confirmed: bool = False,
    ) -> DebugToolAdmission | ToolCommandResult:
        """Apply the canonical debug schema, path, capability, and host gates."""
        tool_class = self.TOOL_MAP.get(tool_name)
        if tool_class is None:
            return ToolCommandResult.failure(
                "unknown_debug_tool",
                "The requested debug tool is unavailable.",
                error_type="input",
            )
        logger.info(
            "Admitting debug tool %s (parameter count: %d)",
            redact_public_text(tool_name),
            len(params),
        )
        tool = tool_class()
        contract = AGENT_ACTION_CONTRACTS.contract_for(tool_name)
        if contract is None:
            return ToolCommandResult.failure(
                tool_name,
                (
                    f"Debug tool '{tool_name}' is not classified by the "
                    "canonical action registry."
                ),
                error_type="contract",
                recoverable=False,
                diagnostics={"boundary": "agent_action_contract"},
            )
        if tool.name != tool_name:
            return ToolCommandResult.failure(
                tool_name,
                "Debug tool registry returned a mismatched tool implementation.",
                command_name=self._mapped_command_name(tool_name),
                error_type="contract",
                recoverable=False,
                diagnostics={
                    "registered_name": tool_name,
                    "adapter_name": tool.name,
                },
            )
        if "confirmed" in params:
            return ToolCommandResult.failure(
                tool_name,
                (
                    "Host confirmation must be supplied by the trusted debug "
                    "transport, not inside tool parameters."
                ),
                command_name=self._mapped_command_name(tool_name),
                error_type="input",
                recoverable=True,
                diagnostics={"policy": "host_confirmation_parameter"},
            )

        if (
            contract.execution_kind is AgentExecutionKind.APPLICATION_COMMAND
            and self.application_runtime is None
        ):
            context = self._runtime_required_context(tool_name)
        else:
            context = self._context_for(tool_name, contract.execution_kind)
        path_validation = PathProvenanceVerifier().validate(
            tool_name,
            params,
            latest_user_text=authorization_text,
            state=context.state,
        )
        if not path_validation.is_valid:
            return self._admission_failure(
                tool_name,
                context,
                path_validation.error_message
                or "The requested path is not authorized.",
                diagnostics={"policy": "path_provenance"},
            )

        validation = VerificationLayer(
            confidence_threshold=0.0,
            tool_schemas={tool_name: tool.parameters},
        ).verify_tool_call((tool_name, params), confidence=1.0)
        if not validation.is_valid:
            return self._admission_failure(
                tool_name,
                context,
                validation.error_message or "Tool parameters did not pass validation.",
                diagnostics={"policy": "tool_schema"},
            )

        if not context.availability.enabled:
            return _DebugBlockPolicy.blocked_result(tool_name, context)

        requires_command_confirmation = HostExecutionPolicy.needs_confirmation(
            context.availability,
            tool_requires_confirmation=tool.requires_confirmation,
        )
        edited_recommendation_fields = assistant_edited_recommendation_fields(
            tool_name,
            params,
        )
        evaluated_params = setting_confirmation_params(tool_name, params)
        requires_setting_confirmation = (
            context.policy_error is None
            and type(context.generation) is int
            and assistant_setting_change_requires_confirmation(
                tool_name,
                evaluated_params,
                context.state,
            )
        )
        needs_confirmation = (
            requires_command_confirmation or requires_setting_confirmation
        )
        if needs_confirmation and confirmed is not True:
            return ToolCommandResult.failure(
                tool_name,
                "Explicit human confirmation is required before this tool can run.",
                command_name=context.availability.command_name,
                state=context.state,
                capability=context.availability.to_dict(),
                error_type="confirmation_required",
                recoverable=True,
                diagnostics={"policy": "host_confirmation"},
            )

        execution_params = evaluated_params
        if needs_confirmation:
            execution_params = ToolAttemptCoordinator.confirmed_params(
                tool_name,
                evaluated_params,
                requires_command_confirmation=requires_command_confirmation,
                publication_generation=context.generation,
                confirmation_kind=(
                    SETTING_CHANGE_CONFIRMATION_KIND
                    if requires_setting_confirmation
                    else None
                ),
                edited_recommendation_fields=edited_recommendation_fields,
            )
        return DebugToolAdmission(
            tool_name=tool_name,
            tool=tool,
            params=execution_params,
            context=context,
        )

    def _execute_admitted(
        self,
        admission: DebugToolAdmission,
    ) -> ToolCommandResult | UiRequest:
        evidence = self._active_evidence
        contract = AGENT_ACTION_CONTRACTS.contract_for(admission.tool_name)
        if evidence is None or contract is None:
            raise RuntimeError("Debug execution evidence was not initialized.")
        observed_tool = _ObservedToolAdapter(
            admission.tool,
            contract.execution_kind,
            evidence,
        )
        registry = _SingleToolRegistry(admission.tool_name, observed_tool)
        host = _DebugExecutionHost(self.study, registry)
        coordinator = ToolExecutionCoordinator(
            host,
            block_policy=_DebugBlockPolicy(),
            application_runtime=self._runtime_for_call(),
        )
        outcome = coordinator.execute(
            admission.tool_name,
            admission.params,
            context=admission.context,
        )
        return outcome.result

    def _context_for(
        self,
        tool_name: str,
        execution_kind: AgentExecutionKind,
    ) -> ToolAvailabilityContext:
        runtime = self._runtime_for_call()
        if runtime is not None:
            try:
                context = get_application_context(
                    self.study,
                    tool_name,
                    runtime=runtime,
                )
            except Exception as exc:
                failure = safe_unexpected_failure(
                    logger,
                    exc,
                    boundary="debug_tool_policy_lookup",
                    operation=tool_name,
                )
                return ToolAttemptCoordinator.unavailable_context(
                    tool_name,
                    failure.message,
                )
            if context is not None:
                return context

        if tool_name in {"list_files", "switch_panel"}:
            return ToolAvailabilityContext(
                availability=ToolAvailability(
                    tool_name=tool_name,
                    enabled=True,
                    read_only=execution_kind is AgentExecutionKind.READ_ONLY,
                ),
                state=None,
                generation=None,
            )
        return ToolAttemptCoordinator.unavailable_context(
            tool_name,
            "ApplicationToolRuntime is required to verify this tool's policy.",
        )

    def _runtime_for_call(self) -> ApplicationToolRuntime | None:
        return (
            self._active_runtime
            if self._active_evidence is not None
            else self.application_runtime
        )

    @staticmethod
    def _runtime_required_context(tool_name: str) -> ToolAvailabilityContext:
        return ToolAvailabilityContext(
            availability=ToolAvailability(
                tool_name=tool_name,
                enabled=True,
                command_name=ToolExecutor._mapped_command_name(tool_name),
            ),
            state=None,
            generation=None,
        )

    @staticmethod
    def _admission_failure(
        tool_name: str,
        context: ToolAvailabilityContext,
        message: str,
        *,
        diagnostics: dict[str, Any],
    ) -> ToolCommandResult:
        return ToolCommandResult.failure(
            tool_name,
            message,
            command_name=context.availability.command_name,
            state=context.state,
            capability=context.availability.to_dict(),
            error_type="input",
            recoverable=True,
            diagnostics={
                **diagnostics,
                "publication_generation": context.generation,
            },
        )

    @staticmethod
    def _mapped_command_name(tool_name: str) -> str | None:
        command = TOOL_TO_COMMAND.get(tool_name)
        return command.value if command is not None else None
