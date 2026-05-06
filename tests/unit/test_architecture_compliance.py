from tests.architecture_compliance import (
    check_ui_capability_gated_controller_readiness,
    check_ui_controller_fallbacks,
    check_ui_controller_render_fallbacks,
    check_ui_direct_controller_mutations,
    check_ui_direct_loader_apply,
    check_ui_observer_direct_update_bridges,
    check_ui_observer_handlers_call_refresh_coordinator,
    check_ui_post_command_controller_echoes,
    check_ui_post_command_local_refreshes,
)


def _write_ui_file(root, source: str) -> None:
    path = root / "XBrainLab" / "ui" / "panels" / "demo" / "sidebar.py"
    path.parent.mkdir(parents=True)
    path.write_text(source, encoding="utf-8")


def test_post_command_refresh_guard_flags_direct_local_refresh(tmp_path):
    _write_ui_file(
        tmp_path,
        """
def run(self):
    result = execute_application_command(self, SomeCommand())
    if result.failed:
        return
    self.update_panel()
""",
    )

    violations = check_ui_post_command_local_refreshes(tmp_path)

    assert len(violations) == 1
    assert "update_panel" in violations[0]
    assert "execute_application_command" in violations[0]


def test_post_command_refresh_guard_allows_legacy_helper(tmp_path):
    _write_ui_file(
        tmp_path,
        """
def run(self):
    result = execute_application_command(self, SomeCommand())
    if result.failed:
        return
    self._update_panel_after_legacy_result(result)
""",
    )

    assert check_ui_post_command_local_refreshes(tmp_path) == []


def test_post_command_refresh_guard_flags_success_guard_local_refresh(tmp_path):
    _write_ui_file(
        tmp_path,
        """
def run(self):
    result = execute_application_command(self, SomeCommand())
    if not result.failed:
        self.update_panel()
""",
    )

    violations = check_ui_post_command_local_refreshes(tmp_path)

    assert len(violations) == 1
    assert "update_panel" in violations[0]


def test_post_command_refresh_guard_flags_missing_result_direct_refresh(tmp_path):
    _write_ui_file(
        tmp_path,
        """
def run(self):
    result = execute_application_command(self, SomeCommand())
    if result is None:
        self.update_panel()
""",
    )

    violations = check_ui_post_command_local_refreshes(tmp_path)

    assert len(violations) == 1
    assert "legacy-result helper" in violations[0]


def test_post_command_refresh_guard_allows_refresh_false_query(tmp_path):
    _write_ui_file(
        tmp_path,
        """
def run(self):
    result = execute_application_command(self, SomeCommand(), refresh=False)
    if result.failed:
        return
    self.on_update()
""",
    )

    assert check_ui_post_command_local_refreshes(tmp_path) == []


def test_post_command_controller_echo_guard_flags_service_success_echo(tmp_path):
    _write_ui_file(
        tmp_path,
        """
def select_model(self):
    result = execute_application_command(self, ConfigureTrainingCommand())
    if result is None:
        run_legacy_controller_fallback(
            self,
            lambda: self.controller.set_model_holder(holder),
        )
    elif result.failed:
        return
    holder = self.controller.get_model_holder()
""",
    )

    violations = check_ui_post_command_controller_echoes(tmp_path)

    assert len(violations) == 1
    assert "get_model_holder" in violations[0]
    assert "service-backed success" in violations[0]


def test_post_command_controller_echo_guard_allows_legacy_branch(tmp_path):
    _write_ui_file(
        tmp_path,
        """
def select_model(self):
    result = execute_application_command(self, ConfigureTrainingCommand())
    if result is None:
        run_legacy_controller_fallback(
            self,
            lambda: self.controller.set_model_holder(holder),
        )
        holder = self.controller.get_model_holder()
    elif result.failed:
        return
""",
    )

    assert check_ui_post_command_controller_echoes(tmp_path) == []


def test_controller_fallback_guard_allows_named_legacy_wrapper(tmp_path):
    _write_ui_file(
        tmp_path,
        """
def run(self):
    result = execute_application_command(self, SomeCommand())
    if result is None:
        self._run_legacy_preprocess_fallback(
            "Filtering Blocked",
            lambda: self.controller.apply_filter(1.0, 40.0, [50.0]),
        )
""",
    )

    assert check_ui_controller_fallbacks(tmp_path) == []


def test_controller_fallback_guard_flags_direct_mutation_in_missing_result(tmp_path):
    _write_ui_file(
        tmp_path,
        """
def run(self):
    result = execute_application_command(self, SomeCommand())
    if result is None:
        self.controller.apply_filter(1.0, 40.0, [50.0])
""",
    )

    violations = check_ui_controller_fallbacks(tmp_path)

    assert len(violations) == 1
    assert "apply_filter" in violations[0]


