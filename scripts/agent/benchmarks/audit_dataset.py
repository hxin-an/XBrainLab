import json

DATASET_PATH = "/mnt/data/lab/XBrainlab_with_agent/scripts/benchmark/data/external_validation_set.json"


def audit_dataset():
    with open(DATASET_PATH) as f:
        data = json.load(f)

    issues = []

    for i, case in enumerate(data):
        inp = case["input"].lower()
        expected_calls = case["expected_tool_calls"]

        # Rule 1: Split Strategy Contradiction
        if "by session" in inp or "per session" in inp:
            for call in expected_calls:
                params = call.get("parameters", {})
                if call["tool_name"] == "generate_dataset":
                    if params.get("split_strategy") != "session":
                        issues.append(
                            f"Case {i}: Input says 'session' but strategy is '{params.get('split_strategy')}'"
                        )

        if "by trial" in inp or "per trial" in inp:
            for call in expected_calls:
                params = call.get("parameters", {})
                if call["tool_name"] == "generate_dataset":
                    if params.get("split_strategy") != "trial":
                        issues.append(
                            f"Case {i}: Input says 'trial' but strategy is '{params.get('split_strategy')}'"
                        )

        # Rule 2: Explicit Values vs Nulls
        # If input mentions a number, but expected is None/null (unless it's a default, but explicit mentions usually imply explicit mapping)
        # Regex for numbers
        # Actually, let's look for specific keys like 'model_name' being null when input mentions a model
        if "eegnet" in inp:
            for call in expected_calls:
                if call["tool_name"] == "set_model":
                    val = call["parameters"].get("model_name")
                    if val != "EEGNet":
                        issues.append(
                            f"Case {i}: Input says 'EEGNet' but model_name is '{val}'"
                        )

        if "sccnet" in inp:
            for call in expected_calls:
                if call["tool_name"] == "set_model":
                    val = call["parameters"].get("model_name")
                    if val != "SCCNet":
                        issues.append(
                            f"Case {i}: Input says 'SCCNet' but model_name is '{val}'"
                        )

        # Rule 3: Start Training vs Switch Panel
        if (
            "see" in inp
            or "show" in inp
            or "monitor" in inp
            or "view" in inp
            or "check" in inp
        ):
            if "training" in inp and "accuracy" in inp:
                # Should NOT be start_training
                for call in expected_calls:
                    if call["tool_name"] == "start_training":
                        issues.append(
                            f"Case {i}: Input implies Viewing but tool is 'start_training'"
                        )

    if not issues:
        print("No obvious issues found with current rules.")
    else:
        print(f"Found {len(issues)} potential issues:")
        for issue in issues:
            print(issue)


if __name__ == "__main__":
    audit_dataset()
