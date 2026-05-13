from XBrainLab.ui.legacy_controller_bootstrap import (
    get_legacy_workflow_controllers_for_panel_bootstrap,
)


class _StudyWithControllers:
    def __init__(self):
        self.calls = []

    def get_controller(self, name):
        self.calls.append(name)
        return f"{name}-controller"


def test_legacy_workflow_controller_bootstrap_reads_expected_controllers():
    study = _StudyWithControllers()

    controllers = get_legacy_workflow_controllers_for_panel_bootstrap(study)

    assert study.calls == [
        "dataset",
        "preprocess",
        "training",
        "evaluation",
        "visualization",
    ]
    assert controllers.dataset == "dataset-controller"
    assert controllers.preprocess == "preprocess-controller"
    assert controllers.training == "training-controller"
    assert controllers.evaluation == "evaluation-controller"
    assert controllers.visualization == "visualization-controller"


def test_legacy_workflow_controller_bootstrap_handles_missing_getter():
    controllers = get_legacy_workflow_controllers_for_panel_bootstrap(object())

    assert controllers.dataset is None
    assert controllers.preprocess is None
    assert controllers.training is None
    assert controllers.evaluation is None
    assert controllers.visualization is None
