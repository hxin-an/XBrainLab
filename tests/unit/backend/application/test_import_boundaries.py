"""Import-boundary guards for the Application Service public package."""

from __future__ import annotations

import os
import subprocess
import sys
import textwrap


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


def test_application_package_root_is_contract_light() -> None:
    """Importing command contracts must not load runtime/training stacks."""
    output = _run_import_probe(
        """
        import sys

        bad_roots = (
            "torch",
            "sklearn",
            "mne",
            "matplotlib",
            "pyvista",
            "pyvistaqt",
            "XBrainLab.backend.application.service",
            "XBrainLab.backend.application.runtime",
            "XBrainLab.backend.application.automation",
            "XBrainLab.backend.application.training_service",
            "XBrainLab.backend.application.dataset_generation_service",
            "XBrainLab.backend.training",
            "XBrainLab.backend.model_base",
        )

        from XBrainLab.backend.application import CommandName, QueryStateCommand

        assert CommandName.QUERY_STATE.value == "query_state"
        assert QueryStateCommand().name == CommandName.QUERY_STATE
        loaded = sorted(
            module
            for module in sys.modules
            if any(module == root or module.startswith(root + ".") for root in bad_roots)
        )
        assert not loaded, loaded
        print("PASS")
        """,
    )
    assert "PASS" in output


def test_state_and_capability_queries_do_not_load_training_stack() -> None:
    """Read-only ApplicationService paths must stay light for Dataset startup."""
    output = _run_import_probe(
        """
        import sys

        from XBrainLab.backend.application.commands import QueryStateCommand
        from XBrainLab.backend.application.runtime import get_application_service
        from XBrainLab.backend.study import Study

        bad_roots = (
            "torch",
            "sklearn",
            "matplotlib",
            "XBrainLab.backend.application.training_service",
            "XBrainLab.backend.application.analysis_service",
            "XBrainLab.backend.application.dataset_generation_service",
            "XBrainLab.backend.training",
            "XBrainLab.backend.model_base",
            "XBrainLab.backend.controller.evaluation_controller",
            "XBrainLab.backend.controller.visualization_controller",
        )

        def bad_new_modules(baseline):
            return sorted(
                module
                for module in set(sys.modules) - baseline
                if any(
                    module == root or module.startswith(root + ".")
                    for root in bad_roots
                )
            )

        study = Study()
        baseline = set(sys.modules)
        service = get_application_service(study)
        service.get_capabilities()
        service.execute(QueryStateCommand(query="state"))
        loaded = bad_new_modules(baseline)
        assert not loaded, loaded
        print("PASS")
        """,
    )
    assert "PASS" in output


def test_dataset_controller_import_does_not_load_io_or_preprocessor_stack() -> None:
    """Controller construction must not load EEG IO until import/preprocess actions."""
    output = _run_import_probe(
        """
        import sys

        bad_roots = (
            "mne",
            "numpy",
            "scipy",
            "XBrainLab.backend.load_data",
            "XBrainLab.backend.preprocessor",
        )

        import XBrainLab.backend.controller.dataset_controller

        loaded = sorted(
            module
            for module in sys.modules
            if any(module == root or module.startswith(root + ".") for root in bad_roots)
        )
        assert not loaded, loaded
        print("PASS")
        """,
    )
    assert "PASS" in output
