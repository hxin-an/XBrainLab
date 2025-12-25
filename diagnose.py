import sys
import os

# Add project root to path
sys.path.append(os.path.abspath(os.path.dirname(__file__)))

def test_import(name, module_name):
    print(f"[-] Testing {name} import...")
    try:
        __import__(module_name)
        print(f"[+] {name} PASS")
        return True
    except ImportError as e:
        print(f"[!] {name} FAIL: {e}")
        return False
    except Exception as e:
        print(f"[!] {name} CRASH: {e}")
        return False

print("=== XBrainLab Diagnostic Tool ===")
print(f"Python: {sys.executable}")

# 1. Test PyQt6
if test_import("PyQt6", "PyQt6.QtWidgets"):
    try:
        from PyQt6.QtWidgets import QApplication
        app = QApplication(sys.argv)
        print("[+] QApplication initialized PASS")
    except Exception as e:
        print(f"[!] QApplication init FAIL: {e}")

# 2. Test PyTorch
test_import("PyTorch", "torch")

# 3. Test Transformers
test_import("Transformers", "transformers")

# 4. Test Agent
print("[-] Testing Agent initialization...")
try:
    from remote.core.agent import Agent
    print("[+] Agent import PASS")
    # Try init
    agent = Agent(use_rag=False, use_voting=False)
    print("[+] Agent init PASS")
except Exception as e:
    print(f"[!] Agent init FAIL: {e}")

print("=== Diagnosis Complete ===")
