from threading import Event
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor, QPalette
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QDialogButtonBox,
    QFrame,
    QHeaderView,
    QScrollArea,
    QTableWidgetItem,
)

from XBrainLab.backend.model_base.model_catalog import BraindecodeProviderStatus
from XBrainLab.ui.dialogs.training import ModelSelectionDialog
from XBrainLab.ui.styles.theme import Theme

HEALTHY_PROVIDER = BraindecodeProviderStatus(
    available=True,
    installed_version="1.6.1",
    reason="",
    checked=True,
)
MISSING_PROVIDER = BraindecodeProviderStatus(
    available=False,
    installed_version=None,
    reason="Braindecode 1.6.1 is not installed.",
    checked=True,
)


def _result_item(dialog: ModelSelectionDialog, model_id: str):
    assert dialog.model_results is not None
    for index in range(dialog.model_results.count()):
        item = dialog.model_results.item(index)
        if item.data(Qt.ItemDataRole.UserRole) == model_id:
            return item
    raise AssertionError(f"Model result was not found: {model_id}")


def _visible_model_ids(dialog: ModelSelectionDialog) -> list[str]:
    assert dialog.model_results is not None
    return [
        str(dialog.model_results.item(index).data(Qt.ItemDataRole.UserRole))
        for index in range(dialog.model_results.count())
        if not dialog.model_results.item(index).isHidden()
    ]


# Dummy model for testing
class DummyModel:
    def __init__(self, param1=10, param2=0.5, param3="test"):
        pass


class NoEditableParamModel:
    def __init__(self, n_classes, channels, samples, sfreq):
        pass


class ManyParamModel:
    def __init__(
        self,
        alpha=1,
        beta=2,
        gamma=3,
        delta=4,
        epsilon=5,
        zeta=6,
        eta=7,
        theta=8,
        iota=9,
        kappa=10,
        lambda_param=11,
        mu=12,
        nu=13,
        xi=14,
        omicron=15,
        pi=16,
    ):
        pass


class FiveParamModel:
    def __init__(self, f1=8, f2=16, d=2, pool_1=4, pool_2=8):
        pass


