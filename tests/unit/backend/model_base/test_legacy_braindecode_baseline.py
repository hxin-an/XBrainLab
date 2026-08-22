from __future__ import annotations

import importlib
import subprocess
import sys

import pytest
import torch

from XBrainLab.backend.model_base.legacy_braindecode import models as legacy_models

_BASELINE_MODELS = (
    ("eegnet", "EEGNet"),
    ("deep4", "Deep4Net"),
    ("shallow_fbcsp", "ShallowFBCSPNet"),
    ("sccnet", "SCCNet"),
    ("eeginception_erp", "EEGInceptionERP"),
    ("eegnex", "EEGNeX"),
)


def _model_kwargs(class_name: str) -> dict[str, object]:
    kwargs: dict[str, object] = {
        "n_chans": 22,
        "n_outputs": 4,
        "n_times": 301,
        "sfreq": 160.0,
    }
    if class_name == "SCCNet":
        kwargs["input_window_seconds"] = 301 / 160
    return kwargs


def test_local_baseline_import_does_not_load_installed_braindecode() -> None:
    process = subprocess.run(  # noqa: S603 - current interpreter, fixed test code
        [
            sys.executable,
            "-c",
            (
                "import sys; "
                "from XBrainLab.backend.model_base.legacy_braindecode "
                "import models; "
                "assert models.EEGNet; "
                "assert not any(name == 'braindecode' or "
                "name.startswith('braindecode.') for name in sys.modules)"
            ),
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert process.returncode == 0, process.stderr


@pytest.mark.parametrize(("module_name", "class_name"), _BASELINE_MODELS)
def test_local_baseline_strictly_loads_upstream_state_and_matches_output(
    module_name: str,
    class_name: str,
) -> None:
    upstream_module = importlib.import_module(f"braindecode.models.{module_name}")
    upstream_class = getattr(upstream_module, class_name)
    legacy_class = getattr(legacy_models, class_name)
    kwargs = _model_kwargs(class_name)

    torch.manual_seed(23)
    upstream = upstream_class(**kwargs).eval()
    legacy = legacy_class(**kwargs).eval()

    upstream_state = upstream.state_dict()
    legacy_state = legacy.state_dict()
    assert list(legacy_state) == list(upstream_state)
    assert {
        key: (tuple(value.shape), value.dtype) for key, value in legacy_state.items()
    } == {
        key: (tuple(value.shape), value.dtype) for key, value in upstream_state.items()
    }
    legacy.load_state_dict(upstream_state, strict=True)

    generator = torch.Generator().manual_seed(41)
    inputs = torch.randn(2, 22, 301, generator=generator)
    with torch.inference_mode():
        expected = upstream(inputs)
        actual = legacy(inputs)

    torch.testing.assert_close(actual, expected, rtol=1e-6, atol=1e-7)


@pytest.mark.parametrize("class_name", ("EEGNet", "EEGNeX"))
def test_local_baseline_representatives_support_finite_backward(
    class_name: str,
) -> None:
    model_class = getattr(legacy_models, class_name)
    model = model_class(**_model_kwargs(class_name)).train()
    generator = torch.Generator().manual_seed(53)
    inputs = torch.randn(2, 22, 301, generator=generator)

    loss = model(inputs).square().mean()
    loss.backward()

    gradients = [
        parameter.grad for parameter in model.parameters() if parameter.requires_grad
    ]
    assert gradients
    assert all(gradient is not None for gradient in gradients)
    assert all(
        torch.isfinite(gradient).all() for gradient in gradients if gradient is not None
    )