def test_controller_render_fallback_guard_flags_stale_read_in_missing_result(
    tmp_path,
):
    _write_ui_file(
        tmp_path,
        """
def update_panel(self):
    result = execute_application_command(self, QueryStateCommand(), refresh=False)
    if result is None:
        rows = self.controller.get_loaded_data_list()
    return rows
""",
    )

    violations = check_ui_controller_render_fallbacks(tmp_path)

    assert len(violations) == 1
    assert "get_loaded_data_list" in violations[0]
    assert "run_legacy_controller_fallback" in violations[0]


def test_controller_render_fallback_guard_allows_explicit_legacy_wrapper(tmp_path):
    _write_ui_file(
        tmp_path,
        """
def update_panel(self):
    result = execute_application_command(self, QueryStateCommand(), refresh=False)
    if result is None:
        rows = run_legacy_controller_fallback(
            self,
            self.controller.get_loaded_data_list,
        )
    return rows
""",
    )

    assert check_ui_controller_render_fallbacks(tmp_path) == []


def test_capability_readiness_guard_flags_controller_gate_after_capability(tmp_path):
    _write_ui_file(
        tmp_path,
        """
def start_training(self):
    train_capability = get_command_capability(self, CommandName.TRAIN)
    if train_capability is not None and not train_capability.enabled:
        return
    if not self.controller.is_training():
        execute_application_command(self, TrainCommand())
""",
    )

    violations = check_ui_capability_gated_controller_readiness(tmp_path)

    assert len(violations) == 1
    assert "controller.is_training" in violations[0]
    assert "capability is None" in violations[0]


def test_capability_readiness_guard_flags_validate_ready_after_capability(tmp_path):
    _write_ui_file(
        tmp_path,
        """
def check_ready(self):
    train_capability = get_command_capability(self, CommandName.TRAIN)
    ready = (
        train_capability.enabled
        if train_capability is not None
        else self.controller.validate_ready()
    )
    self.btn_start.setEnabled(ready)
""",
    )

    violations = check_ui_capability_gated_controller_readiness(tmp_path)

    assert len(violations) == 1
    assert "controller.validate_ready" in violations[0]
    assert "capability is None" in violations[0]


def test_capability_readiness_guard_flags_lock_state_after_capability(tmp_path):
    _write_ui_file(
        tmp_path,
        """
def update_sidebar(self):
    scan_capability = get_command_capability(self, CommandName.SCAN_SOURCE)
    is_locked = self.controller.is_locked()
    if scan_capability is not None:
        self.import_btn.setEnabled(scan_capability.enabled)
    elif is_locked:
        self.import_btn.setToolTip("Dataset is locked.")
""",
    )

    violations = check_ui_capability_gated_controller_readiness(tmp_path)

    assert len(violations) == 1
    assert "controller.is_locked" in violations[0]
    assert "capability is None" in violations[0]


def test_capability_readiness_guard_flags_saliency_params_after_capability(tmp_path):
    _write_ui_file(
        tmp_path,
        """
def set_saliency(self):
    capability = get_command_capability(self, CommandName.SALIENCY)
    if capability is not None and not capability.enabled:
        return
    params = self.controller.get_saliency_params()
    return SaliencyDialog(self, params)
""",
    )

    violations = check_ui_capability_gated_controller_readiness(tmp_path)

    assert len(violations) == 1
    assert "controller.get_saliency_params" in violations[0]
    assert "capability is None" in violations[0]


def test_capability_readiness_guard_flags_channel_names_after_capability(tmp_path):
    _write_ui_file(
        tmp_path,
        """
def set_montage(self):
    capability = get_command_capability(self, CommandName.APPLY_MONTAGE)
    if capability is not None and not capability.enabled:
        return
    channels = self.controller.get_channel_names()
    return MontageDialog(self, channels)
""",
    )

    violations = check_ui_capability_gated_controller_readiness(tmp_path)

    assert len(violations) == 1
    assert "controller.get_channel_names" in violations[0]
    assert "capability is None" in violations[0]


def test_capability_readiness_guard_flags_filenames_after_capability(tmp_path):
    _write_ui_file(
        tmp_path,
        """
def open_smart_parser(self):
    capability = get_command_capability(self, CommandName.APPLY_SMART_PARSE)
    if capability is not None and not capability.enabled:
        return
    files = self.controller.get_filenames()
    return SmartParserDialog(files, self)
""",
    )

    violations = check_ui_capability_gated_controller_readiness(tmp_path)

    assert len(violations) == 1
    assert "controller.get_filenames" in violations[0]
    assert "capability is None" in violations[0]


