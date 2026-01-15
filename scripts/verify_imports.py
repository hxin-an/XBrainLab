import sys
from PyQt6.QtWidgets import QApplication

def check_imports():
    app = QApplication(sys.argv)
    try:
        print("Importing TrainingPanel...")
        from XBrainLab.ui.training.panel import TrainingPanel
        print("TrainingPanel imported successfully.")
        
        print("Importing VisualizationPanel...")
        from XBrainLab.ui.visualization.panel import VisualizationPanel
        print("VisualizationPanel imported successfully.")
        
    except ImportError as e:
        print(f"ImportError: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"Error during import: {e}")
        # Logic error during module init
        sys.exit(1)

if __name__ == "__main__":
    check_imports()
