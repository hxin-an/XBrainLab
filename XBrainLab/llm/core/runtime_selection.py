"""Single policy owner for local Assistant runtime launch selection."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from XBrainLab.llm.core.config import LLMConfig
from XBrainLab.llm.core.model_catalog import local_model_policy_error


class AssistantRuntimeBackend(str, Enum):
    """Backends supported by the product Assistant runtime."""

    LOCAL = "local"


class AssistantRuntimeSelectionOutcome(str, Enum):
    """How the concrete launch model relates to the requested model."""

    EXACT = "exact"
    # Retained so historical runtime snapshots remain deserializable. The
    # product resolver no longer emits fallback selections.
    FALLBACK = "fallback"


class AssistantRuntimeSelectionFailureCode(str, Enum):
    """Typed reasons why a launch request cannot produce a launch spec."""

    UNKNOWN_BACKEND = "unknown_backend"
    UNKNOWN_MODEL = "unknown_model"
    RUNTIME_DISABLED = "runtime_disabled"
    RUNTIME_UNAVAILABLE = "runtime_unavailable"


@dataclass(frozen=True)
class AssistantRuntimeSelectionFailure:
    """Fail-closed result for an invalid or unavailable launch request."""

    code: AssistantRuntimeSelectionFailureCode
    message: str
    requested_backend_id: str
    requested_model_id: str


@dataclass(frozen=True)
class AssistantRuntimeSettingsSnapshot:
    """Immutable model-independent settings captured at resolution time."""

    device: str
    max_new_tokens: int
    timeout: int
    temperature: float
    top_p: float
    do_sample: bool
    load_in_4bit: bool
    cache_dir: str
    local_model_enabled: bool
    local_runtime_notice_acknowledged: bool

    @classmethod
    def from_config(cls, config: LLMConfig) -> AssistantRuntimeSettingsSnapshot:
        """Freeze settings needed to construct the selected runtime."""
        return cls(
            device=str(config.device),
            max_new_tokens=int(config.max_new_tokens),
            timeout=int(config.timeout),
            temperature=float(config.temperature),
            top_p=float(config.top_p),
            do_sample=bool(config.do_sample),
            load_in_4bit=bool(config.load_in_4bit),
            cache_dir=str(config.cache_dir),
            local_model_enabled=bool(config.local_model_enabled),
            local_runtime_notice_acknowledged=bool(
                config.local_runtime_notice_acknowledged
            ),
        )

    def build_config(self, model_id: str) -> LLMConfig:
        """Build an isolated mutable engine config for one exact model."""
        return LLMConfig(
            model_name=model_id,
            device=self.device,
            max_new_tokens=self.max_new_tokens,
            timeout=self.timeout,
            temperature=self.temperature,
            top_p=self.top_p,
            do_sample=self.do_sample,
            load_in_4bit=self.load_in_4bit,
            cache_dir=self.cache_dir,
            inference_mode=AssistantRuntimeBackend.LOCAL.value,
            active_mode=AssistantRuntimeBackend.LOCAL.value,
            local_model_enabled=self.local_model_enabled,
            local_runtime_notice_acknowledged=(self.local_runtime_notice_acknowledged),
        )


@dataclass(frozen=True)
class AssistantRuntimeLaunchSpec:
    """Exact immutable input consumed by controller and worker startup."""

    backend: AssistantRuntimeBackend
    requested_backend_id: str
    requested_model_id: str
    model_id: str
    outcome: AssistantRuntimeSelectionOutcome
    selection_detail: str
    settings: AssistantRuntimeSettingsSnapshot

    @property
    def backend_mode(self) -> str:
        return self.backend.value

    @property
    def fallback_used(self) -> bool:
        return self.outcome is AssistantRuntimeSelectionOutcome.FALLBACK

    def build_config(self) -> LLMConfig:
        """Build an engine config fixed to this resolved model selection."""
        return self.settings.build_config(self.model_id)


@dataclass(frozen=True)
class AssistantRuntimeLaunchResolution:
    """Exactly one launch spec or typed failure from the resolver."""

    launch_spec: AssistantRuntimeLaunchSpec | None = None
    failure: AssistantRuntimeSelectionFailure | None = None

    def __post_init__(self) -> None:
        if (self.launch_spec is None) == (self.failure is None):
            raise ValueError("Runtime resolution requires one spec or one failure.")

    @property
    def available(self) -> bool:
        return self.launch_spec is not None


class AssistantRuntimeLaunchResolver:
    """Resolve one exact backend/model request without catalog fallback."""

    def resolve(
        self,
        config: LLMConfig,
        *,
        requested_backend_id: str | None = None,
        requested_model_id: str | None = None,
    ) -> AssistantRuntimeLaunchResolution:
        """Return an immutable launch spec or a typed fail-closed result."""
        backend_id = str(
            config.inference_mode
            if requested_backend_id is None
            else requested_backend_id
        ).strip()
        model_id = str(
            config.model_name if requested_model_id is None else requested_model_id
        ).strip()

        if backend_id.lower() != AssistantRuntimeBackend.LOCAL.value:
            return self._failure(
                AssistantRuntimeSelectionFailureCode.UNKNOWN_BACKEND,
                (
                    f"Unknown assistant backend {backend_id!r}. "
                    "The product runtime supports only 'local'."
                ),
                backend_id=backend_id,
                model_id=model_id,
            )

        policy_error = local_model_policy_error(model_id)
        if policy_error is not None:
            return self._failure(
                AssistantRuntimeSelectionFailureCode.UNKNOWN_MODEL,
                policy_error,
                backend_id=backend_id,
                model_id=model_id,
            )

        if not config.local_model_enabled:
            return self._failure(
                AssistantRuntimeSelectionFailureCode.RUNTIME_DISABLED,
                (
                    "Local assistant runtime is disabled. Enable it in assistant "
                    "settings when you want to use the local model."
                ),
                backend_id=backend_id,
                model_id=model_id,
            )

        try:
            ready = bool(config.local_backend_ready(model_id))
            detail = config.local_backend_status_message(model_id)
        except Exception as exc:
            return self._failure(
                AssistantRuntimeSelectionFailureCode.RUNTIME_UNAVAILABLE,
                (
                    "Local runtime readiness check failed for requested model "
                    f"{model_id}: {exc!s}"
                ),
                backend_id=backend_id,
                model_id=model_id,
            )

        if not ready:
            unavailable_detail = " ".join(str(detail or "").split())
            message = f"Requested local model {model_id} is unavailable."
            if unavailable_detail:
                message = f"{message} {unavailable_detail}"
            return self._failure(
                AssistantRuntimeSelectionFailureCode.RUNTIME_UNAVAILABLE,
                message,
                backend_id=backend_id,
                model_id=model_id,
            )

        return AssistantRuntimeLaunchResolution(
            launch_spec=AssistantRuntimeLaunchSpec(
                backend=AssistantRuntimeBackend.LOCAL,
                requested_backend_id=backend_id,
                requested_model_id=model_id,
                model_id=model_id,
                outcome=AssistantRuntimeSelectionOutcome.EXACT,
                selection_detail=" ".join(str(detail or "").split()),
                settings=AssistantRuntimeSettingsSnapshot.from_config(config),
            )
        )

    @staticmethod
    def _failure(
        code: AssistantRuntimeSelectionFailureCode,
        message: str,
        *,
        backend_id: str,
        model_id: str,
    ) -> AssistantRuntimeLaunchResolution:
        return AssistantRuntimeLaunchResolution(
            failure=AssistantRuntimeSelectionFailure(
                code=code,
                message=" ".join(str(message or "").split()),
                requested_backend_id=backend_id,
                requested_model_id=model_id,
            )
        )