def test_capability_readiness_guard_flags_preprocessed_list_after_capability(
    tmp_path,
):
    _write_ui_file(
        tmp_path,
        """
def update_sidebar(self):
    preprocess_capability = get_command_capability(self, CommandName.PREPROCESS)
    if preprocess_capability is not None and not preprocess_capability.enabled:
        return
    data_list = self.controller.get_preprocessed_data_list()
    self._update_button_states(bool(data_list))
""",
    )

    violations = check_ui_capability_gated_controller_readiness(tmp_path)

    assert len(violations) == 1
    assert "controller.get_preprocessed_data_list" in violations[0]
    assert "capability is None" in violations[0]


def test_capability_readiness_guard_flags_explicit_legacy_none_branch(tmp_path):
    _write_ui_file(
        tmp_path,
        """
def start_training(self):
    train_capability = get_command_capability(self, CommandName.TRAIN)
    if train_capability is None and self.controller.is_training():
        return
    execute_application_command(self, TrainCommand())
""",
    )

    violations = check_ui_capability_gated_controller_readiness(tmp_path)

    assert len(violations) == 1
    assert "controller.is_training" in violations[0]
    assert "capability is None" in violations[0]


def test_capability_readiness_guard_allows_explicit_legacy_helper(tmp_path):
    _write_ui_file(
        tmp_path,
        """
def start_training(self):
    train_capability = get_command_capability(self, CommandName.TRAIN)
    if train_capability is None:
        ok, running = run_legacy_controller_fallback(
            self,
            lambda: self.controller.is_training(),
        )
        if ok and running:
            return
    execute_application_command(self, TrainCommand())
""",
    )

    assert check_ui_capability_gated_controller_readiness(tmp_path) == []


def test_capability_readiness_guard_allows_local_legacy_value_helper(tmp_path):
    _write_ui_file(
        tmp_path,
        """
def update_sidebar(self):
    scan_capability = get_command_capability(self, CommandName.SCAN_SOURCE)
    if scan_capability is None:
        available, is_locked = self._legacy_controller_value(
            lambda: self.controller.is_locked(),
        )
        if available and is_locked:
            return
    execute_application_command(self, ScanSourceCommand())
""",
    )

    assert check_ui_capability_gated_controller_readiness(tmp_path) == []


def test_capability_readiness_guard_ignores_non_capability_legacy_function(tmp_path):
    _write_ui_file(
        tmp_path,
        """
def start_training(self):
    if not self.controller.is_training():
        self.controller.start_training()
""",
    )

    assert check_ui_capability_gated_controller_readiness(tmp_path) == []


def test_observer_bridge_guard_flags_direct_update_panel(tmp_path):
    _write_ui_file(
        tmp_path,
        """
def _setup_bridges(self):
    self._create_bridge(self.controller, "data_changed", self.update_panel)
""",
    )

    violations = check_ui_observer_direct_update_bridges(tmp_path)

    assert len(violations) == 1
    assert "update_panel" in violations[0]
    assert "refresh_from_observer" in violations[0]


def test_observer_bridge_guard_flags_direct_refresh_from_observer(tmp_path):
    _write_ui_file(
        tmp_path,
        """
def _setup_bridges(self):
    self._create_bridge(self.controller, "data_changed", self.refresh_from_observer)
""",
    )

    violations = check_ui_observer_direct_update_bridges(tmp_path)

    assert len(violations) == 1
    assert "_create_refresh_bridge" in violations[0]


def test_observer_bridge_guard_allows_create_refresh_bridge(tmp_path):
    _write_ui_file(
        tmp_path,
        """
def _setup_bridges(self):
    self._create_refresh_bridge(self.controller, "data_changed")
""",
    )

    assert check_ui_observer_direct_update_bridges(tmp_path) == []


def test_observer_bridge_guard_flags_import_finished_simple_refresh(tmp_path):
    _write_ui_file(
        tmp_path,
        """
def _setup_bridges(self):
    self._create_refresh_bridge(self.controller, "import_finished")
""",
    )

    violations = check_ui_observer_direct_update_bridges(tmp_path)

    assert len(violations) == 1
    assert "import_finished" in violations[0]
    assert "named callback" in violations[0]


def test_observer_bridge_guard_flags_direct_import_finished_bridge(tmp_path):
    _write_ui_file(
        tmp_path,
        """
def _setup_bridges(self):
    self.import_bridge = QtObserverBridge(
        self.controller,
        "import_finished",
        self,
    )
""",
    )

    violations = check_ui_observer_direct_update_bridges(tmp_path)

    assert len(violations) == 1
    assert "import_finished" in violations[0]
    assert "named callback" in violations[0]


def test_observer_bridge_guard_allows_callback_handlers(tmp_path):
    _write_ui_file(
        tmp_path,
        """
def _setup_bridges(self):
    self._create_bridge(self.controller, "training_started", self._on_training_started)
""",
    )

    assert check_ui_observer_direct_update_bridges(tmp_path) == []


