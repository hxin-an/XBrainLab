import sys
import unittest
from unittest.mock import MagicMock, patch

from PyQt6.QtWidgets import QLabel, QWidget

# Mock backend modules before importing UI
sys.modules["XBrainLab.backend.visualization"] = MagicMock()
sys.modules["XBrainLab.backend.visualization.VisualizerType"] = MagicMock()
sys.modules["XBrainLab.backend.visualization.supported_saliency_methods"] = [
    "SmoothGrad"
]

# Import UI components
from XBrainLab.ui.visualization.panel import VisualizationPanel
from XBrainLab.ui.visualization.saliency_3Dplot import (
    Saliency3DPlotWidget,
)
from XBrainLab.ui.visualization.saliency_map import SaliencyMapWidget
from XBrainLab.ui.visualization.saliency_spectrogram import (
    SaliencySpectrogramWidget,
)
from XBrainLab.ui.visualization.saliency_topomap import (
    SaliencyTopographicMapWidget,
)

# app = QApplication(sys.argv) # REMOVED


@unittest.skip("Segfaults in headless environment due to VTK/Qt interaction")
class TestVisualizationPanelRedesign(unittest.TestCase):
    def setUp(self):
        # Patch AggregateInfoPanel
        self.patcher_info = patch("XBrainLab.ui.visualization.panel.AggregateInfoPanel")
        self.MockAggregateInfoPanel = self.patcher_info.start()
        # Make sure the mock instance is a QWidget so layout.addWidget accepts it
        self.MockAggregateInfoPanel.return_value = QWidget()

        # Mock Study and Trainer
        self.mock_study = MagicMock()
        self.mock_trainer = MagicMock()
        self.mock_study.trainer = self.mock_trainer

        # Mock Model Holder
        self.mock_model_holder = MagicMock()
        self.mock_model_holder.target_model.__name__ = "TestModel"
        self.mock_trainer.model_holder = self.mock_model_holder

        # Mock Option
        self.mock_trainer.option.repeat_num = 2

        # Mock Dataset and EpochData
        self.mock_dataset = MagicMock()
        self.mock_epoch_data = MagicMock()
        self.mock_dataset.get_epoch_data.return_value = self.mock_epoch_data
        self.mock_trainer.get_dataset.return_value = self.mock_dataset

        # Mock Plans
        self.mock_plan1 = MagicMock()
        self.mock_plan2 = MagicMock()
        self.mock_trainer.get_plans.return_value = [self.mock_plan1, self.mock_plan2]
        self.mock_trainer.get_training_plan_holders.return_value = [self.mock_trainer]

        # Mock EvalRecord
        self.mock_eval_record = MagicMock()
        self.mock_plan1.get_eval_record.return_value = self.mock_eval_record

        # Mock MainWindow
        self.mock_main_window = MagicMock()
        self.mock_main_window.study = self.mock_study

        # Initialize Panel
        self.panel = VisualizationPanel(self.mock_main_window)
        self.panel.show()  # Ensure isVisible checks work

    def tearDown(self):
        self.panel.close()
        self.patcher_info.stop()

    def test_initialization(self):
        """Test if UI components are initialized correctly."""
        self.assertIsNotNone(self.panel.plan_combo)
        self.assertIsNotNone(self.panel.run_combo)
        self.assertIsNotNone(self.panel.method_combo)
        self.assertIsNotNone(self.panel.abs_check)
        self.assertIsNotNone(self.panel.tabs)

        # Check Tabs
        self.assertEqual(self.panel.tabs.count(), 4)
        self.assertIsInstance(self.panel.tabs.widget(0), SaliencyMapWidget)
        self.assertIsInstance(self.panel.tabs.widget(2), SaliencyTopographicMapWidget)
        self.assertIsInstance(self.panel.tabs.widget(3), Saliency3DPlotWidget)

    def test_unified_controls(self):
        """Test if unified controls update state."""
        # Check Plan Combo Population
        self.assertEqual(
            self.panel.plan_combo.count(), 2
        )  # "Select a plan", "Group 1 (TestModel)"

        # Select Plan
        self.panel.plan_combo.setCurrentIndex(1)

        # Check Run Combo Population
        self.assertEqual(self.panel.run_combo.count(), 3)  # Run 1, Run 2, Average

        # Select Run
        self.panel.run_combo.setCurrentIndex(0)  # Run 1

        # Verify friendly map
        friendly_name = self.panel.plan_combo.currentText()
        self.assertIn(friendly_name, self.panel.friendly_map)
        self.assertEqual(self.panel.friendly_map[friendly_name], self.mock_trainer)

    @patch.object(SaliencyMapWidget, "update_plot")
    def test_update_plot_call(self, mock_update_plot):
        """Test if changing controls calls update_plot on active widget."""
        # Setup
        self.panel.tabs.setCurrentIndex(0)  # Saliency Map
        self.panel.plan_combo.setCurrentIndex(1)
        self.panel.run_combo.setCurrentIndex(0)

        # Manually trigger update to ensure logic is tested regardless of signal timing
        self.panel.on_update()

        # Verify call
        mock_update_plot.assert_called()
        args, _ = mock_update_plot.call_args
        # args: plan, trainer, method, absolute, eval_record
        self.assertEqual(args[0], self.mock_plan1)
        self.assertEqual(args[1], self.mock_trainer)
        self.assertEqual(args[4], self.mock_eval_record)

    @patch.object(SaliencySpectrogramWidget, "update_plot")
    def test_spectrogram_update(self, mock_update_plot):
        """Test Spectrogram update call."""
        self.panel.tabs.setCurrentIndex(1)  # Spectrogram
        self.panel.on_update()
        mock_update_plot.assert_called()

    def test_tab_switching_montage_button(self):
        """Test if Montage button is always visible."""
        # Saliency Map (Tab 0) -> Visible
        self.panel.tabs.setCurrentIndex(0)
        self.panel.on_tab_changed(0)
        self.assertTrue(self.panel.btn_montage.isVisible())

        # Topomap (Tab 2) -> Visible
        self.panel.tabs.setCurrentIndex(2)
        self.panel.on_tab_changed(2)
        self.assertTrue(self.panel.btn_montage.isVisible())

        # 3D Plot (Tab 3) -> Visible
        self.panel.tabs.setCurrentIndex(3)
        self.panel.on_tab_changed(3)
        self.assertTrue(self.panel.btn_montage.isVisible())

    def test_refresh_data(self):
        """Test refresh_data method."""
        # Should call refresh_combos
        with patch.object(self.panel, "refresh_combos") as mock_refresh:
            self.panel.refresh_data()
            mock_refresh.assert_called_once()

    def test_montage_check_topomap(self):
        """Test Montage Check in Topomap Widget."""
        widget = self.panel.tab_topo

        # Case 1: No Montage
        self.mock_epoch_data.get_montage_position.return_value = None

        widget.update_plot(
            self.mock_plan1, self.mock_trainer, "Gradient", False, self.mock_eval_record
        )

        # Verify Error Message
        # The widget clears layout and adds a QLabel
        last_widget = widget.plot_layout.itemAt(widget.plot_layout.count() - 1).widget()
        self.assertIsInstance(last_widget, QLabel)
        self.assertIn("Please Set Montage First", last_widget.text())

    @patch("XBrainLab.ui.visualization.saliency_topomap.plt")
    def test_topomap_plotting(self, mock_plt):
        """Test Topomap plotting logic (figure clearing)."""
        widget = self.panel.tab_topo

        # Setup Montage
        self.mock_epoch_data.get_montage_position.return_value = [[0, 0, 0]]

        # Mock Visualizer
        with patch("XBrainLab.backend.visualization.VisualizerType") as MockVizType:
            mock_viz_instance = MagicMock()
            MockVizType.SaliencyTopoMap.value.return_value = mock_viz_instance
            mock_viz_instance.get_plt.return_value = MagicMock()  # Return a mock figure

            widget.update_plot(
                self.mock_plan1,
                self.mock_trainer,
                "Gradient",
                False,
                self.mock_eval_record,
            )

            # Verify plt.close('all') and plt.figure() called
            mock_plt.close.assert_called_with("all")
            mock_plt.figure.assert_called_once()

    @patch("XBrainLab.ui.visualization.saliency_3Dplot.pyvistaqt")
    @patch("XBrainLab.ui.visualization.saliency_3Dplot.QTimer")
    @patch("XBrainLab.ui.visualization.plot_3d_head.pv")
    @patch("XBrainLab.ui.visualization.plot_3d_head.os.path")
    def test_3d_embedding(self, mock_path, mock_pv, mock_qtimer, mock_pyvistaqt):
        """Test if 3D Plot embeds QtInteractor and defers plotting."""
        widget = self.panel.tab_3d

        # Setup Montage (Required)
        self.mock_epoch_data.get_montage_position.return_value = [[0, 0, 0]]
        self.mock_epoch_data.event_id = {"Event1": 0}

        # Mock QtInteractor to return a real QWidget
        mock_pyvistaqt.QtInteractor.return_value = QWidget()

        # Mock file existence for 3D models
        mock_path.exists.return_value = True
        mock_path.dirname.return_value = "/mock/dir"
        mock_path.join.side_effect = lambda *args: "/".join(args)

        # Mock pv.read
        mock_pv.read.return_value = MagicMock()

        # Mock Saliency3D class to avoid actual plotting logic
        # We need to mock Saliency3D inside the module where it's used
        with patch(
            "XBrainLab.ui.visualization.saliency_3Dplot.Saliency3D"
        ) as MockSaliency3D:
            # Setup QTimer to run immediately
            mock_qtimer.singleShot.side_effect = lambda delay, func: func()

            widget.update_plot(
                self.mock_plan1,
                self.mock_trainer,
                "Gradient",
                False,
                self.mock_eval_record,
            )

            # Verify QtInteractor created
            mock_pyvistaqt.QtInteractor.assert_called_once()

            # Verify QTimer called
            mock_qtimer.singleShot.assert_called_once()

            # Verify Saliency3D instantiated with plotter
            # (because QTimer ran immediately)
            MockSaliency3D.assert_called_once()
            _, kwargs = MockSaliency3D.call_args
            self.assertIn("plotter", kwargs)


if __name__ == "__main__":
    unittest.main()
