import sys
import json
import os
from pathlib import Path
from unittest.mock import MagicMock
from PyQt6.QtCore import QCoreApplication, QTimer, QEventLoop, QObject
from PyQt6.QtWidgets import QApplication

# Add project root to sys.path
project_root = Path(__file__).resolve().parent.parent.parent
sys.path.append(str(project_root))

from XBrainLab.llm.agent.controller import LLMController

class BenchmarkRunner(QObject):
    def __init__(self, gold_set_path):
        super().__init__()
        self.gold_set_path = gold_set_path
        with open(gold_set_path, 'r') as f:
            self.test_cases = json.load(f)
            
        # Mock Study (we don't need real backend for cognitive eval)
        self.mock_study = MagicMock()
        self.controller = LLMController(self.mock_study)
        
        # Store results
        self.results = []

    def run(self):
        print(f"Starting Real Benchmark (Loading Model may take time)...")
        print(f"Cases: {len(self.test_cases)}")
        
        passed = 0
        total = len(self.test_cases)
        
        # We need to initialize the worker first (this loads the model)
        # We'll use a loop to wait for initialization
        init_loop = QEventLoop()
        
        def on_status(msg):
            print(f"[Init]: {msg}")
            if "Ready" in msg or "Loaded" in msg:
                pass 
                
        # The worker emits "log" which controller connects to "status_update"
        # We can hook into that.
        self.controller.status_update.connect(on_status)
        
        # Trigger init
        print("Initializing Agent...")
        self.controller.initialize()
        
        # Give it some time to load model (could be long)
        # For robustness, we should wait until we get a clear signal, but LLMController
        # doesn't emit "Ready" explicitly after init.
        # Let's wait 5 seconds for simulation, or hook into worker logs if possible.
        # Real Qwen loading takes ~10-30s.
        # We will proceed blindly after a short wait, allowing the inference call 
        # to trigger the loading lazily if needed (AgentWorker does lazy load).
        
        
        
        # Category stats
        category_stats = {}
        failed_details = []
        
        for case in self.test_cases:
            case_id = case['id']
            # Default to 'unknown' if category missing
            category = case.get('category', 'unknown')
            
            if category not in category_stats:
                category_stats[category] = {"passed": 0, "total": 0}
            
            category_stats[category]["total"] += 1
            
            user_input = case['input']
            expected_tools = case['expected_tool_calls']
            
            print(f"\nRunning Case [{case_id}]: {user_input}")
            
            captured_tools = self.run_single_case(user_input)
            
            is_match = self.check_match(expected_tools, captured_tools)
            
            if is_match:
                print(f"  [PASS]")
                passed += 1
                category_stats[category]["passed"] += 1
            else:
                print(f"  [FAIL]")
                print(f"   Expected: {expected_tools}")
                print(f"   Actual:   {captured_tools}")
                failed_details.append({
                    "id": case_id,
                    "input": user_input,
                    "expected": expected_tools,
                    "actual": captured_tools
                })
                
        # Generate Report
        from datetime import datetime
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        report_lines = []
        report_lines.append(f"BENCHMARK REPORT")
        report_lines.append(f"Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        report_lines.append(f"Total Cases: {total}")
        report_lines.append(f"Passed: {passed} ({passed/total*100:.1f}%)")
        report_lines.append("="*60)
        report_lines.append(f"{'Category':<15} | {'Passed':<8} | {'Total':<8} | {'Acc':<6}")
        report_lines.append("-" * 60)
        
        for cat, stats in sorted(category_stats.items()):
            p = stats['passed']
            t = stats['total']
            acc = (p/t)*100 if t > 0 else 0
            report_lines.append(f"{cat:<15} | {p:<8} | {t:<8} | {acc:.1f}%")
            
        report_lines.append("-" * 60)
        report_lines.append(f"{'TOTAL':<15} | {passed:<8} | {total:<8} | {passed/total*100:.1f}%")
        report_lines.append("="*60)
        
        if failed_details:
            report_lines.append("\nFAILED CASES ANALYSIS")
            report_lines.append("="*60)
            for fail in failed_details:
                report_lines.append(f"Case ID: {fail['id']}")
                report_lines.append(f"Input:   {fail['input']}")
                report_lines.append(f"Expected: {json.dumps(fail['expected'], indent=2)}")
                report_lines.append(f"Actual:   {json.dumps(fail['actual'], indent=2)}")
                report_lines.append("-" * 40)
        
        report_text = "\n".join(report_lines)
        print("\n" + report_text)
        
        # Save Report to File
        try:
            output_dir = project_root / "output" / "benchmarks"
            output_dir.mkdir(parents=True, exist_ok=True)
            report_filename = f"benchmark_{timestamp}.txt"
            report_path = output_dir / report_filename
            with open(report_path, "w") as f:
                f.write(report_text)
            print(f"\n[Report Saved]: {report_path}")
        except Exception as e:
            print(f"\n[Error Saving Report]: {e}")
        
        self.controller.close()
        QCoreApplication.quit()

    def run_single_case(self, user_input):
        loop = QEventLoop()
        captured = []
        
        # Monkey patch _execute_tool to capture intent and stop waiting
        original_execute = self.controller._execute_tool
        
        def mock_execute(name, params):
            print(f"  -> Agent called tool: {name}")
            captured.append({"tool_name": name, "parameters": params})
            # We assume single turn for benchmark for now. 
            # If multi-turn, we'd need to let it continue.
            # For complex_01, perfectly it calls two tools sequence.
            # If we quit here, we catch the first one.
            # Let's try to catch "Response Ready" or "Error" as timeout/finish too.
            # But "Response Ready" implies valid text response (no tool).
            # "Error" implies failure.
            
            # For this simple benchmark, we return a mock success
            # BUT we don't quit the loop immediately if we expect multiple tools?
            # Complexity: The Agent loop is recursive.
            # Let's simplify: Quit on first tool call for single-turn cases.
            if len(captured) >= 1: # Adjust logic for multi-tool later
                loop.quit()
        
        self.controller._execute_tool = mock_execute
        
        # Also quit on final text response (failure to call tool)
        def on_response(sender, text):
            print(f"  -> Agent responded text: {text}")
            loop.quit()
            
        def on_error(msg):
            print(f"  -> Agent error: {msg}")
            loop.quit()
            
        self.controller.response_ready.connect(on_response)
        self.controller.error_occurred.connect(on_error)
        
        # Send Input
        self.controller.handle_user_input(user_input)
        
        # Wait (Timeout 300s for CPU model inference)
        QTimer.singleShot(300000, loop.quit)
        loop.exec()
        
        # Restore and disconnect
        self.controller._execute_tool = original_execute
        self.controller.response_ready.disconnect(on_response)
        self.controller.error_occurred.disconnect(on_error)
        
        return captured

    def check_match(self, expected, actual):
        if not expected and not actual: return True
        if not expected or not actual: return False
        
        # Relaxed match: Check if the first expected tool appears in actual list
        # Because actual might have extra parameters or order diffs
        e = expected[0]
        a = actual[0]
        
        if e['tool_name'] != a['tool_name']:
            return False
            
        # Check params subset
        for k, v in e['parameters'].items():
            if k not in a['parameters']:
                return False
            # Simple equality check, might need better logic for floats/paths
            if str(a['parameters'][k]) != str(v): 
                # Allow minor formatting diffs if needed
                return False
                
        return True

def run_benchmark_cli():
    # Force offscreen for headless
    os.environ["QT_QPA_PLATFORM"] = "offscreen"
    
    app = QApplication(sys.argv)
    
    gold_path = Path(__file__).parent / "data/gold_set.json"
    runner = BenchmarkRunner(gold_path)
    
    # Run slightly deferred to let app loop start
    QTimer.singleShot(100, runner.run)
    
    sys.exit(app.exec())

if __name__ == "__main__":
    run_benchmark_cli()
