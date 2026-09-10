from unittest.mock import patch

from XBrainLab.backend.model_base.model_catalog import get_model_spec
from XBrainLab.backend.training import ModelHolder


class FakeModel:
    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.state_dict = None

    def load_state_dict(self, state_dict):
        self.state_dict = state_dict


class SignalContextModel(FakeModel):
    __xbrainlab_accepts_signal_context__ = True


def test_model_holder():
    target_model = FakeModel
    model_params_map = {"a": 1, "b": 2}
    pretrained_weight_path = "test.pth"
    holder = ModelHolder(target_model, model_params_map, pretrained_weight_path)

    with patch("torch.load", return_value="state_dict"):
        model = holder.get_model({"c": 3})

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
    assert holder.catalog_identity == {
        "model_id": "braindecode.eegnet",
        "provider": "braindecode",
        "source_revision": "braindecode==1.6.1",
    }


def test_direct_model_holder_ignores_catalog_only_channel_context():
    holder = ModelHolder(FakeModel, {})

    model = holder.get_model({"c": 3, "chs_info": [{"ch_name": "Cz"}]})

    assert model.kwargs == {"c": 3}


def test_effective_model_args_matches_direct_constructor_channel_contract():
    holder = ModelHolder(FakeModel, {})

    assert holder.effective_model_args({"c": 3, "chs_info": [{"ch_name": "Cz"}]}) == {
        "c": 3
    }


def test_effective_model_args_keeps_direct_consumed_channel_context():
    holder = ModelHolder(SignalContextModel, {})
    context = {"c": 3, "chs_info": [{"ch_name": "Cz"}]}

    assert holder.effective_model_args(context) == context


def test_effective_model_args_matches_catalog_constructor_channel_contract():
    context = {"n_classes": 2, "channels": 2, "samples": 128, "sfreq": 128.0}
    chs_info = [{"ch_name": "C3"}, {"ch_name": "C4"}]

    non_consuming = ModelHolder(get_model_spec("braindecode.eegnet").factory, {})
    consuming = ModelHolder(
        get_model_spec("braindecode.interpolatedeegpt").factory,
        {},
    )

    assert (
        non_consuming.effective_model_args({**context, "chs_info": chs_info}) == context
    )
    assert consuming.effective_model_args({**context, "chs_info": chs_info}) == {
        **context,
        "chs_info": chs_info,
    }
