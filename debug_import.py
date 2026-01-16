import os
import sys

# Add project root to path
sys.path.append(os.getcwd())

print("Attempting to import MainWindow...")
try:
    print("Import Successful")
except Exception:
    print("Import Failed!")
    import traceback

    traceback.print_exc()