def test_observer_handler_refresh_guard_flags_handler_without_coordinator(tmp_path):
    _write_ui_file(
        tmp_path,
        """
def _setup_bridges(self):
    self._create_bridge(
        self.controller,
        "training_updated",
        self._on_training_updated,
    )

def _on_training_updated(self):
    self.update_loop()
""",
    )

    violations = check_ui_observer_handlers_call_refresh_coordinator(tmp_path)

    assert len(violations) == 1
    assert "_on_training_updated" in violations[0]
    assert "refresh_after_observer" in violations[0]


def test_observer_handler_refresh_guard_allows_handler_with_coordinator(tmp_path):
    _write_ui_file(
        tmp_path,
        """
def _setup_bridges(self):
    self._create_bridge(
        self.controller,
        "training_updated",
        self._on_training_updated,
    )

def _on_training_updated(self):
    self.update_loop()
    refresh_after_observer(self, event_name="training_updated")
""",
    )

    assert check_ui_observer_handlers_call_refresh_coordinator(tmp_path) == []


def test_observer_handler_refresh_guard_allows_import_finished_callback(tmp_path):
    _write_ui_file(
        tmp_path,
        """
def _setup_bridges(self):
    self._create_bridge(
        self.controller,
        "import_finished",
        self._on_import_finished,
    )

def _on_import_finished(self):
    self.show_import_warnings()
""",
    )

    assert check_ui_observer_handlers_call_refresh_coordinator(tmp_path) == []


def test_direct_loader_apply_guard_flags_product_ui_mutation(tmp_path):
    _write_ui_file(
        tmp_path,
        """
def apply_loader(self, loader):
    loader.apply(self.controller.study, force_update=True)
""",
    )

    violations = check_ui_direct_loader_apply(tmp_path)

    assert len(violations) == 1
    assert "loader.apply" in violations[0]
    assert "legacy loader adapter" in violations[0]


def test_direct_loader_apply_guard_allows_legacy_adapter(tmp_path):
    _write_ui_file(
        tmp_path,
        """
def _apply_legacy_loader(self, loader):
    loader.apply(self.controller.study, force_update=True)
""",
    )

    assert check_ui_direct_loader_apply(tmp_path) == []


def test_direct_controller_mutation_guard_flags_product_ui_mutation(tmp_path):
    _write_ui_file(
        tmp_path,
        """
def rename_subject(self):
    controller = self.controller
    controller.update_metadata(0, subject="S01")
""",
    )

    violations = check_ui_direct_controller_mutations(tmp_path)

    assert len(violations) == 1
    assert "controller.update_metadata" in violations[0]
    assert "ApplicationService" in violations[0]


def test_direct_controller_mutation_guard_flags_self_controller_mutation(tmp_path):
    _write_ui_file(
        tmp_path,
        """
def run_training(self):
    self.controller.start_training()
""",
    )

    violations = check_ui_direct_controller_mutations(tmp_path)

    assert len(violations) == 1
    assert "controller.start_training" in violations[0]


def test_direct_controller_mutation_guard_flags_named_controller_attribute(tmp_path):
    _write_ui_file(
        tmp_path,
        """
def apply_montage(self):
    self.preprocess_controller.apply_montage(["C3", "C4"])
""",
    )

    violations = check_ui_direct_controller_mutations(tmp_path)

    assert len(violations) == 1
    assert "controller.apply_montage" in violations[0]


def test_direct_controller_mutation_guard_allows_legacy_fallback_call(tmp_path):
    _write_ui_file(
        tmp_path,
        """
def run(self):
    run_legacy_controller_fallback(
        self,
        lambda: self.controller.start_training(),
    )
""",
    )

    assert check_ui_direct_controller_mutations(tmp_path) == []


def test_direct_controller_mutation_guard_allows_named_legacy_wrapper_call(tmp_path):
    _write_ui_file(
        tmp_path,
        """
def run(self):
    self._run_legacy_preprocess_fallback(
        "Filtering Blocked",
        lambda: self.controller.apply_filter(1.0, 40.0, [50.0]),
    )
""",
    )

    assert check_ui_direct_controller_mutations(tmp_path) == []


def test_direct_controller_mutation_guard_allows_named_fallback_helper(tmp_path):
    _write_ui_file(
        tmp_path,
        """
def _run_metadata_update_fallback(self, controller):
    controller.update_metadata(0, subject="S01")
""",
    )

    assert check_ui_direct_controller_mutations(tmp_path) == []


def test_direct_controller_mutation_guard_ignores_non_controller_methods(tmp_path):
    _write_ui_file(
        tmp_path,
        """
def clear_ui_table(self):
    self.history_table.clear_history()
""",
    )

    assert check_ui_direct_controller_mutations(tmp_path) == []
