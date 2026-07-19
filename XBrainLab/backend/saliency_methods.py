"""Lightweight canonical names for supported saliency methods."""

recommended_saliency_methods = ["Gradient", "Gradient * Input"]
supported_saliency_methods = ["SmoothGrad", "SmoothGrad_Squared", "VarGrad"]
all_saliency_methods = [*recommended_saliency_methods, *supported_saliency_methods]

__all__ = [
    "all_saliency_methods",
    "recommended_saliency_methods",
    "supported_saliency_methods",
]
