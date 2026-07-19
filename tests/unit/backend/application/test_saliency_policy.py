"""Tests for shared saliency command/UI policy."""

import subprocess
import sys

from XBrainLab.backend.application.saliency_policy import (
    ADVANCED_SALIENCY_METHODS,
    ALL_SALIENCY_METHODS,
    RECOMMENDED_SALIENCY_METHODS,
    baseline_saliency_params,
    normalize_saliency_params,
    recommended_saliency_params_for_method,
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
    probe = subprocess.run(  # noqa: S603 - fixed interpreter and inline probe
        [
            sys.executable,
            "-c",
            (
                "import sys; "
                "import XBrainLab.backend.application.saliency_policy; "
                "assert 'XBrainLab.backend.visualization' not in sys.modules; "
                "assert 'matplotlib.pyplot' not in sys.modules"
            ),
        ],
        check=False,
        capture_output=True,
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


def test_flat_params_apply_to_advanced_methods_when_no_method_list_is_supplied():
    params, requested_method = normalize_saliency_params(
        "SmoothGrad",
        {"nt_samples": 2, "stdevs": 0.25},
    )

    assert requested_method == "SmoothGrad"
    assert params["_methods"] == ["SmoothGrad"]
    assert params["SmoothGrad"]["nt_samples"] == 2
    assert params["SmoothGrad_Squared"]["stdevs"] == 0.25


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
