"""Import-boundary guards for the Dataset panel first-open path."""

from __future__ import annotations

import os
import subprocess
import sys
import textwrap

_BAD_DATASET_IMPORT_ROOTS = (
    "torch",
    "sklearn",
    "mne",
    "matplotlib",
    "numpy",
    "pandas",
    "pyvista",
    "pyvistaqt",
    "vtk",
    "scipy",
    "XBrainLab.backend.application.service",
    "XBrainLab.backend.application.automation",
    "XBrainLab.backend.application.runtime",
    "XBrainLab.backend.application.training_service",
    "XBrainLab.backend.application.analysis_service",
    "XBrainLab.backend.application.dataset_generation_service",
    "XBrainLab.backend.application.preprocess_service",
    "XBrainLab.backend.application.data_interpretation_service",
    "XBrainLab.backend.training",
    "XBrainLab.backend.model_base",
    "XBrainLab.backend.visualization",
    "XBrainLab.backend.controller",
    "XBrainLab.backend.load_data",
    "XBrainLab.backend.preprocessor",
    "XBrainLab.backend.dataset",
    "XBrainLab.ui.dialogs.dataset",
)


def _run_import_probe(code: str) -> str:
    env = {
        **os.environ,
        "MNE_DONTWRITE_HOME": "true",
        "QT_QPA_PLATFORM": "offscreen",
    }
    result = subprocess.run(  # noqa: S603 - subprocess isolates import side effects.
        [sys.executable, "-c", textwrap.dedent(code)],
        check=True,
        capture_output=True,
        env=env,
        text=True,
    )
    return result.stdout


def _bad_roots_literal() -> str:
    return repr(_BAD_DATASET_IMPORT_ROOTS)


def test_dataset_panel_import_and_empty_creation_do_not_load_heavy_stacks() -> None:
    """The Dataset page shell must not import dialogs/training/data IO stacks."""
    output = _run_import_probe(
        f"""
        import sys

        bad_roots = {_bad_roots_literal()}

        def loaded_bad_modules():
            return sorted(
                module
                for module in sys.modules
                if any(
                    module == root or module.startswith(root + ".")
                    for root in bad_roots
                )
            )

        import XBrainLab.ui.panels.dataset.panel
        assert not loaded_bad_modules(), ("after import", loaded_bad_modules())

        from PyQt6.QtWidgets import QApplication
        from XBrainLab.ui.panels.dataset.panel import DatasetPanel

        app = QApplication.instance() or QApplication([])
        panel = DatasetPanel(controller=None, parent=None)
        panel.show()
        app.processEvents()
        assert not loaded_bad_modules(), ("after creation", loaded_bad_modules())
        print("PASS")
        """,
    )
    assert "PASS" in output


def test_dataset_dialog_package_is_lazy() -> None:
    """Importing the dialog package must not import every Dataset dialog."""
    output = _run_import_probe(
        """
        import sys

        import XBrainLab.ui.dialogs.dataset

        loaded_dialogs = sorted(
            module
            for module in sys.modules
            if module.startswith("XBrainLab.ui.dialogs.dataset.")
        )
        assert not loaded_dialogs, loaded_dialogs
        print("PASS")
        """,
    )
    assert "PASS" in output


def test_dataset_actions_import_does_not_load_dialogs() -> None:
    """Action handlers should load dialog classes only at button-action time."""
    output = _run_import_probe(
        """
        import sys

        import XBrainLab.ui.panels.dataset.actions

        loaded_dialogs = sorted(
            module
            for module in sys.modules
            if module.startswith("XBrainLab.ui.dialogs.dataset.")
        )
        assert not loaded_dialogs, loaded_dialogs
        print("PASS")
        """,
    )
    assert "PASS" in output


