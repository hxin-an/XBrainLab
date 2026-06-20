"""Shared saliency method names supported by evaluation and visualization."""

recommended_saliency_methods = ["Gradient", "Gradient * Input"]
supported_saliency_methods = ["SmoothGrad", "SmoothGrad_Squared", "VarGrad"]
all_saliency_methods = [*recommended_saliency_methods, *supported_saliency_methods]
