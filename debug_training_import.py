import os
import sys

sys.path.append(os.getcwd())

print("Attempting to import TrainingManagerWindow...")
try:
    print("Import Successful")
except Exception:
    print("Import Failed!")
    import traceback

    traceback.print_exc()
