import json
import os
import sys

# Setup paths
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.append(PROJECT_ROOT)

from XBrainLab.backend.study import Study
from XBrainLab.debug.tool_executor import ToolExecutor


def verify_all_tools_script():
    script_path = os.path.join(PROJECT_ROOT, "scripts/agent/debug/all_tools.json")
    if not os.path.exists(script_path):
        print(f"Script not found: {script_path}")
        return

    print("Loading script...")
    with open(script_path, encoding="utf-8") as f:
        data = json.load(f)
        calls = data.get("calls", [])

    print(f"Found {len(calls)} calls. executing headless...")

    study = Study()
    executor = ToolExecutor(study)

    for i, call in enumerate(calls):
        tool = call["tool"]
        params = call.get("params", {})
        print(f"[{i + 1}/{len(calls)}] Executing {tool}...")

        try:
            result = executor.execute(tool, params)
            print(f"  Result: {result}")
            if "Error" in result:
                print(f"  FAILED: {result}")
                # Don't stop, see all errors
            else:
                pass
        except Exception as e:
            print(f"  CRASHED: {e}")


if __name__ == "__main__":
    verify_all_tools_script()
