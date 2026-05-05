from tests.architecture_compliance import (
    check_ui_observer_direct_update_bridges,
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


def test_observer_bridge_guard_allows_callback_handlers(tmp_path):
    _write_ui_file(
        tmp_path,
        """
def _setup_bridges(self):
    self._create_bridge(self.controller, "training_started", self._on_training_started)
""",
    )

    assert check_ui_observer_direct_update_bridges(tmp_path) == []
