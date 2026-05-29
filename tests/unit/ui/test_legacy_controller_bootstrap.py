from XBrainLab.ui.legacy_controller_bootstrap import (
    get_legacy_workflow_controllers_for_panel_bootstrap,
)


class _StudyWithControllers:
    def __init__(self):
        self.calls = []

    def get_controller(self, name):
        self.calls.append(name)
        return f"{name}-controller"


def test_legacy_workflow_controller_bootstrap_reads_controllers_lazily():
    study = _StudyWithControllers()

    controllers = get_legacy_workflow_controllers_for_panel_bootstrap(study)

    assert study.calls == []
    assert controllers.dataset == "dataset-controller"
    assert study.calls == ["dataset"]
    assert controllers.dataset == "dataset-controller"
    assert study.calls == ["dataset"]
    assert controllers.preprocess == "preprocess-controller"
    assert study.calls == ["dataset", "preprocess"]
    assert controllers.training == "training-controller"
    assert controllers.evaluation == "evaluation-controller"
    assert controllers.visualization == "visualization-controller"
    assert study.calls == [
        "dataset",
        "preprocess",
        "training",
        "evaluation",
        "visualization",
    ]


def test_legacy_workflow_controller_bootstrap_handles_missing_getter():
    controllers = get_legacy_workflow_controllers_for_panel_bootstrap(object())

    assert controllers.dataset is None
    assert controllers.preprocess is None
    assert controllers.training is None
    assert controllers.evaluation is None
    assert controllers.visualization is None
