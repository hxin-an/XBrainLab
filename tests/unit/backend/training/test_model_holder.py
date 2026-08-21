from unittest.mock import patch

from XBrainLab.backend.training import ModelHolder


class FakeModel:
    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.state_dict = None

    def load_state_dict(self, state_dict):
        self.state_dict = state_dict


def test_model_holder():
    target_model = FakeModel
    model_params_map = {"a": 1, "b": 2}
    pretrained_weight_path = "test.pth"
    holder = ModelHolder(target_model, model_params_map, pretrained_weight_path)

    with patch("torch.load", return_value="state_dict"):
        model = holder.get_model({"c": 3})

        assert holder.get_model_desc_str() == "FakeModel (a=1, b=2)"
        assert model.kwargs == {"a": 1, "b": 2, "c": 3}
        assert model.state_dict == "state_dict"


def test_model_holder_isolates_parameter_mapping_from_caller_mutation():
    params = {"dropout": 0.25, "nested": {"depth": 2}}
    holder = ModelHolder(FakeModel, params)

    params["dropout"] = 0.9
    params["nested"]["depth"] = 4

    assert holder.model_params_map == {"dropout": 0.25, "nested": {"depth": 2}}


def test_model_holder_returns_parameter_snapshot():
    holder = ModelHolder(FakeModel, {"nested": {"depth": 2}})

    snapshot = holder.model_params_map
    snapshot["nested"]["depth"] = 9

    assert holder.model_params_map == {"nested": {"depth": 2}}


def test_model_holder_preserves_stable_catalog_identity():
    holder = ModelHolder(
        FakeModel,
        {},
        model_id="braindecode.eegnet",
        display_name="EEGNet (Braindecode)",
        provider="braindecode",
        source_revision="braindecode==1.6.1",
    )

    assert holder.model_id == "braindecode.eegnet"
    assert holder.display_name == "EEGNet (Braindecode)"
    assert holder.provider == "braindecode"
    assert holder.source_revision == "braindecode==1.6.1"
    assert holder.get_model_desc_str() == "EEGNet (Braindecode)"


def test_direct_model_holder_ignores_catalog_only_channel_context():
    holder = ModelHolder(FakeModel, {})

    model = holder.get_model({"c": 3, "chs_info": [{"ch_name": "Cz"}]})

    assert model.kwargs == {"c": 3}
