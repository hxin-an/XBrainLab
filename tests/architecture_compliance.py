import ast
import os
import sys


def check_file(filepath):
    with open(filepath, encoding="utf-8") as f:
        try:
            tree = ast.parse(f.read(), filename=filepath)
        except SyntaxError:
            return []

    violations = []

    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            is_dialog = False
            for base in node.bases:
                if (isinstance(base, ast.Name) and base.id == "QDialog") or (
                    isinstance(base, ast.Attribute) and base.attr == "QDialog"
                ):
                    is_dialog = True

            if is_dialog:
                for child in ast.walk(node):
                    # Check for self.study assignment
                    if isinstance(child, ast.Assign):
                        for target in child.targets:
                            if (
                                isinstance(target, ast.Attribute)
                                and isinstance(target.value, ast.Name)
                                and target.value.id == "self"
                                and target.attr == "study"
                            ):
                                violations.append(  # noqa: PERF401
                                    f"{filepath}:{node.name} assigns "
                                    f"self.study at line {child.lineno}"
                                )

                    # Check for parent.study access
                    if isinstance(child, ast.Attribute) and child.attr == "study":
                        # check if value is 'parent' or 'self.parent()'
                        if (
                            isinstance(child.value, ast.Name)
                            and child.value.id == "parent"
                        ):
                            violations.append(
                                f"{filepath}:{node.name} accesses "
                                f"parent.study at line {child.lineno}"
                            )
                        elif isinstance(child.value, ast.Call) and (
                            isinstance(child.value.func, ast.Attribute)
                            and child.value.func.attr == "parent"
                        ):
                            violations.append(
                                f"{filepath}:{node.name} accesses "
                                f"self.parent().study at line {child.lineno}"
                            )

    return violations


def main():
    root_dir = os.path.join(os.getcwd(), "XBrainLab", "ui")
    all_violations = []

    for root, _dirs, files in os.walk(root_dir):
        for file in files:
            if file.endswith(".py"):
                path = os.path.join(root, file)
                all_violations.extend(check_file(path))

    if all_violations:
        print("Architecture Violations Found:")
        for v in all_violations:
            print(v)
        sys.exit(1)
    else:
        print("No architecture violations found in QDialogs.")
        sys.exit(0)


if __name__ == "__main__":
    main()
