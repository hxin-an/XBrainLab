import sys
print("Importing PyQt6...")
try:
    from PyQt6.QtWidgets import QApplication, QMainWindow
    print("PyQt6 imported successfully.")
    app = QApplication(sys.argv)
    print("QApplication initialized.")
except Exception as e:
    print(f"Error: {e}")