def test_main_window_dataset_first_open_does_not_load_training_or_dialog_stack() -> (
    None
):
    """MainWindow construction and first Dataset open must stay lightweight."""
    output = _run_import_probe(
        """
        import sys

        from PyQt6.QtWidgets import QApplication

        bad_roots = (
            "torch",
            "sklearn",
            "mne",
            "matplotlib",
            "numpy",
            "pandas",
            "pyvista",
            "pyvistaqt",
            "vtk",
            "scipy",
            "XBrainLab.backend.load_data",
            "XBrainLab.backend.preprocessor",
            "XBrainLab.backend.application.training_service",
            "XBrainLab.backend.application.analysis_service",
            "XBrainLab.backend.application.dataset_generation_service",
            "XBrainLab.backend.application.data_interpretation_service",
            "XBrainLab.backend.training",
            "XBrainLab.backend.model_base",
            "XBrainLab.backend.visualization",
            "XBrainLab.backend.dataset",
            "XBrainLab.backend.controller.evaluation_controller",
            "XBrainLab.backend.controller.visualization_controller",
            "XBrainLab.ui.dialogs.dataset",
        )

        def loaded_bad_modules():
            return sorted(
                module
                for module in sys.modules
                if any(
                    module == root or module.startswith(root + ".")
                    for root in bad_roots
                )
            )

        assert not loaded_bad_modules(), ("after QApplication import", loaded_bad_modules())

        from XBrainLab.backend.study import Study
        assert not loaded_bad_modules(), ("after Study import", loaded_bad_modules())

        from XBrainLab.ui.main_window import MainWindow
        assert not loaded_bad_modules(), ("after MainWindow import", loaded_bad_modules())

        MainWindow._schedule_startup_prewarm = lambda self: None
        MainWindow._schedule_initial_panel_load = lambda self: None
        app = QApplication.instance() or QApplication([])
        assert not loaded_bad_modules(), ("after QApplication creation", loaded_bad_modules())

        study = Study()
        assert not loaded_bad_modules(), ("after Study construction", loaded_bad_modules())

        window = MainWindow(study)
        assert not loaded_bad_modules(), ("after MainWindow construction", loaded_bad_modules())

        window.show()
        app.processEvents()
        assert not loaded_bad_modules(), ("after MainWindow show", loaded_bad_modules())

        window.switch_page(0)
        app.processEvents()
        assert not loaded_bad_modules(), ("after Dataset first open", loaded_bad_modules())
        print("PASS")
        """,
    )
    assert "PASS" in output


def test_main_window_default_startup_prepares_dataset_without_heavy_stacks() -> None:
    """Default startup should prepare Dataset before show without broad imports."""
    output = _run_import_probe(
        """
        import sys

        from PyQt6.QtWidgets import QApplication

        bad_roots = (
            "torch",
            "sklearn",
            "mne",
            "matplotlib",
            "numpy",
            "pandas",
            "pyvista",
            "pyvistaqt",
            "vtk",
            "scipy",
            "XBrainLab.backend.load_data",
            "XBrainLab.backend.preprocessor",
            "XBrainLab.backend.application.training_service",
            "XBrainLab.backend.application.analysis_service",
            "XBrainLab.backend.application.dataset_generation_service",
            "XBrainLab.backend.application.data_interpretation_service",
            "XBrainLab.backend.training",
            "XBrainLab.backend.model_base",
            "XBrainLab.backend.visualization",
            "XBrainLab.backend.dataset",
            "XBrainLab.backend.controller.evaluation_controller",
            "XBrainLab.backend.controller.visualization_controller",
            "XBrainLab.ui.dialogs.dataset",
        )

        def loaded_bad_modules():
            return sorted(
                module
                for module in sys.modules
                if any(
                    module == root or module.startswith(root + ".")
                    for root in bad_roots
                )
            )

        from XBrainLab.backend.study import Study
        from XBrainLab.ui.main_window import MainWindow

        MainWindow._schedule_startup_prewarm = lambda self: None
        app = QApplication.instance() or QApplication([])
        window = MainWindow(Study())
        assert window._loaded_panel_indices == {0}
        assert not loaded_bad_modules(), ("after MainWindow construction", loaded_bad_modules())

        window.show()
        app.processEvents()
        assert window._loaded_panel_indices == {0}
        assert not loaded_bad_modules(), ("after MainWindow show", loaded_bad_modules())
        print("PASS")
        """,
    )
    assert "PASS" in output
