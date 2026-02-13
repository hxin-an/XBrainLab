import sys

try:
    print("Importing PreprocessPanel...")
    # Just check if we can import the module structure
    import XBrainLab.ui.dashboard_panel.preprocess

    print("PreprocessPanel imported successfully.")

    print("Importing Dialogs from dialogs.py...")
    import XBrainLab.ui.dashboard_panel.dialogs  # noqa: F401

    print("Dialogs imported successfully.")

    print("Verification complete.")
except ImportError as e:
    print(f"Import failed: {e}")
    sys.exit(1)
except Exception as e:
    print(f"An error occurred: {e}")
    sys.exit(1)
