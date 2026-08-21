"""Tests for shared saliency command/UI policy."""

import os
import subprocess
import sys

import pytest

from XBrainLab.backend.application.saliency_policy import (
    ADVANCED_SALIENCY_METHODS,
    ALL_SALIENCY_METHODS,
    MAX_SALIENCY_NT_SAMPLES,
    MAX_SALIENCY_NT_SAMPLES_BATCH_SIZE,
    RECOMMENDED_SALIENCY_METHODS,
    baseline_saliency_params,
    normalize_saliency_params,
    recommended_saliency_params_for_method,
    saliency_command_params_from_configured,
    selected_saliency_methods_from_params,
)
from XBrainLab.backend.visualization import (
    all_saliency_methods,
    supported_saliency_methods,
)


def test_policy_methods_follow_visualization_supported_method_names():
    assert list(ADVANCED_SALIENCY_METHODS) == supported_saliency_methods
    assert list(ALL_SALIENCY_METHODS) == all_saliency_methods


def test_policy_import_does_not_cold_start_visualization_stack() -> None:
    child_environment = os.environ.copy()
    for name in tuple(child_environment):
        if name.startswith("COV_CORE_"):
            child_environment.pop(name)

    probe = subprocess.run(  # noqa: S603 - fixed interpreter and inline probe
        [
            sys.executable,
            "-c",
            (
                "import os; import sys; "
                "assert not any(name.startswith('COV_CORE_') for name in os.environ); "
                "import XBrainLab.backend.application.saliency_policy; "
                "assert 'XBrainLab.backend.visualization' not in sys.modules; "
                "assert 'matplotlib.pyplot' not in sys.modules"
            ),
        ],
        check=False,
        capture_output=True,
        env=child_environment,
        text=True,
        timeout=10,
    )

    assert probe.returncode == 0, probe.stderr


def test_recommended_profile_selects_fast_baseline_methods():
    params, requested_method = normalize_saliency_params(
        None,
        {"profile": "recommended"},
    )

    assert requested_method is None
    assert params["_methods"] == list(RECOMMENDED_SALIENCY_METHODS)
    assert params["_profile"] == "recommended"


def test_advanced_profile_defaults_to_advanced_methods():
    params, requested_method = normalize_saliency_params(
        None,
        {"profile": "advanced"},
    )

    assert requested_method is None
    assert params["_methods"] == list(ADVANCED_SALIENCY_METHODS)
    for method in ADVANCED_SALIENCY_METHODS:
        assert params[method]["nt_samples"] == 5


def test_configured_params_round_trip_to_public_command_shape() -> None:
    configured, _requested_method = normalize_saliency_params(
        "SmoothGrad",
        {
            "profile": "advanced",
            "methods": ["SmoothGrad"],
            "SmoothGrad": {"nt_samples": 7, "stdevs": 0.25},
        },
    )

    command_params = saliency_command_params_from_configured(configured)

    assert command_params == {
        "profile": "advanced",
        "methods": ["SmoothGrad"],
        "SmoothGrad": {
            "nt_samples": 7,
            "nt_samples_batch_size": None,
            "stdevs": 0.25,
        },
    }
    assert "_methods" not in command_params
    assert "_profile" not in command_params
    assert "SmoothGrad_Squared" not in command_params
    assert "VarGrad" not in command_params
    renormalized, requested_method = normalize_saliency_params(
        "SmoothGrad",
        command_params,
    )
    assert requested_method == "SmoothGrad"
    assert renormalized == configured


def test_recommended_configured_params_round_trip_to_public_command_shape() -> None:
    configured, _requested_method = normalize_saliency_params(
        "Gradient",
        baseline_saliency_params(),
    )

    command_params = saliency_command_params_from_configured(configured)

    assert command_params == {
        "profile": "recommended",
        "methods": list(RECOMMENDED_SALIENCY_METHODS),
    }
    renormalized, requested_method = normalize_saliency_params(
        "Gradient",
        command_params,
    )
    assert requested_method == "Gradient"
    assert renormalized == configured


def test_flat_params_apply_only_to_requested_advanced_method():
    params, requested_method = normalize_saliency_params(
        "SmoothGrad",
        {"nt_samples": 2, "stdevs": 0.25},
    )

    assert requested_method == "SmoothGrad"
    assert params["_methods"] == ["SmoothGrad"]
    assert params["SmoothGrad"]["nt_samples"] == 2
    assert params["SmoothGrad"]["stdevs"] == 0.25
    assert params["SmoothGrad_Squared"]["nt_samples"] == 5
    assert params["SmoothGrad_Squared"]["stdevs"] == 1.0


@pytest.mark.parametrize(
    ("method", "params", "message"),
    [
        ("IntegratedGradients", None, "Unsupported saliency method"),
        ("Gradient", {"nt_samples": 2}, "does not accept noise parameters"),
        ("SmoothGrad", {"nt_samples": 0}, "nt_samples must be a positive integer"),
        ("SmoothGrad", {"target": 1}, "Unsupported saliency parameter"),
    ],
)
def test_invalid_saliency_configuration_fails_closed(
    method: str,
    params: dict[str, object] | None,
    message: str,
) -> None:
    with pytest.raises(ValueError, match=message):
        normalize_saliency_params(method, params)


@pytest.mark.parametrize(
    ("field", "maximum"),
    [
        ("nt_samples", MAX_SALIENCY_NT_SAMPLES),
        ("nt_samples_batch_size", MAX_SALIENCY_NT_SAMPLES_BATCH_SIZE),
    ],
)
def test_noise_sample_amplification_limits_are_enforced(
    field: str,
    maximum: int,
) -> None:
    with pytest.raises(ValueError, match="must not exceed"):
        normalize_saliency_params("SmoothGrad", {field: maximum + 1})


def test_ui_payload_helpers_share_backend_method_policy():
    baseline = baseline_saliency_params()
    recommended = recommended_saliency_params_for_method("Gradient * Input")
    advanced = recommended_saliency_params_for_method("VarGrad")

    assert baseline == recommended
    assert selected_saliency_methods_from_params(recommended) == set(
        RECOMMENDED_SALIENCY_METHODS,
    )
    assert advanced["profile"] == "advanced"
    assert advanced["methods"] == ["VarGrad"]
    assert selected_saliency_methods_from_params(advanced) == {"VarGrad"}


def test_ui_payload_helper_rejects_unknown_method_without_baseline_fallback():
    with pytest.raises(ValueError, match="Unsupported saliency method"):
        recommended_saliency_params_for_method("IntegratedGradients")


@pytest.mark.parametrize(
    ("method", "params"),
    [
        ("SmoothGrad", {"profile": "recommended"}),
        (None, {"profile": "recommended", "methods": ["SmoothGrad"]}),
        (None, {"profile": "advanced", "methods": ["Gradient"]}),
    ],
)
def test_conflicting_saliency_method_profile_contract_fails_closed(
    method: str | None,
    params: dict[str, object],
) -> None:
    with pytest.raises(ValueError, match="conflict"):
        normalize_saliency_params(method, params)
