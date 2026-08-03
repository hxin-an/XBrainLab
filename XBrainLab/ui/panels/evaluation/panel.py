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
    EvaluationPlanIdentity,
    EvaluationRenderPublication,
    EvaluationRenderRequest,
    EvaluationRunIdentity,
    EvaluationSummaryIdentity,
)
from XBrainLab.backend.application.evaluation_render import (
    evaluation_provenance_presentation,
)
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
    execute_application_command,
    execute_application_command_async,
    get_application_view_publication,
    get_evaluation_render_publication,
)
from XBrainLab.ui.application_publication_renderer import (
    ApplicationPublicationRenderLedger,
)
from XBrainLab.ui.components.info_panel import AggregateInfoPanel
from XBrainLab.ui.components.presentation import ElidingComboBox, ResponsiveControlsBar
from XBrainLab.ui.core.base_panel import BasePanel
from XBrainLab.ui.panels.evaluation.confusion_matrix import ConfusionMatrixWidget
from XBrainLab.ui.panels.evaluation.metrics_bar_chart import MetricsBarChartWidget
from XBrainLab.ui.panels.evaluation.metrics_table import MetricsTableWidget
from XBrainLab.ui.styles.stylesheets import Stylesheets
from XBrainLab.ui.styles.theme import Theme

MODEL_SUMMARY_UNAVAILABLE_TEXT = (
    "Model summary unavailable for the selected run. "
    "Train or refresh the model, then open this tab again."
)
MODEL_SUMMARY_DEFERRED_TEXT = "Open Model Summary to load model details."
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
COMPACT_INFO_SIDEBAR_WIDTH = 220
COMPACT_INFO_SIDEBAR_BREAKPOINT = 540
logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class _EvaluationRunChoice:
    identity: EvaluationRunIdentity
    name: str
    finished: bool


@dataclass(frozen=True, slots=True)
class _EvaluationPlanChoice:
    identity: EvaluationPlanIdentity
    name: str
    runs: tuple[_EvaluationRunChoice, ...]


@dataclass(frozen=True, slots=True)
class _EvaluationSummary:
    available: bool
    plans: tuple[_EvaluationPlanChoice, ...]


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


