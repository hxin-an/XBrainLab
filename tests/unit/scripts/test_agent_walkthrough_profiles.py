"""Stable-v2 model-free frontend walkthrough profile contracts."""

from pathlib import Path

from XBrainLab.debug.tool_debug_mode import ToolDebugMode
from XBrainLab.llm.action_contracts import AGENT_ACTION_CONTRACTS

PROFILE_ROOT = Path("scripts/dev/agent_tool_walkthrough")
VALIDATION_GUIDE = Path("docs/validation/README.md")
PROFILE_NAMES = (
    "contract-failures",
    "complete-workflow",
    "gui-cancellation",
    "lifecycle-routing",
)


def test_walkthrough_profiles_are_strict_and_cover_exact_target_surface() -> None:
    profiles = [
        ToolDebugMode(str(PROFILE_ROOT / "complete-workflow.json")),
        ToolDebugMode(str(PROFILE_ROOT / "lifecycle-routing.json")),
        ToolDebugMode(str(PROFILE_ROOT / "contract-failures.json")),
    ]

    covered = {call.tool for profile in profiles for call in profile.calls}
    assert covered == AGENT_ACTION_CONTRACTS.tool_names()
    assert {profile.profile_id for profile in profiles} == {
        "complete-workflow",
        "lifecycle-routing",
        "contract-failures",
    }


def test_gui_cancellation_profile_advances_after_expected_cancel() -> None:
    profile = ToolDebugMode(str(PROFILE_ROOT / "gui-cancellation.json"))

    first = profile.begin_call()
    assert first is not None
    assert first.tool == "import_eeg_data"
    assert first.expected_outcomes == ("cancelled",)
    assert profile.complete_pending("cancelled") is True

    second = profile.begin_call()
    assert second is not None
    assert second.tool == "switch_panel"
    assert profile.complete_pending("completed") is True
    assert profile.is_complete


def test_walkthrough_profiles_never_bypass_product_confirmation() -> None:
    for path in PROFILE_ROOT.glob("*.json"):
        source = path.read_text(encoding="utf-8")
        assert '"confirmed"' not in source
        assert '"authorization_text"' not in source


def test_validation_guide_publishes_each_parseable_manual_walkthrough_command() -> None:
    guide = VALIDATION_GUIDE.read_text(encoding="utf-8")

    for profile_name in PROFILE_NAMES:
        profile_path = PROFILE_ROOT / f"{profile_name}.json"
        command = f"poetry run python run.py --tool-debug {profile_path.as_posix()}"
        assert command in guide
        assert ToolDebugMode(str(profile_path)).profile_id == profile_name
