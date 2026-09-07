"""Evaluation panel for viewing confusion matrices, metrics, and model summaries."""

import json
import logging
from collections.abc import Mapping
from dataclasses import dataclass
from typing import cast

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLayout,
    QSizePolicy,
    QStackedWidget,
    QTabWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from XBrainLab.backend.application import (
    ApplicationError,
    EvaluateCommand,
    EvaluationCrossFoldIdentity,
    EvaluationPlanIdentity,
    EvaluationRenderPublication,
    EvaluationRenderRequest,
    EvaluationRunIdentity,
    EvaluationSummaryIdentity,
)
from XBrainLab.backend.application.owned_work import OwnedOperationCancelledError
from XBrainLab.backend.application.results import CommandResult
from XBrainLab.backend.application.serialization import serialize_json_value
from XBrainLab.backend.application.state import EvaluationStateSnapshot
from XBrainLab.backend.application.view_publication import (
    APPLICATION_VIEW_PUBLICATION_CHANGED_EVENT,
    ApplicationViewPublication,
)
from XBrainLab.backend.training_state_contract import (
    PostTrainingSaliencyPhase,
    TrainingTerminalOutcome,
)
from XBrainLab.backend.utils.observer import Observable
from XBrainLab.ui.application_capabilities import (
    ApplicationPublicationSubscriptionPort,
    ApplicationUiRuntime,
    EvaluationActionPort,
    EvaluationQueryPort,
    application_ui_runtime,
    begin_evaluation_render_operation,
    cancel_application_operation,
    execute_application_command,
    execute_application_command_async,
    fail_application_operation,
    get_application_view_publication,
    run_evaluation_render_operation,
)
from XBrainLab.ui.application_publication_renderer import (
    ApplicationPublicationRenderLedger,
)
from XBrainLab.ui.components.info_panel import AggregateInfoPanel
from XBrainLab.ui.components.presentation import ElidingComboBox, ResponsiveControlsBar
from XBrainLab.ui.core.base_panel import BasePanel
from XBrainLab.ui.core.worker import PythonThreadWorker
from XBrainLab.ui.panels.evaluation.confusion_matrix import ConfusionMatrixWidget
from XBrainLab.ui.panels.evaluation.metrics_bar_chart import MetricsBarChartWidget
from XBrainLab.ui.panels.evaluation.metrics_table import MetricsTableWidget
from XBrainLab.ui.product_language import (
    fold_display_label,
    run_display_label,
)
from XBrainLab.ui.styles.stylesheets import Stylesheets
from XBrainLab.ui.styles.theme import Theme

MODEL_SUMMARY_UNAVAILABLE_TEXT = (
    "Model summary unavailable for the selected run because its trained model "
    "artifact is not available. Train the run again or select another completed run."
)
MODEL_SUMMARY_DEFERRED_TEXT = "Open Model Summary to load model details."
MODEL_SUMMARY_PENDING_TEXT = "Model details are still being prepared..."
MODEL_SUMMARY_CROSS_FOLD_TEXT = (
    "Model details are available for an individual fold or run."
)
MODEL_SUMMARY_BACKGROUND_UNAVAILABLE_TEXT = (
    "Model summary could not start in the background. Try again after the current "
    "operation finishes."
)
MODEL_SUMMARY_LOAD_FAILED_TEXT = (
    "Model details could not be loaded. Select another completed run or "
    "reopen Evaluation to try again."
)
CHART_TABS_BREAKPOINT = 720
COMPACT_HEIGHT_BREAKPOINT = 600
INFO_SIDEBAR_WIDTH = 260
COMPACT_INFO_SIDEBAR_BREAKPOINT = 540
logger = logging.getLogger(__name__)
EVALUATION_SPLIT_OPTIONS = (
    ("training", "Train"),
    ("validation", "Validation"),
    ("test", "Test"),
)


@dataclass(frozen=True, slots=True)
class _EvaluationRunChoice:
    identity: EvaluationRunIdentity
    name: str
    finished: bool
    splits: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class _EvaluationPlanChoice:
    identity: EvaluationPlanIdentity
    name: str
    runs: tuple[_EvaluationRunChoice, ...]


@dataclass(frozen=True, slots=True)
class _EvaluationCrossFoldChoice:
    identity: EvaluationCrossFoldIdentity
    display_name: str
    run_label: str
    splits: tuple[str, ...]
    fold_count: int
    sample_count: int


@dataclass(frozen=True, slots=True)
class _EvaluationCrossFoldGroup:
    display_name: str
    plan_indexes: tuple[int, ...]
    choices: tuple[_EvaluationCrossFoldChoice, ...]


@dataclass(frozen=True, slots=True)
class _EvaluationSummary:
    available: bool
    plans: tuple[_EvaluationPlanChoice, ...]
    cross_fold_choices: tuple[_EvaluationCrossFoldChoice, ...]


@dataclass(frozen=True, slots=True)
class _EvaluationPublicationSignature:
    """Application fields that can change Evaluation's rendered catalog."""

    usable: bool
    trainer_identity: str | None
    training_boundary_stable: bool
    has_model: bool
    model_name: str | None
    model_params: str
    has_trainer: bool
    is_running: bool
    stable_catalog_generation: int | None
    plan_count: int
    run_count: int
    finished_run_count: int
    terminal_outcome: TrainingTerminalOutcome
    missing_requirements: tuple[str, ...]
    evaluation_state: EvaluationStateSnapshot


@dataclass(frozen=True, slots=True)
class _ModelSummaryRequest:
    sequence: int
    identity: EvaluationSummaryIdentity
    publication_generation: int | None


