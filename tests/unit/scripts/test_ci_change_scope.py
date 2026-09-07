from __future__ import annotations

from io import StringIO

from scripts.dev.ci_change_scope import ChangeScope, classify_changed_paths, main


def test_agent_guidance_change_set_uses_the_focused_lane() -> None:
    scope = classify_changed_paths(
        (
            ".agents/README.md",
            ".codex/config.toml",
            "docs/planning/now.md",
            "scripts/dev/audit_agent_guidance.py",
            "tests/unit/scripts/test_audit_agent_guidance.py",
        )
    )

    assert scope == ChangeScope(
        product=False,
        ui_visual=False,
        agent_guidance=True,
    )


def test_deleted_guidance_test_path_fails_closed_to_product_ci() -> None:
    assert classify_changed_paths(
        ("tests/unit/test_agent_guidance_contract.py",)
    ) == ChangeScope(
        product=True,
        ui_visual=False,
        agent_guidance=False,
    )


def test_guidance_with_documentation_uses_focused_guidance_and_docs_lanes() -> None:
    assert classify_changed_paths(
        (".agents/README.md", "docs/validation/README.md", "docs/decisions/README.md")
    ) == ChangeScope(product=False, ui_visual=False, agent_guidance=True)


def test_planning_document_without_guidance_change_stays_docs_only() -> None:
    assert classify_changed_paths(("docs/planning/now.md",)) == ChangeScope(
        product=False,
        ui_visual=False,
        agent_guidance=False,
    )


def test_general_scripts_tests_and_unknown_paths_fail_closed_to_product_ci() -> None:
    for path in (
        "scripts/dev/run_tests.py",
        "tests/unit/scripts/test_ci_change_scope_extra.py",
        ".github/workflows/docs-pages.yml",
        "run.py",
    ):
        assert classify_changed_paths((path,)).product is True


def test_mixed_guidance_and_product_paths_run_product_ci() -> None:
    for product_path in (
        "XBrainLab/backend/application_service.py",
        "tests/unit/test_architecture.py",
        "scripts/dev/ci_change_scope.py",
        "unknown.file",
    ):
        scope = classify_changed_paths(
            (".agents/README.md", "docs/validation/README.md", product_path)
        )

        assert scope.product is True
        assert scope.agent_guidance is False


def test_empty_change_set_fails_closed_to_product_and_ui_ci() -> None:
    assert classify_changed_paths(()) == ChangeScope(
        product=True,
        ui_visual=True,
        agent_guidance=False,
    )


def test_ui_paths_continue_to_select_visual_regression() -> None:
    assert classify_changed_paths(("XBrainLab/ui/main_window.py",)) == ChangeScope(
        product=True,
        ui_visual=True,
        agent_guidance=False,
    )


def test_cli_emits_github_output_for_empty_stdin(monkeypatch, capsys) -> None:
    monkeypatch.setattr("sys.stdin", StringIO(""))

    assert main() == 0
    assert capsys.readouterr().out.splitlines() == [
        "product=true",
        "ui_visual=true",
        "agent_guidance=false",
    ]
