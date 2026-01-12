import os
current_dir = os.path.abspath("XBrainLab/ui/visualization")
project_root = os.path.dirname(os.path.dirname(current_dir))
model_dir = os.path.join(project_root, 'backend', 'visualization', '3Dmodel')
print(f"Current: {current_dir}")
print(f"Root: {project_root}")
print(f"Model: {model_dir}")