class EvaluationPanel(BasePanel):
    """Panel for analysing trained-model performance.

    Displays confusion matrices, per-class metric tables and bar charts,
    and textual model summaries.  Supports plan/run selection and
    percentage-toggle options.

    Attributes:
        model_combo: ``QComboBox`` for selecting a training fold/plan.
        run_combo: ``QComboBox`` for selecting an individual run or
            average.
        chk_percentage: ``QCheckBox`` toggling percentage display.
        matrix_widget: ``ConfusionMatrixWidget`` for the matrix plot.
        bar_chart: ``MetricsBarChartWidget`` for per-class bar chart.
        metrics_table: ``MetricsTableWidget`` for the metrics table.
        summary_text: ``QTextEdit`` displaying the model summary string.
        info_panel: ``AggregateInfoPanel`` in the sidebar.

    """

    def __init__(
        self,
        parent=None,
        *,
        query_port: EvaluationQueryPort | None = None,
        publication_port: ApplicationPublicationSubscriptionPort | None = None,
        action_port: EvaluationActionPort | None = None,
    ):
        """Initialize the evaluation panel.

        Args:
            parent: Parent widget (typically the main window).
            query_port: Typed application publication/render query port.
            publication_port: Typed application publication subscription port.
            action_port: Typed Evaluation command port.

        """
        self._evaluation_summary: _EvaluationSummary | None = None
        self._evaluation_error: str | None = None
        self._application_generation: int | None = None
        self._application_view_publication: ApplicationViewPublication | None = None
        self._last_application_revision = 0
        self._last_evaluation_publication_signature: (
            _EvaluationPublicationSignature | None
        ) = None
        self._evaluation_render: EvaluationRenderPublication | None = None
        self._model_summary_identity: EvaluationSummaryIdentity | None = None
        self._model_summary_text = ""
        self._model_summary_status: str | None = None
        self._model_summary_request_sequence = 0
        self._active_model_summary_request: _ModelSummaryRequest | None = None
        self._application_summary_dirty = True
        self._evaluation_render_worker: PythonThreadWorker | None = None
        self._evaluation_render_active_request: EvaluationRenderRequest | None = None
        self._evaluation_render_active_operation_id: str | None = None
        self._evaluation_render_pending_request: EvaluationRenderRequest | None = None
        self._evaluation_render_result_seen = False
        self._evaluation_render_shutdown_requested = False
        self._evaluation_render_cleaned_up = False
        self._info_in_chart_tabs = False

        super().__init__(parent=parent, controller=None)

        self._application_render_ledger = ApplicationPublicationRenderLedger(
            panel_name="Evaluation",
            render_publication=self._render_application_publication,
            commit_publication=self._record_application_revision,
            parent=self,
        )
        self._application_refresh_timer = self._application_render_ledger.timer
        runtime = application_ui_runtime(self)
        self._query_port = query_port if query_port is not None else runtime
        self._publication_port = (
            publication_port if publication_port is not None else runtime
        )
        self._action_port = action_port if action_port is not None else runtime
        self._subscribe_to_application_publications()
        self.init_ui()

    def _subscribe_to_application_publications(self) -> None:
        """Refresh state-changing content from the sole application truth."""
        publication_port = self._publication_port
        if publication_port is None:
            return
        self._create_bridge(
            cast(Observable, publication_port),
            APPLICATION_VIEW_PUBLICATION_CHANGED_EVENT,
            self._on_application_view_publication_changed,
        )

    def _on_application_view_publication_changed(
        self,
        publication: object,
    ) -> bool:
        """Render each valid application publication revision at most once."""
        if not self._valid_application_publication(publication):
            logger.error("Ignored malformed Evaluation application publication.")
            return False
        typed_publication = cast(ApplicationViewPublication, publication)
        if typed_publication.revision <= self._last_application_revision:
            return True
        self._application_view_publication = typed_publication
        signature = self._evaluation_publication_signature(typed_publication)
        if signature == self._last_evaluation_publication_signature:
            self._application_generation = typed_publication.generation
            self._evaluation_render = None
            return self._application_render_ledger.record_rendered(typed_publication)
        self.mark_refresh_dirty()
        return self._application_render_ledger.queue(typed_publication)

    def _render_application_publication(
        self,
        publication: ApplicationViewPublication,
    ) -> bool:
        self._application_view_publication = publication
        # A newer publication can be queued re-entrantly while the previous
        # render is still resolving its Evaluation query.  Re-check the
        # render projection here, after the previous revision has committed,
        # so equivalent PENDING -> RUNNING saliency publications do not
        # rebuild the complete Evaluation surface twice.
        if (
            self._evaluation_publication_signature(publication)
            == self._last_evaluation_publication_signature
        ):
            self._application_generation = publication.generation
            self._evaluation_render = None
            return True
        self.update_panel()
        return True

    def update_panel(self):
        """Refresh Evaluation and commit a direct render only after success."""
        self._update_panel_content()
        if self._application_render_ledger.render_in_progress:
            return
        publication = self._application_view_publication
        if publication is not None:
            self._application_render_ledger.record_rendered(publication)

    def _update_panel_content(self):
        """Update panel content when switched to."""
        if hasattr(self, "info_panel"):
            pass  # Handled by InfoPanelService

        previous_generation = self._application_generation
        previous_signature = self._last_evaluation_publication_signature
        previous_trainer_identity = (
            previous_signature.trainer_identity
            if previous_signature is not None
            else None
        )
        previous_plan_identity = (
            self.model_combo.currentData() if hasattr(self, "model_combo") else None
        )
        previous_cross_fold_plan_indexes = (
            previous_plan_identity.plan_indexes
            if isinstance(previous_plan_identity, _EvaluationCrossFoldGroup)
            else None
        )
        previous_run_identity = (
            self.run_combo.currentData() if hasattr(self, "run_combo") else None
        )
        previous_split = (
            self.split_combo.currentData() if hasattr(self, "split_combo") else None
        )
        if self._application_summary_dirty or (
            self._evaluation_summary is None and self._evaluation_error is None
        ):
            refreshed = self._refresh_application_query()
            self._application_summary_dirty = (
                not refreshed
                and self._evaluation_error
                == "Evaluation results are temporarily unavailable."
            )

        if self._application_query_blocks_display():
            self._show_no_data_available()
            return

        current_publication = self._application_view_publication
        current_trainer_identity = (
            current_publication.training_boundary.trainer_identity
            if current_publication is not None
            else None
        )
        preserve_cross_fold_selection = (
            previous_generation != self._application_generation
            and previous_cross_fold_plan_indexes is not None
            and isinstance(previous_run_identity, EvaluationCrossFoldIdentity)
            and previous_trainer_identity is not None
            and previous_trainer_identity == current_trainer_identity
        )
        if (
            previous_generation != self._application_generation
            and not preserve_cross_fold_selection
        ):
            previous_plan_identity = None
            previous_run_identity = None

        self.model_combo.blockSignals(True)
        self.model_combo.clear()

        plans = self._plans_from_application_query()
        if plans:
            self._show_evaluation_controls_available()
            for plan_choice in plans:
                if not any(run_choice.finished for run_choice in plan_choice.runs):
                    continue
                self.model_combo.addItem(
                    fold_display_label(
                        plan_choice.identity.plan_index,
                        plan_choice.name,
                    ),
                    plan_choice.identity,
                )
            for group in self._cross_fold_groups():
                self.model_combo.addItem(
                    group.display_name,
                    group,
                )

            if self.model_combo.count() > 0:
                selected_index = 0
                for i in range(self.model_combo.count()):
                    candidate_identity = self.model_combo.itemData(i)
                    if candidate_identity == previous_plan_identity or (
                        preserve_cross_fold_selection
                        and isinstance(candidate_identity, _EvaluationCrossFoldGroup)
                        and candidate_identity.plan_indexes
                        == previous_cross_fold_plan_indexes
                    ):
                        selected_index = i
                        break

                self.model_combo.setCurrentIndex(selected_index)
                self.on_model_changed(
                    selected_index,
                    preferred_run_identity=previous_run_identity,
                    preferred_split=previous_split,
                )
            else:
                self._show_no_data_available()
        else:
            self._show_no_data_available()

        self.model_combo.blockSignals(False)

    def mark_refresh_dirty(self) -> None:
        """Invalidate the cached ApplicationService evaluation summary."""
        self._application_summary_dirty = True
        self._evaluation_render = None
        self._evaluation_render_pending_request = None
        self._model_summary_identity = None
        self._model_summary_text = ""
        self._model_summary_status = None
        self._invalidate_model_summary_request()

    def _application_query_blocks_display(self) -> bool:
        """Return whether ApplicationService says evaluation is not displayable."""
        summary = self._evaluation_summary
        return self._evaluation_error is not None or (
            summary is not None and not summary.available
        )

    def _refresh_application_query(self) -> bool:
        """Refresh the serializable Evaluation catalog."""
        if (
            self._query_port is None
            or self._publication_port is None
            or self._action_port is None
        ):
            self._fail_closed_application_query()
            return False
        before_publication = self._read_application_publication()
        if before_publication is None or not before_publication.usable:
            self._fail_closed_application_query()
            return False
        result = execute_application_command(
            self,
            EvaluateCommand(),
            refresh=False,
            expected_publication_generation=before_publication.generation,
            runtime=cast(ApplicationUiRuntime, self._action_port),
        )
        if not isinstance(result, CommandResult):
            self._evaluation_summary = None
            self._evaluation_error = "No evaluation results available yet."
            return False
        accepted = self._accept_application_summary(result)
        after_publication = self._read_application_publication()
        catalog_generation = result.diagnostics.get("evaluation_publication_generation")
        if (
            after_publication is None
            or not after_publication.usable
            or after_publication.revision < before_publication.revision
            or (
                accepted
                and (
                    isinstance(catalog_generation, bool)
                    or not isinstance(catalog_generation, int)
                    or catalog_generation < 1
                    or after_publication.generation != catalog_generation
                )
            )
        ):
            self._fail_closed_application_query()
            return False
        self._application_view_publication = after_publication
        self._application_generation = after_publication.generation
        return accepted

    def _read_application_publication(
        self,
    ) -> ApplicationViewPublication | None:
        query_port = self._query_port
        if query_port is None:
            return None
        try:
            publication = get_application_view_publication(
                self,
                runtime=cast(ApplicationUiRuntime, query_port),
            )
        except Exception:
            logger.error(
                "Evaluation application publication query failed.",
                exc_info=True,
            )
            return None
        if not self._valid_application_publication(publication):
            return None
        return cast(ApplicationViewPublication, publication)

    @staticmethod
    def _valid_application_publication(publication: object) -> bool:
        if not isinstance(publication, ApplicationViewPublication):
            return False
        return (
            not isinstance(publication.revision, bool)
            and isinstance(publication.revision, int)
            and publication.revision >= 1
        )

    def _record_application_revision(
        self,
        publication: ApplicationViewPublication,
    ) -> None:
        self._last_application_revision = max(
            self._last_application_revision,
            publication.revision,
        )
        self._last_evaluation_publication_signature = (
            self._evaluation_publication_signature(publication)
        )

    @staticmethod
    def _evaluation_publication_signature(
        publication: ApplicationViewPublication,
    ) -> _EvaluationPublicationSignature:
        """Project one publication onto state that Evaluation actually renders."""
        training = publication.state.training
        boundary = publication.training_boundary
        saliency_phase = publication.state.visualization.post_training_saliency.phase
        saliency_is_mutating_evaluation = saliency_phase in {
            PostTrainingSaliencyPhase.PENDING,
            PostTrainingSaliencyPhase.RUNNING,
        }
        return _EvaluationPublicationSignature(
            usable=publication.usable,
            trainer_identity=boundary.trainer_identity,
            training_boundary_stable=boundary.stable,
            has_model=training.has_model,
            model_name=training.model_name,
            model_params=json.dumps(
                serialize_json_value(training.model_params),
                ensure_ascii=False,
                separators=(",", ":"),
                sort_keys=True,
            ),
            has_trainer=training.has_trainer,
            is_running=training.is_running,
            stable_catalog_generation=(
                boundary.token.generation
                if not training.is_running and not saliency_is_mutating_evaluation
                else None
            ),
            plan_count=training.plan_count,
            run_count=training.run_count,
            finished_run_count=training.finished_run_count,
            terminal_outcome=training.terminal_outcome,
            missing_requirements=tuple(training.missing_requirements),
            evaluation_state=publication.state.evaluation,
        )

    def _fail_closed_application_query(self) -> None:
        self._evaluation_summary = None
        self._evaluation_error = "Evaluation results are temporarily unavailable."
        self._application_generation = None

    def _refresh_application_query_async(
        self,
        *,
        summary_identity: EvaluationSummaryIdentity,
        on_ready=None,
    ) -> bool:
        """Load one model summary off the UI thread."""
        self._model_summary_request_sequence += 1
        request = _ModelSummaryRequest(
            sequence=self._model_summary_request_sequence,
            identity=summary_identity,
            publication_generation=self._application_generation,
        )
        self._active_model_summary_request = request

        def _handle_result(result) -> None:
            if self._active_model_summary_request != request:
                return
            if not isinstance(result, CommandResult):
                logger.error(
                    "Evaluation background query returned an invalid result: %s",
                    type(result).__name__,
                )
                self._active_model_summary_request = None
                self._show_async_query_failure()
                return
            if result.failed:
                logger.error(
                    "Evaluation background query failed: %s",
                    getattr(result, "error_message", None)
                    or getattr(result, "message", "")
                    or "No diagnostic message was provided.",
                )
                self._active_model_summary_request = None
                self._show_async_query_failure()
                return
            if not self._accept_model_summary(result, summary_identity):
                self._active_model_summary_request = None
                self._show_async_query_failure()
                return
            self._active_model_summary_request = None
            if callable(on_ready):
                on_ready()

        def _handle_error(error: tuple) -> None:
            if self._active_model_summary_request != request:
                return
            value = error[1] if len(error) > 1 else error
            formatted_traceback = error[2] if len(error) > 2 else ""
            logger.error(
                "Evaluation background query raised: %s\n%s",
                value,
                formatted_traceback,
            )
            self._active_model_summary_request = None
            self._show_async_query_failure()

        started = execute_application_command_async(
            self,
            EvaluateCommand(summary_identity=summary_identity),
            on_result=_handle_result,
            on_error=_handle_error,
            refresh=False,
            busy_target=self,
            expected_publication_generation=request.publication_generation,
            runtime=cast(ApplicationUiRuntime, self._action_port),
        )
        if not started and self._active_model_summary_request == request:
            self._active_model_summary_request = None
        return started

    def _invalidate_model_summary_request(self) -> None:
        """Make every already-dispatched model-summary callback stale."""
        self._active_model_summary_request = None

    def _show_async_query_failure(self) -> None:
        """Publish a stable terminal state without exposing backend diagnostics."""
        self.summary_text.setText(MODEL_SUMMARY_LOAD_FAILED_TEXT)

    def _plans_from_application_query(self):
        summary = self._evaluation_summary
        return summary.plans if summary is not None else ()

    def _accept_application_summary(self, result: CommandResult) -> bool:
        if result.failed:
            self._evaluation_summary = None
            self._evaluation_error = str(result.message).strip() or (
                "No evaluation results available yet."
            )
            self._application_generation = None
            return False
        diagnostics = result.diagnostics
        if (
            not isinstance(diagnostics, Mapping)
            or diagnostics.get("payload_type") != "evaluation_summary"
            or not isinstance(diagnostics.get("available"), bool)
        ):
            self._evaluation_summary = None
            self._evaluation_error = "Evaluation results are temporarily unavailable."
            self._application_generation = None
            return False
        try:
            plans = self._parse_plan_choices(diagnostics.get("plans"))
            cross_fold_choices = self._parse_cross_fold_choices(
                diagnostics.get("cross_fold_choices", []),
                plans=plans,
            )
        except (TypeError, ValueError):
            logger.error("Evaluation summary identities are invalid.", exc_info=True)
            self._evaluation_summary = None
            self._evaluation_error = "Evaluation results are temporarily unavailable."
            self._application_generation = None
            return False
        available = diagnostics["available"]
        if available and not plans:
            self._evaluation_summary = None
            self._evaluation_error = "Evaluation results are temporarily unavailable."
            self._application_generation = None
            return False
        self._evaluation_summary = _EvaluationSummary(
            available=available,
            plans=plans,
            cross_fold_choices=cross_fold_choices,
        )
        self._evaluation_error = None
        self._evaluation_render = None
        return True

    @staticmethod
    def _parse_plan_choices(value: object) -> tuple[_EvaluationPlanChoice, ...]:
        if not isinstance(value, list):
            raise TypeError("Evaluation plans must be a list")
        choices: list[_EvaluationPlanChoice] = []
        seen_plans: set[EvaluationPlanIdentity] = set()
        for expected_plan_index, raw_plan in enumerate(value):
            if not isinstance(raw_plan, Mapping):
                raise TypeError("Evaluation plan summary must be a mapping")
            raw_identity = raw_plan.get("identity")
            if not isinstance(raw_identity, Mapping):
                raise TypeError("Evaluation plan identity must be a mapping")
            plan_identity = EvaluationPlanIdentity(
                plan_index=raw_identity.get("plan_index"),
            )
            if (
                plan_identity.plan_index != expected_plan_index
                or plan_identity in seen_plans
            ):
                raise ValueError("Evaluation plan identity is not canonical")
            seen_plans.add(plan_identity)
            name = raw_plan.get("name")
            if not isinstance(name, str) or not name.strip():
                raise ValueError("Evaluation plan name is invalid")
            raw_runs = raw_plan.get("runs")
            if not isinstance(raw_runs, list):
                raise TypeError("Evaluation run summaries must be a list")
            runs: list[_EvaluationRunChoice] = []
            for expected_run_index, raw_run in enumerate(raw_runs):
                if not isinstance(raw_run, Mapping):
                    raise TypeError("Evaluation run summary must be a mapping")
                raw_run_identity = raw_run.get("identity")
                if not isinstance(raw_run_identity, Mapping):
                    raise TypeError("Evaluation run identity must be a mapping")
                run_identity = EvaluationRunIdentity(
                    plan=EvaluationPlanIdentity(
                        plan_index=raw_run_identity.get("plan_index"),
                    ),
                    run_index=raw_run_identity.get("run_index"),
                )
                if (
                    run_identity.plan != plan_identity
                    or run_identity.run_index != expected_run_index
                ):
                    raise ValueError("Evaluation run identity is not canonical")
                run_name = raw_run.get("name")
                finished = raw_run.get("finished")
                if not isinstance(run_name, str) or not run_name.strip():
                    raise ValueError("Evaluation run name is invalid")
                if not isinstance(finished, bool):
                    raise TypeError("Evaluation run completion must be boolean")
                raw_splits = raw_run.get("evaluation_splits")
                if raw_splits is None:
                    raw_splits = [raw_run.get("evaluation_split")]
                if not isinstance(raw_splits, list):
                    raise TypeError("Evaluation run splits must be a list")
                splits = tuple(
                    split
                    for split, _label in EVALUATION_SPLIT_OPTIONS
                    if split
                    in {
                        str(value).strip().casefold()
                        for value in raw_splits
                        if value is not None
                    }
                )
                runs.append(
                    _EvaluationRunChoice(
                        identity=run_identity,
                        name=run_name.strip(),
                        finished=finished,
                        splits=splits,
                    )
                )
            choices.append(
                _EvaluationPlanChoice(
                    identity=plan_identity,
                    name=name.strip(),
                    runs=tuple(runs),
                )
            )
        return tuple(choices)

    @staticmethod
    def _parse_cross_fold_choices(
        value: object,
        *,
        plans: tuple[_EvaluationPlanChoice, ...],
    ) -> tuple[_EvaluationCrossFoldChoice, ...]:
        if not isinstance(value, list):
            raise TypeError("Evaluation cross-fold choices must be a list")
        choices: list[_EvaluationCrossFoldChoice] = []
        seen_identities: set[EvaluationCrossFoldIdentity] = set()
        for raw_choice in value:
            if not isinstance(raw_choice, Mapping):
                raise TypeError("Evaluation cross-fold choice must be a mapping")
            raw_identity = raw_choice.get("identity")
            raw_members = (
                raw_identity.get("members")
                if isinstance(raw_identity, Mapping)
                else None
            )
            if not isinstance(raw_members, list):
                raise TypeError("Evaluation cross-fold members must be a list")
            members: list[EvaluationRunIdentity] = []
            for raw_member in raw_members:
                if not isinstance(raw_member, Mapping):
                    raise TypeError("Evaluation cross-fold member must be a mapping")
                member = EvaluationRunIdentity(
                    plan=EvaluationPlanIdentity(
                        plan_index=raw_member.get("plan_index"),
                    ),
                    run_index=raw_member.get("run_index"),
                )
                if member.plan.plan_index >= len(plans):
                    raise ValueError("Evaluation cross-fold member plan is unavailable")
                plan = plans[member.plan.plan_index]
                if member.run_index >= len(plan.runs):
                    raise ValueError("Evaluation cross-fold member run is unavailable")
                run = plan.runs[member.run_index]
                if run.identity != member or not run.finished:
                    raise ValueError("Evaluation cross-fold member is not complete")
                members.append(member)
            identity = EvaluationCrossFoldIdentity(members=tuple(members))
            if identity in seen_identities:
                raise ValueError("Evaluation cross-fold identity is duplicated")
            seen_identities.add(identity)
            display_name = raw_choice.get("display_name")
            run_label = raw_choice.get("run_label")
            raw_splits = raw_choice.get("evaluation_splits")
            fold_count = raw_choice.get("fold_count")
            sample_count = raw_choice.get("sample_count")
            if not isinstance(display_name, str) or not display_name.strip():
                raise ValueError("Evaluation cross-fold display name is invalid")
            if not isinstance(run_label, str) or not run_label.strip():
                raise ValueError("Evaluation cross-fold run label is invalid")
            if not isinstance(raw_splits, list):
                raise TypeError("Evaluation cross-fold splits must be a list")
            normalized_splits = {
                str(raw_split).strip().casefold() for raw_split in raw_splits
            }
            splits = tuple(
                split
                for split, _label in EVALUATION_SPLIT_OPTIONS
                if split in normalized_splits
            )
            if splits != ("test",):
                raise ValueError("Cross-fold summaries must be test-only")
            if (
                isinstance(fold_count, bool)
                or not isinstance(fold_count, int)
                or fold_count != len(identity.members)
            ):
                raise ValueError("Evaluation cross-fold count is invalid")
            if (
                isinstance(sample_count, bool)
                or not isinstance(sample_count, int)
                or sample_count < 1
            ):
                raise ValueError("Evaluation cross-fold sample count is invalid")
            choices.append(
                _EvaluationCrossFoldChoice(
                    identity=identity,
                    display_name=display_name.strip(),
                    run_label=run_label.strip(),
                    splits=splits,
                    fold_count=fold_count,
                    sample_count=sample_count,
                )
            )
        return tuple(choices)

    def _accept_model_summary(
        self,
        result: CommandResult,
        expected_identity: EvaluationSummaryIdentity,
    ) -> bool:
        diagnostics = result.diagnostics
        expected_generation = self._application_generation
        result_generation = diagnostics.get("evaluation_publication_generation")
        current_publication = self._read_application_publication()
        if (
            expected_generation is None
            or isinstance(result_generation, bool)
            or not isinstance(result_generation, int)
            or result_generation != expected_generation
            or current_publication is None
            or not current_publication.usable
            or current_publication.generation != expected_generation
        ):
            return False
        payload = (
            diagnostics.get("model_summary")
            if isinstance(diagnostics, Mapping)
            else None
        )
        if not isinstance(payload, Mapping):
            return False
        if payload.get("identity") != expected_identity.to_dict():
            return False
        text = payload.get("text")
        status = payload.get("status")
        if (
            status not in {"ready", "pending", "unavailable"}
            or not isinstance(text, str)
            or (status == "ready" and not text.strip())
            or (status != "ready" and bool(text))
        ):
            return False
        self._model_summary_identity = expected_identity
        self._model_summary_text = text
        self._model_summary_status = status
        return True

    def _show_no_data_available(self) -> None:
        message = self._evaluation_empty_state_message()
        self._invalidate_model_summary_request()
        self.model_combo.blockSignals(True)
        self.model_combo.clear()
        self.model_combo.setEnabled(False)
        self.model_combo.setToolTip(message)
        self.model_combo.blockSignals(False)
        self.run_combo.blockSignals(True)
        self.run_combo.clear()
        self.run_combo.setEnabled(False)
        self.run_combo.setToolTip(message)
        self.run_combo.blockSignals(False)
        self.split_combo.blockSignals(True)
        self.split_combo.clear()
        self.split_combo.setEnabled(False)
        self.split_combo.setToolTip(message)
        self.split_combo.blockSignals(False)
        self.chk_percentage.setEnabled(False)
        self._clear_metric_views()
        self.summary_text.clear()
        self.no_data_label.setText(message)
        self.plot_stack.setCurrentIndex(1)
        self.bottom_tabs.setVisible(False)

    def _show_evaluation_controls_available(self) -> None:
        self.model_combo.setEnabled(True)
        self.model_combo.setToolTip("")
        self.run_combo.setEnabled(True)
        self.run_combo.setToolTip("")
        self.split_combo.setEnabled(True)
        self.split_combo.setToolTip("")
        self.chk_percentage.setEnabled(True)
        self.bottom_tabs.setVisible(True)

    def _evaluation_empty_state_message(self) -> str:
        return self._evaluation_error or "No evaluation results available yet."

    def _clear_metric_views(self) -> None:
        self.matrix_widget.update_plot(None)
        self.bar_chart.update_plot({})
        self.metrics_table.update_data({})
        self.metrics_table.setProperty("evaluationOutputNumericSummary", None)

    def on_model_changed(
        self,
        index,
        preferred_run_identity=None,
        preferred_split=None,
    ):
        """Handle model selection change."""
        if index < 0:
            return

        plan_identity = self.model_combo.currentData()
        if isinstance(plan_identity, _EvaluationCrossFoldGroup):
            self.run_combo.blockSignals(True)
            self.run_combo.clear()
            for choice in plan_identity.choices:
                self.run_combo.addItem(choice.run_label, choice.identity)
            selected_index = 0
            for i in range(self.run_combo.count()):
                if self.run_combo.itemData(i) == preferred_run_identity:
                    selected_index = i
                    break
            if self.run_combo.count() > 0:
                self.run_combo.setCurrentIndex(selected_index)
            self.run_combo.blockSignals(False)
            self._sync_split_options(preferred_split=preferred_split)
            self.update_views()
            return
        if not isinstance(plan_identity, EvaluationPlanIdentity):
            return
        plan_choice = self._plan_choice(plan_identity)
        if plan_choice is None:
            self._show_no_data_available()
            return

        self.run_combo.blockSignals(True)
        self.run_combo.clear()

        for run_choice in plan_choice.runs:
            if not run_choice.finished:
                continue
            self.run_combo.addItem(
                run_display_label(run_choice.identity.run_index),
                run_choice.identity,
            )
        if any(run_choice.finished for run_choice in plan_choice.runs):
            self.run_combo.addItem(
                "Summary (Finished Runs)",
                plan_choice.identity,
            )

        if self.run_combo.count() > 0:
            selected_index = 0
            for i in range(self.run_combo.count()):
                if self.run_combo.itemData(i) == preferred_run_identity:
                    selected_index = i
                    break
            self.run_combo.setCurrentIndex(selected_index)

        self.run_combo.blockSignals(False)
        self._sync_split_options(preferred_split=preferred_split)
        self.update_views()

    def _on_run_changed(self, _index: int) -> None:
        preferred_split = self.split_combo.currentData()
        self._sync_split_options(preferred_split=preferred_split)
        self.update_views()

    def _available_splits_for_selection(
        self,
        selection: (
            EvaluationPlanIdentity | EvaluationRunIdentity | EvaluationCrossFoldIdentity
        ),
    ) -> tuple[str, ...]:
        if isinstance(selection, EvaluationRunIdentity):
            run = self._run_choice(selection)
            return run.splits if run is not None and run.finished else ()
        if isinstance(selection, EvaluationCrossFoldIdentity):
            choice = self._cross_fold_choice(selection)
            return choice.splits if choice is not None else ()
        plan = self._plan_choice(selection)
        if plan is None:
            return ()
        finished = [run for run in plan.runs if run.finished]
        if not finished:
            return ()
        common = set(finished[0].splits)
        for run in finished[1:]:
            common.intersection_update(run.splits)
        return tuple(
            split for split, _label in EVALUATION_SPLIT_OPTIONS if split in common
        )

    def _sync_split_options(self, *, preferred_split=None) -> None:
        selection = self.run_combo.currentData()
        splits = (
            self._available_splits_for_selection(selection)
            if isinstance(
                selection,
                (
                    EvaluationPlanIdentity,
                    EvaluationRunIdentity,
                    EvaluationCrossFoldIdentity,
                ),
            )
            else ()
        )
        self.split_combo.blockSignals(True)
        self.split_combo.clear()
        labels = dict(EVALUATION_SPLIT_OPTIONS)
        for split in splits:
            self.split_combo.addItem(labels[split], split)
        selected_split = (
            preferred_split
            if preferred_split in splits
            else "test"
            if "test" in splits
            else splits[0]
            if splits
            else None
        )
        if selected_split is not None:
            self.split_combo.setCurrentIndex(self.split_combo.findData(selected_split))
        self.split_combo.setEnabled(bool(splits))
        self.split_combo.setToolTip(
            "" if splits else "No saved predictions are available for this selection."
        )
        self.split_combo.blockSignals(False)

    def _plan_choice(
        self,
        identity: EvaluationPlanIdentity,
    ) -> _EvaluationPlanChoice | None:
        summary = self._evaluation_summary
        if summary is None:
            return None
        return next(
            (choice for choice in summary.plans if choice.identity == identity),
            None,
        )

    def _cross_fold_groups(self) -> tuple[_EvaluationCrossFoldGroup, ...]:
        summary = self._evaluation_summary
        if summary is None:
            return ()
        grouped: dict[tuple[int, ...], list[_EvaluationCrossFoldChoice]] = {}
        for choice in summary.cross_fold_choices:
            key = tuple(member.plan.plan_index for member in choice.identity.members)
            grouped.setdefault(key, []).append(choice)
        return tuple(
            _EvaluationCrossFoldGroup(
                display_name=choices[0].display_name,
                plan_indexes=plan_indexes,
                choices=tuple(choices),
            )
            for plan_indexes, choices in grouped.items()
        )

    def _cross_fold_choice(
        self,
        identity: EvaluationCrossFoldIdentity,
    ) -> _EvaluationCrossFoldChoice | None:
        summary = self._evaluation_summary
        if summary is None:
            return None
        return next(
            (
                choice
                for choice in summary.cross_fold_choices
                if choice.identity == identity
            ),
            None,
        )

    def _run_choice(
        self,
        identity: EvaluationRunIdentity,
    ) -> _EvaluationRunChoice | None:
        plan_choice = self._plan_choice(identity.plan)
        if plan_choice is None:
            return None
        return next(
            (choice for choice in plan_choice.runs if choice.identity == identity),
            None,
        )

    def update_views(self):
        """Update Matrix and Table based on current selection."""
        selection = self.run_combo.currentData()
        split = self.split_combo.currentData()
        if not isinstance(
            selection,
            (
                EvaluationPlanIdentity,
                EvaluationRunIdentity,
                EvaluationCrossFoldIdentity,
            ),
        ) or not isinstance(split, str):
            self._evaluation_render = None
            self._clear_metric_views()
            return

        summary_identity = self._summary_identity(selection)
        if isinstance(selection, EvaluationRunIdentity):
            run_choice = self._run_choice(selection)
            if run_choice is None or not run_choice.finished:
                self._evaluation_render = None
                self._clear_metric_views()
                self._update_summary_if_visible(summary_identity)
                return

        self._clear_metric_views()
        render = self._render_for_selection(selection, split=split)
        if render is None:
            self._evaluation_render = None
            self._clear_metric_views()
            self._update_summary_if_visible(summary_identity)
            return
        render_data = render.data
        if render_data.evaluation_split != split:
            self._show_evaluation_render_unavailable(
                "The selected split changed while Evaluation was updating."
            )
            return
        self.plot_stack.setCurrentIndex(0)
        self.bottom_tabs.setVisible(True)
        show_pct = self.chk_percentage.isChecked()
        self.matrix_widget.update_plot(render_data, show_percentage=show_pct)
        metrics = dict(render_data.metrics)
        class_names = dict(render_data.class_labels)
        self.metrics_table.update_data(metrics, class_names=class_names)
        self.metrics_table.setProperty(
            "classLabels",
            [str(value) for _, value in sorted(class_names.items())],
        )
        self.metrics_table.setProperty(
            "publicationGeneration",
            render.generation,
        )
        self.metrics_table.setProperty("operationId", render.operation_id or "")
        self.metrics_table.setProperty(
            "trainingGeneration",
            render.training_boundary.token.generation,
        )
        self.metrics_table.setProperty(
            "trainingBoundaryStable",
            render.training_boundary.stable,
        )
        self.metrics_table.setProperty(
            "splitSpecificationFingerprint",
            render.split_specification_fingerprint or "",
        )
        self.metrics_table.setProperty(
            "splitEpochRevision",
            render.split_epoch_revision or 0,
        )
        self.metrics_table.setProperty(
            "evaluationOutputNumericSummary",
            render_data.output_numeric_summary.to_dict(),
        )
        plan_indexes: list[int] = []
        run_indexes: list[int] = []
        selection_type = ""
        self.metrics_table.setProperty("fold", -1)
        self.metrics_table.setProperty("runId", "")
        if isinstance(selection, EvaluationRunIdentity):
            plan_index = selection.plan.plan_index
            run_index = selection.run_index
            plan_indexes = [plan_index]
            run_indexes = [run_index]
            self.metrics_table.setProperty("fold", plan_index)
            self.metrics_table.setProperty(
                "runId",
                f"plan-{plan_index}:run-{run_index}",
            )
            selection_type = "run"
        elif isinstance(selection, EvaluationPlanIdentity):
            plan_indexes = [selection.plan_index]
            selection_type = "plan"
        else:
            plan_indexes = [member.plan.plan_index for member in selection.members]
            run_indexes = [member.run_index for member in selection.members]
            selection_type = "cross_fold"
        self.metrics_table.setProperty("planIndexes", plan_indexes)
        self.metrics_table.setProperty("runIndexes", run_indexes)
        self.metrics_table.setProperty("selectionType", selection_type)
        self.metrics_table.setProperty("evaluationSplit", split)
        self.bar_chart.update_plot(metrics, class_names=class_names)
        self._update_summary_if_visible(render_data.summary_identity)

    def _render_for_selection(
        self,
        selection: (
            EvaluationPlanIdentity | EvaluationRunIdentity | EvaluationCrossFoldIdentity
        ),
        *,
        split: str,
    ) -> EvaluationRenderPublication | None:
        request = self._build_evaluation_render_request(selection, split=split)
        if request is None:
            return None
        cached = self._evaluation_render
        if cached is not None and self._same_evaluation_render_target(
            cached.request,
            request,
        ):
            return cached
        if self._request_evaluation_render(request):
            self._show_evaluation_render_loading()
        else:
            self._show_evaluation_render_unavailable(
                "The Evaluation result could not start in the background. "
                "Refresh Evaluation and try again."
            )
        return None

    def _request_evaluation_render(self, request: EvaluationRenderRequest) -> bool:
        """Serialize expensive cross-fold publication reads outside the GUI thread."""
        if self._evaluation_render_shutdown_requested:
            return False
        if self._evaluation_render_worker is not None:
            if self._same_evaluation_render_target(
                request,
                self._evaluation_render_active_request,
            ):
                self._evaluation_render_pending_request = (
                    request if self._evaluation_render_result_seen else None
                )
            else:
                self._evaluation_render_pending_request = request
            return True
        runtime = self._query_port
        if runtime is None:
            return False
        operation = begin_evaluation_render_operation(
            self,
            request,
            runtime=cast(ApplicationUiRuntime, runtime),
        )
        if operation is None:
            return False
        operation_id = operation.operation_id
        worker = PythonThreadWorker(
            self._load_evaluation_render,
            runtime,
            operation_id,
            request,
            name=f"xbrainlab-evaluation-render-{operation_id[:8]}",
        )
        worker.signals.result.connect(
            lambda result, owned=worker, oid=operation_id: (
                self._on_evaluation_render_ready(owned, oid, result)
            )
        )
        worker.signals.error.connect(
            lambda error, owned=worker, oid=operation_id: (
                self._on_evaluation_render_error(owned, oid, error)
            )
        )
        worker.signals.finished.connect(
            lambda owned=worker, oid=operation_id: (
                self._on_evaluation_render_finished(owned, oid)
            )
        )
        self._evaluation_render_worker = worker
        self._evaluation_render_active_request = request
        self._evaluation_render_active_operation_id = operation_id
        self._evaluation_render_pending_request = None
        self._evaluation_render_result_seen = False
        try:
            worker.start()
        except Exception:
            fail_application_operation(
                self,
                operation_id,
                message="The Evaluation worker could not be scheduled.",
                runtime=cast(ApplicationUiRuntime, runtime),
            )
            self._evaluation_render_worker = None
            self._evaluation_render_active_request = None
            self._evaluation_render_active_operation_id = None
            logger.error(
                "Evaluation render publication worker could not start.",
                exc_info=True,
            )
            return False
        return True

    @staticmethod
    def _load_evaluation_render(
        runtime,
        operation_id: str,
        request: EvaluationRenderRequest,
    ) -> tuple[EvaluationRenderRequest, object]:
        publication = run_evaluation_render_operation(
            None,
            operation_id,
            request,
            runtime=runtime,
        )
        if publication is None:
            raise RuntimeError("Evaluation render publication is unavailable")
        return request, publication

    def _on_evaluation_render_ready(
        self,
        worker: PythonThreadWorker | object,
        operation_id: str | None = None,
        result: object | None = None,
    ) -> None:
        if result is None and operation_id is None:
            result = worker
            worker = self._evaluation_render_worker
            operation_id = self._evaluation_render_active_operation_id
        if (
            worker is not self._evaluation_render_worker
            or operation_id != self._evaluation_render_active_operation_id
        ):
            return
        request = self._evaluation_render_active_request
        if self._evaluation_render_shutdown_requested or request is None:
            return
        self._evaluation_render_result_seen = True
        if (
            not isinstance(result, tuple)
            or len(result) != 2
            or result[0] != request
            or getattr(result[1], "request", None) != request
        ):
            if self._same_evaluation_render_target(
                request,
                self._current_evaluation_render_request(),
            ):
                self._show_evaluation_render_unavailable(
                    "The Evaluation result could not be loaded. "
                    "Refresh Evaluation and try again."
                )
            return
        if not self._same_evaluation_render_target(
            request,
            self._current_evaluation_render_request(),
        ):
            return
        self._evaluation_render = cast(EvaluationRenderPublication, result[1])
        self.update_views()

    def _on_evaluation_render_error(
        self,
        worker: PythonThreadWorker | tuple | None,
        operation_id: str | None = None,
        error: tuple | None = None,
    ) -> None:
        if error is None and operation_id is None and isinstance(worker, tuple):
            error = worker
            worker = self._evaluation_render_worker
            operation_id = self._evaluation_render_active_operation_id
        if (
            worker is not self._evaluation_render_worker
            or operation_id != self._evaluation_render_active_operation_id
        ):
            return
        if error is None:
            return
        request = self._evaluation_render_active_request
        if self._evaluation_render_shutdown_requested or request is None:
            return
        self._evaluation_render_result_seen = True
        value: object = (
            error[1]
            if len(error) > 1
            else RuntimeError("Evaluation render worker returned an invalid error")
        )
        if isinstance(value, OwnedOperationCancelledError):
            return
        if not self._same_evaluation_render_target(
            request,
            self._current_evaluation_render_request(),
        ):
            return
        if isinstance(value, ApplicationError):
            application_error = cast(ApplicationError, value)
            diagnostics = application_error.diagnostics
            if (
                diagnostics.get("evaluation_final_unavailable") is True
                or diagnostics.get("evaluation_split_unavailable") is True
            ):
                self._show_evaluation_render_unavailable(str(value))
                return
            if (
                diagnostics.get("evaluation_render_stale") is True
                and diagnostics.get("retryable") is True
            ):
                self.mark_refresh_dirty()
                self._show_evaluation_render_unavailable(str(value))
                return
        logger.error("Evaluation render publication failed: %s", value)
        self.mark_refresh_dirty()
        self._show_evaluation_render_unavailable(
            "The Evaluation result could not be loaded. "
            "Refresh Evaluation and try again."
        )

    def _on_evaluation_render_finished(
        self,
        worker: PythonThreadWorker | None = None,
        operation_id: str | None = None,
    ) -> None:
        worker = worker or self._evaluation_render_worker
        operation_id = operation_id or self._evaluation_render_active_operation_id
        if (
            worker is not self._evaluation_render_worker
            or operation_id != self._evaluation_render_active_operation_id
        ):
            return
        self._evaluation_render_worker = None
        self._evaluation_render_active_request = None
        self._evaluation_render_active_operation_id = None
        self._evaluation_render_result_seen = False
        pending = self._evaluation_render_pending_request
        self._evaluation_render_pending_request = None
        if (
            not self._evaluation_render_shutdown_requested
            and pending is not None
            and self._same_evaluation_render_target(
                pending,
                self._current_evaluation_render_request(),
            )
        ):
            self._request_evaluation_render(pending)

    def _current_evaluation_render_request(self) -> EvaluationRenderRequest | None:
        try:
            selection = self.run_combo.currentData()
            split = self.split_combo.currentData()
        except RuntimeError:
            # A terminal worker callback can arrive after Qt has deleted the
            # panel during close; it is no longer eligible to publish.
            return None
        if not isinstance(
            selection,
            (
                EvaluationPlanIdentity,
                EvaluationRunIdentity,
                EvaluationCrossFoldIdentity,
            ),
        ) or not isinstance(split, str):
            return None
        return self._build_evaluation_render_request(selection, split=split)

    def _build_evaluation_render_request(
        self,
        selection: (
            EvaluationPlanIdentity | EvaluationRunIdentity | EvaluationCrossFoldIdentity
        ),
        *,
        split: str,
    ) -> EvaluationRenderRequest | None:
        generation = self._application_generation
        publication = self._application_view_publication
        if generation is None or publication is None or not publication.usable:
            return None
        trainer_identity = publication.training_boundary.trainer_identity
        dataset = publication.state.dataset
        fingerprint = dataset.split_specification_fingerprint
        revision = dataset.split_epoch_revision
        if trainer_identity is None or fingerprint is None or revision is None:
            return None
        return EvaluationRenderRequest(
            publication_generation=generation,
            selection=selection,
            trainer_identity=trainer_identity,
            split_specification_fingerprint=fingerprint,
            split_epoch_revision=revision,
            split=split,
        )

    @staticmethod
    def _same_evaluation_render_target(
        left: EvaluationRenderRequest | None,
        right: EvaluationRenderRequest | None,
    ) -> bool:
        """Compare render freshness by its selected semantic origin."""
        return (
            left is not None
            and right is not None
            and (
                left.selection == right.selection
                and left.split == right.split
                and left.trainer_identity == right.trainer_identity
                and left.split_specification_fingerprint
                == right.split_specification_fingerprint
                and left.split_epoch_revision == right.split_epoch_revision
            )
        )

    def _show_evaluation_render_unavailable(self, message: str) -> None:
        """Show one stable, user-facing reason for inadmissible final metrics."""
        self._evaluation_render = None
        self._clear_metric_views()
        self.no_data_label.setText(message)
        self.plot_stack.setCurrentIndex(1)
        self.bottom_tabs.setVisible(False)

    def _show_evaluation_render_loading(self) -> None:
        """Replace prior metrics while one All Folds publication is prepared."""
        self._evaluation_render = None
        self._clear_metric_views()
        self.no_data_label.setText("Preparing the Evaluation result...")
        self.plot_stack.setCurrentIndex(1)
        self.bottom_tabs.setVisible(True)

    def _on_percentage_toggled(self, _checked: bool) -> None:
        """Redraw only the matrix; summary metrics remain raw values."""
        render = self._evaluation_render
        if render is None:
            return
        self.matrix_widget.update_plot(
            render.data,
            show_percentage=self.chk_percentage.isChecked(),
        )

    def cleanup(self) -> None:
        """Cancel queued renders and release the publication subscription."""
        self._evaluation_render_cleaned_up = True
        self.begin_evaluation_render_shutdown()
        self._invalidate_model_summary_request()
        self._application_render_ledger.cleanup()
        if hasattr(self, "matrix_widget"):
            self.matrix_widget.cleanup()
        if hasattr(self, "bar_chart"):
            self.bar_chart.cleanup()
        super().cleanup()

    def begin_evaluation_render_shutdown(self) -> None:
        """Reject new renders and request cancellation without blocking Qt."""
        self._evaluation_render_shutdown_requested = True
        self._evaluation_render_pending_request = None
        self.cancel_evaluation_render()

    def cancel_evaluation_render_shutdown(self) -> None:
        """Resume Evaluation after a desktop close attempt was cancelled."""
        if self._evaluation_render_cleaned_up:
            return
        was_shutdown = self._evaluation_render_shutdown_requested
        self._evaluation_render_shutdown_requested = False
        if not was_shutdown:
            return
        request = self._current_evaluation_render_request()
        if request is None:
            return
        if self._evaluation_render_worker is not None:
            self._evaluation_render_pending_request = request
            return
        QTimer.singleShot(0, self.update_views)

    def cancel_evaluation_render(self) -> bool:
        """Request active Evaluation cancellation without the command lock."""
        operation_id = self._evaluation_render_active_operation_id
        if operation_id is None:
            return False
        return cancel_application_operation(
            self,
            operation_id,
            runtime=cast(ApplicationUiRuntime, self._query_port),
        )

    def evaluation_background_work_snapshot(self) -> dict[str, int | bool | str]:
        """Expose exact, non-blocking worker ownership for close diagnostics."""
        worker = self._evaluation_render_worker
        alive = bool(worker is not None and worker.is_alive())
        return {
            "idle": worker is None,
            "remaining_workers": int(worker is not None),
            "alive_workers": int(alive),
            "operation_id": self._evaluation_render_active_operation_id or "",
        }

    def evaluation_background_work_idle(self) -> bool:
        """Return true only after the worker's terminal Qt callback releases it."""
        return self._evaluation_render_worker is None

    def wait_for_evaluation_background_work(self, timeout: float = 0.0) -> bool:
        """Boundedly join the Python-owned worker outside normal GUI cleanup."""
        worker = self._evaluation_render_worker
        if worker is None:
            return True
        worker.join(timeout=max(0.0, float(timeout)))
        return not worker.is_alive()

    def closeEvent(self, event):  # noqa: N802
        """Release the application publication subscription on panel close."""
        self.cleanup()
        super().closeEvent(event)

    @staticmethod
    def _summary_identity(
        selection: (
            EvaluationPlanIdentity | EvaluationRunIdentity | EvaluationCrossFoldIdentity
        ),
    ) -> EvaluationSummaryIdentity | None:
        if isinstance(selection, EvaluationRunIdentity):
            return EvaluationSummaryIdentity(
                plan=selection.plan,
                run=selection,
            )
        if isinstance(selection, EvaluationPlanIdentity):
            return EvaluationSummaryIdentity(plan=selection)
        return None

    def update_model_summary(
        self,
        summary_identity: EvaluationSummaryIdentity,
    ) -> None:
        """Load and display one identity-bound model summary."""
        if not isinstance(summary_identity, EvaluationSummaryIdentity):
            self._invalidate_model_summary_request()
            self.summary_text.setText(MODEL_SUMMARY_UNAVAILABLE_TEXT)
            return
        if self._model_summary_identity == summary_identity:
            self._invalidate_model_summary_request()
            if self._model_summary_status == "ready":
                self.summary_text.setText(self._model_summary_text)
            elif self._model_summary_status == "pending":
                self.summary_text.setText(MODEL_SUMMARY_PENDING_TEXT)
            else:
                self.summary_text.setText(MODEL_SUMMARY_UNAVAILABLE_TEXT)
            return
        self.summary_text.setText("Loading model details...")
        if self._refresh_application_query_async(
            summary_identity=summary_identity,
            on_ready=lambda: self.update_model_summary(summary_identity),
        ):
            return
        self.summary_text.setText(MODEL_SUMMARY_BACKGROUND_UNAVAILABLE_TEXT)

    def _update_summary_if_visible(
        self,
        summary_identity: EvaluationSummaryIdentity | None,
    ) -> None:
        if summary_identity is None:
            self._invalidate_model_summary_request()
            self.summary_text.setText(MODEL_SUMMARY_CROSS_FOLD_TEXT)
            return
        if not self._summary_tab_visible():
            self._invalidate_model_summary_request()
            self.summary_text.setText(MODEL_SUMMARY_DEFERRED_TEXT)
            return
        self.update_model_summary(summary_identity)

    def _summary_tab_visible(self) -> bool:
        bottom_visible = (
            hasattr(self, "bottom_tabs")
            and hasattr(self, "summary_tab")
            and self.bottom_tabs.currentWidget() is self.summary_tab
        )
        compact_visible = (
            getattr(self, "_details_in_chart_tabs", False)
            and self.chart_tabs.currentWidget() is self.summary_tab
        )
        return bottom_visible or compact_visible

    def _on_bottom_tab_changed(self, _index: int) -> None:
        if not self._summary_tab_visible():
            return
        selection = self.run_combo.currentData()
        if isinstance(selection, EvaluationCrossFoldIdentity):
            self._invalidate_model_summary_request()
            self.summary_text.setText(MODEL_SUMMARY_CROSS_FOLD_TEXT)
            return
        if not isinstance(
            selection,
            (
                EvaluationPlanIdentity,
                EvaluationRunIdentity,
                EvaluationCrossFoldIdentity,
            ),
        ):
            self._invalidate_model_summary_request()
            self.summary_text.clear()
            return
        self.update_model_summary(self._summary_identity(selection))

    def _on_chart_tab_changed(self, _index: int) -> None:
        """Load deferred model details when compact mode owns the summary tab."""
        if (
            self._details_in_chart_tabs
            and self.chart_tabs.currentWidget() is self.summary_tab
        ):
            self._on_bottom_tab_changed(-1)

    def update_info(self):
        """Update the aggregate info panel."""
        # Handled by InfoPanelService

    def init_ui(self):
        """Build the evaluation panel layout with plots, toolbar, tabs, and sidebar."""
        self.setObjectName("EvaluationPanel")
        self.setStyleSheet(
            f"""
            QWidget#EvaluationPanel,
            QWidget#EvaluationLeft,
            QWidget#EvaluationControlsBar {{
                background-color: {Theme.BACKGROUND_DARK};
                color: {Theme.TEXT_SECONDARY};
            }}
            QGroupBox#EvaluationPlotsGroup {{
                background-color: {Theme.BACKGROUND_DARK};
                border: 1px solid {Theme.BACKGROUND_LIGHT};
                border-radius: 4px;
                margin-top: 18px;
                color: {Theme.TEXT_SECONDARY};
                font-weight: bold;
            }}
            QGroupBox#EvaluationPlotsGroup::title {{
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 4px;
                color: {Theme.TEXT_SECONDARY};
            }}
            QLabel {{
                background-color: transparent;
                color: {Theme.TEXT_SECONDARY};
            }}
            QTabWidget::pane {{
                border: 1px solid {Theme.BACKGROUND_LIGHT};
                background-color: {Theme.BACKGROUND_DARK};
            }}
            QTabBar::tab {{
                background-color: {Theme.BACKGROUND_MID};
                color: {Theme.TEXT_MUTED};
                border: 1px solid {Theme.BACKGROUND_LIGHT};
                padding: 6px 12px;
            }}
            QTabBar::tab:selected {{
                background-color: {Theme.BACKGROUND_DARK};
                color: {Theme.TEXT_PRIMARY};
            }}
            """
        )
        main_layout = QHBoxLayout(self)
        # Native minimum hints must not prevent the tabbed compact mode.
        main_layout.setSizeConstraint(QLayout.SizeConstraint.SetNoConstraint)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # --- Left Side: Main Content ---
        left_widget = QWidget()
        left_widget.setObjectName("EvaluationLeft")
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(20, 20, 20, 20)
        left_layout.setSpacing(20)
        self.left_widget = left_widget
        self.left_layout = left_layout

        # 1. Plots Group (Top)
        plots_group = QGroupBox("EVALUATION PLOTS")
        plots_group.setObjectName("EvaluationPlotsGroup")
        self.plots_group = plots_group
        plots_layout = QVBoxLayout(plots_group)
        plots_layout.setContentsMargins(10, 20, 10, 10)
        self.plots_layout = plots_layout

        # Stacked Widget for Data vs No Data
        self.plot_stack = QStackedWidget()
        self.plot_stack.setStyleSheet(f"background-color: {Theme.BACKGROUND_DARK};")

        # Page 0: Charts View
        self.charts_container = QWidget()
        self.charts_container.setStyleSheet(
            f"background-color: {Theme.BACKGROUND_DARK};"
        )
        charts_layout = QHBoxLayout(self.charts_container)
        charts_layout.setContentsMargins(0, 0, 0, 0)
        charts_layout.setSpacing(6)
        self.charts_layout = charts_layout
        self._charts_are_tabbed = False
        self._details_in_chart_tabs = False

        # Matrix Widget
        self.matrix_widget = ConfusionMatrixWidget(self)
        charts_layout.addWidget(self.matrix_widget, stretch=1)

        # Bar Chart Widget
        self.bar_chart = MetricsBarChartWidget(self)
        charts_layout.addWidget(self.bar_chart, stretch=1)

        self.chart_tabs = QTabWidget(self.charts_container)
        self.chart_tabs.setObjectName("EvaluationChartTabs")
        self.chart_tabs.setDocumentMode(True)
        chart_tab_bar = self.chart_tabs.tabBar()
        if chart_tab_bar is not None:
            chart_tab_bar.setDrawBase(False)
        self.chart_tabs.currentChanged.connect(self._on_chart_tab_changed)
        self.chart_tabs.hide()

        self.plot_stack.addWidget(self.charts_container)

        # Page 1: No Data View
        self.no_data_label = QLabel("No Data Available")
        self.no_data_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.no_data_label.setStyleSheet(f"color: {Theme.TEXT_MUTED}; font-size: 11pt;")
        self.plot_stack.addWidget(self.no_data_label)

        # Model Selection
        self.model_combo = ElidingComboBox()
        self.model_combo.setMinimumWidth(110)
        self.model_combo.setMaximumWidth(240)
        self.model_combo.setMinimumContentsLength(20)
        self.model_combo.setSizeAdjustPolicy(
            QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon,
        )
        self.model_combo.setSizePolicy(
            QSizePolicy.Policy.Preferred,
            QSizePolicy.Policy.Fixed,
        )
        self.model_combo.setStyleSheet(
            f"{Stylesheets.COMBO_BOX}\nQComboBox {{ min-width: 100px; }}"
        )
        model_view = self.model_combo.view()
        if model_view is not None:
            model_view.setTextElideMode(Qt.TextElideMode.ElideRight)
        self.model_combo.currentIndexChanged.connect(self.on_model_changed)

        # Run Selection
        self.run_combo = ElidingComboBox()
        self.run_combo.setMinimumWidth(140)
        self.run_combo.setMaximumWidth(240)
        self.run_combo.setMinimumContentsLength(18)
        self.run_combo.setSizeAdjustPolicy(
            QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon,
        )
        self.run_combo.setSizePolicy(
            QSizePolicy.Policy.Preferred,
            QSizePolicy.Policy.Fixed,
        )
        self.run_combo.setStyleSheet(
            f"{Stylesheets.COMBO_BOX}\nQComboBox {{ min-width: 100px; }}"
        )
        run_view = self.run_combo.view()
        if run_view is not None:
            run_view.setTextElideMode(Qt.TextElideMode.ElideRight)
        self.run_combo.currentIndexChanged.connect(self._on_run_changed)

        # Prediction split selection
        self.split_combo = ElidingComboBox()
        self.split_combo.setMinimumWidth(80)
        self.split_combo.setMaximumWidth(130)
        self.split_combo.setSizePolicy(
            QSizePolicy.Policy.Preferred,
            QSizePolicy.Policy.Fixed,
        )
        self.split_combo.setStyleSheet(
            f"{Stylesheets.COMBO_BOX}\nQComboBox {{ min-width: 70px; }}"
        )
        self.split_combo.currentIndexChanged.connect(self.update_views)

        # Options
        self.chk_percentage = QCheckBox("Show percentages")
        self.chk_percentage.setStyleSheet(Stylesheets.CHECKBOX_MUTED)
        self.chk_percentage.setSizePolicy(
            QSizePolicy.Policy.Fixed,
            QSizePolicy.Policy.Fixed,
        )
        self.chk_percentage.setMinimumWidth(self.chk_percentage.sizeHint().width())
        self.chk_percentage.setToolTip(
            "Normalize each true-label row to 100%. Other evaluation metrics "
            "are unchanged."
        )
        self.chk_percentage.toggled.connect(self._on_percentage_toggled)

        self.evaluation_controls_bar = ResponsiveControlsBar(
            [
                ("Fold", self.model_combo),
                ("Run", self.run_combo),
                ("Split", self.split_combo),
            ],
            [self.chk_percentage],
            wrap_width=760,
            greedy_wrap=True,
        )
        self.evaluation_controls_bar.setObjectName("EvaluationControlsBar")
        plots_layout.addWidget(self.evaluation_controls_bar)
        plots_layout.addWidget(self.plot_stack, stretch=1)

        # 2. Bottom Section (Tabs: Metrics & Model Summary)
        self.bottom_tabs = QTabWidget()
        bottom_tab_bar = self.bottom_tabs.tabBar()
        if bottom_tab_bar is not None:
            bottom_tab_bar.setDrawBase(False)

        # Tab 1: Metrics
        self.metrics_tab = QWidget()
        metrics_layout = QVBoxLayout(self.metrics_tab)
        metrics_layout.setContentsMargins(10, 10, 10, 10)
        self.metrics_table = MetricsTableWidget(self)
        metrics_layout.addWidget(self.metrics_table)
        self.bottom_tabs.addTab(self.metrics_tab, "Metrics Summary")

        # Tab 2: Model Summary
        self.summary_tab = QWidget()
        summary_layout = QVBoxLayout(self.summary_tab)
        summary_layout.setContentsMargins(10, 10, 10, 10)
        self.summary_text = QTextEdit()
        self.summary_text.setReadOnly(True)
        self.summary_text.setFontFamily("Courier New")
        self.summary_text.setStyleSheet(Stylesheets.LOG_TEXT)
        summary_layout.addWidget(self.summary_text)
        self.bottom_tabs.addTab(self.summary_tab, "Model Summary")
        self.bottom_tabs.currentChanged.connect(self._on_bottom_tab_changed)

        # Add to left layout directly
        left_layout.addWidget(plots_group, stretch=2)
        left_layout.addWidget(self.bottom_tabs, stretch=1)

        # --- Right Side: Sidebar ---
        self.right_panel = QWidget()
        self.right_panel.setFixedWidth(INFO_SIDEBAR_WIDTH)
        self.right_panel.setObjectName("RightPanel")
        self.right_panel.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.right_panel.setStyleSheet(Stylesheets.SIDEBAR_CONTAINER)

        self.right_layout = QVBoxLayout(self.right_panel)
        self.right_layout.setContentsMargins(10, 20, 10, 20)

        # Aggregate Info
        self.info_panel = AggregateInfoPanel(self.main_window)
        self.info_panel.setStyleSheet(Stylesheets.GROUP_BOX_MINIMAL)
        self.right_layout.addWidget(self.info_panel)

        self.right_layout.addStretch()

        # Add to main layout
        main_layout.addWidget(left_widget, stretch=1)
        main_layout.addWidget(self.right_panel, stretch=0)
        QTimer.singleShot(0, self._update_responsive_layout)

    def resizeEvent(self, event):  # noqa: N802
        """Use one full-width chart at a time when the content area narrows."""
        super().resizeEvent(event)
        if hasattr(self, "charts_container"):
            QTimer.singleShot(0, self._update_responsive_layout)

    def showEvent(self, event) -> None:  # noqa: N802
        """Apply responsive mode after the platform style is polished."""
        super().showEvent(event)
        self._update_responsive_layout()

    def _update_responsive_layout(self) -> None:
        compact_summary = self.contentsRect().width() < COMPACT_INFO_SIDEBAR_BREAKPOINT
        if compact_summary:
            self.right_panel.hide()
        else:
            self._restore_info_sidebar()
        layout = self.layout()
        if layout is not None:
            layout.activate()
        self._update_percentage_label()
        self.evaluation_controls_bar.refresh_layout()
        self._update_chart_layout()
        self._update_height_layout()
        if compact_summary:
            self._move_info_into_chart_tabs()

    def _update_percentage_label(self) -> None:
        """Use the documented compact label only at constrained widths."""
        if not hasattr(self, "evaluation_controls_bar"):
            return
        text = (
            "Show %"
            if self.evaluation_controls_bar.width() < 680
            else "Show percentages"
        )
        if self.chk_percentage.text() == text:
            return
        self.chk_percentage.setText(text)
        self.chk_percentage.setMinimumWidth(self.chk_percentage.sizeHint().width())

    def _move_info_into_chart_tabs(self) -> None:
        """Keep plots usable when the assistant leaves an extremely narrow page."""
        if self._info_in_chart_tabs:
            return
        self.right_layout.removeWidget(self.info_panel)
        self.chart_tabs.addTab(self.info_panel, "Data")
        self._info_in_chart_tabs = True

    def _restore_info_sidebar(self) -> None:
        """Return Data Summary to its accepted fixed sidebar at normal widths."""
        if self._info_in_chart_tabs:
            index = self.chart_tabs.indexOf(self.info_panel)
            if index >= 0:
                self.chart_tabs.removeTab(index)
            self.info_panel.setParent(self.right_panel)
            self.right_layout.insertWidget(0, self.info_panel)
            self.info_panel.show()
            self._info_in_chart_tabs = False
        self.right_panel.setFixedWidth(INFO_SIDEBAR_WIDTH)
        self.right_panel.show()

    def _update_height_layout(self) -> None:
        """Show one result surface at a time in the shortest supported window."""
        if not hasattr(self, "plots_group"):
            return
        compact_height = (
            self.contentsRect().height() < COMPACT_HEIGHT_BREAKPOINT
            and self._charts_are_tabbed
        )
        compact_margins = self._charts_are_tabbed or compact_height
        if compact_margins:
            self.left_layout.setContentsMargins(12, 12, 12, 12)
            self.left_layout.setSpacing(0 if compact_height else 12)
            self.plots_layout.setContentsMargins(6, 20, 6, 10)
        else:
            self.left_layout.setContentsMargins(20, 20, 20, 20)
            self.left_layout.setSpacing(20)
            self.plots_layout.setContentsMargins(10, 20, 10, 10)
        if compact_height:
            self._move_details_into_chart_tabs()
        else:
            self._restore_detail_tabs()

    def _move_details_into_chart_tabs(self) -> None:
        if self._details_in_chart_tabs:
            return
        for page in (self.metrics_tab, self.summary_tab):
            index = self.bottom_tabs.indexOf(page)
            if index >= 0:
                self.bottom_tabs.removeTab(index)
        if self.chart_tabs.count() >= 2:
            self.chart_tabs.setTabText(0, "Matrix")
            self.chart_tabs.setTabText(1, "Class")
        tab_bar = self.chart_tabs.tabBar()
        if tab_bar is not None:
            tab_bar.setStyleSheet("QTabBar::tab { padding: 4px 3px; min-width: 0; }")
        self.chart_tabs.addTab(self.metrics_tab, "Metrics")
        self.chart_tabs.addTab(self.summary_tab, "Model")
        self.bottom_tabs.hide()
        self._details_in_chart_tabs = True

    def _restore_detail_tabs(self) -> None:
        if not self._details_in_chart_tabs:
            return
        for page in (self.metrics_tab, self.summary_tab):
            index = self.chart_tabs.indexOf(page)
            if index >= 0:
                self.chart_tabs.removeTab(index)
        if self.chart_tabs.count() >= 2:
            self.chart_tabs.setTabText(0, "Confusion Matrix")
            self.chart_tabs.setTabText(1, "Per-Class Metrics")
        tab_bar = self.chart_tabs.tabBar()
        if tab_bar is not None:
            tab_bar.setStyleSheet("")
        self.bottom_tabs.addTab(self.metrics_tab, "Metrics Summary")
        self.bottom_tabs.addTab(self.summary_tab, "Model Summary")
        self.bottom_tabs.setVisible(self.plot_stack.currentIndex() == 0)
        self._details_in_chart_tabs = False

    def _update_chart_layout(self) -> None:
        if not hasattr(self, "chart_tabs"):
            return
        use_tabs = self.charts_container.contentsRect().width() < CHART_TABS_BREAKPOINT
        if use_tabs == self._charts_are_tabbed:
            return

        if use_tabs:
            self.charts_layout.removeWidget(self.matrix_widget)
            self.charts_layout.removeWidget(self.bar_chart)
            self.chart_tabs.addTab(self.matrix_widget, "Confusion Matrix")
            self.chart_tabs.addTab(self.bar_chart, "Per-Class Metrics")
            self.charts_layout.addWidget(self.chart_tabs, stretch=1)
            self.chart_tabs.show()
        else:
            self._restore_detail_tabs()
            self.charts_layout.removeWidget(self.chart_tabs)
            while self.chart_tabs.count():
                self.chart_tabs.removeTab(0)
            self.chart_tabs.hide()
            self.matrix_widget.setParent(self.charts_container)
            self.bar_chart.setParent(self.charts_container)
            self.charts_layout.addWidget(self.matrix_widget, stretch=1)
            self.charts_layout.addWidget(self.bar_chart, stretch=1)
            self.matrix_widget.show()
            self.bar_chart.show()
        self._charts_are_tabbed = use_tabs
        QTimer.singleShot(0, self.matrix_widget.fit_plot_to_canvas)
