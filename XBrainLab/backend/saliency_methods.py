"""Lightweight canonical names and record stores for saliency methods."""

from typing import Final

SALIENCY_METHOD_STORE_NAMES: Final[dict[str, str]] = {
    "Gradient": "gradient",
    "Gradient * Input": "gradient_input",
    "SmoothGrad": "smoothgrad",
    "SmoothGrad_Squared": "smoothgrad_sq",
    "VarGrad": "vargrad",
}

recommended_saliency_methods = ["Gradient", "Gradient * Input"]
supported_saliency_methods = ["SmoothGrad", "SmoothGrad_Squared", "VarGrad"]
all_saliency_methods = list(SALIENCY_METHOD_STORE_NAMES)

__all__ = [
    "SALIENCY_METHOD_STORE_NAMES",
    "all_saliency_methods",
    "recommended_saliency_methods",
    "supported_saliency_methods",
]