class _RetryEvaluationPublicationRenderError(RuntimeError):
    """Signal that the current publication was not rendered atomically."""


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
        self._application_summary_dirty = True

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
    ) -> None:
        self._application_view_publication = publication
        self.update_panel()

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
        previous_plan_identity = (
            self.model_combo.currentData() if hasattr(self, "model_combo") else None
        )
        previous_run_identity = (
            self.run_combo.currentData() if hasattr(self, "run_combo") else None
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

        if previous_generation != self._application_generation:
            previous_plan_identity = None
            previous_run_identity = None

        self.model_combo.blockSignals(True)
        self.model_combo.clear()

        plans = self._plans_from_application_query()
        if plans:
            self._show_evaluation_controls_available()
            for i, plan_choice in enumerate(plans):
                self.model_combo.addItem(
                    f"Fold {i + 1}: {plan_choice.name}",
                    plan_choice.identity,
                )

            if self.model_combo.count() > 0:
                selected_index = 0
                for i in range(self.model_combo.count()):
                    if self.model_combo.itemData(i) == previous_plan_identity:
                        selected_index = i
                        break

                self.model_combo.setCurrentIndex(selected_index)
                self.on_model_changed(
                    selected_index,
                    preferred_run_identity=previous_run_identity,
                )
            else:
                self.plot_stack.setCurrentIndex(1)
        else:
            self._show_no_data_available()

        self.model_combo.blockSignals(False)

    def mark_refresh_dirty(self) -> None:
        """Invalidate the cached ApplicationService evaluation summary."""
        self._application_summary_dirty = True
        self._evaluation_render = None
        self._model_summary_identity = None
        self._model_summary_text = ""

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

        def _handle_result(result) -> None:
            if not isinstance(result, CommandResult):
                logger.error(
                    "Evaluation background query returned an invalid result: %s",
                    type(result).__name__,
                )
                self._show_async_query_failure()
                return
            if result.failed:
                logger.error(
                    "Evaluation background query failed: %s",
                    getattr(result, "error_message", None)
                    or getattr(result, "message", "")
                    or "No diagnostic message was provided.",
                )
                self._show_async_query_failure()
                return
            if not self._accept_model_summary(result, summary_identity):
                self._show_async_query_failure()
                return
            if callable(on_ready):
                on_ready()

        def _handle_error(error: tuple) -> None:
            value = error[1] if len(error) > 1 else error
            formatted_traceback = error[2] if len(error) > 2 else ""
            logger.error(
                "Evaluation background query raised: %s\n%s",
                value,
                formatted_traceback,
            )
            self._show_async_query_failure()

        return execute_application_command_async(
            self,
            EvaluateCommand(summary_identity=summary_identity),
            on_result=_handle_result,
            on_error=_handle_error,
            refresh=False,
            busy_target=self,
            expected_publication_generation=self._application_generation,
            runtime=cast(ApplicationUiRuntime, self._action_port),
        )

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
                runs.append(
                    _EvaluationRunChoice(
                        identity=run_identity,
                        name=run_name.strip(),
                        finished=finished,
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
        if not isinstance(text, str):
            return False
        self._model_summary_identity = expected_identity
        self._model_summary_text = text
        return True

    def _show_no_data_available(self) -> None:
        message = self._evaluation_empty_state_message()
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
        self.chk_percentage.setEnabled(False)
        self._set_evaluation_provenance("")
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
        self.chk_percentage.setEnabled(True)
        self.bottom_tabs.setVisible(True)

    def _evaluation_empty_state_message(self) -> str:
        return self._evaluation_error or "No evaluation results available yet."

    def _clear_metric_views(self) -> None:
        self.matrix_widget.update_plot(None)
        self.bar_chart.update_plot({})
        self.metrics_table.update_data({})

    def on_model_changed(self, index, preferred_run_identity=None):
        """Handle model selection change."""
        if index < 0:
            return

        plan_identity = self.model_combo.currentData()
        if not isinstance(plan_identity, EvaluationPlanIdentity):
            return
        plan_choice = self._plan_choice(plan_identity)
        if plan_choice is None:
            self._show_no_data_available()
            return

        self.run_combo.blockSignals(True)
        self.run_combo.clear()

        for i, run_choice in enumerate(plan_choice.runs):
            status = " (Finished)" if run_choice.finished else ""
            self.run_combo.addItem(
                f"Repeat {i + 1}{status}",
                run_choice.identity,
            )
        if any(run_choice.finished for run_choice in plan_choice.runs):
            self.run_combo.addItem(
                "Average (Finished Runs)",
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
        self.update_views()

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
        if not isinstance(
            selection,
            (EvaluationPlanIdentity, EvaluationRunIdentity),
        ):
            self._set_evaluation_provenance("")
            self._clear_metric_views()
            return

        summary_identity = self._summary_identity(selection)
        if isinstance(selection, EvaluationRunIdentity):
            run_choice = self._run_choice(selection)
            if run_choice is None or not run_choice.finished:
                self._clear_metric_views()
                self._update_summary_if_visible(summary_identity)
                return

        render = self._render_for_selection(selection)
        if render is None:
            self._clear_metric_views()
            self._update_summary_if_visible(summary_identity)
            return
        render_data = render.data
        provenance_text, provenance_tooltip = evaluation_provenance_presentation(
            render_data.evaluation_split
        )
        self._set_evaluation_provenance(
            provenance_text,
            tooltip=provenance_tooltip,
        )
        self.plot_stack.setCurrentIndex(0)
        self.bottom_tabs.setVisible(True)
        show_pct = self.chk_percentage.isChecked()
        self.matrix_widget.update_plot(render_data, show_percentage=show_pct)
        metrics = dict(render_data.metrics)
        class_names = dict(render_data.class_labels)
        self.metrics_table.update_data(metrics, class_names=class_names)
        self.bar_chart.update_plot(metrics, class_names=class_names)
        self._update_summary_if_visible(render_data.summary_identity)

    def _render_for_selection(
        self,
        selection: EvaluationPlanIdentity | EvaluationRunIdentity,
    ) -> EvaluationRenderPublication | None:
        generation = self._application_generation
        if generation is None:
            return None
        request = EvaluationRenderRequest(
            publication_generation=generation,
            selection=selection,
        )
        cached = self._evaluation_render
        if cached is not None and cached.request == request:
            return cached
        query_port = self._query_port
        if query_port is None:
            return None
        try:
            publication = get_evaluation_render_publication(
                self,
                request,
                runtime=cast(ApplicationUiRuntime, query_port),
            )
        except ApplicationError as exc:
            if exc.diagnostics.get("evaluation_final_unavailable") is True:
                self._show_evaluation_render_unavailable(str(exc))
                return None
            logger.error("Evaluation render publication failed.", exc_info=True)
            self.mark_refresh_dirty()
            if self._application_render_ledger.render_in_progress:
                raise _RetryEvaluationPublicationRenderError(
                    "Evaluation render changed during publication delivery."
                ) from None
            return None
        except Exception:
            logger.error("Evaluation render publication failed.", exc_info=True)
            self.mark_refresh_dirty()
            if self._application_render_ledger.render_in_progress:
                raise _RetryEvaluationPublicationRenderError(
                    "Evaluation render changed during publication delivery."
                ) from None
            return None
        if publication is None or publication.request != request:
            return None
        self._evaluation_render = publication
        return publication

    def _show_evaluation_render_unavailable(self, message: str) -> None:
        """Show one stable, user-facing reason for inadmissible final metrics."""
        self._evaluation_render = None
        self._set_evaluation_provenance("")
        self._clear_metric_views()
        self.no_data_label.setText(message)
        self.plot_stack.setCurrentIndex(1)
        self.bottom_tabs.setVisible(False)

    def _set_evaluation_provenance(
        self,
        text: str,
        *,
        tooltip: str = "",
    ) -> None:
        self.provenance_label.setText(text)
        self.provenance_label.setToolTip(tooltip)
        self.provenance_label.setVisible(bool(text))

    def cleanup(self) -> None:
        """Cancel queued renders and release the publication subscription."""
        self._application_render_ledger.cleanup()
        if hasattr(self, "matrix_widget"):
            self.matrix_widget.cleanup()
        if hasattr(self, "bar_chart"):
            self.bar_chart.cleanup()
        super().cleanup()

    def closeEvent(self, event):  # noqa: N802
        """Release the application publication subscription on panel close."""
        self.cleanup()
        super().closeEvent(event)

    @staticmethod
    def _summary_identity(
        selection: EvaluationPlanIdentity | EvaluationRunIdentity,
    ) -> EvaluationSummaryIdentity:
        if isinstance(selection, EvaluationRunIdentity):
            return EvaluationSummaryIdentity(
                plan=selection.plan,
                run=selection,
            )
        return EvaluationSummaryIdentity(plan=selection)

    def update_model_summary(
        self,
        summary_identity: EvaluationSummaryIdentity,
    ) -> None:
        """Load and display one identity-bound model summary."""
        if not isinstance(summary_identity, EvaluationSummaryIdentity):
            self.summary_text.setText(MODEL_SUMMARY_UNAVAILABLE_TEXT)
            return
        if self._model_summary_identity == summary_identity:
            self.summary_text.setText(
                self._model_summary_text or MODEL_SUMMARY_UNAVAILABLE_TEXT
            )
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
        summary_identity: EvaluationSummaryIdentity,
    ) -> None:
        if not self._summary_tab_visible():
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
        if not isinstance(
            selection,
            (EvaluationPlanIdentity, EvaluationRunIdentity),
        ):
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
        self.model_combo.setMinimumWidth(180)
        self.model_combo.setMaximumWidth(360)
        self.model_combo.setMinimumContentsLength(20)
        self.model_combo.setSizeAdjustPolicy(
            QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon,
        )
        self.model_combo.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Fixed,
        )
        self.model_combo.setStyleSheet(Stylesheets.COMBO_BOX)
        model_view = self.model_combo.view()
        if model_view is not None:
            model_view.setTextElideMode(Qt.TextElideMode.ElideRight)
        self.model_combo.currentIndexChanged.connect(self.on_model_changed)

        # Run Selection
        self.run_combo = ElidingComboBox()
        self.run_combo.setMinimumWidth(180)
        self.run_combo.setMaximumWidth(300)
        self.run_combo.setMinimumContentsLength(18)
        self.run_combo.setSizeAdjustPolicy(
            QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon,
        )
        self.run_combo.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Fixed,
        )
        self.run_combo.setStyleSheet(Stylesheets.COMBO_BOX)
        run_view = self.run_combo.view()
        if run_view is not None:
            run_view.setTextElideMode(Qt.TextElideMode.ElideRight)
        self.run_combo.currentIndexChanged.connect(self.update_views)

        # Options
        self.chk_percentage = QCheckBox("Percent")
        self.chk_percentage.setStyleSheet(Stylesheets.CHECKBOX_MUTED)
        self.chk_percentage.setSizePolicy(
            QSizePolicy.Policy.Fixed,
            QSizePolicy.Policy.Fixed,
        )
        self.chk_percentage.setMinimumWidth(self.chk_percentage.sizeHint().width())
        self.chk_percentage.toggled.connect(self.update_views)

        self.provenance_label = QLabel()
        self.provenance_label.setObjectName("EvaluationProvenance")
        self.provenance_label.setStyleSheet(
            f"color: {Theme.TEXT_MUTED}; padding-left: 4px;"
        )
        self.provenance_label.setSizePolicy(
            QSizePolicy.Policy.Fixed,
            QSizePolicy.Policy.Fixed,
        )
        self.provenance_label.hide()

        self.evaluation_controls_bar = ResponsiveControlsBar(
            [("Model", self.model_combo), ("Run", self.run_combo)],
            [self.chk_percentage, self.provenance_label],
            wrap_width=600,
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

    def _update_responsive_layout(self) -> None:
        self._update_info_sidebar_width()
        self._update_chart_layout()
        self._update_height_layout()

    def _update_info_sidebar_width(self) -> None:
        """Keep the fixed summary visible when the assistant narrows the page."""
        if not hasattr(self, "right_panel"):
            return
        target_width = (
            COMPACT_INFO_SIDEBAR_WIDTH
            if self.contentsRect().width() < COMPACT_INFO_SIDEBAR_BREAKPOINT
            else INFO_SIDEBAR_WIDTH
        )
        if self.right_panel.width() != target_width:
            self.right_panel.setFixedWidth(target_width)

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
