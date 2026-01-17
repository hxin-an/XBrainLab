from XBrainLab.backend.evaluation.metric import Metric


def test_metric_enum_values():
    assert Metric.ACC.value == "Accuracy (%)"
    assert Metric.AUC.value == "Area under ROC-curve"
    assert Metric.KAPPA.value == "kappa value"


def test_metric_enum_members():
    members = list(Metric)
    assert len(members) == 3
    assert Metric.ACC in members
    assert Metric.AUC in members
    assert Metric.KAPPA in members
