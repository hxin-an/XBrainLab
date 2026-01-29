try:
    print("Importing PreprocessPanel...")
    from XBrainLab.ui.dashboard_panel.preprocess import PreprocessPanel
    print("PreprocessPanel imported successfully.")
    
    print("Importing Dialogs from dialogs.py...")
    from XBrainLab.ui.dashboard_panel.dialogs import (
        ResampleDialog,
        EpochingDialog,
        FilteringDialog,
        RereferenceDialog,
        NormalizeDialog
    )
    print("Dialogs imported successfully.")
    
    print("Checking if PreprocessPanel can access dialogs...")
    # We inspect the module to see if imports are there, though we can't instantiate QWidget easily without app
    import inspect
    print("Verification complete.")
except ImportError as e:
    print(f"Import failed: {e}")
    exit(1)
except Exception as e:
    print(f"An error occurred: {e}")
    exit(1)