class TestModelSelection:
    @pytest.fixture
    def dialog(self, qtbot):
        # Mock model_base members
        with patch("inspect.getmembers") as mock_getmembers:
            mock_getmembers.return_value = [("DummyModel", DummyModel)]

            mock_controller = MagicMock()
            dialog = ModelSelectionDialog(
                None,
                mock_controller,
                provider_status=HEALTHY_PROVIDER,
            )
            qtbot.addWidget(dialog)
            return dialog

    def test_init(self, dialog):
        assert dialog.windowTitle() == "Model Selection"
        assert dialog.model_results is not None
        assert dialog.model_results.count() == 1
        assert dialog._selected_model_id == "xbrainlab.dummymodel"

    def test_product_catalog_defaults_to_braindecode_eegnet(self, qtbot):
        dialog = ModelSelectionDialog(
            None,
            MagicMock(),
            provider_status=HEALTHY_PROVIDER,
        )
        qtbot.addWidget(dialog)

        assert dialog.model_results is not None
        assert dialog._selected_model_id == "braindecode.eegnet"
        assert dialog.model_results.count() == 64
        assert _result_item(dialog, "xbrainlab.eegnet") is not None
        assert _result_item(dialog, "braindecode.ctnet") is not None
        unavailable = _result_item(dialog, "braindecode.eegminer")
        assert not unavailable.flags() & Qt.ItemFlag.ItemIsEnabled
        assert "license" in unavailable.toolTip().casefold()
        assert dialog.params_table is not None
        parameter_keys = {
            dialog.params_table.item(row, 0).data(Qt.ItemDataRole.UserRole)
            for row in range(dialog.params_table.rowCount())
        }
        assert parameter_keys.isdisjoint(
            {"n_outputs", "n_chans", "n_times", "sfreq"},
        )

    def test_dataset_context_disables_incompatible_model_with_visible_reason(
        self,
        qtbot,
    ):
        controller = SimpleNamespace(
            get_epoch_data=lambda: SimpleNamespace(
                get_model_args=lambda: {
                    "n_classes": 4,
                    "channels": 22,
                    "samples": 256,
                    "sfreq": 128.0,
                    "chs_info": [],
                }
            )
        )
        dialog = ModelSelectionDialog(
            None,
            controller,
            provider_status=HEALTHY_PROVIDER,
        )
        qtbot.addWidget(dialog)

        blocked = _result_item(dialog, "braindecode.cbramod")
        allowed = _result_item(dialog, "braindecode.eegnet")
        assert not blocked.flags() & Qt.ItemFlag.ItemIsEnabled
        assert "divisible by 200" in blocked.toolTip()
        assert allowed.flags() & Qt.ItemFlag.ItemIsEnabled

    def test_search_matches_name_alias_family_task_and_stable_id(self, qtbot):
        dialog = ModelSelectionDialog(
            None,
            MagicMock(),
            provider_status=HEALTHY_PROVIDER,
        )
        qtbot.addWidget(dialog)
        assert dialog.search_input is not None

        dialog.search_input.setText("eegconformer")
        assert _visible_model_ids(dialog) == ["braindecode.eegconformer"]

        dialog.search_input.setText("attention classification")
        visible = _visible_model_ids(dialog)
        assert "braindecode.eegconformer" in visible
        assert "braindecode.ctnet" in visible

        dialog.search_input.setText("braindecode.atcnet")
        assert _visible_model_ids(dialog) == ["braindecode.atcnet"]

    def test_no_match_preserves_selection_but_disables_confirm(self, qtbot):
        dialog = ModelSelectionDialog(
            None,
            MagicMock(),
            provider_status=HEALTHY_PROVIDER,
        )
        qtbot.addWidget(dialog)
        assert dialog.search_input is not None
        assert dialog.confirm_btn is not None
        assert dialog.no_match_label is not None

        selected_id = dialog._selected_model_id
        dialog.search_input.setText("not a real architecture")
        assert dialog._selected_model_id == selected_id
        assert dialog.no_match_label.isVisible() is False
        assert dialog.no_match_label.isHidden() is False
        assert not dialog.confirm_btn.isEnabled()

        dialog.search_input.clear()
        assert dialog._selected_model_id == selected_id
        assert dialog.confirm_btn.isEnabled()

    def test_missing_provider_requires_explicit_recovery_selection(self, qtbot):
        dialog = ModelSelectionDialog(
            None,
            MagicMock(),
            provider_status=MISSING_PROVIDER,
        )
        qtbot.addWidget(dialog)
        assert dialog.model_results is not None
        assert dialog.provider_banner is not None
        assert dialog.confirm_btn is not None

        assert dialog.model_results.count() == 60
        assert dialog._selected_model_id is None
        assert not dialog.confirm_btn.isEnabled()
        assert "local recovery" in dialog.provider_banner.text().casefold()
        assert _result_item(dialog, "legacy.braindecode.eegnet") is not None
        with pytest.raises(AssertionError):
            _result_item(dialog, "braindecode.eegnet")

        recovery = _result_item(dialog, "legacy.braindecode.eegnet")
        dialog.model_results.setCurrentItem(recovery)
        assert dialog._selected_model_id == "legacy.braindecode.eegnet"
        assert dialog.confirm_btn.isEnabled()

    def test_persisted_recovery_id_is_not_rebound_when_provider_recovers(self, qtbot):
        dialog = ModelSelectionDialog(
            None,
            MagicMock(),
            initial_model_name="legacy.braindecode.eegnet",
            provider_status=HEALTHY_PROVIDER,
        )
        qtbot.addWidget(dialog)

        assert dialog._selected_model_id == "legacy.braindecode.eegnet"
        assert _result_item(dialog, "legacy.braindecode.eegnet") is not None
        assert _result_item(dialog, "braindecode.eegnet") is not None

    def test_confirm_binds_exact_catalog_provider_identity(self, qtbot):
        dialog = ModelSelectionDialog(
            None,
            MagicMock(),
            provider_status=HEALTHY_PROVIDER,
        )
        qtbot.addWidget(dialog)
        assert dialog.model_results is not None
        selected = _result_item(dialog, "braindecode.ctnet")
        dialog.model_results.setCurrentItem(selected)

        with patch("PyQt6.QtWidgets.QDialog.accept") as base_accept:
            dialog.accept()

        base_accept.assert_called_once()
        holder = dialog.get_result()
        assert holder is not None
        assert holder.model_id == "braindecode.ctnet"
        assert holder.provider == "braindecode"
        assert holder.source_revision

    def test_reject_does_not_create_or_change_model_selection(self, qtbot):
        dialog = ModelSelectionDialog(
            None,
            MagicMock(),
            provider_status=HEALTHY_PROVIDER,
        )
        qtbot.addWidget(dialog)

        dialog.reject()

        assert dialog.get_result() is None

    def test_keyboard_moves_to_filtered_result_and_confirms(self, qtbot):
        dialog = ModelSelectionDialog(
            None,
            MagicMock(),
            provider_status=HEALTHY_PROVIDER,
        )
        qtbot.addWidget(dialog)
        dialog.show()
        assert dialog.search_input is not None

        dialog.search_input.setText("braindecode.atcnet")
        qtbot.keyClick(dialog.search_input, Qt.Key.Key_Down)
        assert dialog._selected_model_id == "braindecode.atcnet"

        with patch("PyQt6.QtWidgets.QDialog.accept") as base_accept:
            qtbot.keyClick(dialog.search_input, Qt.Key.Key_Return)
        base_accept.assert_called_once()

    def test_no_match_enter_cannot_accept_hidden_selection(self, qtbot):
        dialog = ModelSelectionDialog(
            None,
            MagicMock(),
            provider_status=HEALTHY_PROVIDER,
        )
        qtbot.addWidget(dialog)
        dialog.show()
        assert dialog.search_input is not None

        dialog.search_input.setText("not a real architecture")
        with patch("PyQt6.QtWidgets.QDialog.accept") as base_accept:
            qtbot.keyClick(dialog.search_input, Qt.Key.Key_Return)

        base_accept.assert_not_called()
        assert dialog.get_result() is None

    def test_enter_first_selects_visible_result_when_old_selection_is_hidden(
        self,
        qtbot,
    ):
        dialog = ModelSelectionDialog(
            None,
            MagicMock(),
            provider_status=HEALTHY_PROVIDER,
        )
        qtbot.addWidget(dialog)
        dialog.show()
        assert dialog.search_input is not None

        dialog.search_input.setText("braindecode.atcnet")
        with patch("PyQt6.QtWidgets.QDialog.accept") as base_accept:
            qtbot.keyClick(dialog.search_input, Qt.Key.Key_Return)

        base_accept.assert_not_called()
        assert dialog._selected_model_id == "braindecode.atcnet"
        assert dialog.get_result() is None

    def test_provider_preflight_is_background_and_preserves_user_selection(
        self,
        qtbot,
    ):
        started = Event()
        release = Event()

        def checked_status_after_release():
            started.set()
            release.wait(timeout=2)
            return HEALTHY_PROVIDER

        with patch(
            "XBrainLab.ui.dialogs.training.model_selection_dialog."
            "braindecode_provider_status",
            side_effect=checked_status_after_release,
        ):
            dialog = ModelSelectionDialog(None, MagicMock())
            qtbot.addWidget(dialog)
            dialog.show()
            qtbot.waitUntil(started.is_set, timeout=1_000)

            assert dialog.search_input is not None
            assert dialog.search_input.isEnabled()
            assert dialog.model_results is not None
            dialog.search_input.setText("sccnet")
            local_sccnet = _result_item(dialog, "xbrainlab.sccnet")
            dialog.model_results.setCurrentItem(local_sccnet)
            assert dialog._selected_model_id == "xbrainlab.sccnet"

            release.set()
            qtbot.waitUntil(
                lambda: not dialog._provider_check_pending,
                timeout=2_000,
            )

        assert dialog._selected_model_id == "xbrainlab.sccnet"
        assert dialog.search_input.text() == "sccnet"
        assert dialog._provider_worker is not None
        dialog._provider_worker.join(timeout=1)
        assert not dialog._provider_worker.is_alive()

    def test_params_population(self, dialog):
        # Verify params table is populated
        assert dialog.params_table.rowCount() == 3

        # Check param names and default values
        params = {}
        for row in range(dialog.params_table.rowCount()):
            name = dialog.params_table.item(row, 0).text()
            val = dialog.params_table.item(row, 1).text()
            params[name] = val

        assert params["param1"] == "10"
        assert params["param2"] == "0.5"
        assert params["param3"] == "test"

    def test_params_table_has_no_initial_white_selection(self, dialog):
        assert dialog.params_table is not None
        assert dialog.params_table.selectedItems() == []
        assert dialog.params_table.currentRow() == -1
        assert (
            dialog.params_table.selectionMode()
            == QAbstractItemView.SelectionMode.NoSelection
        )
        assert dialog.params_table.height() <= 240
        assert dialog.params_table.palette().color(QPalette.ColorRole.Highlight) == (
            QColor(Theme.TABLE_SELECTION)
        )
        assert dialog.params_table.palette().color(
            QPalette.ColorGroup.Inactive,
            QPalette.ColorRole.Highlight,
        ) == QColor(Theme.TABLE_SELECTION)
        assert dialog.params_table.palette().color(
            QPalette.ColorGroup.Inactive,
            QPalette.ColorRole.HighlightedText,
        ) == QColor(Theme.TEXT_PRIMARY)
        assert dialog.findChild(QDialogButtonBox) is None
        assert dialog.confirm_btn is not None
        assert dialog.confirm_btn.text() == "Confirm"
        assert "QListWidget#ModelSearchResults" in dialog.styleSheet()

    def test_default_catalog_scrolls_without_hiding_confirm(self, dialog, qtbot):
        dialog.show()
        qtbot.wait(50)

        scroll = dialog.findChild(QScrollArea, "ModelSelectionContentScroll")
        assert scroll is not None
        scrollbar = scroll.verticalScrollBar()
        assert scrollbar is not None
        assert scrollbar.maximum() > 0
        assert dialog.confirm_btn is not None
        assert dialog.confirm_btn.isVisibleTo(dialog)

    def test_model_sections_do_not_draw_internal_vertical_frame_lines(self, dialog):
        sections = dialog.findChildren(QFrame, "ModelSection")
        assert len(sections) >= 2
        assert all(section.frameShape() == QFrame.Shape.NoFrame for section in sections)
        section_style = dialog.styleSheet().split("QFrame#ModelSection", 1)[1]
        section_style = section_style.split("}", 1)[0]
        assert "border: none;" in section_style
        scrollbar_style = dialog.styleSheet().split("QScrollBar:vertical", 1)[1]
        scrollbar_style = scrollbar_style.split("}", 1)[0]
        assert "background: transparent;" in scrollbar_style

    def test_realistic_parameter_count_keeps_bounded_catalog_scroll(self, qtbot):
        with patch("inspect.getmembers") as mock_getmembers:
            mock_getmembers.return_value = [("FiveParamModel", FiveParamModel)]

            dialog = ModelSelectionDialog(
                None,
                MagicMock(),
                provider_status=HEALTHY_PROVIDER,
            )
            qtbot.addWidget(dialog)

        dialog.show()
        qtbot.wait(50)

        scroll = dialog.findChild(QScrollArea, "ModelSelectionContentScroll")
        assert scroll is not None
        scrollbar = scroll.verticalScrollBar()
        assert scrollbar is not None
        assert scrollbar.maximum() > 0
        assert dialog.confirm_btn is not None
        assert dialog.confirm_btn.isVisibleTo(dialog)

    def test_realistic_parameters_use_product_labels_and_preserve_raw_keys(
        self,
        qtbot,
    ):
        with patch("inspect.getmembers") as mock_getmembers:
            mock_getmembers.return_value = [("FiveParamModel", FiveParamModel)]
            dialog = ModelSelectionDialog(
                None,
                MagicMock(),
                provider_status=HEALTHY_PROVIDER,
            )
            qtbot.addWidget(dialog)

        assert dialog.params_table is not None
        labels_by_key = {
            dialog.params_table.item(row, 0).data(
                Qt.ItemDataRole.UserRole
            ): dialog.params_table.item(
                row,
                0,
            )
            for row in range(dialog.params_table.rowCount())
        }
        assert labels_by_key["f1"].text() == "Temporal filters"
        assert labels_by_key["f2"].text() == "Pointwise filters"
        assert labels_by_key["d"].text() == "Depth multiplier"
        assert labels_by_key["pool_1"].text() == "First pooling size"
        assert labels_by_key["pool_2"].text() == "Second pooling size"
        assert all(item.toolTip() for item in labels_by_key.values())

        dialog.accept()
        holder = dialog.get_result()
        assert holder is not None
        assert holder.model_params_map == {
            "f1": 8,
            "f2": 16,
            "d": 2,
            "pool_1": 4,
            "pool_2": 8,
        }

    def test_params_table_height_fits_visible_rows(self, dialog):
        assert dialog.params_table is not None
        header = dialog.params_table.horizontalHeader()
        assert isinstance(header, QHeaderView)
        expected_max_height = (
            header.height()
            + sum(
                dialog.params_table.rowHeight(row)
                for row in range(dialog.params_table.rowCount())
            )
            + 12
        )
        assert dialog.params_table.height() <= expected_max_height

    def test_params_table_stays_visible_for_models_without_editable_params(self, qtbot):
        with patch("inspect.getmembers") as mock_getmembers:
            mock_getmembers.return_value = [
                ("NoEditableParamModel", NoEditableParamModel)
            ]

            dialog = ModelSelectionDialog(
                None,
                MagicMock(),
                provider_status=HEALTHY_PROVIDER,
            )
            qtbot.addWidget(dialog)

        assert dialog.params_group is not None
        assert dialog.params_table is not None
        assert not dialog.params_group.isHidden()
        assert dialog.params_table.rowCount() == 1
        name_item = dialog.params_table.item(0, 0)
        assert name_item is not None
        assert "No editable parameters" in name_item.text()

    def test_content_scrolls_when_model_parameters_exceed_dialog_height(self, qtbot):
        with patch("inspect.getmembers") as mock_getmembers:
            mock_getmembers.return_value = [("ManyParamModel", ManyParamModel)]

            dialog = ModelSelectionDialog(
                None,
                MagicMock(),
                provider_status=HEALTHY_PROVIDER,
            )
            qtbot.addWidget(dialog)

        dialog.resize(600, 300)
        dialog.show()
        qtbot.wait(50)

        scroll = dialog.findChild(QScrollArea, "ModelSelectionContentScroll")
        assert scroll is not None
        assert scroll.widgetResizable()
        assert scroll.horizontalScrollBarPolicy() == (
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        assert scroll.verticalScrollBarPolicy() == Qt.ScrollBarPolicy.ScrollBarAsNeeded
        scrollbar = scroll.verticalScrollBar()
        assert scrollbar is not None
        assert scrollbar.maximum() > 0
        assert dialog.confirm_btn is not None
        assert dialog.confirm_btn.isVisibleTo(dialog)
        assert "QScrollArea#ModelSelectionContentScroll" in dialog.styleSheet()

    def test_confirm(self, dialog):
        # Modify a parameter
        dialog.params_table.setItem(0, 1, QTableWidgetItem("20"))

        # Click OK
        with patch("PyQt6.QtWidgets.QDialog.accept") as mock_accept:
            dialog.accept()
            mock_accept.assert_called_once()

        # Verify result
        holder = dialog.get_result()
        assert holder is not None
        assert holder.target_model == DummyModel
        assert holder.model_params_map["param1"] == 20
        assert holder.model_params_map["param2"] == 0.5
        assert holder.model_params_map["param3"] == "test"

    def test_load_weight(self, dialog):
        with patch("PyQt6.QtWidgets.QFileDialog.getOpenFileName") as mock_open:
            mock_open.return_value = ("/path/to/weight.pth", "Model Weights (*)")

            dialog.load_pretrained_weight()

            assert dialog.pretrained_weight_path == "/path/to/weight.pth"
            assert dialog.weight_btn.text() == "Clear"

            # Click again to clear
            dialog.load_pretrained_weight()
            assert dialog.pretrained_weight_path is None
            assert dialog.weight_label.text() == "None"
            assert dialog.weight_btn.text() == "Load"
